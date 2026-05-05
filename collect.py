"""
Scrapes all post stubs from the logged-in user's 收藏夹 (Favorites).
Returns a list of {url, title, cover_image_url} dicts.

Run standalone for a diagnostic report:
    python collect.py
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from scraper import BROWSER_DATA_DIR


COLLECT_URL = "https://www.xiaohongshu.com/user/profile/me/collect"
_MAX_EMPTY_SCROLLS = 4


async def _open_context(headless: bool):
    p = await async_playwright().start()
    context = await p.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="zh-CN",
    )
    return p, context


async def _scrape_collect(debug: bool = False) -> list[dict]:
    headless = not debug
    p, context = await _open_context(headless)
    page = await context.new_page()
    await page.goto(COLLECT_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    print(f"\n[CHECKPOINT 1] URL after load: {page.url}")

    if "login" in page.url or await page.locator('input[type="tel"], [class*="signflow"]').count() > 0:
        print("[CHECKPOINT 1] >> Login wall detected. Please log in then press Enter...")
        input()

    if debug:
        await _debug_dom_snapshot(page)
        print("\n[CHECKPOINT 2] DOM snapshot done. Press Enter to start scrolling...")
        input()

    stubs = await _scroll_and_collect(page, debug=debug)
    await context.close()
    await p.stop()
    return stubs


async def _debug_dom_snapshot(page) -> None:
    print("\n--- DOM SNAPSHOT ---")

    # Check each selector individually
    for sel in ["section.note-item", ".notes-item", ".collect-item", ".note-card"]:
        n = await page.locator(sel).count()
        print(f"  '{sel}': {n} elements")

    # Sample raw hrefs to verify URL format
    hrefs = await page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href*="/explore/"]'))
                   .map(a => a.getAttribute('href')).slice(0, 5)
    """)
    print(f"  sample /explore/ hrefs: {hrefs}")

    # Total unique note IDs visible in DOM right now (ground truth for this scroll position)
    unique_ids_now = await page.evaluate("""
        () => new Set(
            Array.from(document.querySelectorAll('a[href*="/explore/"]'))
                 .map(a => (a.getAttribute('href') || '').split('/explore/')[1].split('?')[0])
                 .filter(Boolean)
        ).size
    """)
    print(f"  unique /explore/ note IDs in DOM right now: {unique_ids_now}")
    print("--- END SNAPSHOT ---\n")


async def _scroll_and_collect(page, debug: bool = False) -> list[dict]:
    stubs: list[dict] = []
    seen_ids: set[str] = set()
    empty_scrolls = 0
    scroll_num = 0

    while empty_scrolls < _MAX_EMPTY_SCROLLS:
        scroll_num += 1
        raw_count, cards = await _extract_cards(page, seen_ids)
        new_count = len(cards)

        print(
            f"  [scroll {scroll_num:3d}] DOM cards: {raw_count:4d} | "
            f"new: {new_count:3d} | "
            f"total: {len(stubs) + new_count:4d} | "
            f"empty_scrolls: {empty_scrolls}"
        )

        if cards:
            stubs.extend(cards)
            for c in cards:
                seen_ids.add(c["note_id"])
            empty_scrolls = 0
        else:
            empty_scrolls += 1

        prev_height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        new_height = await page.evaluate("document.body.scrollHeight")

        if new_height == prev_height:
            empty_scrolls += 1
            print(f"           >> height unchanged ({new_height}px), empty_scrolls → {empty_scrolls}")

    has_dupes = len(stubs) != len({s["note_id"] for s in stubs})
    print(f"\n[CHECKPOINT 3] Done. Unique posts: {len(stubs)} | Duplicate note_ids in list: {has_dupes}")
    return stubs


async def _extract_cards(page, seen_ids: set[str]) -> tuple[int, list[dict]]:
    results = await page.evaluate("""
        () => {
            const map = new Map();
            document.querySelectorAll(
                'section.note-item, .notes-item, .collect-item, .note-card'
            ).forEach(card => {
                const a = card.querySelector('a[href*="/explore/"]');
                if (!a) return;
                const href = a.getAttribute('href') || '';
                const noteId = href.split('/explore/')[1].split('?')[0];
                if (!noteId || map.has(noteId)) return;
                const img = card.querySelector('img');
                const titleEl = card.querySelector('.title, .note-title, span, p');
                map.set(noteId, {
                    note_id: noteId,
                    url: 'https://www.xiaohongshu.com/explore/' + noteId,
                    title: titleEl ? titleEl.innerText.trim()
                                   : (img ? img.getAttribute('alt') || '' : ''),
                    cover_image_url: img
                        ? (img.src || img.getAttribute('data-src') || '') : '',
                });
            });
            return Array.from(map.values());
        }
    """)
    new_cards = [r for r in results if r["note_id"] not in seen_ids]
    return len(results), new_cards


