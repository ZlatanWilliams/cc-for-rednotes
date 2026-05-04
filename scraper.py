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

    img_els = await page.locator("img").all()
    seen: set[str] = set()
    for img in img_els:
        src = await img.get_attribute("src") or ""
        if not src or src in seen:
            continue
        if any(cdn in src for cdn in ["sns-webpic", "ci.xiaohongshu", "xhscdn", "fe-static"]):
            width = await img.get_attribute("width") or "0"
            if int(width) < 50 if width.isdigit() else False:
                continue
            seen.add(src)
            data["image_urls"].append(src)

    if not data["image_urls"]:
        for img in img_els:
            for attr in ["data-src", "data-original"]:
                src = await img.get_attribute(attr) or ""
                if src and src not in seen:
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

                if "login" in page.url:
                    await page.close()
                    if headless:
                        await context.close()
                        return await _scrape_all(urls, headless=False)
                    print("  [Error] Login redirect detected — skipping.")
                    results.append({})
                    continue

                note = await _extract_note(page)
                results.append(note)
            except Exception as e:
                print(f"  [Error] Failed to scrape: {e}")
                results.append({})
            finally:
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
