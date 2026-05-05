"""
Playwright automation that creates 专辑 (albums) in the user's XHS 收藏夹
and moves posts into them one at a time via SortSession.

XHS UI selectors are defined as constants at the top — update them here
if XHS changes its DOM.
"""

import asyncio

from playwright.async_api import async_playwright, Page

from scraper import BROWSER_DATA_DIR
from collect import get_profile_url, navigate_to_collect

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
SEL_NOTE_CARD = 'section.note-item, .notes-item, .collect-item, .note-card'
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


class SortSession:
    """
    Keeps a single browser context open for the full sort run.
    Tracks which albums have already been created.

    Usage:
        session = SortSession()
        await session.open()
        await session.ensure_album("美食")
        ok = await session.move_post("abc123def", "美食")
        await session.close()
    """

    def __init__(self):
        self._p = None
        self._ctx = None
        self._page: Page | None = None
        self.created_albums: set[str] = set()

    async def open(self) -> None:
        self._p = await async_playwright().start()
        self._ctx = await self._p.chromium.launch_persistent_context(
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
        for page in self._ctx.pages[1:]:
            await page.close()
        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()

        # Navigate to 收藏夹 via profile → 收藏 tab click
        profile_url = await get_profile_url(self._page)
        if not profile_url:
            raise RuntimeError("Not logged in — cannot open 收藏夹.")
        ok = await navigate_to_collect(self._page, profile_url)
        if not ok:
            raise RuntimeError("Could not navigate to 收藏 tab.")

    async def ensure_album(self, name: str) -> None:
        """Create the album on XHS if it hasn't been created this session."""
        if name in self.created_albums:
            return
        try:
            btn = self._page.locator(SEL_NEW_ALBUM_BTN).first
            await btn.wait_for(timeout=5000)
            await btn.click()
            await asyncio.sleep(0.8)

            inp = self._page.locator(SEL_ALBUM_NAME_INPUT).first
            await inp.wait_for(timeout=3000)
            await inp.fill(name)
            await asyncio.sleep(0.3)

            confirm = self._page.locator(SEL_ALBUM_CONFIRM_BTN).first
            await confirm.click()
            await asyncio.sleep(1)

            self.created_albums.add(name)
            print(f"  [Album created] '{name}'")
        except Exception as e:
            print(f"  [Error] Could not create album '{name}': {e}")

    async def move_post(self, note_id: str, album_name: str) -> bool:
        """Find a post card by note ID and move it to the named album."""
        page = self._page

        card = page.locator(f'{SEL_NOTE_CARD}:has(a[href*="{note_id}"])').first
        if await card.count() == 0:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            if await card.count() == 0:
                print(f"  [Skip] Card not found: {note_id}")
                return False

        await card.hover()
        await asyncio.sleep(0.4)

        menu_btn = card.locator(SEL_CARD_MENU).first
        if await menu_btn.count() == 0:
            print(f"  [Skip] No menu button: {note_id}")
            return False

        await menu_btn.click()
        await asyncio.sleep(0.5)

        move_opt = page.locator(SEL_MOVE_TO_ALBUM).first
        try:
            await move_opt.wait_for(timeout=3000)
            await move_opt.click()
            await asyncio.sleep(0.5)
        except Exception:
            print(f"  [Skip] '移动到专辑' option not found: {note_id}")
            await page.keyboard.press("Escape")
            return False

        album_opt = page.locator(f'{SEL_ALBUM_OPTION}:has-text("{album_name}")').first
        try:
            await album_opt.wait_for(timeout=3000)
            await album_opt.click()
            await asyncio.sleep(0.5)
        except Exception:
            print(f"  [Skip] Album option '{album_name}' not visible: {note_id}")
            await page.keyboard.press("Escape")
            return False

        return True

    async def close(self) -> None:
        if self._ctx:
            await self._ctx.close()
        if self._p:
            await self._p.stop()
