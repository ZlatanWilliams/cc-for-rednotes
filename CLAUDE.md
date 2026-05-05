# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Scrapes one or more Xiaohongshu (RedNote) notes by URL, sends the text and images to an OpenAI-compatible vision model, and saves a structured Markdown file to an Obsidian vault at `D:\Personal Data\obsidian\zzy-kb\raw\rednotes\`.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # then fill in your credentials
```

`.env` requires:
- `OPENAI_API_KEY` — API key for the third-party provider
- `OPENAI_BASE_URL` — provider endpoint (must end with `/v1`)
- `MODEL_NAME` — must be a vision-capable model (e.g. `gpt-4o`)

## Running

```bash
# Single note
python main.py "https://www.xiaohongshu.com/explore/<id>"

# Multiple notes in one pass
python main.py "https://..." "https://..." "https://..."

# Auto-sort 收藏夹 into 专辑 on XHS
python sort.py
```

First run opens a headed browser for manual login; the session persists in `browser_data/` and all subsequent runs are headless (except `sort.py` which always runs headed for UI interactions).

## Architecture

Two independent pipelines share the same browser session (`browser_data/`).

**Pipeline 1 — Note scraper** (`main.py`): `main.py` → `scraper.py` → `processor.py` → file write.

**Pipeline 2 — Favorites sorter** (`sort.py`): `sort.py` → `collect.py` → `categorize.py` → `sort_into_albums.py` → XHS UI.

**`scraper.py`** — Playwright async scraper.
- `scrape_notes(urls)` is the public API; opens **one** persistent browser context for all URLs, then closes it. This avoids re-authenticating per note.
- `scrape_note(url)` is a single-URL convenience wrapper around `scrape_notes`.
- Login detection happens in `_ensure_logged_in()`, which checks selectors and URL for login state; if login is needed it blocks on `input()` so the user can authenticate in the open window.
- `_extract_note(page)` uses CSS selector fallback chains for title/author/body text, and CDN hostname matching (`sns-webpic`, `ci.xiaohongshu`, `xhscdn`) to distinguish note images from UI icons.
- Uses `wait_until="domcontentloaded"` + a 3-second sleep (not `networkidle`) because XHS continuously fires background requests that would cause `networkidle` to time out.

**`processor.py`** — OpenAI-compatible vision API caller.
- Builds a multipart `content` list (text + `image_url` blocks with base64 data URIs) and sends it in one `chat.completions.create` call.
- Caps images at `MAX_IMAGES = 10` per note.
- Returns the full Markdown string including YAML front matter (source, author, date, tags).

**`main.py`** — Orchestrator and CLI.
- Scrapes all URLs in one batch call, then iterates results calling `process_note` per note.
- Per-note failures (scrape or AI error) are caught individually; the run continues for remaining notes.
- Output filename: `YYYY-MM-DD_<title>.md`.

## Modifying selectors

If XHS changes its DOM, update the fallback selector lists in `_extract_note()` (`scraper.py:65–106`). The CDN hostname filter for images is at `scraper.py:92`.

For the favorites sorter, all UI interaction selectors (新建专辑, 移动到专辑, album options) are defined as constants at the top of `sort_into_albums.py` — update them there if XHS changes its UI.
