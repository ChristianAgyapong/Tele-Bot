import json
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from config.settings import QUIZ_DIFFICULTY, QUIZ_MAX_TOKENS, QUIZ_TEMPERATURE, logger
from services.ai_service import generate_response
from handlers.messages import send_ai_reply
from handlers.start import MAIN_KEYBOARD

DEFAULT_QUIZ_QUESTIONS = 5
QUIZ_KEY = "active_quiz"
DOMAIN_TERMS = {
    "stack": {"stack", "lifo", "push", "pop", "top"},
    "stacks": {"stack", "lifo", "push", "pop", "top"},
    "queue": {"queue", "fifo", "enqueue", "dequeue", "front"},
    "queues": {"queue", "fifo", "enqueue", "dequeue", "front"},
}


def _quiz_is_on_topic(questions: list[dict], topic: str) -> bool:
    requested_terms = set(re.findall(r"[a-z]+", topic.lower()))
    required_terms = set().union(
        *(DOMAIN_TERMS.get(term, set()) for term in requested_terms)
    )
    if not required_terms:
        return True

    quiz_text = " ".join(
        question["question"]
        + " "
        + " ".join(question["options"])
        + " "
        + question["explanation"]
        for question in questions
    ).lower()
    return any(term in quiz_text for term in required_terms)


def _parse_quiz(response: str, question_count: int = DEFAULT_QUIZ_QUESTIONS) -> list[dict]:
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Quiz response was empty")

    cleaned = re.sub(r"```(?:json)?", "", response, flags=re.IGNORECASE).replace("```", "")
    start = cleaned.find("[")
    if start == -1:
        object_start = cleaned.find("{")
        if object_start != -1:
            try:
                payload, _ = json.JSONDecoder().raw_decode(cleaned[object_start:])
                questions = payload.get("questions") if isinstance(payload, dict) else None
            except json.JSONDecodeError as error:
                raise ValueError("Quiz response contained invalid JSON") from error
        else:
            raise ValueError("Quiz response did not contain quiz JSON")
    else:
        try:
            questions, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        except json.JSONDecodeError as error:
            raise ValueError("Quiz response contained invalid JSON") from error

    if not isinstance(questions, list) or len(questions) != question_count:
        raise ValueError(f"Quiz must contain exactly {question_count} questions")

    normalized_questions = []
    for question in questions:
        if isinstance(question, dict):
            answer = question.get("correct", question.get("answer"))
            if isinstance(answer, str):
                answer = answer.strip().upper().rstrip(".")
                if answer in "ABCD":
                    question["correct"] = "ABCD".index(answer)
                elif answer.isdigit():
                    question["correct"] = int(answer)
            elif isinstance(answer, int):
                question["correct"] = answer

        if (
            not isinstance(question, dict)
            or not isinstance(question.get("question"), str)
            or not question["question"].strip()
            or not isinstance(question.get("options"), list)
            or len(question["options"]) != 4
            or not all(
                isinstance(option, str) and option.strip()
                for option in question["options"]
            )
            or not isinstance(question.get("correct"), int)
            or not 0 <= question["correct"] < 4
            or not isinstance(question.get("explanation"), str)
            or not question["explanation"].strip()
        ):
            raise ValueError("Invalid quiz question format")
        normalized_questions.append(question)
    return normalized_questions


