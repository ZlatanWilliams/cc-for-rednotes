#!/usr/bin/env python
"""
Favorites auto-sorter — scrapes the logged-in user's 收藏夹, then sorts each
post into an AI-assigned 专辑 one by one, creating the album on XHS if needed.

Usage:
    python sort.py           # normal run
    python sort.py --debug   # visible browser, checkpoints, pause before each move
"""

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()


async def _sort_one_by_one(stubs: list[dict], debug: bool = False) -> None:
    from categorize import categorize_one
    from sort_into_albums import SortSession

    total = len(stubs)
    session = SortSession()

    print("\n[2/2] Opening browser and navigating to 收藏夹...")
    try:
        await session.open()
    except RuntimeError as e:
        print(f"[Error] {e}")
        sys.exit(1)

    succeeded = failed = 0

    for i, stub in enumerate(stubs, 1):
        title = stub.get("title") or "(no title)"
        note_id = stub.get("note_id", "")
        print(f"\n[{i}/{total}] '{title}'")

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
            print(f"  ✓ Moved")
            succeeded += 1
        else:
            print(f"  ✗ Skipped")
            failed += 1

    await session.close()
    print(f"\nDone. {succeeded} moved, {failed} skipped.")


def main():
    debug = "--debug" in sys.argv

    print("\n=== RedNote 收藏夹 Auto-Sorter ===")
    if debug:
        print("(DEBUG mode — browser visible, pauses before each move)\n")
    else:
        print()

    print("[1/2] Collecting posts from 收藏夹...")
    from collect import get_collect_stubs
    stubs = get_collect_stubs(debug=debug)

    if not stubs:
        print("[Error] No posts found in 收藏夹. Make sure you are logged in.")
        sys.exit(1)

    print(f"  Found {len(stubs)} posts.")

    asyncio.run(_sort_one_by_one(stubs, debug=debug))


if __name__ == "__main__":
    main()
