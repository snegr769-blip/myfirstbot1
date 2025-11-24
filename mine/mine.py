import sqlite3
import logging
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import datetime
import re

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен вашего бота
TOKEN = "8465058780:AAEaiC30ddSmsloRO_W-kTMh0W13wj4Oadk"

# Словарь для хранения задач авторазмута
unmute_tasks = {}

# Магазин предметов
SHOP_ITEMS = {
    # Страница 1 - Знаки зодиака
    1: [
        {"emoji": "♈", "name": "Овен", "price": 250},
        {"emoji": "♉", "name": "Телец", "price": 250},
        {"emoji": "♊", "name": "Близнецы", "price": 250},
        {"emoji": "♋", "name": "Рак", "price": 250},
        {"emoji": "♌", "name": "Лев", "price": 250},
        {"emoji": "♍", "name": "Дева", "price": 250},
        {"emoji": "♎", "name": "Весы", "price": 250},
        {"emoji": "♏", "name": "Скорпион", "price": 250},
        {"emoji": "♐", "name": "Стрелец", "price": 250},
        {"emoji": "♑", "name": "Козерог", "price": 250},
        {"emoji": "♒", "name": "Водолей", "price": 250},
        {"emoji": "♓", "name": "Рыбы", "price": 250},
    ],
    # Страница 2 - Эмоции и символы
    2: [
        {"emoji": "💤", "name": "Сон", "price": 300},
        {"emoji": "💦", "name": "Капли", "price": 350},
        {"emoji": "☮", "name": "Мир", "price": 400},
        {"emoji": "✝", "name": "Крест", "price": 400},
        {"emoji": "❤", "name": "Сердце", "price": 500},
        {"emoji": "💔", "name": "Разбитое сердце", "price": 500},
        {"emoji": "💕", "name": "Два сердца", "price": 550},
        {"emoji": "💖", "name": "Блестящее сердце", "price": 550},
    ],
    # Страница 3 - Символы и звезды
    3: [
        {"emoji": "♾", "name": "Бесконечность", "price": 600},
        {"emoji": "⚛", "name": "Атом", "price": 600},
        {"emoji": "⚠", "name": "Предупреждение", "price": 600},
        {"emoji": "💎", "name": "Алмаз", "price": 700},
        {"emoji": "🌌", "name": "Галактика", "price": 750},
        {"emoji": "⭐", "name": "Звезда", "price": 750},
        {"emoji": "✨", "name": "Искры", "price": 800},
    ],
    # Страница 4 - Природа и еда
    4: [
        {"emoji": "🎨", "name": "Палитра", "price": 850},
        {"emoji": "🍪", "name": "Печенье", "price": 900},
        {"emoji": "🍑", "name": "Персик", "price": 900},
        {"emoji": "🍄", "name": "Гриб", "price": 900},
        {"emoji": "🍓", "name": "Клубника", "price": 900},
        {"emoji": "🍒", "name": "Вишня", "price": 900},
        {"emoji": "🍌", "name": "Банан", "price": 900},
        {"emoji": "🍀", "name": "Клевер", "price": 1000},
        {"emoji": "🥀", "name": "Увядшая роза", "price": 1000},
    ],
    # Страница 5 - Редкие предметы
    5: [
        {"emoji": "🏆", "name": "Кубок", "price": 5000},
        {"emoji": "🐝", "name": "Пчела", "price": 5000},
        {"emoji": "🦋", "name": "Бабочка", "price": 5000},
        {"emoji": "🧠", "name": "Мозг", "price": 5000},
    ]
}

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    
    # Таблица для RP-команд
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rp_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emoji TEXT NOT NULL,
            action_text TEXT NOT NULL,
            trigger_word TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Таблица для мутов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mutes (
            user_id INTEGER,
            chat_id INTEGER,
            unmute_time DATETIME,
            reason TEXT,
            PRIMARY KEY (user_id, chat_id)
        )
    ''')
    
    # Таблица для варнов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warns (
            user_id INTEGER,
            chat_id INTEGER,
            admin_id INTEGER,
            reason TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, chat_id, timestamp)
        )
    ''')
    
    # Таблица для правил чатов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_rules (
            chat_id INTEGER PRIMARY KEY,
            rules_text TEXT,
            set_by INTEGER,
            set_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица для профилей пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER,
            chat_id INTEGER,
            shards INTEGER DEFAULT 0,
            last_dig_time DATETIME,
            PRIMARY KEY (user_id, chat_id)
        )
    ''')
    
    # Таблица для предметов пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_items (
            user_id INTEGER,
            chat_id INTEGER,
            item_emoji TEXT,
            item_name TEXT,
            purchase_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, chat_id, item_emoji)
        )
    ''')
    
    # Добавляем несколько базовых команд
    cursor.execute('''
        INSERT OR IGNORE INTO rp_commands (emoji, action_text, trigger_word) 
        VALUES 
        ('🤗', 'обнял', 'обнять'),
        ('😘', 'поцеловал', 'поцеловать'),
        ('👋', 'помахал', 'помахать')
    ''')
    
    conn.commit()
    conn.close()

