from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

from config.settings import TELEGRAM_BOT_TOKEN, logger
from handlers.start import clear_command, start_command, help_command
from handlers.messages import handle_message, select_mode
from handlers.academics import (
    explain_command,
    quiz_answer,
    quiz_command,
    quiz_count,
    quiz_setup,
)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            ("start", "Open the study assistant"),
            ("help", "Show available features"),
            ("quiz", "Start a clickable quiz"),
            ("explain", "Explain a topic clearly"),
            ("clear", "Clear chat memory"),
        ]
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global fallback so an unhandled exception never crashes the bot."""
    logger.error(
        "Unhandled exception while processing update: %s", update, exc_info=context.error
    )


def build_application() -> Application:
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("explain", explain_command))
    application.add_handler(CallbackQueryHandler(quiz_answer, pattern=r"^quiz:"))
    application.add_handler(CallbackQueryHandler(quiz_setup, pattern=r"^quizsetup:"))
    application.add_handler(CallbackQueryHandler(quiz_count, pattern=r"^quizcount:"))
    application.add_handler(
        MessageHandler(filters.Regex(r"^(Chat|Explain|Quiz)$"), select_mode)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_error_handler(on_error)

    return application


def main():
    logger.info("Starting ChrixHelp AI...")

    application = build_application()

    logger.info("ChrixHelp AI is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()