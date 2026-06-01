"""
Step 2: Use DeepSeek API to parse raw reading texts into structured paragraph database.
Output: 知识库/六级阅读段落库.json
"""
import os
import json
import asyncio
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(r'../.env')

RAW_DIR = r'../知识库/reading_raw'
OUT_PATH = r'../知识库/六级阅读段落库.json'
API_KEY = os.getenv('DEEPSEEK_API_KEY')
BASE_URL = 'https://api.deepseek.com/v1'
MODEL = 'deepseek-chat'
SEMAPHORE_LIMIT = 3

SYSTEM_PROMPT = (
    '你是六级阅读解析专家。将六级阅读原始文本解析为结构化段落数据。\n'
    '识别三个部分:\n'
    '1. 选词填空 (Section A): 一个带空格的段落 + 15个备选词\n'
    '2. 长篇阅读匹配 (Section B): 多个标有A,B,C的段落 + 10个匹配题\n'
    '3. 仔细阅读 (Section C): 2篇完整文章，每篇后有5个选择题\n'
    '\n'
    '输出JSON数组，每个对象包含:\n'
    '- id: 例如 "2024-06-1-S-1-1" (S=选词填空, B=长篇阅读, C=仔细阅读)\n'
    '- title: 文章标题或主题（英文）\n'
    '- type: 选词填空 或 长篇阅读 或 仔细阅读\n'
    '- source: 年份-月份-套数\n'
    '- passage_index: 从1开始(整数)\n'
    '- paragraph_index: 从1开始(整数)\n'
    '- paragraph_text: 段落英文原文\n'
    '- previous_context: 前文总结（英文），只对仔细阅读有效\n'
    '- total_paragraphs: 该篇总段数(整数)\n'
    '\n'
    '重要要求:\n'
    '1. 只保留文章段落原文，不要题目、选项、Directions说明文字\n'
    '2. 长篇阅读段落去掉A. B. C. 等字母标记\n'
    '3. 选词填空保留原文和空格编号（如26,27），不要word bank列表\n'
    '4. 仔细阅读按自然段落拆分，每个段落一个对象。第一段previous_context填空字符串，后续段落用英文简要总结之前内容\n'
    '5. 仔细阅读有两篇，passage_index=1和2\n'
    '6. 去除页面编号、水印网址等干扰\n'
    '7. 保持原文原貌\n'
    '8. id格式: source-type-passage_index-paragraph_index\n'
    '9. 所有index必须是整数从1开始\n'
    '10. 仔细阅读必须拆分为多个段落(非一整篇)，每个paragraph_text只包含一个自然段\n'
    '11. 非仔细阅读类型的previous_context设置为空字符串'
)


def parse_source_from_filename(fname):
    base = os.path.splitext(fname)[0]
    parts = base.split('-')
    if len(parts) == 3:
        year, month, s = parts
        return f"{year}年{month}月-第{s}套"
    return base


async def process_one_file(client, semaphore, fname, existing_data):
    fpath = os.path.join(RAW_DIR, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    if len(raw_text) < 500:
        print(f'  [SKIP] {fname}: too short ({len(raw_text)} chars)')
        return []

    source = parse_source_from_filename(fname)

    # Resume support: skip if already processed
    existing_ids = {item['id'] for item in existing_data if item.get('source') == source}
    if existing_ids:
        print(f'  [SKIP] {fname} ({source}): already processed ({len(existing_ids)} paragraphs)')
        return []

    async with semaphore:
        print(f'  [API] {fname} ({source})...', end='', flush=True)
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"请解析以下六级阅读原始文本。source为: {source}\n\n原始文本:\n{raw_text}"},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=8192,
            )
            content = resp.choices[0].message.content
            if not content:
                print(' EMPTY RESPONSE')
                return []

            parsed = json.loads(content)

            # Handle wrapping
            if isinstance(parsed, dict):
                for key in ['passages', 'paragraphs', 'data', 'results']:
                    if key in parsed and isinstance(parsed[key], list):
                        parsed = parsed[key]
                        break

            if not isinstance(parsed, list):
                print(f' UNEXPECTED FORMAT: {type(parsed)}')
                return []

            # Validate and normalize
            for item in parsed:
                pi = item.get('passage_index', 1)
                ppi = item.get('paragraph_index', 1)
                if not isinstance(pi, int) or pi < 1:
                    pi = 1
                if not isinstance(ppi, int) or ppi < 1:
                    ppi = 1
                item['passage_index'] = pi
                item['paragraph_index'] = ppi

                t_code = {'选词填空': 'S', '长篇阅读': 'B', '仔细阅读': 'C'}.get(
                    item.get('type', ''), 'X')
                item['id'] = f"{source}-{t_code}-{pi}-{ppi}"
                item['source'] = source

                ctx = item.get('previous_context')
                if ctx is None or not isinstance(ctx, str):
                    item['previous_context'] = ''

                tp = item.get('total_paragraphs')
                if not isinstance(tp, int):
                    item['total_paragraphs'] = 1

                if not item.get('title'):
                    item['title'] = ''

            print(f' {len(parsed)} paragraphs')
            return parsed

        except Exception as e:
            print(f' ERROR: {e}')
            return []


async def main():
    existing_data = []
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        print(f'Loaded existing data: {len(existing_data)} paragraphs')

    files = sorted(f for f in os.listdir(RAW_DIR) if f.endswith('.txt'))
    print(f'Total files to process: {len(files)}')

    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)

    tasks = [process_one_file(client, semaphore, fname, existing_data) for fname in files]
    results = await asyncio.gather(*tasks)

    all_paragraphs = list(existing_data)
    new_count = 0
    for paras in results:
        if paras:
            all_paragraphs.extend(paras)
            new_count += len(paras)

    all_paragraphs.sort(key=lambda x: (x.get('source', ''), x.get('passage_index', 0), x.get('paragraph_index', 0)))

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_paragraphs, f, ensure_ascii=False, indent=2)

    print(f'\nDone! Total paragraphs: {len(all_paragraphs)}')
    print(f'Newly added: {new_count}')
    type_stats = {}
    for item in all_paragraphs:
        t = item.get('type', 'unknown')
        type_stats[t] = type_stats.get(t, 0) + 1
    print('Paragraph type distribution:')
    for t, c in sorted(type_stats.items()):
        print(f'  {t}: {c}')


if __name__ == '__main__':
    asyncio.run(main())