# Функция для получения RP-команды по триггеру
def get_rp_command(trigger_word):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT emoji, action_text FROM rp_commands WHERE trigger_word = ?', (trigger_word,))
    result = cursor.fetchone()
    conn.close()
    return result

# Функция для получения всех RP-команд
def get_all_rp_commands():
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT emoji, action_text, trigger_word FROM rp_commands')
    results = cursor.fetchall()
    conn.close()
    return results

# Функция для добавления новой RP-команды
def add_rp_command(emoji, action_text, trigger_word):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO rp_commands (emoji, action_text, trigger_word) VALUES (?, ?, ?)', 
                      (emoji, action_text, trigger_word))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False  # Триггер слово уже существует
    conn.close()
    return success

# Функции для мутов
def add_mute(user_id, chat_id, unmute_time, reason=""):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO mutes (user_id, chat_id, unmute_time, reason) VALUES (?, ?, ?, ?)',
                  (user_id, chat_id, unmute_time.isoformat(), reason))
    conn.commit()
    conn.close()

def get_mute(user_id, chat_id):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT unmute_time, reason FROM mutes WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
    result = cursor.fetchone()
    conn.close()
    return result

def remove_mute(user_id, chat_id):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM mutes WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
    conn.commit()
    conn.close()

# Функции для варнов
def add_warn(user_id, chat_id, admin_id, reason=""):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO warns (user_id, chat_id, admin_id, reason) VALUES (?, ?, ?, ?)',
                  (user_id, chat_id, admin_id, reason))
    conn.commit()
    cursor.execute('SELECT COUNT(*) FROM warns WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
    warn_count = cursor.fetchone()[0]
    conn.close()
    return warn_count

def remove_warn(user_id, chat_id):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM warns WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
    current_count = cursor.fetchone()[0]
    
    if current_count > 0:
        cursor.execute('''
            DELETE FROM warns 
            WHERE user_id = ? AND chat_id = ? 
            AND timestamp = (SELECT MAX(timestamp) FROM warns WHERE user_id = ? AND chat_id = ?)
        ''', (user_id, chat_id, user_id, chat_id))
        conn.commit()
        new_count = current_count - 1
    else:
        new_count = 0
    
    conn.close()
    return new_count

def get_warn_count(user_id, chat_id):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM warns WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# Функции для правил чата
def set_chat_rules(chat_id, rules_text, set_by):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO chat_rules (chat_id, rules_text, set_by) VALUES (?, ?, ?)',
                  (chat_id, rules_text, set_by))
    conn.commit()
    conn.close()

def get_chat_rules(chat_id):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT rules_text FROM chat_rules WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def remove_chat_rules(chat_id):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM chat_rules WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

# Функции для профилей пользователей
def get_user_profile(user_id, chat_id):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT shards, last_dig_time FROM user_profiles WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
    result = cursor.fetchone()
    
    if not result:
        # Создаем профиль, если его нет
        cursor.execute('INSERT INTO user_profiles (user_id, chat_id, shards, last_dig_time) VALUES (?, ?, 0, NULL)',
                      (user_id, chat_id))
        conn.commit()
        shards = 0
        last_dig_time = None
    else:
        shards, last_dig_time = result
    
    # Получаем предметы пользователя
    cursor.execute('SELECT item_emoji, item_name FROM user_items WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
    items = cursor.fetchall()
    
    conn.close()
    return shards, last_dig_time, items

def update_user_shards(user_id, chat_id, shards):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO user_profiles (user_id, chat_id, shards) VALUES (?, ?, ?)',
                  (user_id, chat_id, shards))
    conn.commit()
    conn.close()

def update_dig_time(user_id, chat_id):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE user_profiles SET last_dig_time = CURRENT_TIMESTAMP WHERE user_id = ? AND chat_id = ?',
                  (user_id, chat_id))
    conn.commit()
    conn.close()

def add_user_item(user_id, chat_id, item_emoji, item_name):
    conn = sqlite3.connect('rp_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO user_items (user_id, chat_id, item_emoji, item_name) VALUES (?, ?, ?, ?)',
                  (user_id, chat_id, item_emoji, item_name))
    conn.commit()
    conn.close()

