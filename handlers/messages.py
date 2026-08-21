from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from config.settings import MAX_HISTORY_MESSAGES, MAX_USER_MESSAGE_LENGTH, logger
from services.ai_service import FALLBACK_MESSAGE, generate_response
from services.vision_service import VISION_FALLBACK_MESSAGE, analyze_image
from utils.helpers import format_telegram_message, split_message
from handlers.start import MAIN_KEYBOARD

CONVERSATION_KEY = "conversation"
MODE_KEY = "mode"
QUIZ_SETUP_KEY = "quiz_setup"
SOCIAL_REPLIES = {
    "thanks": "You're welcome. I'm here whenever you need help.",
    "thank you": "You're welcome. I'm here whenever you need help.",
    "thank you so much": "You're very welcome.",
    "thx": "You're welcome.",
    "ty": "You're welcome.",
}


async def select_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mode = update.message.text.strip().lower()
    context.chat_data[MODE_KEY] = mode

    if mode == "chat":
        message = "Chat mode selected. Send me any question."
    elif mode == "explain":
        message = "Explain mode selected. Send me a topic and I'll teach it clearly."
    else:
        message = "Choose a difficulty and number of questions first."

    if mode == "quiz":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Easy", callback_data="quizsetup:easy"),
                    InlineKeyboardButton("Medium", callback_data="quizsetup:medium"),
                    InlineKeyboardButton("Hard", callback_data="quizsetup:hard"),
                ]
            ]
        )
        await update.message.reply_text(message, reply_markup=keyboard)
        return

    await update.message.reply_text(message, reply_markup=MAIN_KEYBOARD)


async def send_ai_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    remember: bool = False,
) -> None:
    """
    Generate an AI response for `prompt` and send it back to the chat,
    formatted and chunked. Shared by the plain message handler and the
    /quiz and /explain commands so they don't duplicate this logic.
    """
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        history = list(context.chat_data.get(CONVERSATION_KEY, [])) if remember else []
        response = await generate_response(prompt, history=history)

        if remember and response != FALLBACK_MESSAGE:
            updated_history = history + [
                {"role": "user", "content": prompt.strip()},
                {"role": "assistant", "content": response},
            ]
            context.chat_data[CONVERSATION_KEY] = updated_history[
                -MAX_HISTORY_MESSAGES:
            ]
        formatted_response = format_telegram_message(response)
        chunks = split_message(formatted_response)

        for chunk in chunks:
            await update.message.reply_text(
                chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    except Exception:
        logger.exception("Failed to handle AI request for chat %s", chat_id)
        await update.message.reply_text(
            "Something went wrong on my end. Please try again in a moment."
        )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return

    message_text = update.message.text.strip()
    social_reply = SOCIAL_REPLIES.get(message_text.casefold())
    if social_reply:
        await update.message.reply_text(social_reply, reply_markup=MAIN_KEYBOARD)
        return

    mode = context.chat_data.get(MODE_KEY, "chat")
    if mode == "quiz" and QUIZ_SETUP_KEY not in context.chat_data:
        await update.message.reply_text(
            "Choose Quiz, difficulty, and question count before sending an image.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    if mode == "quiz":
        if QUIZ_SETUP_KEY not in context.chat_data:
            await update.message.reply_text("Choose a quiz difficulty first.")
            return
        from handlers.academics import create_quiz

        quiz_setup = context.chat_data[QUIZ_SETUP_KEY]
        await create_quiz(
            update,
            context,
            message_text,
            difficulty=quiz_setup["difficulty"],
            question_count=quiz_setup["question_count"],
        )
        return

    if len(message_text) > MAX_USER_MESSAGE_LENGTH:
        await update.message.reply_text(
            f"Please keep your message under {MAX_USER_MESSAGE_LENGTH} characters "
            "so I can process it reliably."
        )
        return

    if mode == "explain":
        message_text = (
            "Explain this topic like a patient teacher. Start with the key idea, "
            "then give an analogy, steps, and one example: " + message_text
        )

    await send_ai_reply(update, context, message_text, remember=True)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return

    mode = context.chat_data.get(MODE_KEY, "chat")
    caption = (update.message.caption or "").strip()
    if mode == "explain":
        image_prompt = (
            caption
            or "Explain the important concepts in this image like a patient teacher."
        )
    elif mode == "quiz":
        image_prompt = (
            "Identify the exact academic topic and important concepts shown in this "
            "image. Return a concise study description that can be used to create "
            "a domain-specific quiz. Do not solve or discuss unrelated topics. "
            + (f"User focus: {caption}" if caption else "")
        )
    else:
        image_prompt = (
            caption
            or "Analyze this image and answer or explain what is important in it."
        )
    if len(caption) > MAX_USER_MESSAGE_LENGTH:
        await update.message.reply_text(
            f"Please keep the image question under {MAX_USER_MESSAGE_LENGTH} characters."
        )
        return

    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        photo_file = await context.bot.get_file(update.message.photo[-1].file_id)
        image_bytes = await photo_file.download_as_bytearray()
        response = await analyze_image(bytes(image_bytes), image_prompt)
        if mode == "quiz":
            if response == VISION_FALLBACK_MESSAGE:
                await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)
                return
            from handlers.academics import create_quiz

            quiz_setup = context.chat_data[QUIZ_SETUP_KEY]
            await create_quiz(
                update,
                context,
                response,
                difficulty=quiz_setup["difficulty"],
                question_count=quiz_setup["question_count"],
            )
            return
        for chunk in split_message(format_telegram_message(response)):
            await update.message.reply_text(
                chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=MAIN_KEYBOARD,
            )
    except Exception:
        logger.exception("Failed to analyze image for chat %s", update.effective_chat.id)
        await update.message.reply_text(
            "I couldn't analyze that image right now. Please try again.",
            reply_markup=MAIN_KEYBOARD,
        )