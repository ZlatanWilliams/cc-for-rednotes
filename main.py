#!/usr/bin/env python
"""
RedNote organizer — scrapes one or more Xiaohongshu notes and saves each as
a structured Markdown file in your Obsidian vault.

Usage:
    python main.py "<url1>" "<url2>" ...

On the first run a browser window opens so you can log in to Xiaohongshu
manually. The session is saved to browser_data/ and reused automatically
on all subsequent runs.
"""

import re
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path(r"D:\Personal Data\obsidian\zzy-kb\raw\rednotes")


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = name.strip(". ")
    return name[:80] or "untitled"


def _save_note(note_data: dict, markdown: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    title = note_data.get("title") or "untitled"
    filename = f"{date.today().isoformat()}_{_safe_filename(title)}.md"
    output_path = OUTPUT_DIR / filename
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def main():
    urls = [a.strip() for a in sys.argv[1:] if a.strip().startswith("http")]
    if not urls:
        print("Usage: python main.py \"<url1>\" \"<url2>\" ...")
        sys.exit(1)

    total = len(urls)
    print(f"\nProcessing {total} note(s)...\n")

    from scraper import scrape_notes
    from processor import process_note

    print(f"[Step 1/3] Scraping {total} note(s)...")
    notes = scrape_notes(urls)

    succeeded = 0
    failed = 0

    for i, (url, note_data) in enumerate(zip(urls, notes), 1):
        print(f"\n--- Note {i}/{total} ---")

        if not note_data:
            print(f"  [Failed] Could not scrape: {url}")
            failed += 1
            continue

        print(f"  Title : {note_data.get('title', '(none)')}")
        print(f"  Author: {note_data.get('author', '(unknown)')}")

        print(f"[Step 2/3] Processing with AI model...")
        try:
            markdown = process_note(note_data)
        except Exception as e:
            print(f"  [Failed] AI processing error: {e}")
            failed += 1
            continue

        print(f"[Step 3/3] Saving file...")
        output_path = _save_note(note_data, markdown)
        print(f"  Saved: {output_path}")
        succeeded += 1

    print(f"\nDone. {succeeded} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()
