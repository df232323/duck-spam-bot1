import os
import asyncio
import logging
from typing import Dict, List
from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command  # ← ИСПРАВЛЕНО!
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from session_manager import load_session_file, check_session
from proxy_manager import test_proxy, test_proxy_with_ping, get_proxy_dict
from broadcast_engine import BroadcastEngine
from config import ADMIN_IDS, SESSIONS_DIR, MEDIA_DIR
from utils import format_time, format_progress_bar, truncate_text

logger = logging.getLogger(__name__)

# Инициализация
broadcast_engine = BroadcastEngine()
user_broadcasts = {}

# ===== FSM STATES =====
class TemplateStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_link_url = State()
    waiting_for_link_text = State()

class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_user_action = State()
    waiting_for_proxy_string = State()
    waiting_for_delay = State()

# ===== КЛАВИАТУРЫ =====
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📱 Загрузить аккаунты")],
            [KeyboardButton(text="📝 Шаблон"), KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text="🔐 Админ-панель")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

def get_settings_inline():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Только взаимные", callback_data="toggle_mutual")],
        [InlineKeyboardButton(text="⏱ Изменить задержку", callback_data="change_delay")],
        [InlineKeyboardButton(text="🗑 Удаление сообщений", callback_data="toggle_delete")],
        [InlineKeyboardButton(text="🔄 Сброс сессий", callback_data="toggle_reset")],
        [InlineKeyboardButton(text="🌐 Выбрать прокси", callback_data="select_proxy")],
        [InlineKeyboardButton(text="➕ Добавить прокси", callback_data="add_my_proxy")],
        [InlineKeyboardButton(text="❌ Удалить прокси", callback_data="remove_my_proxy")],
        [InlineKeyboardButton(text="🔍 Проверить прокси", callback_data="test_proxies")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_accounts_inline(accounts_count: int = 0):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Загрузить .session файл", callback_data="add_session")],
        [InlineKeyboardButton(text="🔍 Проверить аккаунты", callback_data="check_sessions")],
        [InlineKeyboardButton(text="🗑 Удалить невалидные", callback_data="delete_invalid")],
        [InlineKeyboardButton(text="🗑 Удалить все аккаунты", callback_data="delete_all")],
        [InlineKeyboardButton(text="🚀 Запустить рассылку", callback_data="start_broadcast")],
        [InlineKeyboardButton(text=f"📋 Мои аккаунты ({accounts_count})", callback_data="list_sessions")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_template_inline():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изменить текст", callback_data="edit_text"),
            InlineKeyboardButton(text="📌 Оставить текущий", callback_data="keep_text")
        ],
        [
            InlineKeyboardButton(text="🔗 Добавить гипер-ссылку", callback_data="add_link"),
            InlineKeyboardButton(text="🚫 Удалить гипер-ссылку", callback_data="remove_link")
        ],
        [
            InlineKeyboardButton(text="📎 Добавить файл", callback_data="add_file"),
            InlineKeyboardButton(text="🗑 Удалить файл", callback_data="remove_file")
        ]
    ])

def get_admin_inline():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление доступом", callback_data="admin_users")],
        [InlineKeyboardButton(text="🌐 Управление прокси", callback_data="admin_proxies")],
        [InlineKeyboardButton(text="📊 Логи рассылок", callback_data="admin_logs")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_proxy_selection_inline():
    proxies = db.get_proxies()
    if not proxies:
        return None
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for proxy in proxies:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🌐 {truncate_text(proxy['proxy_string'], 30)}...", 
                callback_data=f"set_proxy_{proxy['id']}"
            )
        ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_settings")])
    return keyboard

def get_proxy_delete_inline():
    proxies = db.get_proxies()
    if not proxies:
        return None
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for proxy in proxies:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🗑 {truncate_text(proxy['proxy_string'], 30)}...", 
                callback_data=f"del_proxy_{proxy['id']}"
            )
        ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_settings")])
    return keyboard

def get_admin_proxy_delete_inline():
    proxies = db.get_proxies()
    if not proxies:
        return None
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for proxy in proxies:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🗑 {truncate_text(proxy['proxy_string'], 30)}...", 
                callback_data=f"del_admin_proxy_{proxy['id']}"
            )
        ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_proxies")])
    return keyboard

