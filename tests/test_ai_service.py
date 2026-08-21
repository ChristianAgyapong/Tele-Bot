from unittest.mock import AsyncMock, patch

import pytest
from groq import GroqError

from config.settings import AI_SYSTEM_PROMPT
from services.ai_service import FALLBACK_MESSAGE, generate_response


def test_ai_prompt_requests_chatgpt_style_phone_friendly_format():
    assert "Do not use Markdown tables" in AI_SYSTEM_PROMPT
    assert "Start with the direct answer" in AI_SYSTEM_PROMPT
    assert "Never make the student answer" in AI_SYSTEM_PROMPT
    assert "Quiz and exam preparation is allowed" in AI_SYSTEM_PROMPT
    assert "Do not promise perfect accuracy" in AI_SYSTEM_PROMPT
    assert "evaluate every option" in AI_SYSTEM_PROMPT
    assert "calculations are recomputed" in AI_SYSTEM_PROMPT
    assert "locate the exact blank" in AI_SYSTEM_PROMPT
    assert "Return the exact missing answer first" in AI_SYSTEM_PROMPT


def test_required_secrets_are_trimmed():
    from config.settings import GROQ_API_KEY, TELEGRAM_BOT_TOKEN

    assert TELEGRAM_BOT_TOKEN == TELEGRAM_BOT_TOKEN.strip()
    assert GROQ_API_KEY == GROQ_API_KEY.strip()


def test_ai_prompt_requires_rigorous_human_academic_tutoring():
    assert "state assumptions" in AI_SYSTEM_PROMPT
    assert "working code" in AI_SYSTEM_PROMPT
    assert "avoid canned openings" in AI_SYSTEM_PROMPT.lower()
    assert "do not turn words like 'thank you'" in AI_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_generate_response_sends_history_to_groq():
    completion = type(
        "Completion",
        (),
        {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "Direct answer"})()})()]},
    )()

    with patch(
        "services.ai_service.client.chat.completions.create",
        new=AsyncMock(return_value=completion),
    ) as create:
        response = await generate_response(
            "What is gravity?",
            history=[{"role": "user", "content": "Explain force."}],
        )

    assert response == "Direct answer"
    messages = create.await_args.kwargs["messages"]
    assert messages[-2:] == [
        {"role": "user", "content": "Explain force."},
        {"role": "user", "content": "What is gravity?"},
    ]
    assert create.await_args.kwargs["temperature"] == 0.3


@pytest.mark.asyncio
async def test_generate_response_returns_fallback_on_groq_failure():
    with patch(
        "services.ai_service.client.chat.completions.create",
        new=AsyncMock(side_effect=GroqError("temporary failure")),
    ):
        response = await generate_response("Try again")

    assert response == FALLBACK_MESSAGE