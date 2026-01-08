import asyncio
import io
import base64
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
from groq import Groq
from PIL import Image

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.environ.get('API_KEY')

MODEL_ID = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = (
    "You are a helpful assistant inside a Telegram chat. "
    "You can see images, quoted messages, and recent chat context. "
    "Use that context when replying."
)

groq_client = Groq(api_key=GROQ_API_KEY)
conversation_history = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! I support text and images via GROQ Vision.")


def image_to_base64(image_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(image_bytes))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def get_groq_response(chat_id: int, parts: list) -> str:
    if chat_id not in conversation_history:
        conversation_history[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    conversation_history[chat_id].append({"role": "user", "content": parts})
    conversation_history[chat_id] = conversation_history[chat_id][:1] + conversation_history[chat_id][-10:]

    try:
        resp = groq_client.chat.completions.create(
            model=MODEL_ID,
            messages=conversation_history[chat_id],
            temperature=0.6,
        )
        reply = resp.choices[0].message.content
        conversation_history[chat_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return f"❌ GROQ Error: {e}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    chat = update.effective_chat
    bot_username = context.bot.username
    incoming_text = message.text or message.caption or ""

    if chat.type in ("group", "supergroup"):
        is_mentioned = f"@{bot_username}" in incoming_text
        is_reply = message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id
        if not (is_mentioned or is_reply):
            return

    user_text = incoming_text.replace(f"@{bot_username}", "").strip()

    if message.reply_to_message:
        quoted = message.reply_to_message.text or message.reply_to_message.caption
        if quoted:
            user_text = f"Context:\n{quoted}\n\nUser:\n{user_text}"

    parts = []
    if user_text:
        parts.append({"type": "text", "text": user_text})

    if message.photo:
        photo_file = await message.photo[-1].get_file()
        buf = io.BytesIO()
        await photo_file.download_to_memory(buf)
        b64 = image_to_base64(buf.getvalue())
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })

    if not parts:
        return

    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)

    reply = get_groq_response(chat.id, parts)
    await message.reply_text(reply)


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_message))
    print("🤖 Bot running with GROQ Vision")
    app.run_polling()


if __name__ == "__main__":
    main()