# Проверка является ли пользователь администратором
async def is_admin(update: Update, context: CallbackContext, user_id: int = None) -> bool:
    if user_id is None:
        user_id = update.effective_user.id
    
    chat_id = update.effective_chat.id
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Admin check error: {e}")
        return False

# Функция для автоматического размута
async def schedule_unmute(bot, user_id, chat_id, user_name, seconds):
    """Создает задачу для автоматического размута через указанное время"""
    try:
        # Создаем уникальный ключ для задачи
        task_key = f"{user_id}_{chat_id}"
        
        # Если уже есть задача для этого пользователя, отменяем её
        if task_key in unmute_tasks:
            unmute_tasks[task_key].cancel()
            logger.info(f"Cancelled existing unmute task for user {user_name}")
        
        # Создаем новую задачу
        task = asyncio.create_task(
            auto_unmute_user(bot, user_id, chat_id, user_name, seconds)
        )
        unmute_tasks[task_key] = task
        
        logger.info(f"Scheduled auto-unmute for user {user_name} in {seconds} seconds")
        
    except Exception as e:
        logger.error(f"Error scheduling unmute: {e}")

async def auto_unmute_user(bot, user_id, chat_id, user_name, seconds):
    """Автоматически размучивает пользователя через указанное время"""
    try:
        # Ждем указанное количество секунд
        await asyncio.sleep(seconds)
        
        # Восстанавливаем права
        unmute_permissions = ChatPermissions(
            can_send_messages=True
        )
        
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=unmute_permissions
        )
        
        # Удаляем из базы
        remove_mute(user_id, chat_id)
        
        # Отправляем уведомление
        await bot.send_message(
            chat_id=chat_id,
            text=f"🔊 Пользователь {user_name} автоматически размучен!"
        )
        
        # Удаляем задачу из словаря
        task_key = f"{user_id}_{chat_id}"
        if task_key in unmute_tasks:
            del unmute_tasks[task_key]
        
        logger.info(f"Successfully auto-unmuted user {user_name}")
        
    except Exception as e:
        logger.error(f"Error in auto unmute for user {user_name}: {e}")
        # Если не удалось размутить, все равно удаляем из базы
        remove_mute(user_id, chat_id)

