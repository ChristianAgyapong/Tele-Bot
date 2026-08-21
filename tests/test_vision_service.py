from unittest.mock import AsyncMock, patch

import pytest

from services.vision_service import (
    VISION_NOT_CONFIGURED_MESSAGE,
    analyze_image,
)


@pytest.mark.asyncio
async def test_analyze_image_explains_missing_openrouter_configuration():
    with patch("services.vision_service.OPENROUTER_API_KEY", ""):
        result = await analyze_image(b"image-bytes")

    assert result == VISION_NOT_CONFIGURED_MESSAGE


@pytest.mark.asyncio
async def test_analyze_image_sends_base64_image_to_openrouter():
    response = type(
        "Response",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": "Image analyzed"}}]},
        },
    )()
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return None

        post = AsyncMock(return_value=response)

    client = FakeClient()

    with patch("services.vision_service.OPENROUTER_API_KEY", "test-key"), patch(
        "services.vision_service.httpx.AsyncClient", return_value=client
    ):
        result = await analyze_image(b"image-bytes", "What does this show?")

    assert result == "Image analyzed"
    payload = client.post.await_args.kwargs["json"]
    assert payload["messages"][0]["role"] == "system"
    assert "identify the task" in payload["messages"][0]["content"]
    user_content = payload["messages"][1]["content"]
    image_url = user_content[1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")
    assert user_content[0]["text"].startswith(
        "User request: What does this show?"
    )
    assert payload["model"] == "google/gemini-2.5-flash"