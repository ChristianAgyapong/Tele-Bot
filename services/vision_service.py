import base64

import httpx

from config.settings import OPENROUTER_API_KEY, OPENROUTER_MODEL, logger

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_FALLBACK_MESSAGE = (
    "I couldn't analyze that image right now. Please try again in a moment."
)
VISION_NOT_CONFIGURED_MESSAGE = (
    "Image analysis is not configured yet. Please add the OpenRouter API key in Render."
)


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

    image_data = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
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
        async with httpx.AsyncClient(timeout=45.0) as client:
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