# ===== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ =====
def setup_handlers(dp: Dispatcher):
    
    # ===== СТАРТ =====
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        user = message.from_user
        db.create_user(user.id, user.username, user.first_name)
        logger.info(f"Пользователь {user.id} запустил бота")
        await message.answer(
            "🦆 **DUCK SPAM**\n\n_Выберите действие:_",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

    # ===== НАЗАД =====
    @dp.callback_query(lambda c: c.data == "back_to_main")
    async def back_to_main(callback: types.CallbackQuery):
        await callback.message.delete()
        await callback.message.answer(
            "🦆 **DUCK SPAM**\n\n_Выберите действие:_",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "back_settings")
    async def back_settings(callback: types.CallbackQuery):
        await callback.message.delete()
        await show_settings_callback(callback)
        await callback.answer()

    # ===== ПРОФИЛЬ =====
    @dp.message(lambda m: m.text == "👤 Профиль")
    async def show_profile(message: types.Message):
        user_id = message.from_user.id
        user = db.get_user(user_id)
        sessions = db.get_sessions(user_id)

        proxy_text = "🚫 Не назначен"
        if user and user['proxy_id']:
            proxy = db.get_proxy(user['proxy_id'])
            if proxy:
                proxy_text = f"✅ {truncate_text(proxy['proxy_string'], 40)}..."

        text = (
            f"👤 **ПРОФИЛЬ**\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"📅 _Регистрация:_ {user['reg_date'] if user else 'Неизвестно'}\n"
            f"📊 _Загружено аккаунтов:_ {user['total_sessions_loaded'] if user else 0}\n"
            f"📱 _Аккаунтов сейчас:_ {len(sessions)}\n"
            f"🌐 _Прокси:_ {proxy_text}"
        )
        await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    # ===== АККАУНТЫ =====
    @dp.message(lambda m: m.text == "📱 Загрузить аккаунты")
    async def show_accounts_menu(message: types.Message):
        user_id = message.from_user.id
        sessions = db.get_sessions(user_id)
        text = (
            "📂 **Управление аккаунтами**\n\n"
            "_• Загружайте .session файлы (Telethon/Pyrogram)_\n"
            "_• Проверяйте работоспособность аккаунтов_\n"
            "_• Запускайте рассылку одновременно на все аккаунты_\n\n"
            f"📱 _Аккаунтов:_ {len(sessions)}"
        )
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_accounts_inline(len(sessions))
        )

    @dp.callback_query(lambda c: c.data == "add_session")
    async def add_session(callback: types.CallbackQuery):
        await callback.message.edit_text(
            "📄 **Загрузка .session**\n\n_Отправьте .session файл или ZIP архив с .session файлами._",
            parse_mode="Markdown"
        )
        await callback.answer()

    @dp.message(lambda message: message.document)
    async def handle_document(message: types.Message):
        user_id = message.from_user.id
        doc = message.document
        fname = doc.file_name.lower()
        logger.info(f"Пользователь {user_id} отправил файл: {fname}")

        # ===== ФАЙЛЫ ДЛЯ ШАБЛОНА =====
        is_template_file = any(fname.endswith(ext) for ext in ['.apk', '.jpg', '.png', '.mp4', '.gif', '.pdf'])
        
        if is_template_file:
            template = db.get_template(user_id)
            if template and template['text']:
                if template['file_path']:
                    old_file = os.path.join(MEDIA_DIR, f"template_{user_id}_{template['file_path']}")
                    if os.path.exists(old_file):
                        try:
                            os.remove(old_file)
                        except Exception as e:
                            logger.warning(f"Не удалось удалить старый файл: {e}")
                
                file_path = os.path.join(MEDIA_DIR, f"template_{user_id}_{doc.file_name}")
                await message.bot.download(doc, file_path)
                db.save_template(user_id, text=template['text'], file_path=doc.file_name)
                await message.answer(
                    f"✅ **Файл добавлен в шаблон!**\n\n📁 {doc.file_name}",
                    parse_mode="Markdown",
                    reply_markup=get_template_inline()
                )
                return
            else:
                await message.answer(
                    "❌ _Сначала создайте текст шаблона в разделе 📝 Шаблон._",
                    parse_mode="Markdown",
                    reply_markup=get_main_keyboard()
                )
                return

        # ===== .SESSION ФАЙЛЫ =====
        if fname.endswith('.session'):
            file_path = os.path.join(MEDIA_DIR, f"temp_{user_id}_{doc.file_name}")
            await message.bot.download(doc, file_path)
            result = await load_session_file(user_id, file_path)
            if os.path.exists(file_path):
                os.remove(file_path)
            
            if result['status'] == 'success':
                logger.info(f"Загружена сессия для {result.get('username')}, контактов: {result.get('total_contacts', 0)}")
                await message.answer(
                    f"✅ **Сессия загружена!**\n\n📱 @{result.get('username', 'Неизвестно')}\n"
                    f"📋 _Контактов:_ {result.get('total_contacts', 0)}\n"
                    f"🔄 _Взаимных:_ {result.get('mutual_contacts', 0)}",
                    parse_mode="Markdown",
                    reply_markup=get_main_keyboard()
                )
                await show_accounts_menu(message)
            else:
                await message.answer(
                    f"❌ **Ошибка:** {result.get('error', 'Неизвестная ошибка')}",
                    parse_mode="Markdown",
                    reply_markup=get_main_keyboard()
                )
            return

        # ===== ZIP АРХИВЫ =====
        if fname.endswith('.zip'):
            import zipfile
            import shutil
            
            file_path = os.path.join(MEDIA_DIR, f"temp_{user_id}_{doc.file_name}")
            await message.bot.download(doc, file_path)
            await message.answer("⏳ _Обработка архива..._", parse_mode="Markdown", reply_markup=get_main_keyboard())

            temp_dir = os.path.join(MEDIA_DIR, f"session_temp_{user_id}")
            os.makedirs(temp_dir, exist_ok=True)
            
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    zf.extractall(temp_dir)
                
                results = []
                for f in os.listdir(temp_dir):
                    if f.endswith('.session'):
                        session_path = os.path.join(temp_dir, f)
                        result = await load_session_file(user_id, session_path)
                        results.append(result)
                
                shutil.rmtree(temp_dir)
                
                success = [r for r in results if r['status'] == 'success']
                errors = [r for r in results if r['status'] == 'error']
                
                text = f"📄 **Результат загрузки:**\n\n✅ _Успешно:_ {len(success)}\n❌ _Ошибок:_ {len(errors)}"
                await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())
                await show_accounts_menu(message)
                
            except Exception as e:
                logger.error(f"Ошибка распаковки ZIP: {e}")
                await message.answer(f"❌ _Ошибка распаковки: {str(e)[:100]}_", parse_mode="Markdown", reply_markup=get_main_keyboard())
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        await message.answer("❌ _Неподдерживаемый формат_", parse_mode="Markdown", reply_markup=get_main_keyboard())

    # ===== ПРОВЕРКА АККАУНТОВ =====
    @dp.callback_query(lambda c: c.data == "check_sessions")
    async def check_sessions(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        sessions = db.get_sessions(user_id)
        if not sessions:
            await callback.message.edit_text("❌ _Нет аккаунтов для проверки_", parse_mode="Markdown")
            await callback.answer()
            return

        await callback.message.edit_text(
            "🔍 **Проверка аккаунтов...**\n\n_⏳ Пожалуйста, подождите..._",
            parse_mode="Markdown"
        )

        user = db.get_user(user_id)
        proxy_dict = None
        if user and user['proxy_id']:
            proxy = db.get_proxy(user['proxy_id'])
            if proxy:
                proxy_dict = get_proxy_dict(proxy['proxy_string'])

        results = []
        for session in sessions:
            is_valid, msg = await check_session(session['id'], user_id, proxy_dict)
            results.append({"session": session, "valid": is_valid, "msg": msg})

        text = "🔍 **Результат проверки:**\n\n"
        valid = [r for r in results if r['valid']]
        invalid = [r for r in results if not r['valid']]
        
        for r in valid[:10]:
            username = r['session']['username'] if r['session']['username'] else r['session']['phone']
            total = r['session']['total_contacts'] or 0
            mutual = r['session']['mutual_contacts'] or 0
            text += f"✅ @{username} | контактов: {total} | взаимных: {mutual}\n"
        for r in invalid[:10]:
            username = r['session']['username'] if r['session']['username'] else r['session']['phone']
            text += f"❌ @{username} | ошибка: {r['msg']}\n"
        text += f"\n\n✅ Работают: {len(valid)}\n❌ Не работают: {len(invalid)}"
        
        await callback.message.edit_text(text, reply_markup=get_accounts_inline(len(sessions)))
        await callback.answer()

    # ===== УДАЛЕНИЕ =====
    @dp.callback_query(lambda c: c.data == "delete_invalid")
    async def delete_invalid(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        sessions = db.get_sessions(user_id)
        invalid = [s for s in sessions if not s['is_valid']]
        if not invalid:
            await callback.message.edit_text(
                "❌ _Нет невалидных аккаунтов_", 
                parse_mode="Markdown", 
                reply_markup=get_accounts_inline(len(sessions))
            )
            await callback.answer()
            return
        
        for session in invalid:
            session_path = os.path.join(SESSIONS_DIR, session['session_name'])
            if os.path.exists(f"{session_path}.session"):
                try:
                    os.remove(f"{session_path}.session")
                except Exception as e:
                    logger.error(f"Не удалось удалить файл сессии: {e}")
            db.delete_session(session['id'])
        
        sessions = db.get_sessions(user_id)
        await callback.message.edit_text(
            f"🗑 _Удалено {len(invalid)} невалидных аккаунтов_", 
            parse_mode="Markdown", 
            reply_markup=get_accounts_inline(len(sessions))
        )
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "delete_all")
    async def delete_all_sessions(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        sessions = db.get_sessions(user_id)
        if not sessions:
            await callback.message.edit_text(
                "❌ _Нет аккаунтов для удаления_", 
                parse_mode="Markdown", 
                reply_markup=get_accounts_inline(0)
            )
            await callback.answer()
            return
        
        for session in sessions:
            session_path = os.path.join(SESSIONS_DIR, session['session_name'])
            if os.path.exists(f"{session_path}.session"):
                try:
                    os.remove(f"{session_path}.session")
                except Exception as e:
                    logger.error(f"Не удалось удалить файл сессии: {e}")
            db.delete_session(session['id'])
        
        await callback.message.edit_text(
            f"🗑 _Удалено {len(sessions)} аккаунтов_", 
            parse_mode="Markdown", 
            reply_markup=get_accounts_inline(0)
        )
        await callback.answer()

    # ===== СПИСОК АККАУНТОВ =====
    @dp.callback_query(lambda c: c.data == "list_sessions")
    async def list_sessions(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        sessions = db.get_sessions(user_id)
        if not sessions:
            await callback.message.edit_text(
                "❌ _Нет аккаунтов_", 
                parse_mode="Markdown", 
                reply_markup=get_accounts_inline(0)
            )
            await callback.answer()
            return
        
        text = "📋 **Ваши аккаунты:**\n\n"
        for i, session in enumerate(sessions[:20], 1):
            username = session['username'] if session['username'] else session['phone']
            status = "✅" if session['is_valid'] else "❌"
            total = session['total_contacts'] or 0
            mutual = session['mutual_contacts'] or 0
            text += f"{i}. {status} @{username} | _контактов:_ {total} | _взаимных:_ {mutual}\n"
        if len(sessions) > 20:
            text += f"\n_...и еще {len(sessions)-20} аккаунтов_"
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_accounts_inline(len(sessions)))
        await callback.answer()

    # ===== РАССЫЛКА =====
    @dp.callback_query(lambda c: c.data == "start_broadcast")
    async def start_broadcast(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        
        sessions = db.get_valid_sessions(user_id)
        if not sessions:
            await callback.message.edit_text(
                "❌ _Нет валидных аккаунтов для рассылки_", 
                parse_mode="Markdown", 
                reply_markup=get_accounts_inline(0)
            )
            await callback.answer()
            return
        
        template = db.get_template(user_id)
        if not template or not template['text']:
            await callback.message.edit_text(
                "❌ _Сначала создайте шаблон в разделе 📝 Шаблон_", 
                parse_mode="Markdown", 
                reply_markup=get_accounts_inline(len(sessions))
            )
            await callback.answer()
            return
        
        user = db.get_user(user_id)
        settings = {
            "delay": user['delay'] if user else 3,
            "only_mutual": user['only_mutual'] if user else False,
            "delete_after_send": user['delete_after_send'] if user else False,
            "auto_delete_invalid": user['auto_delete_invalid'] if user else False
        }

        broadcast_id = await broadcast_engine.start_broadcast(
            user_id=user_id,
            sessions=sessions,
            template=template,
            settings=settings,
            bot=callback.bot
        )
        
        user_broadcasts[user_id] = broadcast_id
        
        await callback.message.delete()
        new_message = await callback.message.answer("🚀 _Рассылка запущена..._", parse_mode="Markdown")
        
        asyncio.create_task(update_broadcast_status(new_message, broadcast_id))
        await callback.answer()

    async def update_broadcast_status(message: types.Message, broadcast_id: str):
        """Обновление статуса рассылки"""
        while True:
            progress = broadcast_engine.get_progress(broadcast_id)
            if not progress:
                break
            
            status = progress['status']
            
            if status == "completed":
                text = "📄 **Рассылка завершена**\n\n"
                text += f"✅ Сообщений всего успешно: {progress['sent']}\n"
                text += f"❌ Сообщений неудачно: {progress['failed']}\n"
                error_accounts = sum(1 for s in progress['sessions_status'].values() if s.get('status') == 'error')
                text += f"⚠️ Аккаунтов с ошибкой: {error_accounts}\n\n"
                for s_id, s_data in progress['sessions_status'].items():
                    name = s_data.get('name', 'Неизвестно')
                    sent_ok = s_data.get('sent', 0)
                    sent_fail = s_data.get('failed', 0)
                    status_icon = "✅" if s_data.get('status') == 'completed' else "❌"
                    text += f"{status_icon} {name}: {sent_ok}✓ {sent_fail}✗\n"
                
                for uid, bid in list(user_broadcasts.items()):
                    if bid == broadcast_id:
                        del user_broadcasts[uid]
                        break
                
                try:
                    await message.edit_text(text, parse_mode="Markdown", reply_markup=get_accounts_inline(0))
                except Exception as e:
                    logger.warning(f"Ошибка обновления статуса: {e}")
                break
            
            if status == "stopped":
                for uid, bid in list(user_broadcasts.items()):
                    if bid == broadcast_id:
                        del user_broadcasts[uid]
                        break
                try:
                    await message.edit_text("⏹ _Рассылка остановлена_", parse_mode="Markdown", reply_markup=get_accounts_inline(0))
                except Exception as e:
                    logger.warning(f"Ошибка обновления статуса: {e}")
                break
            
            # Прогресс
            sessions_status = progress['sessions_status']
            stats = progress['stats']
            total_accounts = len(sessions_status)
            
            text = f"🚀 **Рассылка на {total_accounts} аккаунтов**\n"
            text += f"🔄 Работают: {stats['running']} | 🕓 Ждут: {stats['waiting']} | ✅ Готовы: {stats['completed']} | ❌ Ошибки: {stats['error']}\n\n"
            
            for s_id, s_data in list(sessions_status.items())[:10]:
                name = s_data.get('name', 'Неизвестно')
                status_icon = {
                    'running': '🔄',
                    'completed': '🟢',
                    'error': '🔴',
                    'waiting': '🕓'
                }.get(s_data.get('status'), '🕓')
                sent_ok = s_data.get('sent', 0)
                sent_fail = s_data.get('failed', 0)
                total_contacts = s_data.get('total_contacts', 0)
                error_msg = s_data.get('error_msg', '')
                
                if status_icon == "🔴":
                    text += f"{status_icon} {name}: ✅{sent_ok} ❌{sent_fail} | контактов: {total_contacts} | ошибка: {truncate_text(error_msg, 30)}\n"
                else:
                    text += f"{status_icon} {name}: ✅{sent_ok} ❌{sent_fail} | контактов: {total_contacts}\n"
            
            if len(sessions_status) > 10:
                text += f"\n_...и еще {len(sessions_status)-10} аккаунтов_"
            
            text += f"\n\n📊 Итого: ✅{progress['sent']} ❌{progress['failed']}\n"
            text += f"\n_Обновление каждые 5 сек._"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏹️ Остановить рассылку", callback_data="stop_broadcast")]
            ])
            
            try:
                await message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
            except Exception as e:
                logger.warning(f"Ошибка обновления статуса: {e}")
            
            await asyncio.sleep(5)

    @dp.callback_query(lambda c: c.data == "stop_broadcast")
    async def stop_broadcast(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        broadcast_id = user_broadcasts.get(user_id)
        if broadcast_id:
            broadcast_engine.stop_broadcast(broadcast_id)
            await callback.message.edit_text("⏹ _Рассылка остановлена_", parse_mode="Markdown", reply_markup=get_accounts_inline(0))
            await callback.answer("Рассылка остановлена")
        else:
            await callback.answer("Нет активной рассылки", show_alert=True)

    # ===== ШАБЛОН =====
    @dp.message(lambda m: m.text == "📝 Шаблон")
    async def show_template_menu(message: types.Message):
        user_id = message.from_user.id
        template = db.get_template(user_id)

        has_file = bool(template and template['file_path'])
        has_link = bool(template and template['link_url'])
        text_content = template['text'] if template and template['text'] else "Помнишь?"
        
        file_name = "Нет"
        if has_file:
            file_name = template['file_path']

        text = "❓ **Вы хотите изменить шаблон?**\n\n"
        text += f"📁 _Файл:_ {file_name}\n"
        text += f"🌐 _Прикреплённая ссылка:_ {'Есть' if has_link else 'Нету'}\n"
        text += f"\n📝 _Текущий текст шаблона:_\n\n{text_content[:500]}"
        if len(text_content) > 500:
            text += "\n\n_...текст обрезан_"

        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_template_inline()
        )

    @dp.callback_query(lambda c: c.data == "add_file")
    async def add_file(callback: types.CallbackQuery):
        await callback.message.edit_text(
            "📎 **Добавление файла в шаблон**\n\n_Отправьте файл (фото/видео/документ/APK)._\n_Он будет прикрепляться к каждому сообщению._",
            parse_mode="Markdown"
        )
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "edit_text")
    async def edit_text(callback: types.CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "✏️ **Введите новый текст шаблона**\n\n_Просто напишите сообщение с текстом для рассылки._",
            parse_mode="Markdown"
        )
        await state.set_state(TemplateStates.waiting_for_text)
        await callback.answer()

    @dp.message(TemplateStates.waiting_for_text)
    async def process_text(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        text = message.text
        template = db.get_template(user_id)
        if template:
            db.save_template(user_id, text=text, file_path=template['file_path'], 
                           link_url=template['link_url'], link_text=template['link_text'])
        else:
            db.save_template(user_id, text=text)
        await state.clear()
        await message.answer("✅ _Текст шаблона сохранен!_", parse_mode="Markdown", reply_markup=get_template_inline())

    @dp.callback_query(lambda c: c.data == "keep_text")
    async def keep_text(callback: types.CallbackQuery):
        await callback.message.edit_text("✅ _Текст оставлен без изменений_", parse_mode="Markdown", reply_markup=get_template_inline())
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "add_link")
    async def add_link(callback: types.CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "🔗 **Добавить гипер-ссылку**\n\n_Отправьте URL ссылки._\nНапример: `https://t.me/duck_spam`",
            parse_mode="Markdown"
        )
        await state.set_state(TemplateStates.waiting_for_link_url)
        await callback.answer()

    @dp.message(TemplateStates.waiting_for_link_url)
    async def process_link_url(message: types.Message, state: FSMContext):
        url = message.text.strip()
        await state.update_data(link_url=url)
        await message.answer(
            "🔗 **Теперь отправьте текст для ссылки**\n\n_Например: `Нажми сюда`_",
            parse_mode="Markdown"
        )
        await state.set_state(TemplateStates.waiting_for_link_text)

    @dp.message(TemplateStates.waiting_for_link_text)
    async def process_link_text(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        link_text = message.text
        data = await state.get_data()
        link_url = data.get('link_url')

        template = db.get_template(user_id)
        if template:
            db.save_template(user_id, text=template['text'], file_path=template['file_path'], 
                           link_url=link_url, link_text=link_text)
        else:
            db.save_template(user_id, link_url=link_url, link_text=link_text)

        await state.clear()
        await message.answer("✅ _Ссылка добавлена в шаблон!_", parse_mode="Markdown", reply_markup=get_template_inline())

    @dp.callback_query(lambda c: c.data == "remove_link")
    async def remove_link(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        template = db.get_template(user_id)
        if template:
            db.save_template(user_id, text=template['text'], file_path=template['file_path'], 
                           link_url=None, link_text=None)
            await callback.message.edit_text("🚫 _Ссылка удалена_", parse_mode="Markdown", reply_markup=get_template_inline())
        else:
            await callback.message.edit_text("❌ _Нет ссылки для удаления_", parse_mode="Markdown", reply_markup=get_template_inline())
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "remove_file")
    async def remove_file(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        template = db.get_template(user_id)
        if template and template['file_path']:
            file_path = os.path.join(MEDIA_DIR, f"template_{user_id}_{template['file_path']}")
            if os.path.exists(file_path):
                os.remove(file_path)
            db.save_template(user_id, text=template['text'], file_path=None, 
                           link_url=template['link_url'], link_text=template['link_text'])
            await callback.message.edit_text("🗑 _Файл удален_", parse_mode="Markdown", reply_markup=get_template_inline())
        else:
            await callback.message.edit_text("❌ _Нет файла для удаления_", parse_mode="Markdown", reply_markup=get_template_inline())
        await callback.answer()

    # ===== НАСТРОЙКИ =====
    @dp.message(lambda m: m.text == "⚙️ Настройки")
    async def show_settings(message: types.Message):
        await show_settings_callback_from_message(message)

    async def show_settings_callback_from_message(message: types.Message):
        user_id = message.from_user.id
        user = db.get_user(user_id)
        if not user:
            await message.answer("❌ _Ошибка_", parse_mode="Markdown", reply_markup=get_main_keyboard())
            return

        proxy_text = "🚫 Не назначен"
        if user['proxy_id']:
            proxy = db.get_proxy(user['proxy_id'])
            if proxy:
                proxy_text = f"✅ {truncate_text(proxy['proxy_string'], 40)}..."

        text = (
            f"⚙️ **Настройки**\n\n"
            f"🔄 _Только взаимные_ - {'✅ ВКЛ' if user['only_mutual'] else '❌ ВЫКЛ'}\n"
            f"⏱ _Задержка_ - {user['delay']} сек\n"
            f"🗑 _Удаление сообщений_ - {'✅ ВКЛ' if user['delete_after_send'] else '❌ ВЫКЛ'}\n"
            f"🔄 _Сброс сессий_ - {'✅ ВКЛ' if user['auto_delete_invalid'] else '❌ ВЫКЛ'}\n\n"
            f"🌐 _Прокси:_ {proxy_text}"
        )
        
        await message.answer(text, parse_mode="Markdown", reply_markup=get_settings_inline())

    async def show_settings_callback(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        if not user:
            await callback.message.edit_text("❌ _Ошибка_", parse_mode="Markdown")
            return

        proxy_text = "🚫 Не назначен"
        if user['proxy_id']:
            proxy = db.get_proxy(user['proxy_id'])
            if proxy:
                proxy_text = f"✅ {truncate_text(proxy['proxy_string'], 40)}..."

        text = (
            f"⚙️ **Настройки**\n\n"
            f"🔄 _Только взаимные_ - {'✅ ВКЛ' if user['only_mutual'] else '❌ ВЫКЛ'}\n"
            f"⏱ _Задержка_ - {user['delay']} сек\n"
            f"🗑 _Удаление сообщений_ - {'✅ ВКЛ' if user['delete_after_send'] else '❌ ВЫКЛ'}\n"
            f"🔄 _Сброс сессий_ - {'✅ ВКЛ' if user['auto_delete_invalid'] else '❌ ВЫКЛ'}\n\n"
            f"🌐 _Прокси:_ {proxy_text}"
        )
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_settings_inline())

    @dp.callback_query(lambda c: c.data == "toggle_mutual")
    async def toggle_mutual(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        new_value = 0 if user['only_mutual'] else 1
        db.update_user_settings(user_id, only_mutual=new_value)
        await show_settings_callback(callback)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "toggle_delete")
    async def toggle_delete(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        new_value = 0 if user['delete_after_send'] else 1
        db.update_user_settings(user_id, delete_after_send=new_value)
        await show_settings_callback(callback)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "toggle_reset")
    async def toggle_reset(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        new_value = 0 if user['auto_delete_invalid'] else 1
        db.update_user_settings(user_id, auto_delete_invalid=new_value)
        await show_settings_callback(callback)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "change_delay")
    async def change_delay(callback: types.CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "⏱ **Введите новую задержку**\n\n_Число от 1 до 60 секунд._",
            parse_mode="Markdown"
        )
        await state.set_state(AdminStates.waiting_for_delay)
        await callback.answer()

    @dp.message(AdminStates.waiting_for_delay)
    async def process_delay(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        try:
            delay = int(message.text.strip())
            if 1 <= delay <= 60:
                db.update_user_settings(user_id, delay=delay)
                await message.answer(f"✅ _Задержка установлена: {delay} сек_", parse_mode="Markdown", reply_markup=get_main_keyboard())
            else:
                await message.answer("❌ _Введите число от 1 до 60_", parse_mode="Markdown", reply_markup=get_main_keyboard())
        except ValueError:
            await message.answer("❌ _Введите число_", parse_mode="Markdown", reply_markup=get_main_keyboard())
        await state.clear()

    @dp.callback_query(lambda c: c.data == "select_proxy")
    async def select_proxy(callback: types.CallbackQuery):
        keyboard = get_proxy_selection_inline()
        if not keyboard:
            await callback.message.edit_text("❌ _Нет доступных прокси_", parse_mode="Markdown", reply_markup=get_main_keyboard())
            await callback.answer()
            return
        await callback.message.edit_text("🌐 **Выберите прокси:**", parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(lambda c: c.data.startswith("set_proxy_"))
    async def set_proxy(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        proxy_id = int(callback.data.split("_")[2])
        db.set_user_proxy(user_id, proxy_id)
        await show_settings_callback(callback)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "add_my_proxy")
    async def add_my_proxy(callback: types.CallbackQuery):
        await callback.message.edit_text(
            "➕ **Добавить прокси**\n\n_Отправьте прокси в формате:_\n`socks5://user:pass@host:port`\n_или_\n`http://host:port`\n\n_Пример: `socks5://user:pass@154.196.21.238:63889`_",
            parse_mode="Markdown"
        )
        await callback.answer()

    @dp.message(lambda m: m.text and any(x in m.text for x in ['socks5://', 'http://', 'socks4://']))
    async def process_my_proxy(message: types.Message):
        user_id = message.from_user.id
        proxy_string = message.text.strip()
        
        is_work, msg = await test_proxy(proxy_string)
        
        if is_work:
            proxy_type = proxy_string.split('://')[0]
            db.add_proxy(proxy_string, proxy_type, user_id)
            await message.answer(f"✅ _Прокси добавлен и работает!_\n{msg}", parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            await message.answer(f"❌ _Прокси не работает:_\n{msg}", parse_mode="Markdown", reply_markup=get_main_keyboard())

    @dp.callback_query(lambda c: c.data == "remove_my_proxy")
    async def remove_my_proxy(callback: types.CallbackQuery):
        keyboard = get_proxy_delete_inline()
        if not keyboard:
            await callback.message.edit_text("❌ _Нет прокси для удаления_", parse_mode="Markdown", reply_markup=get_main_keyboard())
            await callback.answer()
            return
        await callback.message.edit_text("🗑 **Выберите прокси для удаления:**", parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(lambda c: c.data.startswith("del_proxy_"))
    async def delete_selected_proxy(callback: types.CallbackQuery):
        proxy_id = int(callback.data.split("_")[2])
        db.delete_proxy(proxy_id)
        await show_settings_callback(callback)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "test_proxies")
    async def test_proxies(callback: types.CallbackQuery):
        proxies = db.get_proxies()
        if not proxies:
            await callback.message.edit_text("❌ _Нет прокси для проверки_", parse_mode="Markdown")
            await callback.answer()
            return
        
        await callback.message.edit_text("🔍 _Проверка прокси..._\n\n_⏳ Пожалуйста, подождите..._", parse_mode="Markdown")
        
        results = []
        for proxy in proxies:
            result = await test_proxy_with_ping(proxy['proxy_string'])
            results.append({
                "id": proxy['id'],
                "string": proxy['proxy_string'],
                "status": result['status'],
                "recommendation": result['recommendation'],
                "ping": result['ping'],
                "is_work": result['is_work']
            })
        
        text = "🔍 **Результат проверки прокси:**\n\n"
        for r in results:
            text += f"{r['status']}\n"
            text += f"{r['recommendation']}\n"
            text += f"{r['ping']}\n"
            text += f"📌 {truncate_text(r['string'], 50)}\n\n"
            text += "─" * 20 + "\n\n"
        
        if len(text) > 4000:
            text = text[:3900] + "\n\n_...текст обрезан_"
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_settings_inline())
        await callback.answer()

    # ===== АДМИН-ПАНЕЛЬ =====
    @dp.message(lambda m: m.text == "🔐 Админ-панель")
    async def show_admin(message: types.Message):
        user_id = message.from_user.id
        if user_id not in ADMIN_IDS:
            await message.answer("⛔ _Доступ запрещен_", parse_mode="Markdown", reply_markup=get_main_keyboard())
            return

        stats = db.get_total_stats()
        text = (
            f"🔐 **АДМИН-ПАНЕЛЬ**\n\n"
            f"📊 **СТАТИСТИКА:**\n"
            f"👥 _Пользователей:_ {stats['total_users']}\n"
            f"✅ _С доступом:_ {stats['subscribed_users']}\n"
            f"📨 _Рассылок выполнено:_ {stats['total_broadcasts']}\n"
            f"📩 _Сообщений отправлено:_ {stats['total_success']}\n"
            f"❌ _Ошибок доставки:_ {stats['total_failed']}\n"
            f"📱 _Аккаунтов подключено:_ {stats['total_sessions']}\n"
            f"🌐 _Прокси в базе:_ {stats['total_proxies']}"
        )
        await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_inline())

    @dp.callback_query(lambda c: c.data == "admin_users")
    async def admin_users(callback: types.CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Выдать доступ", callback_data="give_access")],
            [InlineKeyboardButton(text="➖ Забрать доступ", callback_data="remove_access")],
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_admin")]
        ])
        await callback.message.edit_text("👥 **УПРАВЛЕНИЕ ДОСТУПОМ**\n\n_Выберите действие:_", parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "back_admin")
    async def back_admin(callback: types.CallbackQuery):
        await callback.message.delete()
        await show_admin(callback.message)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "give_access")
    async def give_access(callback: types.CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await state.set_data({"action": "give"})
        await callback.message.edit_text(
            "➕ **ВЫДАТЬ ДОСТУП**\n\n_Отправьте ID пользователя._\nНапример: `123456789`",
            parse_mode="Markdown"
        )
        await state.set_state(AdminStates.waiting_for_user_id)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "remove_access")
    async def remove_access(callback: types.CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await state.set_data({"action": "remove"})
        await callback.message.edit_text(
            "➖ **ЗАБРАТЬ ДОСТУП**\n\n_Отправьте ID пользователя._\nНапример: `123456789`",
            parse_mode="Markdown"
        )
        await state.set_state(AdminStates.waiting_for_user_id)
        await callback.answer()

    @dp.message(AdminStates.waiting_for_user_id)
    async def process_access(message: types.Message, state: FSMContext):
        try:
            target_id = int(message.text.strip())
            user = db.get_user(target_id)
            if not user:
                await message.answer(f"❌ _Пользователь {target_id} не найден_", parse_mode="Markdown", reply_markup=get_admin_inline())
                await state.clear()
                return
            
            data = await state.get_data()
            action = data.get("action", "give")
            
            if action == "give":
                db.update_user_settings(target_id, subscribed=1)
                await message.answer(f"✅ _Пользователю {target_id} выдан доступ!_", parse_mode="Markdown", reply_markup=get_admin_inline())
            else:
                db.update_user_settings(target_id, subscribed=0)
                await message.answer(f"✅ _У пользователя {target_id} забран доступ!_", parse_mode="Markdown", reply_markup=get_admin_inline())
        except ValueError:
            await message.answer("❌ _Неверный ID. Отправьте число._", parse_mode="Markdown", reply_markup=get_admin_inline())
        except Exception as e:
            logger.error(f"Ошибка в process_access: {e}")
            await message.answer(f"❌ _Ошибка: {str(e)[:50]}_", parse_mode="Markdown", reply_markup=get_admin_inline())
        await state.clear()

    @dp.callback_query(lambda c: c.data == "list_users")
    async def list_users(callback: types.CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        
        users = db.get_all_users(20)
        if not users:
            text = "📋 **Список пользователей**\n\n_Нет пользователей_"
        else:
            text = "📋 **Список пользователей:**\n\n"
            for u in users:
                status = "✅" if u['subscribed'] else "❌"
                name = u['username'] if u['username'] else u['first_name']
                text += f"{status} {name} (ID: {u['id']})\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")]
        ])
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "admin_proxies")
    async def admin_proxies(callback: types.CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        
        proxies = db.get_proxies()
        text = "🌐 **УПРАВЛЕНИЕ ПРОКСИ**\n\n"
        if proxies:
            text += "Список прокси:\n"
            for p in proxies[:10]:
                text += f"🔹 {truncate_text(p['proxy_string'], 50)}... (ID: {p['id']})\n"
            if len(proxies) > 10:
                text += f"\n_...и еще {len(proxies)-10} прокси_"
        else:
            text += "_Нет прокси в базе_"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить прокси", callback_data="add_admin_proxy")],
            [InlineKeyboardButton(text="🗑 Удалить прокси", callback_data="del_admin_proxy")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_admin")]
        ])
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "add_admin_proxy")
    async def add_admin_proxy(callback: types.CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await callback.message.edit_text(
            "➕ **Добавить прокси**\n\n_Отправьте прокси в формате:_\n`socks5://user:pass@host:port`\n_или_\n`http://host:port`",
            parse_mode="Markdown"
        )
        await state.set_state(AdminStates.waiting_for_proxy_string)
        await callback.answer()

    @dp.message(AdminStates.waiting_for_proxy_string)
    async def process_admin_add_proxy(message: types.Message, state: FSMContext):
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("⛔ Доступ запрещен", reply_markup=get_main_keyboard())
            await state.clear()
            return
        proxy_string = message.text.strip()
        if '://' in proxy_string:
            proxy_type = proxy_string.split('://')[0]
            db.add_proxy(proxy_string, proxy_type, message.from_user.id)
            await message.answer("✅ _Прокси добавлен в базу!_", parse_mode="Markdown", reply_markup=get_admin_inline())
        else:
            await message.answer("❌ _Неверный формат прокси_", parse_mode="Markdown", reply_markup=get_admin_inline())
        await state.clear()

    @dp.callback_query(lambda c: c.data == "del_admin_proxy")
    async def del_admin_proxy(callback: types.CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        keyboard = get_admin_proxy_delete_inline()
        if not keyboard:
            await callback.message.edit_text("❌ _Нет прокси для удаления_", parse_mode="Markdown", reply_markup=get_admin_inline())
            await callback.answer()
            return
        await callback.message.edit_text("🗑 **Выберите прокси для удаления:**", parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(lambda c: c.data.startswith("del_admin_proxy_"))
    async def delete_admin_proxy(callback: types.CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        proxy_id = int(callback.data.split("_")[3])
        db.delete_proxy(proxy_id)
        await callback.message.edit_text("🗑 _Прокси удален!_", parse_mode="Markdown", reply_markup=get_admin_inline())
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "admin_logs")
    async def admin_logs(callback: types.CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        
        logs = db.get_broadcast_logs(10)
        if not logs:
            text = "📊 **Логи рассылок**\n\n_Нет записей_"
        else:
            text = "📊 **Последние рассылки:**\n\n"
            for log in logs:
                text += f"🆔 #{log['id']}\n"
                text += f"👤 Пользователь: {log['user_id']}\n"
                text += f"📅 {log['datetime']}\n"
                text += f"✅ Успешно: {log['success']} | ❌ Ошибок: {log['failed']}\n"
                text += f"⏱ Длительность: {format_time(log['duration_seconds'])}\n"
                text += "─" * 20 + "\n\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_admin")]
        ])
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()
