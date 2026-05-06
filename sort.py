#!/usr/bin/env python
"""
Favorites auto-sorter — opens the logged-in user's 收藏夹, reads the posts
visible on the first page, and sorts each one into an AI-assigned 专辑,
creating the album on XHS if needed.

Usage:
    python sort.py           # normal run
    python sort.py --debug   # pause before each move
"""

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()


async def _run(debug: bool) -> None:
    from categorize import categorize_one
    from sort_into_albums import SortSession

    session = SortSession()

    print("\n[1/2] Opening browser and navigating to 收藏夹...")
    try:
        await session.open()
    except RuntimeError as e:
        print(f"[Error] {e}")
        sys.exit(1)

    print("[2/2] Reading first-page posts...")
    stubs = await session.get_first_page_stubs()
    if not stubs:
        print("[Error] No posts found on the first page of 收藏夹.")
        await session.close()
        sys.exit(1)
    print(f"  Found {len(stubs)} posts.")

    succeeded = failed = 0

    for i, stub in enumerate(stubs, 1):
        title = stub.get("title") or "(no title)"
        note_id = stub.get("note_id", "")
        print(f"\n[{i}/{len(stubs)}] '{title}'")

        album = categorize_one(stub, sorted(session.created_albums))
        print(f"  → Album: '{album}'")

        if debug:
            ans = input("  Press Enter to move, or type 's' to skip: ").strip().lower()
            if ans == "s":
                print("  Skipped.")
                failed += 1
                continue

        await session.ensure_album(album)

        ok = await session.move_post(note_id, album)
        if ok:
            print("  ✓ Moved")
            succeeded += 1
        else:
            print("  ✗ Skipped")
            failed += 1

    await session.close()
    print(f"\nDone. {succeeded} moved, {failed} skipped.")


def main():
    debug = "--debug" in sys.argv

    print("\n=== RedNote 收藏夹 Auto-Sorter ===")
    if debug:
        print("(DEBUG mode — pauses before each move)\n")
    else:
        print()

    asyncio.run(_run(debug))


if __name__ == "__main__":
    main()
