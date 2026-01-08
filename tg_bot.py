import asyncio
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')

MODEL = "meta-llama/llama-3.3-70b-instruct:free"

SYSTEM_PROMPT = (
    "You are a helpful assistant inside a Telegram chat. "
    "You can see quoted messages and recent chat context when they are provided. "
    "Use that context when replying. Be concise, friendly, and informative."
)

conversation_history = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! Send a message or reply to one.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Reply to a message or @mention me in groups.")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversation_history[update.effective_chat.id] = []
    await update.message.reply_text("🗑️ History cleared.")

def _call_llm(payload):
    return requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=40,
    )

async def get_llm_response(chat_id: int, user_message: str) -> str:
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []

    conversation_history[chat_id].append({"role": "user", "content": user_message})
    conversation_history[chat_id] = conversation_history[chat_id][-10:]

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            *conversation_history[chat_id],
        ],
    }

    try:
        response = await asyncio.to_thread(_call_llm, payload)

        if response.status_code != 200:
            return f"❌ OpenRouter error {response.status_code}: {response.text}"

        data = response.json()
        msg = data["choices"][0]["message"]["content"]

        conversation_history[chat_id].append({"role": "assistant", "content": msg})
        return msg

    except requests.Timeout:
        return "⏳ AI timed out. Try again."
    except Exception as e:
        return f"❌ Error: {e}"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    bot_username = context.bot.username

    if not message or not message.text:
        return

    is_private = chat.type == "private"
    is_mentioned = f"@{bot_username}" in message.text
    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user.id == context.bot.id
    )

    # In groups, only respond to mentions or replies to the bot
    if chat.type in ("group", "supergroup"):
        if not (is_mentioned or is_reply_to_bot):
            return

    user_text = message.text.replace(f"@{bot_username}", "").strip()

    quoted = None
    if message.reply_to_message and message.reply_to_message.text:
        quoted = message.reply_to_message.text.strip()

    if quoted:
        user_text = f"Quoted message:\n{quoted}\n\nUser reply:\n{user_text}"

    if not user_text:
        return

    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    response = await get_llm_response(chat.id, user_text)
    await message.reply_text(response)

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is running... Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == "__main__":
    main()

