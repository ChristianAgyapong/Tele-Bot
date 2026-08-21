import json
from unittest.mock import AsyncMock, patch

import pytest

from handlers.academics import (
    _parse_quiz,
    _quiz_is_on_topic,
    quiz_command,
    quiz_count,
    quiz_setup,
)


class FakeMessage:
    reply_text = AsyncMock()


class FakeUpdate:
    message = FakeMessage()
    effective_chat = type("Chat", (), {"id": 1})()


class FakeBot:
    send_chat_action = AsyncMock()
    send_message = AsyncMock()


class FakeContext:
    args = ["Photosynthesis"]
    bot = FakeBot()
    chat_data = {}


def test_parse_quiz_accepts_fenced_json_with_preface():
    question = {
        "question": "Which process uses chlorophyll?",
        "options": ["Photosynthesis", "Digestion", "Evaporation", "Rusting"],
        "correct": 0,
        "explanation": "Chlorophyll captures light for photosynthesis.",
    }
    response = "Here is your quiz:\n```json\n" + str([question]).replace("'", '"')
    response = response[:-1] + "," + ",".join(
        response[response.find("{"):response.find("}") + 1] for _ in range(4)
    ) + "]\n```"

    questions = _parse_quiz(response)

    assert len(questions) == 5
    assert questions[0]["question"] == question["question"]


def test_parse_quiz_normalizes_letter_answer():
    questions = [
        {
            "question": "Which is correct?",
            "options": ["A", "B", "C", "D"],
            "answer": "C",
            "explanation": "C is correct.",
        }
    ] * 5

    parsed = _parse_quiz(json.dumps(questions))

    assert parsed[0]["correct"] == 2


def test_quiz_topic_guard_rejects_unrelated_math_questions_for_stacks():
    questions = [
        {
            "question": "What is the derivative of x squared?",
            "options": ["2x", "x", "x squared", "1"],
            "correct": 0,
            "explanation": "The power rule gives 2x.",
        }
    ] * 5

    assert not _quiz_is_on_topic(questions, "stacks and queue")


class FakeCallbackQuery:
    def __init__(self, data):
        self.data = data
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()


class CallbackUpdate:
    def __init__(self, data):
        self.callback_query = FakeCallbackQuery(data)
        self.effective_chat = type("Chat", (), {"id": 1})()


@pytest.mark.asyncio
async def test_quiz_setup_stores_difficulty_and_shows_count_options():
    context = type("Context", (), {"chat_data": {}})()

    await quiz_setup(CallbackUpdate("quizsetup:hard"), context)

    assert context.chat_data["quiz_setup"] == {
        "difficulty": "hard",
        "question_count": 5,
    }


@pytest.mark.asyncio
async def test_quiz_count_stores_selected_question_count():
    bot = type("Bot", (), {"send_message": AsyncMock()})()
    context = type(
        "Context",
        (),
        {"chat_data": {"quiz_setup": {"difficulty": "easy"}}, "bot": bot},
    )()

    await quiz_count(CallbackUpdate("quizcount:15"), context)

    assert context.chat_data["quiz_setup"]["question_count"] == 15
    assert context.chat_data["mode"] == "quiz"


@pytest.mark.asyncio
async def test_quiz_command_sends_clickable_questions():
    response = (
        '[{"question":"What is chlorophyll?",'
        '"options":["A pigment","A sugar","A mineral","A gas"],'
        '"correct":0,"explanation":"Chlorophyll captures light energy."},'
        '{"question":"Where is it found?",'
        '"options":["Leaves","Roots","Rocks","Clouds"],"correct":0,'
        '"explanation":"It is mainly found in plant leaves."},'
        '{"question":"What does it absorb?",'
        '"options":["Light","Sound","Heat","Water"],"correct":0,'
        '"explanation":"It absorbs light energy."},'
        '{"question":"What process uses it?",'
        '"options":["Photosynthesis","Digestion","Evaporation","Rusting"],'
        '"correct":0,"explanation":"It supports photosynthesis."},'
        '{"question":"What color is it?",'
        '"options":["Green","Red","Blue","Black"],"correct":0,'
        '"explanation":"Chlorophyll is green."}]'
    )

    with patch(
        "handlers.academics.generate_response",
        new=AsyncMock(return_value=response),
    ) as generate_response:
        await quiz_command(FakeUpdate(), FakeContext())

    generate_response.assert_awaited_once()
    assert generate_response.await_args.kwargs["max_tokens"] >= 2000
    prompt = generate_response.await_args.args[0]
    assert "infer the primary academic domain" in prompt.lower()
    assert "application, reasoning, comparison" in prompt
    assert "plausible and based on common mistakes" in prompt
    assert "Photosynthesis" in prompt
    assert FakeUpdate.message.reply_text.await_count == 1
    assert FakeContext.bot.send_message.await_count == 1
    keyboard = FakeContext.bot.send_message.await_args.kwargs["reply_markup"]
    assert len(keyboard.inline_keyboard) == 4
    assert keyboard.inline_keyboard[0][0].callback_data == "quiz:0:0"