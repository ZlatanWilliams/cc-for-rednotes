# cc-for-rednotes

Scrapes one or more [Xiaohongshu (RedNote)](https://www.xiaohongshu.com) notes by URL, sends the text and images to a vision-capable AI model, and saves a structured Markdown file to your Obsidian vault.

## Requirements

- Python 3.10+
- An API key for an OpenAI-compatible provider with a **vision-capable** model

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://your-provider/v1
MODEL_NAME=gpt-4o
```

`MODEL_NAME` must support image input (vision). `OPENAI_BASE_URL` should end with `/v1`.

## Usage

```bash
# Single note
python main.py "https://www.xiaohongshu.com/explore/<note-id>"

# Multiple notes in one run
python main.py "https://..." "https://..." "https://..."
```

**First run:** a browser window opens so you can log in to Xiaohongshu manually. The session is saved to `browser_data/` and reused automatically on all subsequent runs.

Each note is saved as `YYYY-MM-DD_<title>.md` in the configured output directory (`D:\Personal Data\obsidian\zzy-kb\raw\rednotes\` by default — change `OUTPUT_DIR` in `main.py`).

## Output format

```markdown
---
source: https://www.xiaohongshu.com/explore/...
author: 作者名
date: 2026-05-05
tags:
  - rednotes
---

# Note title

## Key points
...

## Image content
...

## Summary
...
```
