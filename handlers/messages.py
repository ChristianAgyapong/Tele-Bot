import asyncio
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from config.settings import MAX_HISTORY_MESSAGES, MAX_USER_MESSAGE_LENGTH, logger
from services.ai_service import FALLBACK_MESSAGE, generate_response
from services.vision_service import VISION_FALLBACK_MESSAGE, analyze_image
from utils.helpers import format_telegram_message, split_message
from handlers.start import MAIN_KEYBOARD, keyboard_for_mode

CONVERSATION_KEY = "conversation"
MODE_KEY = "mode"
QUIZ_SETUP_KEY = "quiz_setup"
SOCIAL_REPLIES = {
    "thanks": "You're welcome! I'm here whenever you need help.",
    "thank you": "You're welcome! Happy to help.",
    "thank you so much": "You're very welcome!",
    "thx": "You're welcome!",
    "ty": "You're welcome!",
    "great": "Glad that helped! What would you like to explore next?",
    "awesome": "Awesome! Let me know if you want to break down another topic.",
    "nice": "Glad it was clear! Feel free to ask whenever you have more questions.",
    "cool": "Glad that made sense!",
    "perfect": "Perfect! Ready whenever you want to work on the next topic.",
    "got it": "Great! Let me know whenever you're ready for the next topic.",
    "makes sense": "Glad it made sense! Ask away if you have any follow-ups.",
    "ok": "Got it! What shall we work on next?",
    "okay": "Got it! What shall we work on next?",
    "alright": "Alright! Let me know what you'd like to look at next.",
    "good": "Glad that helped!",
}


async def _keep_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    try:
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        return


async def select_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mode = update.message.text.strip().lower().replace("● ", "")
    context.chat_data[MODE_KEY] = mode

    # Clear any stale quiz setup whenever the user switches modes.
    # Without this, switching to Chat/Explain while quiz_setup exists still
    # routes the next message into create_quiz.
    if mode != "quiz":
        context.chat_data.pop(QUIZ_SETUP_KEY, None)

    if mode == "chat":
        await update.message.reply_text(
            "💬 Chat mode — ask me anything!",
            reply_markup=keyboard_for_mode("chat"),
        )
    elif mode == "explain":
        await update.message.reply_text(
            "📖 Explain mode — send me any topic and I'll break it down clearly.",
            reply_markup=keyboard_for_mode("explain"),
        )
    else:
        # Quiz mode — show the active keyboard first, then the difficulty picker.
        await update.message.reply_text(
            "🧠 Quiz mode — choose a difficulty to get started.",
            reply_markup=keyboard_for_mode("quiz"),
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🟢 Easy", callback_data="quizsetup:easy"),
                    InlineKeyboardButton("🟡 Medium", callback_data="quizsetup:medium"),
                    InlineKeyboardButton("🔴 Hard", callback_data="quizsetup:hard"),
                ]
            ]
        )
        await update.message.reply_text(
            "Select a difficulty level:", reply_markup=keyboard
        )


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
    clean_social = re.sub(r"[^\w\s]", "", message_text.casefold()).strip()
    social_reply = SOCIAL_REPLIES.get(clean_social) or SOCIAL_REPLIES.get(message_text.casefold())
    if social_reply:
        mode = context.chat_data.get(MODE_KEY, "chat")
        await update.message.reply_text(social_reply, reply_markup=keyboard_for_mode(mode))
        return

    mode = context.chat_data.get(MODE_KEY, "chat")
    if mode == "quiz":
        if QUIZ_SETUP_KEY not in context.chat_data:
            await update.message.reply_text(
                "⚙️ Please choose a difficulty and question count first.",
                reply_markup=keyboard_for_mode("quiz"),
            )
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
            "Explain this topic like an expert tutor. Break it down using the Feynman technique. "
            "Start with the core intuition, give a relatable everyday analogy, provide clear steps, "
            "and finish with an easy-to-follow practical example grounded in authentic Ghana-based context. "
            "Draw naturally from: local names (Kwame, Ama, Kofi, Abena, Akosua, Yaw, Adjoa, Kojo), "
            "MoMo transactions, susu savings, waakye/kenkey sellers, trotro/taxi journeys, chop bars, "
            "Makola/Kejetia markets, BECE or WASSCE prep, KNUST/Legon/UCC campus life, MTN/AirtelTigo data bundles, "
            "cocoa farming, NHIS, Black Stars matches, cities like Accra/Kumasi/Tamale. "
            "Pick whichever fits most naturally for the topic. "
            "Avoid static clichés like 'Think of it as...'. Topic: " + message_text
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
        if QUIZ_SETUP_KEY not in context.chat_data:
            await update.message.reply_text(
                "⚙️ Please choose a difficulty and question count first.",
                reply_markup=keyboard_for_mode("quiz"),
            )
            return
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
        typing_task = asyncio.create_task(
            _keep_typing(context, update.effective_chat.id)
        )
        photo_file = await context.bot.get_file(update.message.photo[-1].file_id)
        image_bytes = await photo_file.download_as_bytearray()
        response = await analyze_image(bytes(image_bytes), image_prompt)
        if mode == "quiz":
            if response == VISION_FALLBACK_MESSAGE:
                await update.message.reply_text(response, reply_markup=keyboard_for_mode("quiz"))
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

        # Store image analysis in conversation memory so follow-up user messages can refer back to it
        if response != VISION_FALLBACK_MESSAGE:
            history = list(context.chat_data.get(CONVERSATION_KEY, []))
            user_entry = f"[User sent an image] {caption}" if caption else "[User sent an image]"
            updated_history = history + [
                {"role": "user", "content": user_entry},
                {"role": "assistant", "content": response},
            ]
            context.chat_data[CONVERSATION_KEY] = updated_history[-MAX_HISTORY_MESSAGES:]

        for chunk in split_message(format_telegram_message(response)):
            await update.message.reply_text(
                chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=keyboard_for_mode(mode),
            )
    except Exception:
        logger.exception("Failed to analyze image for chat %s", update.effective_chat.id)
        await update.message.reply_text(
            "I couldn't analyze that image right now. Please try again.",
            reply_markup=keyboard_for_mode(mode),
        )
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass