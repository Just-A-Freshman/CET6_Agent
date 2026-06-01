"""
Web interface for CET-6 Reading Paragraph Summary Practice.
"""
import os
import re
import json
import random
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(r'../.env')

DB_PATH = r'../知识库/六级阅读段落库.json'
HISTORY_PATH = r'../知识库/六级阅读练习记录.json'
API_KEY = os.getenv('DEEPSEEK_API_KEY')
BASE_URL = 'https://api.deepseek.com/v1'
MODEL = 'deepseek-chat'

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
app = Flask(__name__, template_folder='templates', static_folder='static')


# --- Data loading (same as CLI version) ---

def clean_text(text):
    if not text:
        return ''
    text = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else ' ' for c in text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


with open(DB_PATH, 'r', encoding='utf-8') as f:
    raw_json = f.read()
raw_json = re.sub(r'\\u[dD][89a-fA-F][0-9a-fA-F]{2}', ' ', raw_json)
raw_json = re.sub(r'\\u[dD][cC][0-9a-fA-f]{2}', ' ', raw_json)
ALL_PARAGRAPHS = json.loads(raw_json)

for p in ALL_PARAGRAPHS:
    p['paragraph_text'] = clean_text(p.get('paragraph_text', ''))
    p['previous_context'] = clean_text(p.get('previous_context', ''))


def load_history():
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []
    return []


def save_history(history):
    with open(HISTORY_PATH, 'w', encoding='utf-8') as f:
        f.write(json.dumps(history, ensure_ascii=True, indent=2))


def get_practiced_ids():
    h = load_history()
    return {entry.get('passage_id', '') for entry in h}


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
        resp.choices[0].message.content = clean_text(resp.choices[0].message.content)
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


def scaffolding_split(text):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result = []
    for sent in sentences:
        words = sent.split()
        if len(words) > 15:
            sent = re.sub(
                r'\b(which|that|because|although|while|whereas|if|when|since|unless|until'
                r'|as\s+(?:long\s+as|soon\s+as|far\s+as))\b',
                lambda m: f' / {m.group(1)}', sent, flags=re.IGNORECASE)
            sent = re.sub(
                r'\b(and|but|or|so|yet|however|therefore|moreover|furthermore|nevertheless)\b',
                lambda m: f' / {m.group(1)}', sent, flags=re.IGNORECASE)
            sent = re.sub(
                r'\b(who|whom|whose|where|when)\b',
                lambda m: f' / {m.group(1)}', sent, flags=re.IGNORECASE)
        result.append(sent)
    return '\n'.join(result)


def scaffolding_context(text, item):
    ctx = item.get('previous_context', '')
    prompt = (
        f'你是一名英语六级阅读辅导老师。学生将阅读以下段落并尝试用中文总结。\n'
        f'请提供一些有助于理解段落内容的背景提示或上下文信息（用中文，2-3句）。\n\n'
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


def get_ai_feedback(text, context, user_summary):
    prompt = (
        '你是一名严格的英语六级阅读老师。评价学生用中文写的段落总结。\n\n'
        '英文段落原文:\n'
        f'{text}\n\n'
    )
    if context:
        prompt += f'前文背景:\n{context}\n\n'
    prompt += (
        f'学生的中文总结:\n{user_summary}\n\n'
        '请从以下维度评价（用中文，简洁精炼）：\n'
        '1. 准确性：总结中有没有事实性错误或理解偏差？\n'
        '2. 完整性：是否覆盖了段落的核心信息？有没有遗漏关键点？\n'
        '3. 核心观点：是否准确抓住了段落主旨？\n\n'
        '最后给出一个参考中文总结（50字以内）。\n'
        '格式：\n'
        '准确性：xxx\n'
        '完整性：xxx\n'
        '核心观点：是/否\n'
        '参考总结：xxx'
    )
    resp = safe_llm_call(
        messages=[{"role": "user", "content": prompt}],
        temperature=0, max_tokens=2000,
    )
    return resp.choices[0].message.content or ''


# --- Flask routes ---

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/stats')
def api_stats():
    practiced = get_practiced_ids()
    stats = {'total': len(ALL_PARAGRAPHS), 'practiced': len(practiced), 'by_type': {}}
    for t in ['选词填空', '长篇阅读', '仔细阅读']:
        total = sum(1 for p in ALL_PARAGRAPHS if p['type'] == t)
        remaining = sum(1 for p in ALL_PARAGRAPHS if p['type'] == t and p['id'] not in practiced)
        stats['by_type'][t] = {'total': total, 'remaining': remaining}
    return jsonify(stats)


@app.route('/api/random_paragraph', methods=['POST'])
def api_random_paragraph():
    data = request.get_json()
    ptype = data.get('type', '仔细阅读')
    practiced = get_practiced_ids()
    candidates = [p for p in ALL_PARAGRAPHS if p['type'] == ptype and p['id'] not in practiced]
    if not candidates:
        candidates = [p for p in ALL_PARAGRAPHS if p['type'] == ptype]
    if not candidates:
        return jsonify({'error': 'No paragraphs found for this type'}), 404
    item = random.choice(candidates)
    return jsonify({
        'id': item['id'],
        'type': item['type'],
        'title': item.get('title', ''),
        'source': item['source'],
        'passage_index': item['passage_index'],
        'paragraph_index': item['paragraph_index'],
        'total_paragraphs': item['total_paragraphs'],
        'paragraph_text': item['paragraph_text'],
        'previous_context': item.get('previous_context', ''),
    })


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
    result = scaffolding_split(text)
    return jsonify({'result': result})


@app.route('/api/scaffolding/context', methods=['POST'])
def api_context():
    data = request.get_json()
    text = clean_text(data.get('text', ''))
    item = data.get('item', {})
    result = scaffolding_context(text, item)
    return jsonify({'result': result})


@app.route('/api/feedback', methods=['POST'])
def api_feedback():
    data = request.get_json()
    text = clean_text(data.get('text', ''))
    context = clean_text(data.get('context', ''))
    summary = data.get('summary', '').strip()
    if not summary:
        return jsonify({'error': 'Summary is required'}), 400
    result = get_ai_feedback(text, context, summary)
    # Save to history
    history = load_history()
    history.append({
        'datetime': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
        'passage_id': data.get('passage_id', ''),
        'type': data.get('type', ''),
        'source': data.get('source', ''),
        'title': data.get('title', ''),
        'paragraph_index': data.get('paragraph_index', 0),
        'scaffolding_used': data.get('scaffolding_used', []),
        'my_summary': summary,
        'ai_feedback': result,
    })
    save_history(history)
    return jsonify({'result': result})


@app.route('/api/history')
def api_history():
    history = load_history()
    return jsonify(history)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
