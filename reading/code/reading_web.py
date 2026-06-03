"""
Web interface for CET-6 Reading Paragraph Summary Practice.
"""
import os
import re
import json
import sys
import sqlite3
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv

# Use absolute path for root to avoid working directory issues
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))

SQLITE_PATH = os.path.join(_PROJECT_ROOT, '知识库/reading.db')
JSON_DB_PATH = os.path.join(_PROJECT_ROOT, '知识库/六级阅读段落库.json')
JSON_NOTES_PATH = os.path.join(_PROJECT_ROOT, '知识库/六级阅读笔记.json')
JSON_HISTORY_PATH = os.path.join(_PROJECT_ROOT, '知识库/六级阅读练习记录.json')
JSON_DIALOG_PATH = os.path.join(_PROJECT_ROOT, '知识库/六级阅读对话记录.json')
API_KEY = os.getenv('DEEPSEEK_API_KEY')
BASE_URL = 'https://api.deepseek.com/v1'
MODEL = 'deepseek-chat'

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
app = Flask(__name__, template_folder='templates', static_folder='static')


# --- Database helpers ---

def ensure_db():
    """Initialize SQLite DB from JSON files if it doesn't exist."""
    if os.path.exists(SQLITE_PATH):
        return
    # Re-import from migrate_to_sqlite logic
    import sqlite3
    conn = sqlite3.connect(SQLITE_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS paragraphs (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, type TEXT NOT NULL,
            source TEXT NOT NULL, passage_index INTEGER NOT NULL,
            paragraph_index INTEGER NOT NULL, total_paragraphs INTEGER NOT NULL,
            paragraph_text TEXT NOT NULL, previous_context TEXT DEFAULT '');
        CREATE INDEX IF NOT EXISTS idx_paragraphs_type ON paragraphs(type);
        CREATE INDEX IF NOT EXISTS idx_paragraphs_source ON paragraphs(source);
        CREATE TABLE IF NOT EXISTS notes (passage_id TEXT PRIMARY KEY, text TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, datetime TEXT NOT NULL,
            passage_id TEXT, type TEXT, source TEXT, title TEXT,
            paragraph_index INTEGER, my_summary TEXT, ai_feedback TEXT);
        CREATE INDEX IF NOT EXISTS idx_history_passage_id ON history(passage_id);
        CREATE TABLE IF NOT EXISTS scaffolds (
            history_id INTEGER, tool_name TEXT NOT NULL,
            PRIMARY KEY (history_id, tool_name));
        CREATE TABLE IF NOT EXISTS dialogues (
            passage_id TEXT PRIMARY KEY, messages TEXT NOT NULL DEFAULT '[]');
    """)
    # Import paragraphs
    if os.path.exists(JSON_DB_PATH):
        with open(JSON_DB_PATH, 'r', encoding='utf-8') as f:
            raw = f.read()
        raw = re.sub(r'\\u[dD][89a-fA-F][0-9a-fA-F]{2}', ' ', raw)
        raw = re.sub(r'\\u[dD][cC][0-9a-fa-f]{2}', ' ', raw)
        paras = json.loads(raw)
        data = []
        for p in paras:
            data.append((
                p['id'], p.get('title', ''), p['type'], p['source'],
                p['passage_index'], p['paragraph_index'], p['total_paragraphs'],
                clean_text(p.get('paragraph_text', '')),
                clean_text(p.get('previous_context', '')),
            ))
        conn.executemany(
            "INSERT OR REPLACE INTO paragraphs VALUES (?,?,?,?,?,?,?,?,?)",
            data
        )
    # Import notes
    if os.path.exists(JSON_NOTES_PATH):
        with open(JSON_NOTES_PATH, 'r', encoding='utf-8') as f:
            notes = json.load(f)
        conn.executemany(
            "INSERT OR REPLACE INTO notes VALUES (?,?)",
            [(pid, t) for pid, t in notes.items()]
        )
    # Import history + scaffolds
    if os.path.exists(JSON_HISTORY_PATH):
        with open(JSON_HISTORY_PATH, 'r', encoding='utf-8') as f:
            raw = f.read()
        raw = re.sub(r'\\u[dD][89a-fA-F][0-9a-fA-F]{2}', ' ', raw)
        raw = re.sub(r'\\u[dD][cC][0-9a-fa-f]{2}', ' ', raw)
        hist = json.loads(raw)
        for h in hist:
            cur = conn.execute(
                "INSERT INTO history (datetime, passage_id, type, source, title, paragraph_index, my_summary, ai_feedback) VALUES (?,?,?,?,?,?,?,?)",
                (h.get('datetime', ''), h.get('passage_id', ''), h.get('type', ''),
                 h.get('source', ''), h.get('title', ''), h.get('paragraph_index', 0),
                 h.get('my_summary', ''), h.get('ai_feedback', ''))
            )
            for tool in (h.get('scaffolding_used') or []):
                conn.execute("INSERT INTO scaffolds VALUES (?,?)", (cur.lastrowid, tool))
    # Import dialogues
    if os.path.exists(JSON_DIALOG_PATH):
        with open(JSON_DIALOG_PATH, 'r', encoding='utf-8') as f:
            dialogs = json.load(f)
        conn.executemany(
            "INSERT OR REPLACE INTO dialogues VALUES (?,?)",
            [(pid, json.dumps(msgs, ensure_ascii=False)) for pid, msgs in dialogs.items()]
        )
    conn.commit()
    conn.close()
    print("[db] Initialized from JSON files")


def get_db():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def clean_text(text):
    if not text:
        return ''
    text = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else ' ' for c in text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def get_practiced_ids():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT passage_id FROM history WHERE passage_id != ''").fetchall()
    conn.close()
    return {r['passage_id'] for r in rows}


def get_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0]
    practiced_ids = get_practiced_ids()
    practiced = len(practiced_ids)
    by_type = {}
    for t in ['选词填空', '长篇阅读', '仔细阅读']:
        row = conn.execute("SELECT COUNT(*) FROM paragraphs WHERE type=?", (t,)).fetchone()
        total_t = row[0]
        remaining = conn.execute(
            "SELECT COUNT(*) FROM paragraphs WHERE type=? AND id NOT IN (SELECT passage_id FROM history WHERE passage_id != '')",
            (t,)
        ).fetchone()[0]
        by_type[t] = {'total': total_t, 'remaining': remaining}
    conn.close()
    return {'total': total, 'practiced': practiced, 'by_type': by_type}


def get_random_paragraph(ptype):
    conn = get_db()
    practiced = get_practiced_ids()
    if practiced:
        cur = conn.execute(
            "SELECT * FROM paragraphs WHERE type=? AND id NOT IN (SELECT passage_id FROM history WHERE passage_id != '') ORDER BY RANDOM() LIMIT 1",
            (ptype,)
        )
        row = cur.fetchone()
        if row:
            conn.close()
            return row_to_dict(row)
    # Fallback: any paragraph of this type
    cur = conn.execute("SELECT * FROM paragraphs WHERE type=? ORDER BY RANDOM() LIMIT 1", (ptype,))
    row = cur.fetchone()
    conn.close()
    return row_to_dict(row)


def get_paragraph(passage_id):
    conn = get_db()
    cur = conn.execute("SELECT * FROM paragraphs WHERE id=?", (passage_id,))
    row = cur.fetchone()
    conn.close()
    return row_to_dict(row)


def get_note(passage_id):
    conn = get_db()
    cur = conn.execute("SELECT text FROM notes WHERE passage_id=?", (passage_id,))
    row = cur.fetchone()
    conn.close()
    return row['text'] if row else ''


def save_note(passage_id, text):
    conn = get_db()
    if text:
        conn.execute(
            "INSERT INTO notes (passage_id, text) VALUES (?, ?) ON CONFLICT(passage_id) DO UPDATE SET text=?",
            (passage_id, text, text)
        )
    else:
        conn.execute("DELETE FROM notes WHERE passage_id=?", (passage_id,))
    conn.commit()
    conn.close()


def get_dialog(passage_id):
    conn = get_db()
    cur = conn.execute("SELECT messages FROM dialogues WHERE passage_id=?", (passage_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row['messages'])
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def save_dialog(passage_id, messages):
    conn = get_db()
    if messages:
        conn.execute(
            "INSERT INTO dialogues (passage_id, messages) VALUES (?, ?) ON CONFLICT(passage_id) DO UPDATE SET messages=?",
            (passage_id, json.dumps(messages, ensure_ascii=False), json.dumps(messages, ensure_ascii=False))
        )
    else:
        conn.execute("DELETE FROM dialogues WHERE passage_id=?", (passage_id,))
    conn.commit()
    conn.close()


def get_history():
    conn = get_db()
    rows = conn.execute("""
        SELECT h.*, GROUP_CONCAT(s.tool_name, ',') as tool_names
        FROM history h
        LEFT JOIN scaffolds s ON s.history_id = h.id
        GROUP BY h.id
        ORDER BY h.datetime DESC
    """).fetchall()
    result = []
    for r in rows:
        entry = dict(r)
        tools = r['tool_names'].split(',') if r['tool_names'] else []
        entry['scaffolding_used'] = [t for t in tools if t]
        del entry['tool_names']
        result.append(entry)
    conn.close()
    return result


def save_history_entry(datetime, passage_id, ptype, source, title, paragraph_index, summary, feedback, scaffolding_used):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO history (datetime, passage_id, type, source, title, paragraph_index, my_summary, ai_feedback)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime, passage_id, ptype, source, title, paragraph_index, summary, feedback))
    hid = cur.lastrowid
    for tool in (scaffolding_used or []):
        conn.execute("INSERT INTO scaffolds (history_id, tool_name) VALUES (?, ?)", (hid, tool))
    conn.commit()
    conn.close()


def safe_llm_call(messages, **kwargs):
    def _deep_clean(obj):
        if isinstance(obj, str):
            return obj.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
        elif isinstance(obj, dict):
            return {k: _deep_clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_deep_clean(item) for item in obj]
        return obj
    messages = _deep_clean(messages)
    resp = client.chat.completions.create(model=MODEL, messages=messages, **kwargs)
    if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
        content = resp.choices[0].message.content
        # Only remove surrogate characters, preserve all whitespace including newlines
        content = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else ' ' for c in content)
        resp.choices[0].message.content = content.strip()
    return resp


# --- Scaffolding helpers ---

def scaffolding_glossary(text):
    prompt = (
        '你是一名英语六级阅读辅导老师。提取以下段落中3-5个对理解最重要的关键词汇，'
        '给出中文释义和简单解释。\n\n'
        '输出格式为简洁的列表，每行一个词：\n'
        'word - 中文释义\n\n'
        f'段落：\n{text}'
    )
    resp = safe_llm_call(
        messages=[{"role": "user", "content": prompt}],
        temperature=0, max_tokens=1000,
    )
    return resp.choices[0].message.content or ''


def scaffolding_split(text, dimension='sense-group'):
    prompts = {
        'constituent': (
            '你是一名英语六级阅读辅导老师。下面是一个英文段落。'
            '请按句子语法成分拆分成更小的结构单元。具体来说，识别并拆分以下成分：\n'
            '- 主语部分 / 谓语部分\n'
            '- 定语从句及其修饰的名词\n'
            '- 状语从句 / 介词短语作状语\n'
            '- 宾语从句 / 表语从句\n'
            '- 同位语\n'
            '- 不定式短语 / 分词短语\n\n'
            '示例：\n'
            '原文：The study / conducted by researchers / shows that regular exercise / can significantly improve mental health.\n'
            '（按成分拆分：主语部分 / 定语修饰 / 谓语+宾语从句 / 从句内谓语+宾语）\n\n'
            '规则：\n'
            '- 用一个空格 + "/" + 一个空格 作为分隔符\n'
            '- 不改变原文任何单词\n'
            '- 不添加任何解释或额外文字\n'
            '- 在标点符号处不要盲目切分，要考虑前面的词是否和标点后的词属于同一语法成分\n'
            '- 如果段落很短（不足8个词），直接返回原文不加分隔符\n\n'
            f'段落：\n{text}'
        ),
        'sense-group': (
            '你是一名英语六级阅读辅导老师。下面是一个英文段落。'
            '请按意群（能表达完整意义的最小单元）拆分成更小的结构单元。\n\n'
            '规则：\n'
            '- 用一个空格 + "/" + 一个空格 作为分隔符\n'
            '- 不改变原文任何单词\n'
            '- 不添加任何解释或额外文字\n'
            '- 如果段落很短（不足8个词），直接返回原文不加分隔符\n\n'
            f'段落：\n{text}'
        ),
        'content': (
            '你是一名英语六级阅读辅导老师。下面是一个英文段落。'
            '请按段落内核心观点进行切分，把表达不同观点的部分分开，但不拆散完整句子。\n\n'
            '规则：\n'
            '- 用两个空格 + "//" + 两个空格 作为段落内不同观点之间的分隔符\n'
            '- 不改变原文任何单词\n'
            '- 不添加任何解释或额外文字\n'
            '- 如果段落只有一个核心观点，直接返回原文不加分隔符\n\n'
            f'段落：\n{text}'
        ),
    }
    prompt = prompts.get(dimension, prompts['sense-group'])
    resp = safe_llm_call(
        messages=[{"role": "user", "content": prompt}],
        temperature=0, max_tokens=2000,
    )
    return resp.choices[0].message.content or text


def scaffolding_context(text, item):
    ctx = item.get('previous_context', '')
    prompt = (
        f'你是一名英语六级阅读辅导老师。学生即将阅读下面的英文段落。\n'
        f'请提供一些有助于理解该段落内容的背景知识或上下文信息（用中文，2-3句）。\n'
        f'注意：不要总结段落本身的内容，只需提供阅读它所需的背景信息。\n\n'
        f'文章标题: {item.get("title", "")}\n'
        f'来源: {item["source"]}\n'
        f'上文总结: {ctx if ctx else "(暂无)"}\n\n'
        f'段落原文:\n{text}'
    )
    resp = safe_llm_call(
        messages=[{"role": "user", "content": prompt}],
        temperature=0, max_tokens=800,
    )
    return resp.choices[0].message.content or ''


# --- Chat / AI tutor ---

CHAT_SYSTEM_PROMPT = (
    "你是一名英语六级阅读辅导老师。你的核心任务是引导学生用自己的话总结英文段落的大意。\n\n"
    "当前段落：\n{paragraph_text}\n\n"
    "前文背景：\n{previous_context}\n\n"
    "规则：\n"
    "1. 如果学生用中文给出了段落大意总结，你给出反馈评价后，必须在回复末尾另起一行输出以下标记（不要加任何额外文字在标记之后）：\n"
    '   <CET6_SUMMARY>{"is_summary": true, "summary_text": "将学生的总结原文放在这里"}</CET6_SUMMARY>\n'
    "2. 如果学生在问翻译、词义或语法问题，正常回答，不加任何标记\n"
    "3. 如果学生还没有给出总结，通过追问、提示、引导帮助学生\n"
    "4. 用中文回复\n\n"
    "重要：标记 <CET6_SUMMARY> 必须出现在回复的最后一行，前面用换行隔开。"
)


def save_summary_to_history(paragraph_id, ptype, source, title, paragraph_index, summary):
    save_history_entry(
        datetime=__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
        passage_id=paragraph_id,
        ptype=ptype,
        source=source,
        title=title,
        paragraph_index=paragraph_index,
        summary=summary,
        feedback='',
        scaffolding_used=[],
    )


@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json()
    paragraph_id = data.get('paragraph_id', '')
    paragraph_text = data.get('paragraph_text', '')
    previous_context = data.get('previous_context', '')
    ptype = data.get('type', '')
    source = data.get('source', '')
    title = data.get('title', '')
    paragraph_index = data.get('paragraph_index', 0)
    messages = data.get('messages', [])
    user_message = data.get('user_message', '')

    if not user_message.strip():
        return jsonify({'error': 'Message is required'}), 400

    # Insert system prompt at the beginning
    sys_prompt = CHAT_SYSTEM_PROMPT.replace('{paragraph_text}', paragraph_text).replace('{previous_context}', previous_context)

    full_messages = [{"role": "system", "content": sys_prompt}]
    for m in messages:
        full_messages.append({"role": m["role"], "content": m["content"]})

    def generate():
        stream = client.chat.completions.create(
            model=MODEL,
            messages=full_messages,
            stream=True,
            temperature=0.3,
            max_tokens=3000,
        )
        full_response = ''
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                yield f'data: {json.dumps({"content": content})}\n\n'

        # After streaming completes, check for summary marker
        if '<CET6_SUMMARY>' in full_response:
            try:
                start = full_response.index('<CET6_SUMMARY>') + len('<CET6_SUMMARY>')
                end = full_response.index('</CET6_SUMMARY>', start)
                summary_json = full_response[start:end].strip()
                # Strip markdown code fences if LLM wrapped the JSON
                summary_json = re.sub(r'^```(?:json)?\s*', '', summary_json)
                summary_json = re.sub(r'\s*```$', '', summary_json)
                info = json.loads(summary_json)
                if info.get('is_summary'):
                    save_summary_to_history(
                        paragraph_id=paragraph_id,
                        ptype=ptype,
                        source=source,
                        title=title,
                        paragraph_index=paragraph_index,
                        summary=info.get('summary_text', ''),
                    )
                    yield f'data: {json.dumps({"summary_saved": True})}\n\n'
            except Exception as e:
                print(f"[chat] summary parse error: {e}", file=__import__('sys').stderr)

        yield 'data: [DONE]\n\n'

    return app.response_class(generate(), mimetype='text/event-stream')


@app.route('/api/dialogs/<passage_id>')
def api_get_dialog(passage_id):
    messages = get_dialog(passage_id)
    return jsonify({'messages': messages})


@app.route('/api/dialogs/<passage_id>', methods=['POST'])
def api_save_dialog(passage_id):
    data = request.get_json()
    messages = data.get('messages', [])
    save_dialog(passage_id, messages)
    return jsonify({'ok': True})


# --- Flask routes ---

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/stats')
def api_stats():
    return jsonify(get_stats())


@app.route('/api/random_paragraph', methods=['POST'])
def api_random_paragraph():
    data = request.get_json()
    ptype = data.get('type', '仔细阅读')
    item = get_random_paragraph(ptype)
    if not item:
        return jsonify({'error': 'No paragraphs found for this type'}), 404
    return jsonify(item)


@app.route('/api/paragraph/<passage_id>')
def api_paragraph(passage_id):
    item = get_paragraph(passage_id)
    if not item:
        return jsonify({'error': 'Paragraph not found'}), 404
    return jsonify(item)


@app.route('/api/notes/<passage_id>')
def api_get_note(passage_id):
    text = get_note(passage_id)
    return jsonify({'text': text})


@app.route('/api/notes/<passage_id>', methods=['POST'])
def api_save_note(passage_id):
    data = request.get_json()
    text = (data.get('text', '') or '').strip()
    save_note(passage_id, text)
    return jsonify({'ok': True})


@app.route('/api/scaffolding/glossary', methods=['POST'])
def api_glossary():
    data = request.get_json()
    text = clean_text(data.get('text', ''))
    result = scaffolding_glossary(text)
    return jsonify({'result': result})


@app.route('/api/scaffolding/split', methods=['POST'])
def api_split():
    data = request.get_json()
    text = data.get('text', '')
    dimension = data.get('dimension', 'sense-group')
    result = scaffolding_split(text, dimension)
    return jsonify({'result': result})


@app.route('/api/scaffolding/context', methods=['POST'])
def api_context():
    data = request.get_json()
    text = clean_text(data.get('text', ''))
    item = data.get('item', {})
    result = scaffolding_context(text, item)
    return jsonify({'result': result})


@app.route('/api/history')
def api_history():
    return jsonify(get_history())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
