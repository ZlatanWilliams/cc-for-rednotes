"""
Sends all collected post stubs to the AI model and gets back a
{post_url: album_name} categorization mapping.
"""

import json
import re

from processor import _get_client


def categorize_one(stub: dict, existing_albums: list[str]) -> str:
    """
    Given a single post stub and the current list of existing album names,
    return the album name to assign (reusing an existing one if it fits,
    or proposing a new short Chinese name).
    """
    client, model = _get_client()
    title = stub.get("title") or "(no title)"
    existing = "、".join(existing_albums) if existing_albums else "（暂无）"

    prompt = (
        f"A user saved a Xiaohongshu post titled: \"{title}\"\n\n"
        f"Existing albums: {existing}\n\n"
        "Which album should this post go into?\n"
        "- If one of the existing albums clearly fits, return exactly that album name.\n"
        "- If none fits, suggest a new short Chinese album name (2–6 characters).\n"
        "Return ONLY the album name, nothing else."
    )

    response = client.chat.completions.create(
        model=model,
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()



    """
    Takes a list of {url, title, cover_image_url} stubs.
    Returns {url: album_name} for every stub.
    """
    client, model = _get_client()

    # Build a numbered list for the prompt
    lines = []
    for i, s in enumerate(stubs, 1):
        title = s.get("title") or "(no title)"
        lines.append(f"{i}. {title}")
    post_list = "\n".join(lines)

    prompt = (
        "Below is a numbered list of posts saved in a user's Xiaohongshu (RedNote) favorites.\n\n"
        f"{post_list}\n\n"
        "Please:\n"
        "1. Identify the natural topic clusters among these posts.\n"
        "2. Assign a short, descriptive Chinese album name (专辑名) to each cluster (2–6 characters).\n"
        "3. Assign every post to exactly one album.\n"
        "4. Return ONLY a JSON object mapping each post number (as a string) to its album name.\n"
        "   Example: {\"1\": \"美食\", \"2\": \"旅行\", \"3\": \"美食\"}\n"
        "No explanation, no markdown fences — raw JSON only."
    )

    print(f"  Sending {len(stubs)} posts to {model} for categorization...")
    response = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if model wraps the response
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    index_map: dict[str, str] = json.loads(raw)

    # Convert 1-based index keys back to post URLs
    url_map: dict[str, str] = {}
    for idx_str, album in index_map.items():
        idx = int(idx_str) - 1
        if 0 <= idx < len(stubs):
            url_map[stubs[idx]["url"]] = album.strip()

    albums = sorted(set(url_map.values()))
    print(f"  Categorized into {len(albums)} album(s): {', '.join(albums)}")
    return url_map
