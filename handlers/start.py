from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

def keyboard_for_mode(active_mode: str = "chat") -> ReplyKeyboardMarkup:
    labels = {
        mode: f"● {mode.title()}" if mode == active_mode else mode.title()
        for mode in ("chat", "explain", "quiz")
    }
    return ReplyKeyboardMarkup(
        [[
            KeyboardButton(labels["chat"]),
            KeyboardButton(labels["explain"]),
            KeyboardButton(labels["quiz"]),
        ]],
        resize_keyboard=True,
        is_persistent=True,
    )


MAIN_KEYBOARD = keyboard_for_mode()


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    await update.message.reply_text(
        f"👋 Hey {user.first_name}! I'm <b>ChrixHelp AI</b>, your personal study tutor.\n\n"
        "I can help you with:\n"
        "• 📝 Homework &amp; assignments\n"
        "• 💡 Explaining tricky concepts\n"
        "• 🧠 Quizzes on any topic\n"
        "• 🖼️ Analyzing images &amp; diagrams\n\n"
        "Use the buttons below to switch modes, or type /help for all commands.",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "<b>📚 ChrixHelp AI Commands</b>\n\n"
        "<b>General</b>\n"
        "/start — Welcome message\n"
        "/help — Show this help\n"
        "/clear — Reset memory &amp; active quiz\n\n"
        "<b>Learning</b>\n"
        "/quiz [topic] — Generate a multiple-choice quiz\n"
        "  e.g. <code>/quiz Cell Biology</code>\n"
        "/explain [topic] — In-depth teacher-style explanation\n"
        "  e.g. <code>/explain Newton's second law</code>\n"
        "/summarize — Summarize text you paste\n\n"
        "<b>Modes (use the keyboard buttons)</b>\n"
        "💬 Chat — Free-form Q&amp;A with memory\n"
        "📖 Explain — Every message gets a deep explanation\n"
        "🧠 Quiz — Send a topic (or photo!) to get a quiz\n\n"
        "You can also send a 🖼️ <b>photo</b> of notes or a problem!",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )


async def clear_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    for key in ("conversation", "active_quiz", "quiz_setup", "mode"):
        context.chat_data.pop(key, None)
    await update.message.reply_text(
        "✅ All cleared! Memory, active quiz, and mode have been reset.\n"
        "We're starting fresh — what would you like to work on?",
        reply_markup=MAIN_KEYBOARD,
    )