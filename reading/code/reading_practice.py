"""
Step 3: Interactive CET-6 Reading Paragraph Summary Practice.
"""
import os
import re
import json
import random
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(r'../.env')

DB_PATH = r'../知识库/六级阅读段落库.json'
HISTORY_PATH = r'../知识库/六级阅读练习记录.json'
API_KEY = os.getenv('DEEPSEEK_API_KEY')
BASE_URL = 'https://api.deepseek.com/v1'
MODEL = 'deepseek-chat'

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def clean_text(text):
    if not text:
        return ''
    text = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else ' ' for c in text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Load database
with open(DB_PATH, 'r', encoding='utf-8') as f:
    raw_json = f.read()
# Clean surrogate escapes in raw JSON
raw_json = re.sub(r'\\u[dD][89a-fA-F][0-9a-fA-F]{2}', ' ', raw_json)
raw_json = re.sub(r'\\u[dD][cC][0-9a-fA-f]{2}', ' ', raw_json)
ALL_PARAGRAPHS = json.loads(raw_json)

for p in ALL_PARAGRAPHS:
    p['paragraph_text'] = clean_text(p.get('paragraph_text', ''))
    p['previous_context'] = clean_text(p.get('previous_context', ''))

# Load history
HISTORY = []
if os.path.exists(HISTORY_PATH):
    try:
        with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
            HISTORY = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print('Warning: history file corrupted, starting fresh.')
        HISTORY = []

TYPE_LABELS = {
    '选词填空': '选词填空 (Section A)',
    '长篇阅读': '长篇阅读匹配 (Section B)',
    '仔细阅读': '仔细阅读 (Section C)',
}


def safe_llm_call(messages, **kwargs):
    """LLM call with robust surrogate encoding protection."""
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
    # Also clean the response content
    if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
        resp.choices[0].message.content = clean_text(resp.choices[0].message.content)
    return resp


def print_header(text):
    print()
    print('=' * 60)
    print(f'  {text}')
    print('=' * 60)


def print_divider():
    print('-' * 60)


def show_stats(paragraphs=None):
    if paragraphs is None:
        paragraphs = ALL_PARAGRAPHS
    total = len(paragraphs)
    print(f'\n题库统计：共 {total} 个段落')
    for t in ['仔细阅读', '长篇阅读', '选词填空']:
        count = sum(1 for p in paragraphs if p['type'] == t)
        print(f'  {TYPE_LABELS[t]}: {count}')
    print(f'  已练习: {len(HISTORY)} 段')


def get_paragraphs_by_type(ptype):
    practiced_ids = {h.get('passage_id', '') for h in HISTORY}
    return [p for p in ALL_PARAGRAPHS if p['type'] == ptype and p['id'] not in practiced_ids]


def display_paragraph(item):
    print_divider()
    print(f'{item["type"]}  {item.get("title", "")}')
    print(f'  来源: {item["source"]}')
    if item['type'] == '仔细阅读':
        print(f'  段落: {item["paragraph_index"]}/{item["total_paragraphs"]}')
        ctx = item.get('previous_context', '')
        if ctx:
            print(f'  上文: {ctx}')
    elif item['type'] == '长篇阅读':
        print(f'  段落: {item["paragraph_index"]}/{item["total_paragraphs"]}')
    print_divider()
    print(item['paragraph_text'])
    print_divider()


def scaffolding_glossary(paragraph_text):
    paragraph_text = clean_text(paragraph_text)
    prompt = (
        '你是一名英语六级阅读辅导老师。提取以下段落中3-5个对理解最重要的关键词汇，'
        '给出中文释义和简单解释。\n\n'
        '输出格式为简洁的列表，每行一个词：\n'
        'word - 中文释义\n\n'
        f'段落：\n{paragraph_text}'
    )
    resp = safe_llm_call(
        messages=[{"role": "user", "content": prompt}],
        temperature=0, max_tokens=1000,
    )
    return resp.choices[0].message.content or ''


def scaffolding_split(paragraph_text):
    sentences = re.split(r'(?<=[.!?])\s+', paragraph_text)
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