# Команда /start
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    # Кнопка для добавления в чат
    keyboard = [
        [InlineKeyboardButton("➕ Добавить в чат", url=f"https://t.me/{(await context.bot.get_me()).username}?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎭 Привет, {user.first_name}! Я Карни - бот для RP-общения и модерации.\n\n"
        "✨ <b>Что я умею:</b>\n"
        "• Создавать атмосферные RP-действия\n"
        "• Помогать админам поддерживать порядок\n"
        "• Систему профилей с коллекцией предметов\n"
        "• Магазин с уникальными эмодзи\n"
        "• Автоматический размут по времени\n\n"
        "🛠 <b>Основные команды:</b>\n"
        "/menu - Меню управления\n"
        "/list - Список RP-команд\n"
        "!профиль - Мой профиль\n"
        "!магазин - Магазин предметов\n"
        "!правила - Правила чата\n\n"
        "Добавь меня в группу для полного функционала! 🎪",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# Меню управления
async def menu(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("📋 Список команд", callback_data="list_commands")],
        [InlineKeyboardButton("➕ Добавить команду", callback_data="add_command")],
        [InlineKeyboardButton("🛠 Модерация", callback_data="moderation_help")],
        [InlineKeyboardButton("👤 Профиль", callback_data="show_profile_menu")],
        [InlineKeyboardButton("🛒 Магазин", callback_data="show_shop_menu_1")],
        [InlineKeyboardButton("➕ Добавить в чат", url=f"https://t.me/{(await context.bot.get_me()).username}?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎮 <b>Меню управления Карни</b>", reply_markup=reply_markup, parse_mode='HTML')

# Обработчик кнопок меню
async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "list_commands":
        commands = get_all_rp_commands()
        if commands:
            commands_text = "📋 <b>Список RP-команд:</b>\n\n"
            for emoji, action_text, trigger_word in commands:
                commands_text += f"{emoji} {action_text} - триггер: '{trigger_word}'\n"
            await query.edit_message_text(commands_text, parse_mode='HTML')
        else:
            await query.edit_message_text("❌ Нет добавленных RP-команд")

    elif query.data == "add_command":
        await query.edit_message_text(
            "Чтобы добавить новую RP-команду, используйте команду:\n"
            "/addcommand эмодзи действие триггер\n\n"
            "Например:\n"
            "/addcommand 😊 улыбнулся улыбка"
        )

    elif query.data == "moderation_help":
        await query.edit_message_text(
            "🛠 <b>Команды модерации (только для админов):</b>\n\n"
            "🔇 <b>Мут:</b>\n"
            "Ответь на сообщение: 'мут 1 час'\n"
            "Формат: мут [число] [секунды/минуты/часы/дни]\n"
            "Примеры: 'мут 30 минут', 'мут 1 день'\n\n"
            "🔊 <b>Размут:</b>\n"
            "Ответь на сообщение: 'размут'\n\n"
            "👢 <b>Кик:</b>\n"
            "Ответь на сообщение: 'кик'\n\n"
            "⚠️ <b>Варны:</b>\n"
            "Ответь на сообщение: '+варн' - выдать варн\n"
            "Ответь на сообщение: '-варн' - снять варн\n"
            "После 3 варнов - автоматический кик\n\n"
            "📜 <b>Правила:</b>\n"
            "+правила [текст] - установить правила\n"
            "-правила - удалить правила\n"
            "!правила - показать правила",
            parse_mode='HTML'
        )

    elif query.data == "show_profile_menu":
        await show_profile_from_menu(update, context)

    elif query.data.startswith("show_shop_menu_"):
        page = int(query.data.split("_")[3])
        await show_shop_page_from_menu(update, context, page)

    elif query.data.startswith("show_shop_"):
        page = int(query.data.split("_")[2])
        await show_shop_page(update, context, page)

    elif query.data.startswith("buy_item_"):
        parts = query.data.split("_")
        page = int(parts[2])
        item_index = int(parts[3])
        await buy_item(update, context, page, item_index)

    # ИСПРАВЛЕНИЕ 1: Добавлен обработчик для кнопки "Назад в меню"
    elif query.data == "back_to_menu":
        await back_to_menu(update, context)

# Функция для показа профиля из меню
async def show_profile_from_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id  # Исправлено: получаем chat_id из сообщения
    
    # Получаем данные профиля
    shards, last_dig_time, items = get_user_profile(user.id, chat_id)
    
    # Проверяем является ли пользователь админом
    is_user_admin = await is_admin(update, context, user.id)
    role = "👑 Администратор" if is_user_admin else "👤 Участник"
    
    # Получаем количество варнов
    warn_count = get_warn_count(user.id, chat_id)
    
    # Формируем текст профиля
    profile_text = f"👤 <b>Профиль {user.first_name}</b>\n\n"
    profile_text += f"📛 <b>Ник:</b> {user.first_name}\n"
    profile_text += f"🎖️ <b>Должность:</b> {role}\n"
    profile_text += f"⚠️ <b>Варны:</b> {warn_count}/3\n"
    profile_text += f"💎 <b>Осколков:</b> {shards}\n\n"
    
    if items:
        profile_text += "🎁 <b>Предметы:</b>\n"
        for item_emoji, item_name in items:
            profile_text += f"• {item_emoji} {item_name}\n"
    else:
        profile_text += "🎁 <b>Предметы:</b> Пока нет предметов\n"
        profile_text += "🛒 Загляни в магазин !магазин"
    
    keyboard = [
        [InlineKeyboardButton("🛒 Магазин", callback_data="show_shop_menu_1")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(profile_text, reply_markup=reply_markup, parse_mode='HTML')

# Функция для показа магазина из меню
async def show_shop_page_from_menu(update: Update, context: CallbackContext, page: int):
    query = update.callback_query
    await show_shop_page(update, context, page, from_menu=True)

async def show_shop_page(update: Update, context: CallbackContext, page: int, from_menu=False):
    """Показывает страницу магазина"""
    if page not in SHOP_ITEMS:
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text("❌ Такой страницы магазина не существует.")
        else:
            await update.message.reply_text("❌ Такой страницы магазина не существует.")
        return
    
    items = SHOP_ITEMS[page]
    keyboard = []
    
    # Создаем кнопки для предметов (максимум 4 в ряд)
    row = []
    for i, item in enumerate(items):
        if len(row) == 2:  # 2 кнопки в ряд
            keyboard.append(row)
            row = []
        row.append(InlineKeyboardButton(
            f"{item['emoji']} - {item['price']}💎", 
            callback_data=f"buy_item_{page}_{i}"
        ))
    
    if row:  # Добавляем оставшиеся кнопки
        keyboard.append(row)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"show_shop_{page-1}"))
    
    if page < len(SHOP_ITEMS):
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"show_shop_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка профиля и возврата в меню
    menu_buttons = []
    menu_buttons.append(InlineKeyboardButton("👤 Мой профиль", callback_data="show_profile_menu"))
    if from_menu:
        menu_buttons.append(InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu"))
    
    keyboard.append(menu_buttons)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    page_titles = {
        1: "♈ Знаки зодиака",
        2: "💝 Эмоции и символы", 
        3: "✨ Символы и звезды",
        4: "🌿 Природа и еда",
        5: "🏆 Редкие предметы"
    }
    
    text = (
        f"🛒 <b>Магазин предметов</b> - {page_titles[page]}\n\n"
        f"📄 Страница {page}/{len(SHOP_ITEMS)}\n"
        f"💎 Для покупки нужны осколки\n"
        f"🔄 Используй !копать каждые 12 часов"
    )
    
    if hasattr(update, 'callback_query'):
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

# Команда для возврата в меню
async def back_to_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    # Создаем меню заново
    keyboard = [
        [InlineKeyboardButton("📋 Список команд", callback_data="list_commands")],
        [InlineKeyboardButton("➕ Добавить команду", callback_data="add_command")],
        [InlineKeyboardButton("🛠 Модерация", callback_data="moderation_help")],
        [InlineKeyboardButton("👤 Профиль", callback_data="show_profile_menu")],
        [InlineKeyboardButton("🛒 Магазин", callback_data="show_shop_menu_1")],
        [InlineKeyboardButton("➕ Добавить в чат", url=f"https://t.me/{(await context.bot.get_me()).username}?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🎮 <b>Меню управления Карни</b>", reply_markup=reply_markup, parse_mode='HTML')

# Команда для добавления новой RP-команды
async def add_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Неправильный формат команды!\n"
            "Используйте: /addcommand эмодзи действие триггер\n"
            "Пример: /addcommand 😊 улыбнулся улыбка"
        )
        return

    emoji = context.args[0]
    action_text = context.args[1]
    trigger_word = context.args[2]

    success = add_rp_command(emoji, action_text, trigger_word)
    
    if success:
        await update.message.reply_text(f"✅ Команда добавлена: {emoji} {action_text} - триггер: '{trigger_word}'")
    else:
        await update.message.reply_text("❌ Ошибка: такое триггер-слово уже существует!")

# Команда для просмотра всех RP-команд
async def list_commands(update: Update, context: CallbackContext) -> None:
    commands = get_all_rp_commands()
    if commands:
        commands_text = "📋 <b>Список всех RP-команд:</b>\n\n"
        for emoji, action_text, trigger_word in commands:
            commands_text += f"{emoji} {action_text} - триггер: '{trigger_word}'\n"
        await update.message.reply_text(commands_text, parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Нет добавленных RP-команд")

# Команда !правила
async def show_rules(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    rules = get_chat_rules(chat_id)
    
    if rules:
        await update.message.reply_text(f"📜 <b>Правила чата:</b>\n\n{rules}", parse_mode='HTML')
    else:
        await update.message.reply_text("ℹ️ Правила для этого чата еще не установлены.")

# Команда +правила
async def add_rules(update: Update, context: CallbackContext) -> None:
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Эта команда только для администраторов!")
        return

    # ИСПРАВЛЕНИЕ 2: Получаем полный текст сообщения и удаляем команду
    message_text = update.message.text.strip()
    if not message_text or len(message_text) <= 9:  # "+правила " - 9 символов
        await update.message.reply_text("❌ Укажите текст правил после команды: +правила [текст правил]")
        return

    # Извлекаем текст правил (удаляем "+правила " из начала)
    rules_text = message_text[9:].strip()
    
    if not rules_text:
        await update.message.reply_text("❌ Укажите текст правил после команды: +правила [текст правил]")
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    set_chat_rules(chat_id, rules_text, user_id)
    await update.message.reply_text("✅ Правила чата установлены!")

# Команда -правила
async def remove_rules(update: Update, context: CallbackContext) -> None:
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Эта команда только для администраторов!")
        return

    chat_id = update.effective_chat.id
    remove_chat_rules(chat_id)
    await update.message.reply_text("✅ Правила чата удалены!")

# Команда !профиль
async def show_profile(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Получаем данные профиля
    shards, last_dig_time, items = get_user_profile(user.id, chat_id)
    
    # Проверяем является ли пользователь админом
    is_user_admin = await is_admin(update, context, user.id)
    role = "👑 Администратор" if is_user_admin else "👤 Участник"
    
    # Получаем количество варнов
    warn_count = get_warn_count(user.id, chat_id)
    
    # Формируем текст профиля
    profile_text = f"👤 <b>Профиль {user.first_name}</b>\n\n"
    profile_text += f"📛 <b>Ник:</b> {user.first_name}\n"
    profile_text += f"🎖️ <b>Должность:</b> {role}\n"
    profile_text += f"⚠️ <b>Варны:</b> {warn_count}/3\n"
    profile_text += f"💎 <b>Осколков:</b> {shards}\n\n"
    
    if items:
        profile_text += "🎁 <b>Предметы:</b>\n"
        for item_emoji, item_name in items:
            profile_text += f"• {item_emoji} {item_name}\n"
    else:
        profile_text += "🎁 <b>Предметы:</b> Пока нет предметов\n"
        profile_text += "🛒 Загляни в магазин !магазин"
    
    await update.message.reply_text(profile_text, parse_mode='HTML')

# Команда !копать
async def dig_shards(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    shards, last_dig_time, items = get_user_profile(user.id, chat_id)
    
    # Проверяем, можно ли копать
    if last_dig_time:
        last_dig = datetime.datetime.fromisoformat(last_dig_time)
        time_since_last_dig = datetime.datetime.now() - last_dig
        hours_passed = time_since_last_dig.total_seconds() / 3600
        
        if hours_passed < 12:
            hours_left = 12 - hours_passed
            await update.message.reply_text(
                f"⏳ Вы уже копали сегодня!\n"
                f"Следующая возможность через: {hours_left:.1f} часов"
            )
            return
    
    # Генерируем случайное количество осколков
    found_shards = random.randint(1, 50)
    if found_shards == 50:
        found_shards = 100  # Джекпот!
        message = f"🎉 <b>ДЖЕКПОТ!</b> Вы нашли {found_shards} осколков! 💎"
    elif found_shards >= 40:
        message = f"🌟 <b>Отлично!</b> Вы нашли {found_shards} осколков! ✨"
    elif found_shards >= 20:
        message = f"👍 <b>Хорошо!</b> Вы нашли {found_shards} осколков! 💫"
    else:
        message = f"🔍 Вы нашли {found_shards} осколков 💎"
    
    # Обновляем профиль
    new_shards = shards + found_shards
    update_user_shards(user.id, chat_id, new_shards)
    update_dig_time(user.id, chat_id)
    
    await update.message.reply_text(
        f"{message}\n"
        f"💎 <b>Теперь у вас:</b> {new_shards} осколков\n\n"
        f"⏰ Следующее копание через 12 часов",
        parse_mode='HTML'
    )

# Команда !магазин - ПРОСТАЯ ФУНКЦИЯ КОТОРАЯ РАБОТАЕТ
async def show_shop(update: Update, context: CallbackContext) -> None:
    """Простая функция для показа магазина"""
    page = 1
    items = SHOP_ITEMS[page]
    keyboard = []
    
    # Создаем кнопки для предметов
    row = []
    for i, item in enumerate(items):
        if len(row) == 2:
            keyboard.append(row)
            row = []
        row.append(InlineKeyboardButton(
            f"{item['emoji']} - {item['price']}💎", 
            callback_data=f"buy_item_{page}_{i}"
        ))
    
    if row:
        keyboard.append(row)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"show_shop_{page-1}"))
    
    if page < len(SHOP_ITEMS):
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"show_shop_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка профиля
    keyboard.append([InlineKeyboardButton("👤 Мой профиль", callback_data="show_profile_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    page_titles = {
        1: "♈ Знаки зодиака",
        2: "💝 Эмоции и символы", 
        3: "✨ Символы и звезды",
        4: "🌿 Природа и еда",
        5: "🏆 Редкие предметы"
    }
    
    text = (
        f"🛒 <b>Магазин предметов</b> - {page_titles[page]}\n\n"
        f"📄 Страница {page}/{len(SHOP_ITEMS)}\n"
        f"💎 Для покупки нужны осколки\n"
        f"🔄 Используй !копать каждые 12 часов"
    )
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def buy_item(update: Update, context: CallbackContext, page: int, item_index: int):
    """Покупка предмета в магазине"""
    query = update.callback_query
    await query.answer()
    
    if page not in SHOP_ITEMS or item_index >= len(SHOP_ITEMS[page]):
        await query.edit_message_text("❌ Этот предмет больше не доступен.")
        return
    
    item = SHOP_ITEMS[page][item_index]
    user = query.from_user
    chat_id = query.message.chat.id
    
    # Получаем текущие осколки пользователя
    shards, last_dig_time, items = get_user_profile(user.id, chat_id)
    
    # Проверяем, хватает ли осколков
    if shards < item['price']:
        await query.edit_message_text(
            f"❌ Недостаточно осколков!\n"
            f"💎 Нужно: {item['price']}\n"
            f"💎 У вас: {shards}\n\n"
            f"🔄 Используй !копать для получения осколков"
        )
        return
    
    # Проверяем, есть ли уже этот предмет
    user_items = [item_emoji for item_emoji, item_name in items]
    if item['emoji'] in user_items:
        await query.edit_message_text(f"❌ У вас уже есть предмет {item['emoji']}!")
        return
    
    # Покупаем предмет
    new_shards = shards - item['price']
    update_user_shards(user.id, chat_id, new_shards)
    add_user_item(user.id, chat_id, item['emoji'], item['name'])
    
    await query.edit_message_text(
        f"🎉 <b>Поздравляем с покупкой!</b>\n\n"
        f"🛍️ <b>Куплено:</b> {item['emoji']} {item['name']}\n"
        f"💎 <b>Потрачено:</b> {item['price']} осколков\n"
        f"💎 <b>Осталось:</b> {new_shards} осколков\n\n"
        f"✨ Предмет добавлен в ваш профиль!",
        parse_mode='HTML'
    )

# Обработчик мутов
async def handle_mute(update: Update, context: CallbackContext, mute_text: str) -> None:
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Эта команда только для администраторов!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, которого хотите замутить!")
        return

    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id
    chat_id = update.effective_chat.id

    # Парсим время мута
    pattern = r'мут\s+(\d+)\s*(секунд[ыу]?|минут[ыу]?|час[аов]?|день|дня|дней|недел[яюи])'
    match = re.search(pattern, mute_text.lower())
    
    if not match:
        await update.message.reply_text(
            "❌ Неправильный формат команды!\n"
            "Используйте: мут [число] [секунды/минуты/часы/дни/недели]\n"
            "Пример: 'мут 1 час', 'мут 30 минут'"
        )
        return

    amount = int(match.group(1))
    time_unit = match.group(2)

    # Конвертируем в секунды
    time_units = {
        'секунд': 1,
        'секунды': 1,
        'секунду': 1,
        'минут': 60,
        'минуты': 60,
        'минуту': 60,
        'час': 3600,
        'часа': 3600,
        'часов': 3600,
        'день': 86400,
        'дня': 86400,
        'дней': 86400,
        'неделю': 604800,
        'недели': 604800,
        'недель': 604800
    }

    seconds = amount * time_units.get(time_unit, 60)
    unmute_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)

    # Добавляем мут в базу
    add_mute(target_user_id, chat_id, unmute_time)
    
    # Ограничиваем права пользователя
    try:
        until_date = int(unmute_time.timestamp())
        
        # Минимальный набор параметров для старых версий
        mute_permissions = ChatPermissions(
            can_send_messages=False
        )
        
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user_id,
            permissions=mute_permissions,
            until_date=until_date
        )
        
        # Запускаем задачу авторазмута
        await schedule_unmute(
            context.bot, 
            target_user_id, 
            chat_id, 
            target_user.first_name, 
            seconds
        )
        
        time_display = f"{amount} {time_unit}"
        await update.message.reply_text(
            f"🔇 Пользователь {target_user.first_name} заглушен на {time_display}!\n"
            f"⏰ Авторазмут через {seconds} секунд"
        )
        
        # Удаляем команду мут
        await update.message.delete()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при выдаче мута: {e}")
        logger.error(f"Mute error: {e}")

# Обработчик размута
async def handle_unmute(update: Update, context: CallbackContext) -> None:
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Эта команда только для администраторов!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, которого хотите размутить!")
        return

    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id
    chat_id = update.effective_chat.id

    try:
        # Минимальный набор параметров для размута
        unmute_permissions = ChatPermissions(
            can_send_messages=True
        )
        
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user_id,
            permissions=unmute_permissions
        )
        
        # Удаляем мут из базы
        remove_mute(target_user_id, chat_id)
        
        # Отменяем задачу авторазмута, если она есть
        task_key = f"{target_user_id}_{chat_id}"
        if task_key in unmute_tasks:
            unmute_tasks[task_key].cancel()
            del unmute_tasks[task_key]
            logger.info(f"Cancelled auto-unmute task for user {target_user.first_name}")
        
        await update.message.reply_text(f"🔊 Пользователь {target_user.first_name} размучен!")
        
        # Удаляем команду размут
        await update.message.delete()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при размуте пользователя: {e}")
        logger.error(f"Unmute error: {e}")

# Обработчик кика
async def handle_kick(update: Update, context: CallbackContext) -> None:
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Эта команда только для администраторов!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, которого хотите кикнуть!")
        return

    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id
    chat_id = update.effective_chat.id

    try:
        await context.bot.ban_chat_member(chat_id, target_user_id)
        await context.bot.unban_chat_member(chat_id, target_user_id)
        
        await update.message.reply_text(f"👢 Пользователь {target_user.first_name} кикнут из чата!")
        
        # Удаляем команду кик
        await update.message.delete()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при кике пользователя: {e}")
        logger.error(f"Kick error: {e}")

# Обработчик варнов
async def handle_warn(update: Update, context: CallbackContext, action: str) -> None:
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Эта команда только для администраторов!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя!")
        return

    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id
    chat_id = update.effective_chat.id
    admin_id = update.effective_user.id

    if action == "+":
        # Добавляем варн
        warn_count = add_warn(target_user_id, chat_id, admin_id)
        
        await update.message.reply_text(
            f"⚠️ Выдан варн {target_user.first_name} | {warn_count}/3"
        )
        
        # Проверяем на автоматический кик
        if warn_count >= 3:
            try:
                await context.bot.ban_chat_member(chat_id, target_user_id)
                await context.bot.unban_chat_member(chat_id, target_user_id)
                await update.message.reply_text(
                    f"👢 Пользователь {target_user.first_name} автоматически кикнут за 3 варна!"
                )
                # Удаляем все варны после кика
                conn = sqlite3.connect('rp_bot.db')
                cursor = conn.cursor()
                cursor.execute('DELETE FROM warns WHERE user_id = ? AND chat_id = ?', (target_user_id, chat_id))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Auto-kick error: {e}")
    
    elif action == "-":
        # Снимаем варн
        warn_count = remove_warn(target_user_id, chat_id)
        
        await update.message.reply_text(
            f"✅ Снят варн {target_user.first_name} | {warn_count}/3"
        )
    
    # Удаляем команду варн
    await update.message.delete()

# Проверка мута при новом сообщении
async def check_mute(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    mute_info = get_mute(user_id, chat_id)
    if mute_info:
        unmute_time = datetime.datetime.fromisoformat(mute_info[0])
        if datetime.datetime.now() < unmute_time:
            # Удаляем сообщение заблокированного пользователя
            try:
                await update.message.delete()
            except Exception as e:
                logger.error(f"Failed to delete muted user message: {e}")
        else:
            # Время мута истекло, удаляем из базы
            remove_mute(user_id, chat_id)

# Обработчик всех сообщений
async def handle_message(update: Update, context: CallbackContext) -> None:
    # Пропускаем команды
    if update.message.text and update.message.text.startswith('/'):
        return
    
    message_text = update.message.text.strip() if update.message.text else ""
    
    # Проверяем мут (для всех пользователей)
    await check_mute(update, context)
    
    # Обработка специальных команд
    if message_text.lower() == '!правила':
        await show_rules(update, context)
        return
    
    elif message_text.lower() == '!профиль':
        await show_profile(update, context)
        return
    
    elif message_text.lower() == '!копать':
        await dig_shards(update, context)
        return
    
    # ИСПРАВЛЕНИЕ 3: Команда !магазин теперь работает ПРОСТО И ПОНЯТНО
    elif message_text.lower() == '!магазин':
        await show_shop(update, context)
        return
    
    # Обработка модерационных команд (только для админов)
    if message_text.lower().startswith('мут'):
        await handle_mute(update, context, message_text)
        return
    
    elif message_text.lower() == 'размут':
        await handle_unmute(update, context)
        return
    
    elif message_text.lower() == 'кик':
        await handle_kick(update, context)
        return
    
    elif message_text.lower() == '+варн':
        await handle_warn(update, context, "+")
        return
    
    elif message_text.lower() == '-варн':
        await handle_warn(update, context, "-")
        return
    
    # ИСПРАВЛЕНИЕ 2: Обработка команд правил с учетом полного текста
    elif message_text.lower().startswith('+правила'):
        await add_rules(update, context)
        return
    
    elif message_text.lower() == '-правила':
        await remove_rules(update, context)
        return
    
    # Обработка RP-команд (для всех пользователей)
    elif update.message.reply_to_message and message_text:
        rp_command = get_rp_command(message_text.lower())
        
        if rp_command:
            emoji, action_text = rp_command
            
            # Получаем информацию об отправителе исходного сообщения
            original_sender = update.message.reply_to_message.from_user
            original_sender_name = original_sender.first_name
            
            # Получаем информацию об отправителе RP-действия
            action_sender = update.message.from_user
            action_sender_name = action_sender.first_name
            
            # Создаем RP-сообщение
            rp_message = f"{emoji} | {action_sender_name} {action_text} {original_sender_name}"
            
            # Отправляем сообщение как ответ на исходное сообщение человека
            await update.message.reply_to_message.reply_text(rp_message)
            
            # Удаляем исходное сообщение с триггером
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение: {e}")

# Обработчик ошибок
async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(f"Ошибка: {context.error}")

# Основная функция
def main() -> None:
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = Application.builder().token(TOKEN).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("list", list_commands))
    application.add_handler(CommandHandler("addcommand", add_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик текстовых сообщений (должен быть последним)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)

    # Запуск бота
    print("🎭 Бот Карни запущен! Теперь с системой профилей и магазином!")
    application.run_polling()

if __name__ == '__main__':
    main()
