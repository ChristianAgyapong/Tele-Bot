from unittest.mock import AsyncMock, patch

import pytest

from handlers.messages import handle_photo


class FakePhoto:
    file_id = "photo-id"


class FakeMessage:
    photo = [FakePhoto()]
    caption = "Explain the diagram"
    reply_text = AsyncMock()


class FakeUpdate:
    message = FakeMessage()
    effective_chat = type("Chat", (), {"id": 1})()


class FakeFile:
    async def download_as_bytearray(self):
        return bytearray(b"image")


class FakeBot:
    send_chat_action = AsyncMock()
    get_file = AsyncMock(return_value=FakeFile())


class FakeContext:
    bot = FakeBot()
    chat_data = {"mode": "explain"}


@pytest.mark.asyncio
async def test_photo_uses_explain_mode_prompt():
    with patch(
        "handlers.messages.analyze_image",
        new=AsyncMock(return_value="This diagram shows a process."),
    ) as analyze:
        await handle_photo(FakeUpdate(), FakeContext())

    analyze.assert_awaited_once()
    assert analyze.await_args.args[1] == "Explain the diagram"