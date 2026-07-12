import os
from dotenv import load_dotenv

# Загружаем .env файл
load_dotenv()

# ===== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ =====
def get_env_var(name, required=True, default=None):
    """Безопасное получение переменных окружения"""
    value = os.environ.get(name, default)
    if required and value is None:
        raise ValueError(f"❌ Переменная {name} не задана! Укажите в .env")
    return value

BOT_TOKEN = get_env_var("BOT_TOKEN")
ADMIN_IDS = []
admin_ids_str = get_env_var("ADMIN_IDS", default="")
if admin_ids_str:
    ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

API_ID = int(get_env_var("API_ID"))
API_HASH = get_env_var("API_HASH")
PORT = int(os.environ.get("PORT", 5000))

# ===== НАСТРОЙКИ =====
DEFAULT_DELAY = 3
DEFAULT_ONLY_MUTUAL = True
DEFAULT_DELETE_AFTER_SEND = True
DEFAULT_AUTO_DELETE_INVALID = True

# Максимальное количество одновременных рассылок
MAX_CONCURRENT_BROADCASTS = 5

# ===== ПУТИ =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
TDATA_DIR = os.path.join(DATA_DIR, "tdatas")
MEDIA_DIR = os.path.join(DATA_DIR, "media")
DB_PATH = os.path.join(DATA_DIR, "duck_spam.db")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Создаём все необходимые папки
for dir_path in [DATA_DIR, SESSIONS_DIR, TDATA_DIR, MEDIA_DIR, LOGS_DIR]:
    os.makedirs(dir_path, exist_ok=True)

# ===== ЛОГИРОВАНИЕ =====
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE = os.path.join(LOGS_DIR, "broadcast.log")