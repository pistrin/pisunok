import os
import threading
import random
import re
import time
import subprocess
import urllib.request
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_ID = 6624457671
DOWNLOAD_FOLDER = 'downloads'
MAX_SIZE_MB = 50
RENDER_URL = os.environ.get("RENDER_URL", "https://pisunok.onrender.com")  # свой URL

app = Flask(__name__)

def is_authorized(update):
    return update.effective_user.id == MY_ID

def get_size_mb(path):
    return os.path.getsize(path) / (1024 * 1024)

def parse_time(time_str):
    total_seconds = 0
    matches = re.findall(r'(\d+)([mhs])', time_str)
    for value, unit in matches:
        value = int(value)
        if unit == 'm':
            total_seconds += value * 60
        elif unit == 'h':
            total_seconds += value * 3600
        elif unit == 's':
            total_seconds += value
    return total_seconds

async def send_reminder(context, chat_id, text):
    await context.bot.send_message(chat_id, f"⏰ Напоминание: {text}")

async def start(update, context):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🤖 Привет! Я работаю на Render (24/7).\n"
        "📹 Отправь ссылку — скачаю в 1080p (MP4 H.264).\n"
        "🪙 /m — подбросить монетку (орёл/решка).\n"
        "🔁 /echo <текст> — повторю твой текст.\n"
        "⏰ /remind <время> <текст> — напоминалка.\n"
        "🎵 /audio <ссылка> — скачать MP3."
    )

async def echo(update, context):
    if not is_authorized(update):
        return
    text = update.message.text.replace('/echo', '').strip()
    if not text:
        await update.message.reply_text("⚠️ Напиши текст после /echo")
        return
    await update.message.reply_text(text)

async def coin(update, context):
    if not is_authorized(update):
        return
    result = random.choice(["орёл", "решка"])
    await update.message.reply_text(f"🪙 Монетка упала на: **{result}**!")

async def remind(update, context):
    if not is_authorized(update):
        return
    try:
        args = update.message.text.split(maxsplit=2)
        if len(args) < 3:
            await update.message.reply_text("⚠️ Использование: /remind 15m Выключить чайник")
            return
        time_str, reminder_text = args[1], args[2]
        seconds = parse_time(time_str)
        if seconds <= 0:
            await update.message.reply_text("⚠️ Неправильный формат. Используй 15m, 1h, 30s.")
            return
        await update.message.reply_text(f"⏳ Напоминание через {time_str}.")
        def timer_callback():
            import asyncio
            asyncio.run(send_reminder(context, update.effective_chat.id, reminder_text))
        threading.Timer(seconds, timer_callback).start()
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def audio(update, context):
    if not is_authorized(update):
        return
    url = update.message.text.replace('/audio', '').strip()
    if not url:
        await update.message.reply_text("⚠️ Использование: /audio <ссылка>")
        return
    await update.message.reply_text("⏳ Извлекаю аудио...")
    try:
        ydl_opts = {
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = os.path.splitext(ydl.prepare_filename(info))[0]
            filename = base + '.mp3'
        await context.bot.send_audio(update.effective_chat.id, open(filename, 'rb'), caption="✅ Готово!")
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def video(update, context):
    if not is_authorized(update):
        return
    url = update.message.text.strip()
    await update.message.reply_text("⏳ Скачиваю видео...")
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
        'format': 'bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'skip': ['hls', 'dash']
            }
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not filename.endswith('.mp4'):
                base = os.path.splitext(filename)[0]
                new_filename = base + '.mp4'
                if os.path.exists(new_filename):
                    filename = new_filename

        size_mb = get_size_mb(filename)
        if size_mb > MAX_SIZE_MB:
            await update.message.reply_text(f"📦 Видео {size_mb:.1f} МБ, сжимаю до 720p...")
            compressed = filename.replace('.mp4', '_720p.mp4')
            cmd = [
                'ffmpeg', '-i', filename,
                '-vf', 'scale=1280:720',
                '-b:v', '1000k',
                '-maxrate', '1000k',
                '-bufsize', '2000k',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-preset', 'veryfast',
                '-y',
                compressed
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            await context.bot.send_video(update.effective_chat.id, open(compressed, 'rb'), caption="✅ Сжато до 720p")
            os.remove(compressed)
        else:
            await context.bot.send_video(update.effective_chat.id, open(filename, 'rb'), caption=f"✅ Готово ({size_mb:.1f} МБ)")
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

def run_bot():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("echo", echo))
    application.add_handler(CommandHandler("m", coin))
    application.add_handler(CommandHandler("remind", remind))
    application.add_handler(CommandHandler("audio", audio))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, video))
    print("бот запущен 🦞")
    application.run_polling()

# ====== ПИНГ ДЛЯ ПОДДЕРЖАНИЯ АКТИВНОСТИ ======
def ping_self():
    while True:
        try:
            time.sleep(840)  # каждые 14 минут
            urllib.request.urlopen(RENDER_URL + "/health", timeout=5)
            print("pong")
        except Exception as e:
            print(f"ошибка пинга: {e}")

# ====== FLASK ======
@app.route('/')
def home():
    return "Бот жив 🦞"

@app.route('/health')
def health():
    return "OK", 200

if __name__ == "__main__":
    # Запускаем пинг в фоне
    ping_thread = threading.Thread(target=ping_self)
    ping_thread.daemon = True
    ping_thread.start()

    # Flask в фоне
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    )
    flask_thread.daemon = True
    flask_thread.start()

    # Бот в основном потоке
    run_bot()
