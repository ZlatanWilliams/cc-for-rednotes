#!/usr/bin/env python
"""
RedNote scraper — extracts title, author, body text, and image URLs from a
Xiaohongshu note page using a persistent Playwright browser context.

On the first run the browser launches in headed mode so you can log in
manually; the session is saved to browser_data/ and reused on every
subsequent run.
"""

import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext

BROWSER_DATA_DIR = Path(__file__).parent / "browser_data"

_LOGIN_KEYWORDS = ("登录", "登陆")
_CDN_HOSTS = ("xhscdn", "ci.xiaohongshu", "sns-webpic", "fe-static")


async def _ensure_logged_in(context: BrowserContext) -> None:
    page = await context.new_page()
    await page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")
    await asyncio.sleep(2)

    url = page.url
    needs_login = "login" in url or await page.locator('[data-testid="login"]').count() > 0

    if not needs_login:
        try:
            await page.wait_for_selector(".user-avatar, .account-info, .login-btn", timeout=3000)
            needs_login = await page.locator(".login-btn").count() > 0
        except Exception:
            pass

    if needs_login:
        print("\n[Login required] A browser window has opened. Please log in to "
              "Xiaohongshu manually.")
        print("Press Enter here once you have logged in...", flush=True)
        await page.close()
        input()
    else:
        await page.close()


async def _resolve_short_url(url: str) -> str:
    """Follow xhslink.com redirects to get the canonical xiaohongshu.com URL."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        final_url = page.url
        await browser.close()
    return final_url


def _is_login_page(note: dict) -> bool:
    title = note.get("title", "")
    return any(kw in title for kw in _LOGIN_KEYWORDS)


async def _extract_note(page) -> dict:
    data = {
        "title": "",
        "author": "",
        "text": "",
        "image_urls": [],
        "url": page.url,
    }

    for sel in ["#detail-title", ".title", ".note-title", "h1"]:
        el = page.locator(sel).first
        if await el.count() > 0:
            data["title"] = (await el.inner_text()).strip()
            if data["title"]:
                break

    for sel in [".username", ".author-name", ".user-name", ".nickname"]:
        el = page.locator(sel).first
        if await el.count() > 0:
            data["author"] = (await el.inner_text()).strip()
            if data["author"]:
                break

    for sel in ["#detail-desc", ".note-text", ".desc", ".content"]:
        el = page.locator(sel).first
        if await el.count() > 0:
            data["text"] = (await el.inner_text()).strip()
            if data["text"]:
                break

    # Scroll to trigger lazy-loaded images, then scroll back
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(1)
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)

    # Collect all image sources in one JS pass (src, data-src, data-original)
    raw_imgs = await page.evaluate("""
        () => Array.from(document.querySelectorAll('img')).map(img => ({
            src: img.src || img.getAttribute('data-src') || img.getAttribute('data-original') || '',
            w: img.naturalWidth || img.width || 0,
            h: img.naturalHeight || img.height || 0
        }))
    """)

    seen: set[str] = set()
    for img in raw_imgs:
        src = img.get("src", "")
        if not src or src in seen:
            continue
        if not any(cdn in src for cdn in _CDN_HOSTS):
            continue
        w, h = img.get("w", 0), img.get("h", 0)
        # Keep if large enough, or if dimensions unknown (naturalSize not loaded yet)
        if (w == 0 and h == 0) or w >= 100 or h >= 100:
            seen.add(src)
            data["image_urls"].append(src)

    return data


async def _scrape_all(urls: list[str], headless: bool) -> list[dict]:
    BROWSER_DATA_DIR.mkdir(exist_ok=True)
    results = []

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )

        if not headless:
            await _ensure_logged_in(context)

        for i, url in enumerate(urls, 1):
            print(f"  Scraping {i}/{len(urls)}: {url[:80]}")
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # Detect login: URL-based redirect OR modal overlay
                login_modal = await page.locator(
                    'input[type="tel"], .login-container, [class*="signflow"]'
                ).count()
                if "login" in page.url or login_modal > 0:
                    await page.close()
                    await context.close()
                    if headless:
                        return await _scrape_all(urls, headless=False)
                    print("  [Error] Login required but already in headed mode — skipping.")
                    results.extend([{}] * (len(urls) - len(results)))
                    return results

                note = await _extract_note(page)

                # Post-extraction safety: login modal may have appeared after load
                if _is_login_page(note):
                    await page.close()
                    await context.close()
                    if headless:
                        return await _scrape_all(urls, headless=False)
                    print("  [Error] Got login page title — skipping.")
                    results.append({})
                    continue

                results.append(note)
            except Exception as e:
                print(f"  [Error] Failed to scrape: {e}")
                results.append({})
            finally:
                if not page.is_closed():
                    await page.close()

        await context.close()

    return results


def scrape_notes(urls: list[str]) -> list[dict]:
    """Scrape one or more RedNote URLs. Returns a list of note dicts in the same order."""
    resolved = []
    for url in urls:
        if "xhslink.com" in url:
            url = asyncio.run(_resolve_short_url(url))
        resolved.append(url)

    first_run = not BROWSER_DATA_DIR.exists() or not any(BROWSER_DATA_DIR.iterdir())
    headless = not first_run
    return asyncio.run(_scrape_all(resolved, headless=headless))


def scrape_note(url: str) -> dict:
    """Convenience wrapper for scraping a single URL."""
    results = scrape_notes([url])
    return results[0] if results else {}
