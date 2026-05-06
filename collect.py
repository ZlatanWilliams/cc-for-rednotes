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

async def _is_login_modal_visible(page: Page) -> bool:
    """Returns True if a login modal/mask is currently blocking the page."""
    return await page.evaluate("""
        () => {
            const mask = document.querySelector('i.reds-mask, [class*="reds-mask"]');
            const phoneInput = document.querySelector('input[placeholder*="手机号"]');
            return !!(
                (mask && getComputedStyle(mask).display !== 'none') ||
                (phoneInput && getComputedStyle(phoneInput).display !== 'none')
            );
        }
    """)


async def _wait_for_login(page: Page, prompt_msg: str) -> None:
    """Block until the user logs in."""
    print(f"\n[Login required] {prompt_msg}")
    print("Please log in to Xiaohongshu in the browser window, then press Enter...")
    input()
    await asyncio.sleep(3)


async def get_profile_url(page: Page) -> str | None:
    """
    Navigate to XHS home, verify login by finding the user's own profile link.
    Returns the profile URL, or None if not logged in.
    """
    await page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    print(f"[CHECKPOINT 1] Home URL: {page.url}")

    if await _is_login_modal_visible(page):
        await _wait_for_login(page, "Login modal detected on home page.")
        await page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

    # Prefer the logged-in user's own nav/sidebar avatar link over feed links
    profile_href = await page.evaluate("""
        () => {
            const ownSelectors = [
                'a.user-wrapper',
                '.side-bar a[href*="/user/profile/"]',
                'nav a[href*="/user/profile/"]',
                'aside a[href*="/user/profile/"]',
                '.left-sidebar a[href*="/user/profile/"]',
            ];
            for (const sel of ownSelectors) {
                const el = document.querySelector(sel);
                if (el) return el.getAttribute('href');
            }
            // Last-resort: any profile link not inside a feed card
            const all = Array.from(document.querySelectorAll('a[href*="/user/profile/"]'));
            const nav = all.find(a => !a.closest('section') && !a.closest('[class*="note"]') && !a.closest('[class*="card"]'));
            return nav ? nav.getAttribute('href') : (all.length ? all[0].getAttribute('href') : null);
        }
    """)

    print(f"[CHECKPOINT 1] Profile href found: {profile_href}")
    return f"https://www.xiaohongshu.com{profile_href.split('?')[0]}" if profile_href else None


async def navigate_to_collect(page: Page, profile_url: str) -> bool:
    """
    Go to the profile page and click the 收藏 tab.
    Returns True on success.
    """
    print(f"[CHECKPOINT 2] Navigating to profile: {profile_url}")
    await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    print(f"[CHECKPOINT 2] Profile page URL: {page.url}")

    if await _is_login_modal_visible(page):
        await _wait_for_login(page, "Login modal appeared after navigating to profile.")
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

    # Find and click the 收藏 tab
    tab = page.locator(
        'div[class*="tab"]:has-text("收藏"), '
        'span[class*="tab"]:has-text("收藏"), '
        'li:has-text("收藏"), '
        '*[class*="collect"]:has-text("收藏")'
    ).first
    count = await tab.count()
    print(f"[CHECKPOINT 2] 收藏 tab found: {count > 0}")

    if count == 0:
        # Fallback: print all tab-like elements to help diagnose
        all_tabs = await page.evaluate("""
            () => Array.from(document.querySelectorAll(
                '[class*="tab"], [class*="Tab"], [role="tab"]'
            )).map(el => ({cls: el.className, text: el.innerText.trim()}))
              .filter(t => t.text)
              .slice(0, 10)
        """)
        print(f"[CHECKPOINT 2] All tab-like elements found: {all_tabs}")
        return False

    # Guard against login modal blocking the click
    if await _is_login_modal_visible(page):
        await _wait_for_login(page, "Login modal is blocking the 收藏 tab click.")
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        tab = page.locator(
            'div[class*="tab"]:has-text("收藏"), '
            'span[class*="tab"]:has-text("收藏"), '
            'li:has-text("收藏"), '
            '*[class*="collect"]:has-text("收藏")'
        ).first

    await tab.click()
    await asyncio.sleep(2)
    print(f"[CHECKPOINT 2] After clicking 收藏 tab, URL: {page.url}")
    return True


# ---------------------------------------------------------------------------
# Main scrape flow
# ---------------------------------------------------------------------------

async def _scrape_collect(debug: bool = False) -> list[dict]:
    p, ctx = await _make_context(headless=not debug)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    profile_url = await get_profile_url(page)

    if not profile_url:
        print("[Error] Cannot find your profile link even after login. Aborting.")
        await ctx.close()
        await p.stop()
        return []

    ok = await navigate_to_collect(page, profile_url)
    if not ok:
        print("[Error] Could not find or click the 收藏 tab. See tab list above for diagnostics.")
        await ctx.close()
        await p.stop()
        return []

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

    print(f"  Scrolling page: {page.url}")
    if "/collect" not in page.url:
        print("  [WARNING] URL does not contain '/collect' — may be on wrong page!")

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

def get_collect_stubs(debug: bool = False) -> list[dict]:
    """Returns all post stubs from the logged-in user's 收藏夹."""
    return asyncio.run(_scrape_collect(debug=debug))


if __name__ == "__main__":
    # python collect.py  →  debug mode: visible browser, checkpoints, DOM snapshot
    print("Running in DEBUG mode — browser will be visible, pauses at checkpoints.")
    stubs = asyncio.run(_scrape_collect(debug=True))
    print(f"\nFinal count: {len(stubs)}")
