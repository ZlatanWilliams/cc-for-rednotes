#!/usr/bin/env python
"""
Favorites auto-sorter — scrapes the logged-in user's 收藏夹, uses AI to
categorize posts into named 专辑, then creates those albums on XHS and
moves each post into the right one.

Usage:
    python sort.py
"""

import sys
from dotenv import load_dotenv

load_dotenv()


def main():
    print("\n=== RedNote 收藏夹 Auto-Sorter ===\n")

    print("[1/3] Collecting posts from 收藏夹...")
    from collect import get_collect_stubs
    stubs = get_collect_stubs()

    if not stubs:
        print("[Error] No posts found in 收藏夹. Make sure you are logged in.")
        sys.exit(1)

    print(f"\n[2/3] Categorizing {len(stubs)} posts with AI...")
    from categorize import categorize_posts
    try:
        url_to_album = categorize_posts(stubs)
    except Exception as e:
        print(f"[Error] Categorization failed: {e}")
        sys.exit(1)

    print(f"\n[3/3] Sorting posts into albums on XHS...")
    from sort_into_albums import sort_into_albums
    sort_into_albums(url_to_album)


if __name__ == "__main__":
    main()
