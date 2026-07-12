import os
import asyncio
import logging
from flask import Flask, jsonify
from threading import Thread
from config import PORT
from main import main

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Переменные для хранения статуса бота
bot_status = {"status": "stopped", "thread": None}

@app.route('/')
def home():
    return """
    <html>
        <head><title>🦆 DUCK SPAM</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #1a1a2e; color: #e0e0e0;">
            <h1>🦆 DUCK SPAM БОТ</h1>
            <p style="font-size: 18px;">Бот работает 24/7 на <strong>Render</strong> 🚀</p>
            <p style="font-size: 14px; color: #888;">
                <a href="/status" style="color: #4fc3f7;">Проверить статус</a> |
                <a href="/health" style="color: #4fc3f7;">Health Check</a>
            </p>
            <p style="font-size: 12px; color: #555; margin-top: 50px;">
                Telegram Bot: <a href="https://t.me/spam_duck_bot" style="color: #4fc3f7;">@spam_duck_bot</a>
            </p>
        </body>
    </html>
    """

@app.route('/status')
def status():
    return jsonify(bot_status)

@app.route('/health')
def health():
    return "OK", 200

def run_bot():
    """Запуск бота в отдельном потоке"""
    try:
        logger.info("🚀 Запуск бота...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except Exception as e:
        logger.error(f"❌ Ошибка бота: {e}")
        bot_status["status"] = "error"
        bot_status["error"] = str(e)

if __name__ == "__main__":
    # Запускаем бота в фоновом потоке
    bot_status["status"] = "starting"
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    bot_status["status"] = "running"
    bot_status["thread"] = "running"
    
    # Запускаем веб-сервер
    port = int(os.environ.get("PORT", PORT))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port)