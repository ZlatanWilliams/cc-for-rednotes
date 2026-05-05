"""
Scrapes all post stubs from the logged-in user's 收藏夹 (Favorites).
Returns a list of {url, title, cover_image_url} dicts.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from scraper import BROWSER_DATA_DIR


COLLECT_URL = "https://www.xiaohongshu.com/user/profile/me/collect"
_MAX_EMPTY_SCROLLS = 4  # stop after this many scrolls with no new posts


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
    seen_urls: set[str] = set()
    empty_scrolls = 0

    while empty_scrolls < _MAX_EMPTY_SCROLLS:
        cards = await _extract_cards(page, seen_urls)
        if cards:
            stubs.extend(cards)
            for c in cards:
                seen_urls.add(c["url"])
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


async def _extract_cards(page, seen_urls: set[str]) -> list[dict]:
    results = await page.evaluate("""
        () => Array.from(document.querySelectorAll(
            'section.note-item, .notes-item, .collect-item, .note-card, [class*="note-item"]'
        )).map(card => {
            const a = card.querySelector('a[href*="/explore/"]');
            const img = card.querySelector('img');
            const titleEl = card.querySelector('.title, .note-title, span, p');
            return {
                url: a ? 'https://www.xiaohongshu.com' + a.getAttribute('href') : '',
                title: titleEl ? titleEl.innerText.trim() : (img ? img.getAttribute('alt') || '' : ''),
                cover_image_url: img ? (img.src || img.getAttribute('data-src') || '') : '',
            };
        }).filter(c => c.url)
    """)
    return [r for r in results if r["url"] not in seen_urls]


def get_collect_stubs() -> list[dict]:
    """Public entry point. Returns all post stubs from the user's 收藏夹."""
    if not BROWSER_DATA_DIR.exists() or not any(BROWSER_DATA_DIR.iterdir()):
        print("[Warning] No saved browser session found. Will open headed browser.")
        return asyncio.run(_scrape_collect_headed())
    return asyncio.run(_scrape_collect())
