from unittest.mock import AsyncMock, patch

import pytest

from handlers.messages import handle_message


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.reply_text = AsyncMock()


class FakeUpdate:
    def __init__(self, text):
        self.message = FakeMessage(text)
        self.effective_chat = type("Chat", (), {"id": 1})()


class FakeBot:
    send_chat_action = AsyncMock()


class FakeContext:
    def __init__(self):
        self.chat_data = {}
        self.bot = FakeBot()


@pytest.mark.asyncio
async def test_message_handler_sends_history_to_ai_and_stores_reply():
    update = FakeUpdate("What is photosynthesis?")
    context = FakeContext()

    with patch(
        "handlers.messages.generate_response",
        new=AsyncMock(return_value="It is how plants make food."),
    ) as generate_response:
        await handle_message(update, context)

    generate_response.assert_awaited_once_with(
        "What is photosynthesis?", history=[]
    )
    assert context.chat_data["conversation"] == [
        {"role": "user", "content": "What is photosynthesis?"},
        {"role": "assistant", "content": "It is how plants make food."},
    ]


@pytest.mark.asyncio
async def test_message_handler_rejects_oversized_messages():
    update = FakeUpdate("x" * 2001)
    context = FakeContext()

    with patch(
        "handlers.messages.generate_response", new=AsyncMock()
    ) as generate_response:
        await handle_message(update, context)

    generate_response.assert_not_awaited()
    update.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_mode_selection_uses_compact_confirmation():
    from handlers.messages import select_mode

    update = FakeUpdate("Explain")
    context = FakeContext()

    await select_mode(update, context)

    assert update.message.reply_text.await_args.args[0] == "Explain mode"


@pytest.mark.asyncio
async def test_thank_you_gets_a_short_social_reply_without_ai_call():
    update = FakeUpdate("Thank you")
    context = FakeContext()

    with patch("handlers.messages.generate_response", new=AsyncMock()) as generate_response:
        await handle_message(update, context)

    generate_response.assert_not_awaited()
    assert update.message.reply_text.await_args.args[0] == (
        "You're welcome. I'm here whenever you need help."
    )
    