def scaffolding_context(paragraph_text, item):
    paragraph_text = clean_text(paragraph_text)
    ctx = item.get('previous_context', '')
    prompt = (
        f'你是一名英语六级阅读辅导老师。学生将阅读以下段落并尝试用中文总结。\n'
        f'请提供一些有助于理解段落内容的背景提示或上下文信息（用中文，2-3句）。\n\n'
        f'文章标题: {item.get("title", "")}\n'
        f'来源: {item["source"]}\n'
        f'上文总结: {ctx if ctx else "(暂无)"}\n\n'
        f'段落原文:\n{paragraph_text}'
    )
    resp = safe_llm_call(
        messages=[{"role": "user", "content": prompt}],
        temperature=0, max_tokens=800,
    )
    return resp.choices[0].message.content or ''


def get_ai_feedback(paragraph_text, previous_context, user_summary):
    paragraph_text = clean_text(paragraph_text)
    previous_context = clean_text(previous_context)
    prompt = (
        '你是一名严格的英语六级阅读老师。评价学生用中文写的段落总结。\n\n'
        '英文段落原文:\n'
        f'{paragraph_text}\n\n'
    )
    if previous_context:
        prompt += f'前文背景:\n{previous_context}\n\n'

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


def run_practice():
    print_header('英语六级阅读段落总结练习')
    show_stats()

    while True:
        print('\n选择段落类型：')
        print('  1. 仔细阅读 (推荐，最适合作总结练习)')
        print('  2. 长篇阅读匹配')
        print('  3. 选词填空')
        print('  0. 退出')
        choice = input('\n请选择 (0-3): ').strip()

        if choice == '0':
            print('练习结束！')
            break

        type_map = {'1': '仔细阅读', '2': '长篇阅读', '3': '选词填空'}
        ptype = type_map.get(choice)
        if not ptype:
            print('无效选择，请重试。')
            continue

        candidates = get_paragraphs_by_type(ptype)
        if not candidates:
            print(f'"{TYPE_LABELS[ptype]}" 没有可用的新段落（可能已经全部练习过了）。')
            continue

        item = random.choice(candidates)
        scaffolding_used = []
        display_paragraph(item)

        while True:
            print('\n需要辅助理解吗？')
            print('  1. 直接总结（不需要帮助）')
            print('  2. 查看关键单词释义')
            print('  3. 长难句用"/"拆分')
            print('  4. 查看更多上下文提示')
            print('  5. 换一段')
            sc_choice = input('\n请选择 (1-5): ').strip()

            if sc_choice == '1':
                break
            elif sc_choice == '2':
                print('\n[关键单词释义]')
                print(scaffolding_glossary(item['paragraph_text']))
                scaffolding_used.append('glossary')
                print()
            elif sc_choice == '3':
                print('\n[长难句拆分]')
                print(scaffolding_split(item['paragraph_text']))
                scaffolding_used.append('splitting')
                print()
            elif sc_choice == '4':
                print('\n[上下文提示]')
                print(scaffolding_context(item['paragraph_text'], item))
                scaffolding_used.append('context')
                print()
            elif sc_choice == '5':
                print('换一段...')
                item = random.choice(candidates)
                display_paragraph(item)
                scaffolding_used = []
            else:
                print('无效选择。')

        print('\n请用中文简要总结本段的大意（50字以内）:')
        user_summary = input('总结: ').strip()
        if not user_summary:
            print('跳过本段。')
            continue

        print('\n正在分析你的总结...')
        feedback = get_ai_feedback(
            item['paragraph_text'],
            item.get('previous_context', ''),
            user_summary
        )
        print('\n[AI反馈]')
        print(feedback)

        HISTORY.append({
            'datetime': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
            'passage_id': item['id'],
            'type': item['type'],
            'source': item['source'],
            'title': item.get('title', ''),
            'paragraph_index': item['paragraph_index'],
            'scaffolding_used': scaffolding_used,
            'my_summary': user_summary,
            'ai_feedback': feedback,
        })
        with open(HISTORY_PATH, 'w', encoding='utf-8') as f:
            data_str = json.dumps(HISTORY, ensure_ascii=True, indent=2)
            f.write(data_str)

        print()
        again = input('继续练习？(Enter=继续, q=退出): ').strip().lower()
        if again == 'q':
            print('练习结束！')
            break


if __name__ == '__main__':
    run_practice()
