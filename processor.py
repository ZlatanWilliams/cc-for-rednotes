import base64
import os
from datetime import date

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MAX_IMAGES = 10


def _get_client() -> tuple[OpenAI, str]:
    api_key = os.environ["OPENAI_API_KEY"]
    base_url = os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("MODEL_NAME", "gpt-4o")
    return OpenAI(api_key=api_key, base_url=base_url), model


def _download_image(url: str, client: httpx.Client) -> bytes | None:
    try:
        resp = client.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"  [Skip] Image download failed: {url[:60]}... ({e})")
        return None


def _guess_media_type(url: str) -> str:
    lower = url.lower()
    if ".png" in lower:
        return "image/png"
    if ".gif" in lower:
        return "image/gif"
    if ".webp" in lower:
        return "image/webp"
    return "image/jpeg"


def process_note(note_data: dict) -> str:
    """Analyze note content with the AI model and return a formatted Markdown string."""
    client_ai, model = _get_client()

    title = note_data.get("title") or "Untitled"
    author = note_data.get("author") or "Unknown"
    text = note_data.get("text", "")
    image_urls = note_data.get("image_urls", [])[:MAX_IMAGES]
    source_url = note_data.get("url", "")

    print(f"  Text length: {len(text)} chars, images: {len(image_urls)}")

    image_blocks = []
    if image_urls:
        print(f"  Downloading {len(image_urls)} image(s)...")
        with httpx.Client(
            headers={
                "Referer": "https://www.xiaohongshu.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        ) as http:
            for i, url in enumerate(image_urls, 1):
                print(f"  Downloading image {i}/{len(image_urls)}...", end="\r")
                img_data = _download_image(url, http)
                if img_data:
                    media_type = _guess_media_type(url)
                    b64 = base64.standard_b64encode(img_data).decode("utf-8")
                    image_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{b64}"},
                    })
        print()

    content = []

    if image_blocks:
        content.append({
            "type": "text",
            "text": f"The following is a Xiaohongshu (RedNote) post with {len(image_blocks)} image(s) and body text.",
        })
        for i, block in enumerate(image_blocks, 1):
            content.append({"type": "text", "text": f"\n[Image {i}]"})
            content.append(block)

    content.append({
        "type": "text",
        "text": f"\n[Body text]\n{text}" if text else "\n[Body text] (none)",
    })

    content.append({
        "type": "text",
        "text": (
            "\n\nBased on the content above, please:\n"
            "1. Transcribe all text visible in each image as accurately as possible.\n"
            "2. Understand the topic and meaning of each image.\n"
            "3. Merge the image content with the body text into a well-structured, detailed Markdown note.\n"
            "4. The note should include:\n"
            "   - Key knowledge points or takeaways (grouped under subheadings)\n"
            "   - All important text found in the images\n"
            "   - A complete organized summary\n"
            "5. Write the output in Chinese, preserving the original language style.\n"
            "6. Output only the Markdown body (starting from the first ##). Do not include YAML front matter.\n"
        ),
    })

    print(f"  Calling {model} to process content...")
    response = client_ai.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )

    body = response.choices[0].message.content.strip()

    front_matter = (
        "---\n"
        f"source: {source_url}\n"
        f"author: {author}\n"
        f"date: {date.today().isoformat()}\n"
        "tags:\n  - rednotes\n"
        "---\n\n"
        f"# {title}\n\n"
    )

    return front_matter + body