async def _send_quiz_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quiz = context.chat_data[QUIZ_KEY]
    question = quiz["questions"][quiz["index"]]
    buttons = [
        [InlineKeyboardButton(f"{label}. {option}", callback_data=f"quiz:{quiz['index']}:{index}")]
        for index, (label, option) in enumerate(zip("ABCD", question["options"]))
    ]
    # Escape AI-generated text before inserting into HTML parse_mode message.
    # Questions from the model can contain <, >, & (e.g. x < y, a > b, &c.)
    # which cause Telegram to throw BadRequest: Can't parse entities.
    safe_question = (
        question["question"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"<b>Question {quiz['index'] + 1} of {len(quiz['questions'])}</b>\n\n"
            f"{safe_question}"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def create_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    topic: str,
    difficulty: str = QUIZ_DIFFICULTY,
    question_count: int = DEFAULT_QUIZ_QUESTIONS,
):
    if not topic:
        await update.message.reply_text("Send a topic for the quiz, for example: Biology")
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    prompt = (
        "You are an expert assessment designer. Read the user's entire quiz request "
        "as context, not just as a keyword. Infer the primary academic domain, the "
        "specific subtopics, and the likely level from the wording. If the request "
        "is a sentence or describes something being studied, build the quiz around "
        "the concepts and relationships in that description. Do not ask for more "
        "details before creating the quiz.\n\n"
        f"Topic lock: {topic}\n"
        "Every question, option, and explanation must stay inside this topic lock. "
        "Do not switch to a related subject or use generic mathematics questions "
        "unless the topic lock explicitly asks for mathematics.\n"
        f"Create exactly {question_count} {difficulty} multiple-choice "
        "questions that test understanding of that inferred domain. Avoid generic "
        "definitions, obvious recall, unrelated foundation questions, and trick "
        "wording. Make the questions domain-specific and useful for learning. Mix "
        "application, reasoning, comparison, prediction, and misconception-checking. "
        "Use realistic examples, calculations, code, evidence, or scenarios when "
        "appropriate for the domain. Make distractors plausible and based on common "
        "mistakes, not random nonsense. Cover different important subtopics and do "
        "not repeat the same idea.\n\n"
        "Return ONLY valid JSON, with no Markdown or extra text. Use this exact shape: "
        '{"questions":[{"question":"...","options":["...","...","...","..."],'
        '"correct":0,"explanation":"..."}]}. The correct value is the zero-based '
        "index of the correct option. Each explanation must briefly explain the "
        "reasoning and why the correct option fits the domain. Keep each question "
        "and explanation concise so the complete JSON response fits in one answer. "
        "Keep each question under 160 characters and each explanation under 120 characters."
    )

    try:
        response = await generate_response(
            prompt,
            max_tokens=QUIZ_MAX_TOKENS,
            temperature=QUIZ_TEMPERATURE,
        )
        try:
            questions = _parse_quiz(response, question_count)
            if not _quiz_is_on_topic(questions, topic):
                raise ValueError("Quiz output was not sufficiently related to the topic")
        except ValueError:
            retry_prompt = (
                "Create a corrected quiz that strictly stays on the requested topic. "
                "Return only an object with a questions array containing exactly "
                f"{question_count} questions, each with question, four options, "
                "correct (0-3), and explanation. Every item must test the topic lock, "
                "not a neighboring subject. Return no Markdown.\n\n"
                f"Topic lock: {topic}\nAttempted quiz:\n" + response
            )
            response = await generate_response(
                retry_prompt,
                max_tokens=QUIZ_MAX_TOKENS,
                temperature=QUIZ_TEMPERATURE,
            )
            questions = _parse_quiz(response, question_count)
            if not _quiz_is_on_topic(questions, topic):
                raise ValueError("Corrected quiz was not sufficiently related to the topic")
        context.chat_data[QUIZ_KEY] = {"questions": questions, "index": 0, "score": 0}
        await update.message.reply_text(
            "Your quiz is ready. Choose an answer below:",
            reply_markup=MAIN_KEYBOARD,
        )
        await _send_quiz_question(update, context)
    except Exception:
        logger.exception("Failed to create quiz for chat %s", update.effective_chat.id)
        await update.message.reply_text(
            "I couldn't create that quiz right now. Please try another topic.",
            reply_markup=MAIN_KEYBOARD,
        )


async def quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    quiz = context.chat_data.get(QUIZ_KEY)
    if not quiz:
        await query.answer()
        await query.edit_message_text("This quiz has expired. Choose Quiz to start a new one.")
        return

    _, question_index, answer_index = query.data.split(":")
    if int(question_index) != quiz["index"]:
        # Answer the query with an alert — do NOT call query.answer() before
        # this point, because a query can only be answered once.
        await query.answer("That question has already been answered.", show_alert=True)
        return

    # Acknowledge the button tap now that we know it's valid.
    await query.answer()
    question = quiz["questions"][quiz["index"]]
    selected = int(answer_index)
    correct = selected == question["correct"]
    if correct:
        quiz["score"] += 1

    correct_text = question["options"][question["correct"]]
    if correct:
        result_line = "✅ <b>Correct!</b>"
    else:
        escaped = correct_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        result_line = f"❌ Not quite — the answer was <b>{escaped}</b>"

    explanation = (
        question["explanation"]
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    await query.edit_message_text(
        f"{result_line}\n\n{explanation}",
        parse_mode=ParseMode.HTML,
    )
    quiz["index"] += 1

    if quiz["index"] == len(quiz["questions"]):
        total = len(quiz["questions"])
        score = quiz["score"]
        pct = score / total
        if pct == 1.0:
            grade = "🏆 Perfect score!"
        elif pct >= 0.8:
            grade = "🌟 Great job!"
        elif pct >= 0.6:
            grade = "👍 Good effort!"
        else:
            grade = "💪 Keep practising!"
        await query.message.reply_text(
            f"🏁 Quiz complete!\nScore: <b>{score}/{total}</b> {grade}",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
        context.chat_data.pop(QUIZ_KEY, None)
        return

    await _send_quiz_question(update, context)


async def quiz_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, difficulty = query.data.split(":", 1)
    context.chat_data["quiz_setup"] = {"difficulty": difficulty, "question_count": 5}
    emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(difficulty, "🧠")
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("5 questions", callback_data="quizcount:5"),
                InlineKeyboardButton("10 questions", callback_data="quizcount:10"),
                InlineKeyboardButton("15 questions", callback_data="quizcount:15"),
            ]
        ]
    )
    await query.edit_message_text(
        f"{emoji} Difficulty: <b>{difficulty.title()}</b>\nNow choose the number of questions:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def quiz_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    question_count = int(query.data.split(":", 1)[1])
    setup = context.chat_data.setdefault("quiz_setup", {"difficulty": QUIZ_DIFFICULTY})
    setup["question_count"] = question_count
    context.chat_data["mode"] = "quiz"
    await query.edit_message_text(
        f"Ready for a {setup['difficulty'].title()} {question_count}-question quiz. "
        "Send me the topic or a full study description."
    )


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() if context.args else ""

    if not topic:
        await update.message.reply_text(
            "Tell me a topic to quiz you on, e.g.\n<code>/quiz Photosynthesis</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
        return

    await create_quiz(update, context, topic)


async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() if context.args else ""

    if not topic:
        await update.message.reply_text(
            "Tell me what you'd like explained, e.g.\n"
            "<code>/explain Newton's second law</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
        return

    prompt = (
        f"Explain the following topic in depth, like a patient teacher: {topic}. "
        "Include a simple analogy, a clear step-by-step breakdown if it applies, "
        "and one short worked example. Keep it well-structured with headings or "
        "numbered steps."
    )

    await send_ai_reply(update, context, prompt)


async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip() if context.args else ""

    if not text:
        await update.message.reply_text(
            "Paste the text you want summarized after the command, e.g.\n"
            "<code>/summarize [your text here]</code>\n\n"
            "Or switch to 💬 Chat mode and just paste the text with a message "
            "like \"Summarize this: ...\"",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
        return

    prompt = (
        "Summarize the following text concisely. "
        "Use clear bullet points for the key ideas. "
        "Keep the summary under 200 words and preserve all important facts, "
        "numbers, and conclusions. Do not add information not in the original text.\n\n"
        + text
    )

    await send_ai_reply(update, context, prompt)