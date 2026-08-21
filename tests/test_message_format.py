from handlers.messages import format_telegram_message


def test_format_telegram_message_for_telegram():
    raw_text = "Hello there\n\nThis is a paragraph.\n- First item\n- Second item\n\nImportant:" 

    formatted = format_telegram_message(raw_text)

    assert "<b>Important:</b>" in formatted
    assert "First item" in formatted
    assert "Second item" in formatted
    assert "\n\n" in formatted
