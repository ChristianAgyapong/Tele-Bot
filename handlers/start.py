from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
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
        f"Hello {user.first_name}! 👋\n\n"
        "I'm ChrixHelp AI, your personal study tutor.\n"
        "I can help with homework, explain tricky concepts, and quiz you "
        "on any topic.\n\n"
        "Try /help to see everything I can do."
        , reply_markup=MAIN_KEYBOARD
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Here's what I can do:\n\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/clear - Forget our conversation history\n"
        "/quiz [topic] - Generate a quiz to test yourself, e.g. /quiz Cell Biology\n"
        "/explain [topic] - Get an in-depth, teacher-style explanation\n\n"
        "Or just send me any question and I'll help you work through it."
        , reply_markup=MAIN_KEYBOARD
    )


async def clear_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    for key in ("conversation", "active_quiz", "quiz_setup", "mode"):
        context.chat_data.pop(key, None)
    await update.message.reply_text(
        "All bot memory and any active quiz have been cleared. We can start fresh.",
        reply_markup=MAIN_KEYBOARD,
    )