from groq import AsyncGroq, GroqError

from config.settings import (
    AI_MAX_TOKENS,
    AI_SYSTEM_PROMPT,
    AI_TEMPERATURE,
    GROQ_API_KEY,
    GROQ_MODEL,
    logger,
)

# AsyncGroq (not the sync Groq client) — calling the sync client inside an
# `async def` blocks the bot's entire event loop on every AI request.
client = AsyncGroq(api_key=GROQ_API_KEY)

FALLBACK_MESSAGE = (
    "Sorry, I couldn't generate a response right now. Please try again later."
)


async def generate_response(
    message: str,
    history: list[dict[str, str]] | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    temperature: float | None = None,
) -> str:
    if not message or not message.strip():
        return "I didn't catch a message there — could you send that again?"

    try:
        messages = [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            *(history or []),
            {"role": "user", "content": message.strip()},
        ]
        completion = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature if temperature is not None else AI_TEMPERATURE,
            max_tokens=max_tokens or AI_MAX_TOKENS,
            **({"response_format": response_format} if response_format else {}),
        )
        return completion.choices[0].message.content

    except GroqError as error:
        logger.error("Groq API error: %s", error)
        return FALLBACK_MESSAGE

    except Exception:
        logger.exception("Unexpected error while generating AI response")
        return FALLBACK_MESSAGE