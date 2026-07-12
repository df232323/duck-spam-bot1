import asyncio
import os
import time
import logging
from typing import Dict, List, Any, Optional
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError, AuthKeyError
from telethon.tl.functions.contacts import GetContactIDsRequest
from config import SESSIONS_DIR, DEFAULT_DELAY, API_ID, API_HASH, MAX_CONCURRENT_BROADCASTS
import database as db
from utils import format_time
from proxy_manager import get_proxy_dict

logger = logging.getLogger(__name__)

class BroadcastEngine:
    """Движок для управления рассылками"""
    
    def __init__(self):
        self.running = {}  # broadcast_id -> данные
        self.active_broadcasts = set()  # множество активных broadcast_id
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROADCASTS)
    
    async def start_broadcast(self, user_id: int, sessions: List[Dict], template: Dict, 
                             settings: Dict, bot) -> str:
        """Запустить рассылку"""
        broadcast_id = f"{user_id}_{int(time.time())}"
        
        # Создаём конфигурацию для очереди
        config = {
            "user_id": user_id,
            "sessions": [s['id'] for s in sessions],
            "template": dict(template) if template else None,
            "settings": settings
        }
        queue_id = db.add_to_queue(user_id, config)
        
        # Запускаем рассылку асинхронно
        asyncio.create_task(self._run_broadcast(
            broadcast_id, user_id, sessions, template, settings, queue_id, bot
        ))
        
        return broadcast_id
    
    async def _run_broadcast(self, broadcast_id: str, user_id: int, sessions: List[Dict],
                            template: Dict, settings: Dict, queue_id: int, bot):
        """Основная логика рассылки"""
        self.active_broadcasts.add(broadcast_id)
        
        # Инициализируем статусы сессий
        sessions_status = {}
        for session in sessions:
            name = session['username'] if session['username'] else session['phone']
            sessions_status[session['id']] = {
                "name": name,
                "status": "waiting",
                "sent": 0,
                "failed": 0,
                "total_contacts": 0,
                "error_msg": None
            }
        
        self.running[broadcast_id] = {
            "status": "running",
            "start_time": time.time(),
            "total_contacts": 0,
            "sent": 0,
            "failed": 0,
            "sessions_status": sessions_status,
            "results": []
        }
        
        db.update_queue_status(queue_id, "running", None)
        
        # Получаем прокси пользователя
        user = db.get_user(user_id)
        proxy_dict = None
        if user and user['proxy_id']:
            proxy = db.get_proxy(user['proxy_id'])
            if proxy:
                proxy_dict = get_proxy_dict(proxy['proxy_string'])
        
        # Подготавливаем шаблон
        template_text = template['text'] if template else None
        template_file = None
        if template and template['file_path']:
            from config import MEDIA_DIR
            template_file = os.path.join(MEDIA_DIR, f"template_{user_id}_{template['file_path']}")
            if not os.path.exists(template_file):
                logger.warning(f"Файл шаблона не найден: {template_file}")
                template_file = None
        
        # Запускаем задачи для каждой сессии
        tasks = []
        for session in sessions:
            task = self._send_messages(
                broadcast_id, user_id, session, template_text, template_file,
                settings, proxy_dict, bot
            )
            tasks.append(task)
        
        # Ожидаем завершения всех задач
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Подсчитываем итоги
        total_sent = 0
        total_failed = 0
        session_details = []
        
        for result in results:
            if isinstance(result, dict):
                total_sent += result.get('sent', 0)
                total_failed += result.get('failed', 0)
                session_details.append(result)
            else:
                logger.error(f"Ошибка в задаче: {result}")
        
        # Обновляем статус
        self.running[broadcast_id]["status"] = "completed"
        self.running[broadcast_id]["sent"] = total_sent
        self.running[broadcast_id]["failed"] = total_failed
        self.running[broadcast_id]["results"] = session_details
        
        duration = int(time.time() - self.running[broadcast_id]["start_time"])
        
        # Сохраняем лог
        file_name = os.path.basename(template_file) if template_file else None
        log_id = db.add_broadcast_log(
            user_id=user_id,
            total_accounts=len(sessions),
            success=total_sent,
            failed=total_failed,
            proxy_used=proxy_dict['addr'] if proxy_dict else "Не использован",
            template_text=template_text or "Нет текста",
            file_name=file_name,
            duration=duration
        )
        
        # Сохраняем детали
        for detail in session_details:
            db.add_broadcast_detail(
                log_id=log_id,
                session_name=detail.get('name', 'Неизвестно'),
                sent_ok=detail.get('sent', 0),
                sent_fail=detail.get('failed', 0),
                error_text=detail.get('error', None)
            )
        
        db.update_queue_status(queue_id, "completed", time.time())
        
        # Удаляем из активных через 10 минут
        await asyncio.sleep(600)
        self.active_broadcasts.discard(broadcast_id)
        if broadcast_id in self.running:
            del self.running[broadcast_id]
    
    async def _send_messages(self, broadcast_id: str, user_id: int, session: Dict,
                            template_text: str, template_file: Optional[str],
                            settings: Dict, proxy_dict: Optional[Dict], bot) -> Dict:
        """Отправка сообщений для одной сессии"""
        session_id = session['id']
        session_name = session['session_name']
        session_path = os.path.join(SESSIONS_DIR, session_name)
        
        username = session['username'] if session['username'] else session['phone']
        result = {
            "name": username or "Неизвестно",
            "sent": 0,
            "failed": 0,
            "error": None
        }
        
        self.running[broadcast_id]["sessions_status"][session_id]["status"] = "running"
        logger.info(f"🚀 Начинаем рассылку для {username}")
        
        if not os.path.exists(f"{session_path}.session"):
            result["error"] = "Файл сессии не найден"
            result["failed"] = 1
            db.update_session_valid(session_id, 0, "Файл сессии не найден")
            self.running[broadcast_id]["sessions_status"][session_id]["status"] = "error"
            self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = "Файл сессии не найден"
            return result
        
        # Подключаемся с повторными попытками
        client = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = TelegramClient(
                    session_path,
                    API_ID,
                    API_HASH,
                    proxy=proxy_dict,
                    timeout=15
                )
                
                await client.connect()
                me = await client.get_me()
                if me:
                    break
                
                await client.disconnect()
                if attempt == max_retries - 1:
                    result["error"] = "Не удалось авторизоваться"
                    result["failed"] = 1
                    db.update_session_valid(session_id, 0, "Не удалось авторизоваться")
                    self.running[broadcast_id]["sessions_status"][session_id]["status"] = "error"
                    self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = "Не удалось авторизоваться"
                    return result
                await asyncio.sleep(2)
                
            except AuthKeyError:
                if attempt == max_retries - 1:
                    result["error"] = "Невалидная сессия"
                    result["failed"] = 1
                    db.update_session_valid(session_id, 0, "Невалидная сессия")
                    self.running[broadcast_id]["sessions_status"][session_id]["status"] = "error"
                    self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = "Невалидная сессия"
                    return result
                await asyncio.sleep(2)
            except Exception as e:
                if attempt == max_retries - 1:
                    result["error"] = f"Ошибка подключения: {str(e)[:50]}"
                    result["failed"] = 1
                    db.update_session_valid(session_id, 0, str(e)[:100])
                    self.running[broadcast_id]["sessions_status"][session_id]["status"] = "error"
                    self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = str(e)[:50]
                    return result
                await asyncio.sleep(2)
        
        if not client:
            result["error"] = "Не удалось создать клиент"
            result["failed"] = 1
            return result
        
        try:
            # Получаем диалоги с повторными попытками
            dialogs = []
            for attempt in range(3):
                try:
                    dialogs = await client.get_dialogs()
                    if dialogs:
                        break
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(f"Ошибка получения диалогов (попытка {attempt+1}): {e}")
                    await asyncio.sleep(1)
            
            logger.info(f"✅ {username}: Получено диалогов: {len(dialogs)}")
            
            only_mutual = settings.get('only_mutual', True)
            
            # Получаем контакты
            contact_ids = []
            if only_mutual:
                try:
                    contact_ids = await client(GetContactIDsRequest(hash=0))
                    logger.info(f"✅ {username}: Получен список контактов ({len(contact_ids)} записей)")
                except Exception as e:
                    logger.warning(f"Не удалось получить список контактов: {e}")
            
            # Фильтруем контакты
            contacts = []
            for dialog in dialogs:
                if not dialog.is_user and not dialog.is_group and not dialog.is_channel:
                    continue
                    
                if only_mutual:
                    if dialog.is_user and dialog.entity.id in contact_ids:
                        contacts.append(dialog)
                else:
                    contacts.append(dialog)
            
            total_contacts = len(contacts)
            self.running[broadcast_id]["sessions_status"][session_id]["total_contacts"] = total_contacts
            
            if total_contacts == 0:
                result["error"] = "Нет контактов для рассылки"
                result["failed"] = 1
                self.running[broadcast_id]["sessions_status"][session_id]["status"] = "error"
                self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = "Нет контактов"
                await client.disconnect()
                return result
            
            self.running[broadcast_id]["total_contacts"] += total_contacts
            logger.info(f"📋 {username}: Найдено {total_contacts} контактов для рассылки")
            
            delay = settings.get('delay', DEFAULT_DELAY)
            delete_after = settings.get('delete_after_send', False)
            
            for i, dialog in enumerate(contacts, 1):
                try:
                    logger.info(f"📤 {username}: Отправка {i}/{total_contacts} -> {dialog.entity.username or dialog.entity.id}")
                    
                    if template_file and os.path.exists(template_file):
                        if template_text:
                            await client.send_file(
                                dialog.entity,
                                template_file,
                                caption=template_text
                            )
                        else:
                            await client.send_file(dialog.entity, template_file)
                    else:
                        if template_text:
                            await client.send_message(dialog.entity, template_text)
                    
                    result["sent"] += 1
                    self.running[broadcast_id]["sent"] += 1
                    self.running[broadcast_id]["sessions_status"][session_id]["sent"] += 1
                    
                    logger.info(f"✅ {username}: Успешно отправлено {i}/{total_contacts}")
                    
                    if delete_after:
                        try:
                            async for msg in client.iter_messages(dialog.entity, limit=1):
                                await client.delete_messages(dialog.entity, [msg.id])
                                break
                        except Exception as e:
                            logger.warning(f"⚠️ {username}: Не удалось удалить сообщение: {e}")
                    
                    await asyncio.sleep(delay)
                    
                except FloodWaitError as e:
                    result["failed"] += 1
                    self.running[broadcast_id]["failed"] += 1
                    self.running[broadcast_id]["sessions_status"][session_id]["failed"] += 1
                    result["error"] = f"Флуд: ждите {e.seconds} сек"
                    db.update_session_valid(session_id, 0, f"Флуд: {e.seconds} сек")
                    logger.warning(f"⚠️ {username}: Флуд-вейт {e.seconds} сек")
                    await asyncio.sleep(min(e.seconds, 60))
                    continue
                    
                except RPCError as e:
                    error_msg = str(e)
                    if "BANNED" in error_msg:
                        result["error"] = "❌ Аккаунт заблокирован"
                        db.update_session_valid(session_id, 0, "Аккаунт заблокирован")
                        self.running[broadcast_id]["sessions_status"][session_id]["status"] = "error"
                        self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = "Аккаунт заблокирован"
                        logger.error(f"❌ {username}: Аккаунт заблокирован!")
                        break
                    else:
                        result["failed"] += 1
                        self.running[broadcast_id]["failed"] += 1
                        self.running[broadcast_id]["sessions_status"][session_id]["failed"] += 1
                        result["error"] = f"❌ {error_msg[:50]}"
                        self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = error_msg[:50]
                        logger.error(f"❌ {username}: Ошибка RPC: {error_msg[:50]}")
                    
                except Exception as e:
                    error_msg = str(e)
                    if "BANNED" in error_msg:
                        result["error"] = "❌ Аккаунт заблокирован"
                        db.update_session_valid(session_id, 0, "Аккаунт заблокирован")
                        self.running[broadcast_id]["sessions_status"][session_id]["status"] = "error"
                        self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = "Аккаунт заблокирован"
                        logger.error(f"❌ {username}: Аккаунт заблокирован!")
                        break
                    else:
                        result["failed"] += 1
                        self.running[broadcast_id]["failed"] += 1
                        self.running[broadcast_id]["sessions_status"][session_id]["failed"] += 1
                        result["error"] = f"❌ {error_msg[:50]}"
                        self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = error_msg[:50]
                        logger.error(f"❌ {username}: Ошибка: {error_msg[:50]}")
            
            if self.running[broadcast_id]["sessions_status"][session_id]["status"] != "error":
                self.running[broadcast_id]["sessions_status"][session_id]["status"] = "completed"
                logger.info(f"✅ {username}: Рассылка завершена. Отправлено: {result['sent']}, ошибок: {result['failed']}")
            
            await client.disconnect()
            
        except Exception as e:
            result["error"] = f"❌ {str(e)[:100]}"
            result["failed"] = 1
            db.update_session_valid(session_id, 0, str(e)[:100])
            self.running[broadcast_id]["sessions_status"][session_id]["status"] = "error"
            self.running[broadcast_id]["sessions_status"][session_id]["error_msg"] = str(e)[:100]
            logger.error(f"❌ {username}: Критическая ошибка: {e}")
        
        return result
    
    def get_progress(self, broadcast_id: str) -> Optional[Dict]:
        """Получить прогресс рассылки"""
        if broadcast_id not in self.running:
            return None
        
        data = self.running[broadcast_id]
        total = data["total_contacts"]
        sent = data["sent"]
        failed = data["failed"]
        
        progress = (sent / total * 100) if total > 0 else 0
        
        elapsed = time.time() - data["start_time"]
        remaining = 0
        if sent > 0 and progress < 100:
            avg_speed = sent / elapsed if elapsed > 0 else 0
            remaining_contacts = total - sent
            remaining = remaining_contacts / avg_speed if avg_speed > 0 else 0
        
        sessions_status = data.get("sessions_status", {})
        stats = {
            "running": sum(1 for s in sessions_status.values() if s.get("status") == "running"),
            "waiting": sum(1 for s in sessions_status.values() if s.get("status") == "waiting"),
            "completed": sum(1 for s in sessions_status.values() if s.get("status") == "completed"),
            "error": sum(1 for s in sessions_status.values() if s.get("status") == "error")
        }
        
        return {
            "progress": min(progress, 100),
            "sent": sent,
            "failed": failed,
            "total": total,
            "elapsed": elapsed,
            "remaining": remaining,
            "status": data["status"],
            "sessions_status": sessions_status,
            "stats": stats
        }
    
    def stop_broadcast(self, broadcast_id: str) -> bool:
        """Остановить рассылку"""
        if broadcast_id in self.running:
            self.running[broadcast_id]["status"] = "stopped"
            self.active_broadcasts.discard(broadcast_id)
            return True
        return False
    
    def is_running(self, broadcast_id: str) -> bool:
        """Проверить, активна ли рассылка"""
        return broadcast_id in self.active_broadcasts