"""
Step 1: Extract raw reading comprehension text from all CET-6 exam PDFs.
Output: individual .txt files in 知识库/reading_raw/
"""
import os
import re
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
from pypdf import PdfReader

PDF_DIR = r'D:\Learning\English\英语六级\题目\近10年六级真题'
OUT_DIR = r'../知识库/reading_raw'
os.makedirs(OUT_DIR, exist_ok=True)


def extract_all_text(filepath):
    reader = PdfReader(filepath)
    parts = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return '\n'.join(parts)


def collapse_spaced_letters(text):
    """
    Fix text where letters inside words are separated by spaces.
    Ported from extract_writing_final.py. Handles spaced-out characters in 2022+ PDFs.
    """
    # Step 1: collapse sequences of single letters separated by single spaces
    text = re.sub(r'(?<!\w)([A-Za-z])(?: ([A-Za-z]))+(?!\w)',
                  lambda m: m.group(0).replace(' ', ''), text)

    # Step 2: fix common merged word pairs
    fixes = [
        (r'\bto(\w{2,})\b', lambda m: f'to {m.group(1)}' if m.group(1) not in ('wards', 'gether', 'day', 'night', 'morrow') else m.group(0)),
        (r'\bin(\w{2,})\b', lambda m: f'in {m.group(1)}' if m.group(1) not in ('to', 'put', 'putting') else m.group(0)),
        (r'\bof(\w{2,})\b', lambda m: f'of {m.group(1)}'),
        (r'\bno(\w{2,})\b', lambda m: m.group(0) if m.group(1) in ('te', 'tes', 'ted', 'ting') else f'no {m.group(1)}'),
        (r'\bby(\w{2,})\b', lambda m: m.group(0) if m.group(1) in ('pass', 'passed', 'passing', 'product', 'products') else f'by {m.group(1)}'),
    ]
    for pat, repl in fixes:
        text = re.sub(pat, repl, text)

    return text


def collapse_whitespace(text):
    """Collapse all runs of whitespace (handles double-space PDFs)."""
    return re.sub(r'\s+', ' ', text)


def extract_reading_section(text):
    """
    Find and extract the Reading Comprehension section (Part III).
    Tries multiple patterns for robustness across different PDF formats.
    """
    collapsed = collapse_whitespace(text)

    # Find end marker first: Part IV Translation
    end = len(collapsed)
    end_patterns = [
        r'Part\s*IV\s*Translation',
        r'Part\s*Ⅳ\s*Translation',
        r'Part\s*IV',
        r'Part\s*Ⅳ',
    ]
    for pat in end_patterns:
        m = re.search(pat, collapsed)
        if m:
            end = m.start()
            break
    if end == len(collapsed):
        m = re.search(r'Translation', collapsed)
        if m:
            end = m.start()

    # Search for start within the text before Translation
    pre = collapsed[:end]

    start = -1
    start_patterns = [
        r'Part\s*III\s*Reading\s*Comprehension',
        r'Part\s*Ⅲ\s*Reading\s*Comprehension',
        r'Reading\s*Comprehension',
        r'Part\s*III',
        r'Part\s*Ⅲ',
    ]
    for pat in start_patterns:
        m = re.search(pat, pre)
        if m:
            start = m.start()
            break

    # Fallback: find the last "Section A" before Translation
    if start < 0:
        matches = list(re.finditer(r'Section\s*A', pre))
        if matches:
            # The last Section A before Translation should be reading's Section A
            start = matches[-1].start()

    if start >= 0:
        return collapsed[start:end].strip()
    return collapsed.strip()


def get_year_month_set(filename):
    m = re.search(r'(\d{4})年(\d{1,2})月.*?第(\d)套', filename)
    if m:
        return m.group(1), m.group(2).zfill(2), m.group(3)
    return None, None, None


def main():
    files = sorted(f for f in os.listdir(PDF_DIR) if f.endswith('.pdf'))
    stats = {'total': 0, 'ok': 0, 'empty': 0}

    for fname in files:
        year, month, set_num = get_year_month_set(fname)
        if not year:
            print(f'[SKIP] Cannot parse metadata: {fname}')
            continue

        # Output filename: 2024-06-1.txt
        out_name = f'{year}-{month}-{set_num}.txt'
        out_path = os.path.join(OUT_DIR, out_name)

        filepath = os.path.join(PDF_DIR, fname)
        all_text = extract_all_text(filepath)
        reading = extract_reading_section(all_text)
        reading = collapse_spaced_letters(reading)

        stats['total'] += 1

        if not reading or len(reading) < 50:
            stats['empty'] += 1
            print(f'[EMPTY] {out_name}: {fname}')
            # Still save empty for tracking
        else:
            stats['ok'] += 1

        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(reading)

        preview = reading[:80].replace('\n', ' ') + '...' if reading else 'EMPTY'
        print(f'[OK] {out_name} ({len(reading)} chars) {preview}')

    print(f'\nDone. Total: {stats["total"]}, OK: {stats["ok"]}, Empty: {stats["empty"]}')


if __name__ == '__main__':
    main()
