import base64
import io

import httpx
from PIL import Image

from config.settings import OPENROUTER_API_KEY, OPENROUTER_MODEL, logger

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_FALLBACK_MESSAGE = (
    "I couldn't analyze that image right now. Please try again in a moment."
)
VISION_NOT_CONFIGURED_MESSAGE = (
    "Image analysis is not configured yet. Please add the OpenRouter API key in Render."
)
VISION_SYSTEM_PROMPT = (
    "You are ChrixHelp AI's visual academic tutor. Inspect the attached image "
    "carefully and follow the user's request exactly. First identify the task: "
    "description, text transcription, question solving, explanation, comparison, "
    "or data extraction. If the image contains a question, answer it directly and "
    "then show concise reasoning. For math and science, preserve symbols, units, "
    "and formulas and show the working. For code, transcribe relevant code exactly "
    "before explaining the issue and giving a corrected version. For charts or "
    "tables, report the important values and trends without inventing unreadable "
    "details. For screenshots, summarize only visible content. Do not guess the "
    "app, identities, relationships, location, intent, or background context unless "
    "the image clearly supports it. If text is unclear, say which part is unclear "
    "instead of guessing. Never claim you cannot view an attached image.\n\n"
    "Response format:\n"
    "- Start with the answer or one-sentence result.\n"
    "- Use short paragraphs, clear headings, bullets, and numbered steps.\n"
    "- For general image analysis, use at most 5 concise bullets with only the most "
    "important visible details.\n"
    "- Do not use Markdown tables, horizontal rules, filler, speculation, or repeat "
    "the request.\n"
    "- If the user asks only for a description or transcription, do not turn it "
    "into an unnecessary lesson.\n"
)


def optimize_image(image_bytes: bytes, max_dimension: int = 1600) -> bytes:
    """Reduce upload size while preserving enough detail for visual analysis."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        image = image.convert("RGB")
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=82, optimize=True)
        return output.getvalue()


async def analyze_image(
    image_bytes: bytes,
    prompt: str = (
        "Inspect the attached image directly. Describe what you can see and explain "
        "the important details. If it contains a question or problem, solve it "
        "step by step. Do not claim that you cannot view images."
    ),
) -> str:
    if not image_bytes:
        return VISION_FALLBACK_MESSAGE
    if not OPENROUTER_API_KEY:
        logger.error("Image analysis unavailable: OPENROUTER_API_KEY is not configured")
        return VISION_NOT_CONFIGURED_MESSAGE

    try:
        image_bytes = optimize_image(image_bytes)
    except Exception:
        logger.warning("Could not optimize image; sending original bytes")

    image_data = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "User request: " + prompt.strip() + "\n\n"
                            "Analyze the attached image now and respond only to that request."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                    },
                ],
            }
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://chrixhelp-bot.onrender.com",
                    "X-Title": "ChrixHelp AI",
                },
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "\n".join(
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            if isinstance(content, str) and content.strip():
                return content.strip()
    except Exception:
        logger.exception("OpenRouter image analysis failed")

    return VISION_FALLBACK_MESSAGE