"""
Scrapes all post stubs from the logged-in user's 收藏夹 (Favorites).
Returns a list of {url, title, cover_image_url} dicts.

Run standalone for a diagnostic report:
    python collect.py
"""

import asyncio

from playwright.async_api import async_playwright, BrowserContext, Page

from scraper import BROWSER_DATA_DIR

XHS_HOME = "https://www.xiaohongshu.com"
_MAX_EMPTY_SCROLLS = 4


# ---------------------------------------------------------------------------
# Browser context
# ---------------------------------------------------------------------------

async def _make_context(headless: bool):
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context(
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
    for page in ctx.pages[1:]:  # close extra tabs, keep one alive
        await page.close()
    return p, ctx


# ---------------------------------------------------------------------------
# Login + profile URL detection
# ---------------------------------------------------------------------------

async def _get_collect_url(page: Page) -> str | None:
    """
    Navigate to XHS home, verify login, and return the user's 收藏夹 URL.
    Returns None if not logged in.
    """
    await page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    print(f"[CHECKPOINT 1] Home URL: {page.url}")

    # Detect login state: look for a link to the user's own profile in the nav.
    # XHS puts the logged-in user's profile link in the left sidebar.
    profile_href = await page.evaluate("""
        () => {
            // Try common sidebar / nav selectors for the "me" link
            const selectors = [
                'a.user-wrapper',
                '.side-bar a[href*="/user/profile/"]',
                'nav a[href*="/user/profile/"]',
                'a[href*="/user/profile/"]:not([href*="/explore"])',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) return el.getAttribute('href');
            }
            // Fallback: first /user/profile/ link on the page
            const all = document.querySelectorAll('a[href*="/user/profile/"]');
            return all.length ? all[0].getAttribute('href') : null;
        }
    """)

    print(f"[CHECKPOINT 1] Profile href found: {profile_href}")

    if not profile_href:
        return None  # not logged in

    # Build collect URL from profile href, e.g. /user/profile/abc123 → .../abc123/collect
    base = profile_href.split("?")[0].rstrip("/")
    collect_url = f"https://www.xiaohongshu.com{base}/collect"
    print(f"[CHECKPOINT 1] Constructed 收藏夹 URL: {collect_url}")
    return collect_url


# ---------------------------------------------------------------------------
# Main scrape flow
# ---------------------------------------------------------------------------

async def _scrape_collect(debug: bool = False) -> list[dict]:
    p, ctx = await _make_context(headless=not debug)
    page = await ctx.new_page()

    collect_url = await _get_collect_url(page)

    if not collect_url:
        print("\n[Login required] No profile link found — you are not logged in.")
        print("Please log in to Xiaohongshu in the browser window, then press Enter...")
        input()
        # Re-check after login
        collect_url = await _get_collect_url(page)
        if not collect_url:
            print("[Error] Still cannot find profile link after login. Aborting.")
            await ctx.close()
            await p.stop()
            return []

    # Navigate to 收藏夹
    print(f"\n[CHECKPOINT 2] Navigating to 收藏夹: {collect_url}")
    await page.goto(collect_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)
    print(f"[CHECKPOINT 2] 收藏夹 page URL: {page.url}")

    if debug:
        await _debug_dom_snapshot(page)
        print("\n[CHECKPOINT 2] DOM snapshot done. Press Enter to start scrolling...")
        input()

    stubs = await _scroll_and_collect(page)
    await ctx.close()
    await p.stop()
    return stubs


# ---------------------------------------------------------------------------
# DOM snapshot (debug only)
# ---------------------------------------------------------------------------

async def _debug_dom_snapshot(page: Page) -> None:
    print("\n--- DOM SNAPSHOT ---")
    for sel in ["section.note-item", ".notes-item", ".collect-item", ".note-card"]:
        n = await page.locator(sel).count()
        print(f"  '{sel}': {n} elements")

    hrefs = await page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href*="/explore/"]'))
                   .map(a => a.getAttribute('href')).slice(0, 5)
    """)
    print(f"  sample /explore/ hrefs: {hrefs}")

    unique_now = await page.evaluate("""
        () => new Set(
            Array.from(document.querySelectorAll('a[href*="/explore/"]'))
                 .map(a => (a.getAttribute('href') || '').split('/explore/')[1].split('?')[0])
                 .filter(Boolean)
        ).size
    """)
    print(f"  unique /explore/ note IDs in DOM right now: {unique_now}")
    print("--- END SNAPSHOT ---\n")


# ---------------------------------------------------------------------------
# Scroll + collect
# ---------------------------------------------------------------------------

async def _scroll_and_collect(page: Page) -> list[dict]:
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
    print(f"\n[CHECKPOINT 3] Done. Unique posts: {len(stubs)} | Duplicates in list: {has_dupes}")
    return stubs


async def _extract_cards(page: Page, seen_ids: set[str]) -> tuple[int, list[dict]]:
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_collect_stubs() -> list[dict]:
    """Returns all post stubs from the logged-in user's 收藏夹."""
    return asyncio.run(_scrape_collect(debug=False))


if __name__ == "__main__":
    # python collect.py  →  debug mode: visible browser, checkpoints, DOM snapshot
    print("Running in DEBUG mode — browser will be visible, pauses at checkpoints.")
    stubs = asyncio.run(_scrape_collect(debug=True))
    print(f"\nFinal count: {len(stubs)}")
