import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import DB_PATH

def get_db():
    """Получить соединение с БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация базы данных"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            subscribed INTEGER DEFAULT 1,
            reg_date TEXT,
            total_sessions_loaded INTEGER DEFAULT 0,
            proxy_id INTEGER DEFAULT NULL,
            only_mutual INTEGER DEFAULT 1,
            delay INTEGER DEFAULT 3,
            delete_after_send INTEGER DEFAULT 1,
            auto_delete_invalid INTEGER DEFAULT 1,
            broadcast_mode TEXT DEFAULT 'parallel'
        )
    ''')
    
    # Таблица сессий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_name TEXT,
            phone TEXT,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_valid INTEGER DEFAULT 1,
            error_msg TEXT,
            total_contacts INTEGER DEFAULT 0,
            mutual_contacts INTEGER DEFAULT 0,
            last_used TEXT,
            proxy_id INTEGER DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (proxy_id) REFERENCES proxies (id)
        )
    ''')
    
    # Таблица прокси
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proxy_string TEXT UNIQUE,
            proxy_type TEXT,
            is_active INTEGER DEFAULT 1,
            added_by INTEGER,
            added_date TEXT,
            last_test TEXT,
            test_result TEXT
        )
    ''')
    
    # Таблица шаблонов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS templates (
            user_id INTEGER PRIMARY KEY,
            text TEXT,
            file_path TEXT,
            link_url TEXT,
            link_text TEXT,
            updated_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Таблица логов рассылок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcast_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            datetime TEXT,
            total_accounts INTEGER,
            success INTEGER,
            failed INTEGER,
            proxy_used TEXT,
            template_text TEXT,
            file_name TEXT,
            duration_seconds INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Таблица деталей рассылки
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcast_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_id INTEGER,
            session_name TEXT,
            sent_ok INTEGER DEFAULT 0,
            sent_fail INTEGER DEFAULT 0,
            error_text TEXT,
            FOREIGN KEY (log_id) REFERENCES broadcast_log (id)
        )
    ''')
    
    # Таблица очереди рассылок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcast_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            status TEXT DEFAULT 'waiting',
            created_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            config TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# ===== ПОЛЬЗОВАТЕЛИ =====
def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def create_user(user_id: int, username: str, first_name: str):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT OR IGNORE INTO users (id, username, first_name, reg_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username or "", first_name or "", now))
    conn.commit()
    conn.close()

def update_user_settings(user_id: int, **kwargs):
    conn = get_db()
    cursor = conn.cursor()
    for key, value in kwargs.items():
        cursor.execute(f"UPDATE users SET {key} = ? WHERE id = ?", (value, user_id))
    conn.commit()
    conn.close()

def get_all_users(limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, first_name, subscribed FROM users LIMIT ?", (limit,))
    users = cursor.fetchall()
    conn.close()
    return [dict(u) for u in users]

# ===== СЕССИИ =====
def add_session(user_id: int, session_name: str, phone: str, username: str, 
                first_name: str, last_name: str, proxy_id: int = None, 
                total_contacts: int = 0, mutual_contacts: int = 0):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sessions (user_id, session_name, phone, username, first_name, last_name, 
                             proxy_id, total_contacts, mutual_contacts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, session_name, phone, username, first_name, last_name, 
          proxy_id, total_contacts, mutual_contacts))
    conn.commit()
    conn.close()

def get_sessions(user_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE user_id = ? ORDER BY id DESC", (user_id,))
    sessions = cursor.fetchall()
    conn.close()
    return [dict(s) for s in sessions]

def get_valid_sessions(user_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE user_id = ? AND is_valid = 1", (user_id,))
    sessions = cursor.fetchall()
    conn.close()
    return [dict(s) for s in sessions]

def get_session(session_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    session = cursor.fetchone()
    conn.close()
    return dict(session) if session else None

def update_session_valid(session_id: int, is_valid: int, error_msg: str = None):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        UPDATE sessions SET is_valid = ?, error_msg = ?, last_used = ?
        WHERE id = ?
    ''', (is_valid, error_msg, now, session_id))
    conn.commit()
    conn.close()

def update_session_contacts(session_id: int, total_contacts: int, mutual_contacts: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE sessions SET total_contacts = ?, mutual_contacts = ?
        WHERE id = ?
    ''', (total_contacts, mutual_contacts, session_id))
    conn.commit()
    conn.close()

def delete_session(session_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

def delete_all_sessions(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def increment_session_load(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET total_sessions_loaded = total_sessions_loaded + 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

# ===== ПРОКСИ =====
def get_proxies() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM proxies WHERE is_active = 1")
    proxies = cursor.fetchall()
    conn.close()
    return [dict(p) for p in proxies]

def get_proxy(proxy_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM proxies WHERE id = ?", (proxy_id,))
    proxy = cursor.fetchone()
    conn.close()
    return dict(proxy) if proxy else None

def add_proxy(proxy_string: str, proxy_type: str, added_by: int):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT OR IGNORE INTO proxies (proxy_string, proxy_type, added_by, added_date)
        VALUES (?, ?, ?, ?)
    ''', (proxy_string, proxy_type, added_by, now))
    conn.commit()
    conn.close()

def delete_proxy(proxy_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
    conn.commit()
    conn.close()

def set_user_proxy(user_id: int, proxy_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET proxy_id = ? WHERE id = ?", (proxy_id, user_id))
    conn.commit()
    conn.close()

# ===== ШАБЛОНЫ =====
def get_template(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM templates WHERE user_id = ?", (user_id,))
    template = cursor.fetchone()
    conn.close()
    return dict(template) if template else None

def save_template(user_id: int, text: str = None, file_path: str = None, 
                  link_url: str = None, link_text: str = None):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT OR REPLACE INTO templates (user_id, text, file_path, link_url, link_text, updated_date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, text, file_path, link_url, link_text, now))
    conn.commit()
    conn.close()

# ===== ЛОГИ РАССЫЛКИ =====
def add_broadcast_log(user_id: int, total_accounts: int, success: int, failed: int,
                      proxy_used: str, template_text: str, file_name: str, duration: int) -> int:
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO broadcast_log (user_id, datetime, total_accounts, success, failed, 
                                   proxy_used, template_text, file_name, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, now, total_accounts, success, failed, proxy_used, template_text, file_name, duration))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def add_broadcast_detail(log_id: int, session_name: str, sent_ok: int, sent_fail: int, error_text: str = None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO broadcast_details (log_id, session_name, sent_ok, sent_fail, error_text)
        VALUES (?, ?, ?, ?, ?)
    ''', (log_id, session_name, sent_ok, sent_fail, error_text))
    conn.commit()
    conn.close()

def get_broadcast_logs(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM broadcast_log ORDER BY id DESC LIMIT ?", (limit,))
    logs = cursor.fetchall()
    conn.close()
    return [dict(l) for l in logs]

def get_broadcast_details(log_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM broadcast_details WHERE log_id = ?", (log_id,))
    details = cursor.fetchall()
    conn.close()
    return [dict(d) for d in details]

# ===== СТАТИСТИКА =====
def get_total_stats() -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE subscribed = 1")
    subscribed_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM broadcast_log")
    total_broadcasts = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(success) FROM broadcast_log")
    total_success = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(failed) FROM broadcast_log")
    total_failed = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM sessions")
    total_sessions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM proxies WHERE is_active = 1")
    total_proxies = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_users": total_users,
        "subscribed_users": subscribed_users,
        "total_broadcasts": total_broadcasts,
        "total_success": total_success,
        "total_failed": total_failed,
        "total_sessions": total_sessions,
        "total_proxies": total_proxies
    }

# ===== ОЧЕРЕДЬ =====
def add_to_queue(user_id: int, config: Dict[str, Any]) -> int:
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO broadcast_queue (user_id, status, created_at, config)
        VALUES (?, 'waiting', ?, ?)
    ''', (user_id, now, json.dumps(config)))
    queue_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return queue_id

def get_queue_tasks(user_id: int = None) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT * FROM broadcast_queue WHERE user_id = ? AND status IN ('waiting', 'running') ORDER BY id", (user_id,))
    else:
        cursor.execute("SELECT * FROM broadcast_queue WHERE status IN ('waiting', 'running') ORDER BY id")
    tasks = cursor.fetchall()
    conn.close()
    return [dict(t) for t in tasks]

def update_queue_status(queue_id: int, status: str, finished_at: str = None):
    conn = get_db()
    cursor = conn.cursor()
    if finished_at:
        cursor.execute("UPDATE broadcast_queue SET status = ?, finished_at = ? WHERE id = ?", (status, finished_at, queue_id))
    else:
        cursor.execute("UPDATE broadcast_queue SET status = ? WHERE id = ?", (status, queue_id))
    conn.commit()
    conn.close()