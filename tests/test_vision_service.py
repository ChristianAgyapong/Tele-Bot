from unittest.mock import AsyncMock, patch

import pytest

from services.vision_service import analyze_image


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
    image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")
    assert payload["messages"][0]["content"][0]["text"] == "What does this show?"