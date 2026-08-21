# Telegram Chatbot

ChrixHelp AI is a Telegram study assistant with direct academic chat, topic
explanations, and interactive domain-specific quizzes.

## Features

- Telegram bot integration
- `/start` command
- `/help` command
- Text message handling
- Separated AI service architecture
- Environment variable configuration

## Technologies

- Python
- python-telegram-bot
- python-dotenv

## Local setup

1. Create and activate a virtual environment.
2. Install runtime dependencies with `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and add the Telegram and Groq keys.
4. Start the bot with `python -m bot.main`.

Install development dependencies and run tests with:

```text
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Deployment

This bot is a long-running Telegram polling worker. Deploy it as a worker or
container, not as a serverless request function.

### Docker

```text
docker build -t chrixhelp .
docker run --env-file .env --restart unless-stopped chrixhelp
```

### Render, Railway, Fly.io, or a VPS

Create a worker/service with this start command:

```text
python -m bot.main
```

Set `TELEGRAM_BOT_TOKEN` and `GROQ_API_KEY` as platform secrets. Never commit
`.env` or place secrets in the Docker image. Run only one bot instance for a
given token because Telegram polling cannot safely be shared by multiple
workers.

## Project Structure

```text
TelegramChatbot/
│
├── bot/
│   ├── __init__.py
│   └── main.py
│
├── handlers/
│   ├── __init__.py
│   ├── start.py
│   └── message.py
│
├── services/
│   ├── __init__.py
│   └── ai_service.py
│
├── config/
│   ├── __init__.py
│   └── settings.py
│
├── .env
├── .gitignore
├── requirements.txt
└── README.md