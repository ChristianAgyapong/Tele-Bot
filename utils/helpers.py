"""
Formatting utilities shared across handlers.
"""

import html
import re

from config.settings import MAX_TELEGRAM_MESSAGE_LENGTH


def _normalize_math(text: str) -> str:
    replacements = {
        r"\\cdot": "*",
        r"\\times": "*",
        r"\\div": "/",
        r"\\leq": "<=",
        r"\\geq": ">=",
        r"\\neq": "!=",
        r"\\pm": "+/-",
        r"\\approx": "~",
        r"\\text": "",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"\\(?:frac|sqrt)\s*", "", text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\\([%#$&_])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def format_inline_text(text: str) -> str:
    """Escape text and apply lightweight Telegram HTML formatting."""
    text = re.sub(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)", lambda match: _normalize_math(next(group for group in match.groups() if group is not None)), text)
    text = re.sub(r"\\\[(.+?)\\\]", lambda match: _normalize_math(match.group(1)), text)
    text = _normalize_math(text)
    safe_text = html.escape(text, quote=False)
    safe_text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe_text)
    safe_text = re.sub(r"__(.+?)__", r"<b>\1</b>", safe_text)
    safe_text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", safe_text)
    safe_text = re.sub(r"_(.+?)_", r"<i>\1</i>", safe_text)
    safe_text = re.sub(r"`(.+?)`", r"<code>\1</code>", safe_text)
    return safe_text


def _table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _format_table(lines: list[str]) -> str:
    rows = [_table_row(line) for line in lines]
    if len(rows) < 2:
        return format_inline_text(lines[0])

    headers = rows[0]
    data_rows = rows[2:] if all(re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]) else rows[1:]
    formatted_rows = []

    for row in data_rows:
        if not any(row):
            continue
        values = row + [""] * max(0, len(headers) - len(row))
        title = format_inline_text(values[0])
        details = [
            f"<b>{format_inline_text(header)}:</b> {format_inline_text(value)}"
            for header, value in zip(headers[1:], values[1:])
            if value
        ]
        formatted_rows.append("\n".join([f"• {title}", *details]))

    return "\n\n".join(formatted_rows)


def format_telegram_message(text: str) -> str:
    """Convert AI output into a Telegram-friendly HTML layout."""
    if not text:
        return "I couldn't generate a response right now."

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = normalized.split("\n")
    formatted_parts = []
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not line or re.fullmatch(r"[-*_]{3,}", line):
            index += 1
            continue

        if line.startswith("|") and "|" in line[1:]:
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            formatted_parts.append(_format_table(table_lines))
            continue

        if re.match(r"^[-*•]\s+", line):
            bullet_lines = []
            while index < len(lines) and re.match(r"^\s*[-*•]\s+", lines[index]):
                bullet_line = lines[index].strip()
                bullet_lines.append(
                    f"• {format_inline_text(re.sub(r'^[-*•]\s+', '', bullet_line))}"
                )
                index += 1
            formatted_parts.append("\n".join(bullet_lines))
            continue

        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*$", line)
        if heading:
            formatted_parts.append(f"<b>{format_inline_text(heading.group(1))}</b>")
        elif re.match(r"^\d+[.)]\s+", line):
            numbered_lines = []
            while index < len(lines) and re.match(r"^\s*\d+[.)]\s+", lines[index]):
                numbered_lines.append(format_inline_text(lines[index].strip()))
                index += 1
            formatted_parts.append("\n".join(numbered_lines))
            continue
        elif line.endswith(":") and len(line) <= 80:
            formatted_parts.append(f"<b>{format_inline_text(line)}</b>")
        elif (
            not line.startswith(("**", "__"))
            and re.match(r"^[^:]{1,40}:\s+\S", line)
        ):
            label, content = line.split(":", 1)
            formatted_parts.append(
                f"<b>{format_inline_text(label.strip())}:</b>"
                f" {format_inline_text(content.strip())}"
            )
        elif (
            len(line) <= 40
            and index + 1 < len(lines)
            and re.match(r"^\s*\d+[.)]\s+", lines[index + 1])
        ):
            formatted_parts.append(f"<b>{format_inline_text(line)}</b>")
        else:
            paragraph_lines = [format_inline_text(line)]
            index += 1
            while index < len(lines):
                next_line = lines[index].strip()
                if (
                    not next_line
                    or re.fullmatch(r"[-*_]{3,}", next_line)
                    or next_line.startswith("|")
                    or re.match(r"^#{1,6}\s+", next_line)
                    or re.match(r"^[-*•]\s+", next_line)
                    or re.match(r"^\d+[.)]\s+", next_line)
                ):
                    break
                paragraph_lines.append(format_inline_text(next_line))
                index += 1
            formatted_parts.append("\n".join(paragraph_lines))
            continue
        index += 1

    return "\n\n".join(part for part in formatted_parts if part)


def split_message(text: str, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH):
    """Split long Telegram output by paragraph to preserve readability."""
    if len(text) <= max_length:
        return [text]

    paragraphs = re.split(r"\n\s*\n+", text.strip())
    chunks = []
    current = ""

    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_length:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            if len(paragraph) <= max_length:
                current = paragraph
            else:
                current = ""
                for part in re.findall(r".{1,%d}" % max_length, paragraph, re.S):
                    if part.strip():
                        chunks.append(part.strip())

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk]