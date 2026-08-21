import base64

import httpx

from config.settings import OPENROUTER_API_KEY, OPENROUTER_MODEL, logger

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_FALLBACK_MESSAGE = (
    "I couldn't analyze that image right now. Please try again in a moment."
)


async def analyze_image(
    image_bytes: bytes,
    prompt: str = "Analyze this image clearly and explain anything important in it.",
) -> str:
    if not image_bytes or not OPENROUTER_API_KEY:
        return VISION_FALLBACK_MESSAGE

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
            if isinstance(content, str) and content.strip():
                return content.strip()
    except Exception:
        logger.exception("OpenRouter image analysis failed")

    return VISION_FALLBACK_MESSAGE