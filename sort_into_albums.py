"""
Playwright automation that creates 专辑 (albums) in the user's XHS 收藏夹
and moves each saved post into the correct album.

XHS UI interactions are selector-dependent; selectors are defined as
constants at the top so they can be updated if XHS changes its DOM.
"""

import asyncio

from playwright.async_api import async_playwright, Page

from scraper import BROWSER_DATA_DIR

COLLECT_URL = "https://www.xiaohongshu.com/user/profile/me/collect"

# --- Selectors (update here if XHS changes its DOM) ---
SEL_NEW_ALBUM_BTN = (
    'button:has-text("新建专辑"), '
    '[class*="create-album"], '
    '[class*="new-album"], '
    'span:has-text("新建专辑")'
)
SEL_ALBUM_NAME_INPUT = 'input[placeholder*="专辑"], input[placeholder*="名称"], input[type="text"]'
SEL_ALBUM_CONFIRM_BTN = (
    'button:has-text("确定"), '
    'button:has-text("创建"), '
    'button:has-text("保存")'
)
SEL_NOTE_CARD = (
    'section.note-item, '
    '.notes-item, '
    '.collect-item, '
    '[class*="note-item"]'
)
SEL_CARD_MENU = (
    '[class*="more"], '
    '[class*="dots"], '
    'button[class*="option"], '
    '.note-item-menu'
)
SEL_MOVE_TO_ALBUM = (
    '[class*="move-to"], '
    'li:has-text("移动到专辑"), '
    'span:has-text("移动到专辑"), '
    'div:has-text("移动到专辑")'
)
SEL_ALBUM_OPTION = '[class*="album-item"], [class*="album-option"], li[class*="album"]'
# -------------------------------------------------------


async def _create_albums(page: Page, album_names: list[str]) -> None:
    print(f"  Creating {len(album_names)} album(s): {', '.join(album_names)}")
    for name in album_names:
        try:
            btn = page.locator(SEL_NEW_ALBUM_BTN).first
            await btn.wait_for(timeout=5000)
            await btn.click()
            await asyncio.sleep(0.8)

            inp = page.locator(SEL_ALBUM_NAME_INPUT).first
            await inp.wait_for(timeout=3000)
            await inp.fill(name)
            await asyncio.sleep(0.3)

            confirm = page.locator(SEL_ALBUM_CONFIRM_BTN).first
            await confirm.click()
            await asyncio.sleep(1)
            print(f"    Created album: {name}")
        except Exception as e:
            print(f"    [Error] Could not create album '{name}': {e}")


async def _move_post_to_album(page: Page, post_url: str, album_name: str) -> bool:
    """Find a post card by its URL and move it to the named album. Returns True on success."""
    # Extract note ID from URL for matching
    note_id = post_url.rstrip("/").split("/")[-1].split("?")[0]

    # Find the card whose link contains the note ID
    card = page.locator(f'{SEL_NOTE_CARD}:has(a[href*="{note_id}"])').first
    if await card.count() == 0:
        # Scroll to try to find it
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
        if await card.count() == 0:
            print(f"    [Skip] Card not found for: {note_id}")
            return False

    # Hover to reveal the options menu
    await card.hover()
    await asyncio.sleep(0.4)

    menu_btn = card.locator(SEL_CARD_MENU).first
    if await menu_btn.count() == 0:
        print(f"    [Skip] No menu button found for: {note_id}")
        return False

    await menu_btn.click()
    await asyncio.sleep(0.5)

    # Click "移动到专辑"
    move_opt = page.locator(SEL_MOVE_TO_ALBUM).first
    try:
        await move_opt.wait_for(timeout=3000)
        await move_opt.click()
        await asyncio.sleep(0.5)
    except Exception:
        print(f"    [Skip] '移动到专辑' option not found for: {note_id}")
        # Close any open menu
        await page.keyboard.press("Escape")
        return False

    # Select the target album from the list
    album_opt = page.locator(f'{SEL_ALBUM_OPTION}:has-text("{album_name}")').first
    try:
        await album_opt.wait_for(timeout=3000)
        await album_opt.click()
        await asyncio.sleep(0.5)
    except Exception:
        print(f"    [Skip] Album option '{album_name}' not visible for: {note_id}")
        await page.keyboard.press("Escape")
        return False

    return True


async def _sort(url_to_album: dict[str, str]) -> None:
    album_names = sorted(set(url_to_album.values()))

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=False,  # must be visible for UI interactions
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

        print("\n[Step A] Creating albums...")
        await _create_albums(page, album_names)

        print("\n[Step B] Moving posts into albums...")
        succeeded = 0
        failed = 0
        total = len(url_to_album)

        for i, (url, album) in enumerate(url_to_album.items(), 1):
            print(f"  [{i}/{total}] → '{album}'", end=" ")
            ok = await _move_post_to_album(page, url, album)
            if ok:
                print("✓")
                succeeded += 1
            else:
                failed += 1
            await asyncio.sleep(0.3)

        await context.close()

    print(f"\nDone. {succeeded} moved, {failed} skipped.")


def sort_into_albums(url_to_album: dict[str, str]) -> None:
    """Public entry point. Takes {url: album_name} and performs XHS UI automation."""
    asyncio.run(_sort(url_to_album))
