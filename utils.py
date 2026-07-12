import os
import shutil
import re
from datetime import datetime
from typing import Optional, Tuple

def format_time(seconds: float) -> str:
    """Форматировать время в минуты и секунды"""
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{int(seconds)} сек"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes} мин {secs} сек"

def format_progress_bar(progress: float, length: int = 12) -> str:
    """Создать прогресс-бар"""
    filled = int(progress / 100 * length)
    if filled > length:
        filled = length
    bar = "█" * filled + "░" * (length - filled)
    return bar

def parse_proxy(proxy_string: str) -> Tuple[Optional[str], Optional[str]]:
    """Парсинг прокси строки"""
    if proxy_string.startswith("socks5://"):
        return "socks5", proxy_string
    elif proxy_string.startswith("http://"):
        return "http", proxy_string
    elif proxy_string.startswith("socks4://"):
        return "socks4", proxy_string
    else:
        return None, None

def extract_username(phone_or_username: str) -> str:
    """Извлечь username из строки"""
    if phone_or_username.startswith("+"):
        return phone_or_username
    elif phone_or_username.startswith("@"):
        return phone_or_username[1:]
    else:
        return phone_or_username

def clean_filename(filename: str) -> str:
    """Очистить имя файла от недопустимых символов"""
    return re.sub(r'[^\w\-_.]', '_', filename)

def get_file_size(file_path: str) -> str:
    """Получить размер файла в удобном формате"""
    try:
        size = os.path.getsize(file_path)
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} ТБ"
    except:
        return "0 Б"

def safe_delete_file(file_path: str) -> bool:
    """Безопасно удалить файл"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
    except:
        pass
    return False

def safe_delete_dir(dir_path: str) -> bool:
    """Безопасно удалить папку"""
    try:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
            return True
    except:
        pass
    return False

def get_current_time() -> str:
    """Получить текущее время в формате строки"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def truncate_text(text: str, max_length: int = 100) -> str:
    """Обрезать текст до указанной длины"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

def safe_int(value, default=0) -> int:
    """Безопасное преобразование в int"""
    try:
        return int(value)
    except:
        return default