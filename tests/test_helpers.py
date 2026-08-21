from utils.helpers import format_telegram_message, split_message


def test_format_telegram_message_escapes_html_and_formats_inline_markup():
    formatted = format_telegram_message("**Key**: <unsafe>\n`x = 1`")

    assert "<b>Key</b>: &lt;unsafe&gt;" in formatted
    assert "<code>x = 1</code>" in formatted


def test_split_message_preserves_paragraphs_and_length_limit():
    chunks = split_message("First paragraph.\n\nSecond paragraph.", max_length=18)

    assert chunks == ["First paragraph.", "Second paragraph."]
    assert all(len(chunk) <= 18 for chunk in chunks)


def test_split_message_splits_a_single_long_paragraph():
    chunks = split_message("abcdefghijklmnopqrst", max_length=7)

    assert chunks == ["abcdefg", "hijklmn", "opqrst"]


def test_format_telegram_message_converts_markdown_headings_and_tables():
    raw_text = (
        "## Learning types\n\n"
        "| Concept | What it is | Why it matters |\n"
        "|---|---|---|\n"
        "| Supervised learning | Learns from labels. | Useful for prediction. |"
    )

    formatted = format_telegram_message(raw_text)

    assert "<b>Learning types</b>" in formatted
    assert "• Supervised learning" in formatted
    assert "<b>What it is:</b> Learns from labels." in formatted
    assert "|---|---|---|" not in formatted


def test_format_telegram_message_removes_rules_and_formats_lists():
    formatted = format_telegram_message("---\n### Prerequisites\n- Python\n- Statistics")

    assert "---" not in formatted
    assert "<b>Prerequisites</b>" in formatted
    assert "• Python" in formatted
    assert "• Statistics" in formatted
    assert "• Python\n• Statistics" in formatted