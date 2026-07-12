import os
import asyncio
import logging
from threading import Thread
from flask import Flask, jsonify
from config import PORT

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot_status = {"status": "starting"}

# === Flask Routes ===
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
        </body>
    </html>
    """

@app.route('/status')
def status():
    return jsonify(bot_status)

@app.route('/health')
def health():
    return "OK", 200

# === Функция для запуска Flask в отдельном потоке ===
def run_flask():
    port = int(os.environ.get("PORT", PORT))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port)

# === Основная точка входа ===
if __name__ == "__main__":
    # 1. Запускаем Flask в фоновом потоке (для health checks)
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    bot_status["status"] = "running"

    # 2. Запускаем бота в основном потоке (решает проблему asyncio)
    from main import main
    logger.info("🚀 Запуск бота в основном потоке...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен вручную")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка бота: {e}")
        bot_status["status"] = "error"
