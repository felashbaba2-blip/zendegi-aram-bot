import os
import logging
import sqlite3
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler
import edge_tts

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TELEGRAM_TOKEN = "8905829730:AAGhg0oIJ1Qw05LLkT5mQR8v1MCUYsZ4df4"

def init_db():
    conn = sqlite3.connect('bot_settings.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            voice TEXT,
            rate TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_user_settings(user_id):
    conn = sqlite3.connect('bot_settings.db')
    cursor = conn.cursor()
    cursor.execute('SELECT voice, rate FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"voice": row[0], "rate": row[1]}
    else:
        return {"voice": "fa-IR-DilaraNeural", "rate": "+0%"}

def save_user_setting(user_id, key, value):
    settings = get_user_settings(user_id)
    settings[key] = value
    conn = sqlite3.connect('bot_settings.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, voice, rate)
        VALUES (?, ?, ?)
    ''', (user_id, settings["voice"], settings["rate"]))
    conn.commit()
    conn.close()

init_db()

def split_text(text, max_length=900):
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in words:
        if current_length + len(word) + 1 <= max_length:
            current_chunk.append(word)
            current_length += len(word) + 1
        else:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_length = len(word) + 1
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"سلام {user_name} عزیز! 🌿\n"
        "به ربات پیشرفته «زندگی آرام» خوش آمدید.\n\n"
        "✨ **امکانات ربات:**\n"
        "• ارسال متن، فایل متنی (TXT)، فایل PDF یا لینک مقالات\n"
        "• تقسیم‌کننده هوشمند متن‌های طولانی\n"
        "• انتخاب صدای زن/مرد و تنظیم سرعت با دستور /settings"
    )

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("👩 صدای زن (دیلارا)", callback_data="voice_fa-IR-DilaraNeural"),
            InlineKeyboardButton("👨 صدای مرد (فرید)", callback_data="voice_fa-IR-FaridNeural")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎙️ مرحله اول: لطفاً نوع صدا را انتخاب کنید:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("voice_"):
        voice = data.replace("voice_", "")
        save_user_setting(user_id, "voice", voice)
        
        rate_keyboard = [
            [
                InlineKeyboardButton("🐢 سرعت آرام", callback_data="rate_-20%"),
                InlineKeyboardButton("▶️ سرعت عادی", callback_data="rate_+0%"),
                InlineKeyboardButton("🐇 سرعت تند", callback_data="rate_+20%")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(rate_keyboard)
        await query.edit_message_text(
            text="✅ صدا ثبت شد.\n\n⚡️ مرحله دوم: سرعت خواندن را انتخاب کنید:",
            reply_markup=reply_markup
        )
    elif data.startswith("rate_"):
        rate = data.replace("rate_", "")
        save_user_setting(user_id, "rate", rate)
        await query.edit_message_text(
            text="✅ تنظیمات با موفقیت ذخیره شد!\nاکنون متن، فایل یا لینک خود را بفرستید."
        )

async def process_and_send_audio(update: Update, text: str):
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    
    if not text.strip():
        await update.message.reply_text("❌ متن خالی است یا قابل خواندن نیست.")
        return

    chunks = split_text(text)
    await update.message.reply_text(f"⏳ متن شما به {len(chunks)} بخش تقسیم شد و در حال تولید است...")

    try:
        for i, chunk in enumerate(chunks):
            audio_path = f"output_voice_{i}.mp3"
            communicate = edge_tts.Communicate(chunk, settings["voice"], rate=settings["rate"])
            await communicate.save(audio_path)

            with open(audio_path, "rb") as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    title=f"بخش {i+1} - زندگی آرام",
                    performer="Zendegi Aram",
                    filename=f"voice_{i+1}.mp3"
                )
            if os.path.exists(audio_path):
                os.remove(audio_path)
    except Exception as e:
        await update.message.reply_text(f"خطایی رخ داد: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text_to_process = ""

    if message.text:
        text_to_process = message.text

    elif message.document:
        doc = message.document
        file = await context.bot.get_file(doc.file_id)
        file_path = f"downloads_{doc.file_name}"
        await file.download_to_drive(file_path)

        if doc.file_name.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                text_to_process = f.read()
        elif doc.file_name.endswith('.pdf'):
            reader = PdfReader(file_path)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_to_process += extracted + "\n"
        
        if os.path.exists(file_path):
            os.remove(file_path)

    elif text_to_process.startswith("http://") or text_to_process.startswith("https://"):
        try:
            response = requests.get(text_to_process, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style"]):
                script.extract()
            text_to_process = soup.get_text(separator=' ')
        except Exception as e:
            await update.message.reply_text(f"خطا در لینک: {str(e)}")
            return

    if text_to_process:
        await process_and_send_audio(update, text_to_process)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & (~filters.COMMAND), handle_message))

    print("ربات پیشرفته زندگی آرام آماده به کار است...")
    application.run_polling()
