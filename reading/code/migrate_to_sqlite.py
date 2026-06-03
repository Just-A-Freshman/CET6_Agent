"""
Migrate CET-6 reading knowledge base from JSON files to SQLite.
"""
import os
import re
import json
import sqlite3

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(_PROJECT_ROOT, '知识库/reading.db')
PARAGRAPHS_PATH = os.path.join(_PROJECT_ROOT, '知识库/六级阅读段落库.json')
NOTES_PATH = os.path.join(_PROJECT_ROOT, '知识库/六级阅读笔记.json')
HISTORY_PATH = os.path.join(_PROJECT_ROOT, '知识库/六级阅读练习记录.json')
DIALOG_PATH = os.path.join(_PROJECT_ROOT, '知识库/六级阅读对话记录.json')


def clean_text(text):
    if not text:
        return ''
    text = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else ' ' for c in text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def migrate():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()

    # === Create tables ===

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS paragraphs (
            id              TEXT PRIMARY KEY,
            title           TEXT NOT NULL,
            type            TEXT NOT NULL,
            source          TEXT NOT NULL,
            passage_index   INTEGER NOT NULL,
            paragraph_index INTEGER NOT NULL,
            total_paragraphs INTEGER NOT NULL,
            paragraph_text  TEXT NOT NULL,
            previous_context TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_paragraphs_type ON paragraphs(type);
        CREATE INDEX IF NOT EXISTS idx_paragraphs_source ON paragraphs(source);

        CREATE TABLE IF NOT EXISTS notes (
            passage_id TEXT PRIMARY KEY,
            text       TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            datetime        TEXT NOT NULL,
            passage_id      TEXT,
            type            TEXT,
            source          TEXT,
            title           TEXT,
            paragraph_index INTEGER,
            my_summary      TEXT,
            ai_feedback     TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_history_passage_id ON history(passage_id);

        CREATE TABLE IF NOT EXISTS scaffolds (
            history_id INTEGER REFERENCES history(id) ON DELETE CASCADE,
            tool_name  TEXT NOT NULL,
            PRIMARY KEY (history_id, tool_name)
        );

        CREATE TABLE IF NOT EXISTS dialogues (
            passage_id TEXT PRIMARY KEY,
            messages   TEXT NOT NULL DEFAULT '[]'
        );
    """)

    # === Import paragraphs ===
    print("Importing paragraphs...")
    with open(PARAGRAPHS_PATH, 'r', encoding='utf-8') as f:
        raw = f.read()
    raw = re.sub(r'\\u[dD][89a-fA-F][0-9a-fA-F]{2}', ' ', raw)
    raw = re.sub(r'\\u[dD][cC][0-9a-fa-f]{2}', ' ', raw)
    paragraphs = json.loads(raw)

    para_data = []
    for p in paragraphs:
        para_data.append((
            p['id'], p.get('title', ''), p['type'], p['source'],
            p['passage_index'], p['paragraph_index'], p['total_paragraphs'],
            clean_text(p.get('paragraph_text', '')),
            clean_text(p.get('previous_context', '')),
        ))
    cur.executemany("""
        INSERT OR REPLACE INTO paragraphs
        (id, title, type, source, passage_index, paragraph_index, total_paragraphs, paragraph_text, previous_context)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, para_data)
    print(f"  {len(para_data)} paragraphs imported")

    # === Import notes ===
    print("Importing notes...")
    if os.path.exists(NOTES_PATH):
        with open(NOTES_PATH, 'r', encoding='utf-8') as f:
            notes = json.load(f)
        note_data = [(pid, text) for pid, text in notes.items()]
        cur.executemany("INSERT OR REPLACE INTO notes (passage_id, text) VALUES (?, ?)", note_data)
        print(f"  {len(note_data)} notes imported")
    else:
        print("  (no notes file)")

    # Turn off FK enforcement during data import (history may reference test data)
    cur.execute("PRAGMA foreign_keys=OFF")

    # === Import history ===
    print("Importing history...")
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
            raw = f.read()
        raw = re.sub(r'\\u[dD][89a-fA-F][0-9a-fA-F]{2}', ' ', raw)
        raw = re.sub(r'\\u[dD][cC][0-9a-fa-f]{2}', ' ', raw)
        history_list = json.loads(raw)

        scaffold_rows = []
        hist_rows = []
        for h in history_list:
            hist_rows.append((
                h.get('datetime', ''),
                h.get('passage_id', ''),
                h.get('type', ''),
                h.get('source', ''),
                h.get('title', ''),
                h.get('paragraph_index', 0),
                h.get('my_summary', ''),
                h.get('ai_feedback', ''),
            ))

        cur.executemany("""
            INSERT INTO history (datetime, passage_id, type, source, title, paragraph_index, my_summary, ai_feedback)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, hist_rows)

        # Import scaffolds using last_insert_rowid
        for h in history_list:
            tools = h.get('scaffolding_used', [])
            if tools:
                # Find the history row we just inserted — match by datetime+passage_id
                cur.execute(
                    "SELECT id FROM history WHERE datetime=? AND passage_id=?",
                    (h.get('datetime', ''), h.get('passage_id', ''))
                )
                row = cur.fetchone()
                if row:
                    hid = row[0]
                    for tool in tools:
                        scaffold_rows.append((hid, tool))

        if scaffold_rows:
            cur.executemany("INSERT INTO scaffolds (history_id, tool_name) VALUES (?, ?)", scaffold_rows)

        print(f"  {len(hist_rows)} history entries imported")
        print(f"  {len(scaffold_rows)} scaffold records imported")
    else:
        print("  (no history file)")

    # === Import dialogues ===
    print("Importing dialogues...")
    if os.path.exists(DIALOG_PATH):
        with open(DIALOG_PATH, 'r', encoding='utf-8') as f:
            dialogs = json.load(f)
        dialog_data = [(pid, json.dumps(msgs, ensure_ascii=False)) for pid, msgs in dialogs.items()]
        cur.executemany("INSERT OR REPLACE INTO dialogues (passage_id, messages) VALUES (?, ?)", dialog_data)
        print(f"  {len(dialog_data)} dialogues imported")
    else:
        print("  (no dialogues file)")

    conn.commit()
    conn.close()
    print(f"\nDone! Database created at: {DB_PATH}")


if __name__ == '__main__':
    migrate()
