import json
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from config.settings import QUIZ_DIFFICULTY, QUIZ_MAX_TOKENS, QUIZ_TEMPERATURE, logger
from services.ai_service import generate_response
from handlers.messages import send_ai_reply
from handlers.start import MAIN_KEYBOARD
from utils.helpers import split_message

DEFAULT_QUIZ_QUESTIONS = 5
QUIZ_KEY = "active_quiz"
STOP_WORDS = {"a", "an", "the", "in", "on", "of", "for", "and", "or", "to", "with", "is", "about", "quiz", "test", "questions", "me", "how", "what", "why"}
DOMAIN_TERMS = {
    "stack": {"stack", "lifo", "push", "pop", "top"},
    "stacks": {"stack", "lifo", "push", "pop", "top"},
    "queue": {"queue", "fifo", "enqueue", "dequeue", "front"},
    "queues": {"queue", "fifo", "enqueue", "dequeue", "front"},
}


def _quiz_is_on_topic(questions: list[dict], topic: str) -> bool:
    requested_terms = set(re.findall(r"[a-z0-9]+", topic.lower()))
    required_terms = set().union(
        *(DOMAIN_TERMS.get(term, set()) for term in requested_terms)
    )
    
    quiz_text = " ".join(
        question["question"]
        + " "
        + " ".join(question["options"])
        + " "
        + question["explanation"]
        for question in questions
    ).lower()

    if required_terms:
        return any(term in quiz_text for term in required_terms)

    # General domain keyword check against non-stopwords
    key_words = [w for w in requested_terms if w not in STOP_WORDS and len(w) > 2]
    if not key_words:
        return True

    return any(word in quiz_text for word in key_words)


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
    difficulty_guide = {
        "easy": "Focus on foundational concepts, core definitions in context, and direct single-step applications.",
        "medium": "Focus on realistic scenario analysis, cause-and-effect reasoning, and common conceptual pitfalls.",
        "hard": "Focus on complex multi-step reasoning, quantitative/code analysis, edge cases, and comparative evaluation."
    }.get(difficulty.lower(), "Focus on deep domain understanding and practical application.")

    prompt = (
        "You are an expert assessment designer and domain specialist.\n\n"
        f"STRICT DOMAIN LOCK: {topic}\n"
        "100% of every question, option, and explanation MUST strictly stay locked within this academic domain. "
        "Do NOT introduce generic questions, tangential subjects, or unrelated fluff.\n\n"
        f"DIFFICULTY LEVEL ({difficulty.upper()}): {difficulty_guide}\n\n"
        f"Create exactly {question_count} questions ordered in logical conceptual progression "
        "(starting from fundamental domain concepts and advancing to application and analytical reasoning). "
        "Apply Bloom's Taxonomy (Application, Analysis, Evaluation). "
        "Make distractors highly plausible based on authentic student misconceptions within this domain. "
        "Avoid trick wording, generic recall, or ambiguous choices.\n\n"
        "Return ONLY valid JSON with no Markdown. Shape format:\n"
        '{"questions":[{"question":"...","options":["...","...","...","..."],'
        '"correct":0,"explanation":"..."}]}. '
        "Keep each question concise (under 180 characters) and each explanation insightful and educational (150 to 250 characters) "
        "clearly explaining the underlying concept, why the correct option is right, and clearing potential misconceptions."
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
        # A query can only be answered once — don't call query.answer() before this.
        await query.answer("That question has already been answered.", show_alert=True)
        return

    await query.answer()
    question = quiz["questions"][quiz["index"]]
    selected = int(answer_index)
    correct = selected == question["correct"]
    if correct:
        quiz["score"] += 1

    # Record the displayed question number before advancing the index.
    q_num = quiz["index"] + 1
    total = len(quiz["questions"])
    quiz["index"] += 1
    is_last = quiz["index"] == total

    # Format choices
    selected_label = "ABCD"[selected]
    selected_option = question["options"][selected].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    correct_label = "ABCD"[question["correct"]]
    correct_option = question["options"][question["correct"]].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    safe_q = (
        question["question"]
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    explanation = (
        question["explanation"]
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )

    if correct:
        answer_block = (
            f"<b>Your Choice:</b> {selected_label}. {selected_option} ✅\n\n"
            f"💡 <b>Key Insight & Explanation:</b>\n{explanation}"
        )
    else:
        answer_block = (
            f"<b>Your Choice:</b> {selected_label}. {selected_option} ❌\n"
            f"<b>Correct Answer:</b> {correct_label}. {correct_option} ✅\n\n"
            f"💡 <b>Explanation:</b>\n{explanation}"
        )

    # Choose the action button: advance to next question or reveal final score.
    if is_last:
        next_button = InlineKeyboardButton(
            "🏁 See Final Score", callback_data="quiznext:done"
        )
    else:
        next_button = InlineKeyboardButton(
            f"▶️ Next Question ({quiz['index'] + 1}/{total})",
            callback_data=f"quiznext:{quiz['index']}",
        )

    # Edit the same message in-place: show the question + choice breakdown + explanation.
    await query.edit_message_text(
        f"<b>Question {q_num} of {total}</b>\n"
        f"{safe_q}\n\n"
        f"{answer_block}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[next_button]]),
    )


async def quiz_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit the current message to show the next question, or the final score."""
    query = update.callback_query
    await query.answer()
    quiz = context.chat_data.get(QUIZ_KEY)
    if not quiz:
        await query.edit_message_text("This quiz has expired. Choose Quiz to start a new one.")
        return

    _, action = query.data.split(":", 1)

    if action == "done" or quiz["index"] >= len(quiz["questions"]):
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

        # Build full summary of all questions with correct answers
        summary_parts = [
            f"🏁 <b>Quiz Complete!</b>\n"
            f"Score: <b>{score}/{total}</b> ({int(pct * 100)}%) — {grade}\n\n"
            f"📋 <b>Answer Key & Review:</b>\n"
        ]

        for i, q in enumerate(quiz["questions"], start=1):
            safe_q = (
                q["question"]
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            c_idx = q["correct"]
            c_label = "ABCD"[c_idx]
            c_option = (
                q["options"][c_idx]
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            summary_parts.append(
                f"<b>{i}. {safe_q}</b>\n"
                f"   ✅ <b>Answer:</b> {c_label}. {c_option}\n"
            )

        full_text = "\n".join(summary_parts)
        context.chat_data.pop(QUIZ_KEY, None)

        chunks = split_message(full_text, max_length=3800)
        await query.edit_message_text(
            chunks[0],
            parse_mode=ParseMode.HTML,
        )
        for chunk in chunks[1:]:
            await query.message.reply_text(
                chunk,
                parse_mode=ParseMode.HTML,
            )

        # Restore reply keyboard options
        await query.message.reply_text(
            "Ready for another quiz or want to chat? Use the buttons below.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    # Edit the same message to display the next question.
    question = quiz["questions"][quiz["index"]]
    safe_q = (
        question["question"]
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    buttons = [
        [
            InlineKeyboardButton(
                f"{label}. {option}",
                callback_data=f"quiz:{quiz['index']}:{idx}",
            )
        ]
        for idx, (label, option) in enumerate(zip("ABCD", question["options"]))
    ]
    await query.edit_message_text(
        f"<b>Question {quiz['index'] + 1} of {len(quiz['questions'])}</b>\n\n"
        f"{safe_q}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


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
        f"Act as an expert academic tutor and explain the following topic in depth: {topic}.\n\n"
        "Structure your response as follows:\n"
        "1. 🎯 <b>The Core Idea</b>: A simple, intuitive explanation (Feynman technique).\n"
        "2. 💡 <b>Analogy</b>: A relatable real-world comparison using everyday concepts.\n"
        "3. ⚙️ <b>How it Works</b>: Clear breakdown of the key concepts or steps.\n"
        "4. 📝 <b>Example</b>: An easy-to-follow, practical example using plain, familiar words rather than dense technical jargon.\n"
        "5. 🌍 <b>Why it Matters</b>: The broader real-world significance of the topic.\n\n"
        "Keep it highly engaging, accessible, patient, and formatted cleanly for Telegram."
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