def get_collect_stubs() -> list[dict]:
    """Public entry point. Returns all post stubs from the user's 收藏夹."""
    if not BROWSER_DATA_DIR.exists() or not any(BROWSER_DATA_DIR.iterdir()):
        print("[Warning] No saved browser session found. Will open headed browser.")
    return asyncio.run(_scrape_collect(debug=False))


if __name__ == "__main__":
    # python collect.py  →  debug mode with visible browser and checkpoints
    print("Running in DEBUG mode — browser will be visible, pauses at checkpoints.")
    stubs = asyncio.run(_scrape_collect(debug=True))
    print(f"\nFinal count: {len(stubs)}")



async def _scrape_collect() -> list[dict]:
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=True,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )

        page = await context.new_page()
        await page.goto(COLLECT_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # Redirect to login → relaunch headed
        if "login" in page.url or await page.locator('input[type="tel"], [class*="signflow"]').count() > 0:
            await context.close()
            return await _scrape_collect_headed()

        # Resolve the actual URL after redirect (me → real user ID)
        actual_url = page.url
        print(f"  Collect page: {actual_url}")

        stubs = await _scroll_and_collect(page)
        await context.close()
        return stubs


async def _scrape_collect_headed() -> list[dict]:
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = await context.new_page()
        await page.goto(COLLECT_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        print("\n[Login required] Please log in to Xiaohongshu in the browser window.")
        print("Press Enter once you are logged in and can see your 收藏夹...")
        input()
        stubs = await _scroll_and_collect(page)
        await context.close()
        return stubs


async def _scroll_and_collect(page) -> list[dict]:
    stubs: list[dict] = []
    seen_ids: set[str] = set()
    empty_scrolls = 0

    while empty_scrolls < _MAX_EMPTY_SCROLLS:
        cards = await _extract_cards(page, seen_ids)
        if cards:
            stubs.extend(cards)
            for c in cards:
                seen_ids.add(c["note_id"])
            empty_scrolls = 0
            print(f"  Collected {len(stubs)} posts so far...", end="\r")
        else:
            empty_scrolls += 1

        prev_height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        new_height = await page.evaluate("document.body.scrollHeight")

        if new_height == prev_height:
            empty_scrolls += 1

    print(f"\n  Done. Total posts collected: {len(stubs)}")
    return stubs


async def _extract_cards(page, seen_ids: set[str]) -> list[dict]:
    results = await page.evaluate("""
        () => {
            const map = new Map();
            document.querySelectorAll(
                'section.note-item, .notes-item, .collect-item, .note-card'
            ).forEach(card => {
                const a = card.querySelector('a[href*="/explore/"]');
                if (!a) return;
                const href = a.getAttribute('href') || '';
                const noteId = href.split('/explore/')[1].split('?')[0];
                if (!noteId || map.has(noteId)) return;
                const img = card.querySelector('img');
                const titleEl = card.querySelector('.title, .note-title, span, p');
                map.set(noteId, {
                    note_id: noteId,
                    url: 'https://www.xiaohongshu.com/explore/' + noteId,
                    title: titleEl ? titleEl.innerText.trim()
                                   : (img ? img.getAttribute('alt') || '' : ''),
                    cover_image_url: img
                        ? (img.src || img.getAttribute('data-src') || '') : '',
                });
            });
            return Array.from(map.values());
        }
    """)
    return [r for r in results if r["note_id"] not in seen_ids]


def get_collect_stubs() -> list[dict]:
    """Public entry point. Returns all post stubs from the user's 收藏夹."""
    if not BROWSER_DATA_DIR.exists() or not any(BROWSER_DATA_DIR.iterdir()):
        print("[Warning] No saved browser session found. Will open headed browser.")
        return asyncio.run(_scrape_collect_headed())
    return asyncio.run(_scrape_collect())
