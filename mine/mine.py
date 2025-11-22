import sqlite3
import logging
import asyncio
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
        [InlineKeyboardButton("➕ Добавить в чат",
                              url=f"https://t.me/{(await context.bot.get_me()).username}?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Привет, {user.first_name}! Я Карни - бот для RP-общения и модерации.\n\n"
        "📋 Основные команды:\n"
        "/menu - Меню управления\n"
        "/list - Список RP-команд\n"
        "/addcommand - Добавить RP-команду\n\n"
        "🛠 Модерация (только для админов):\n"
        "Ответь на сообщение с командой:\n"
        "• 'мут 1 час' - замутить\n"
        "• 'размут' - размутить\n"
        "• 'кик' - кикнуть\n"
        "• '+варн' - выдать варн\n"
        "• '-варн' - снять варн",
        reply_markup=reply_markup
    )


# Меню управления
async def menu(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("📋 Список команд", callback_data="list_commands")],
        [InlineKeyboardButton("➕ Добавить команду", callback_data="add_command")],
        [InlineKeyboardButton("🛠 Модерация", callback_data="moderation_help")],
        [InlineKeyboardButton("➕ Добавить в чат",
                              url=f"https://t.me/{(await context.bot.get_me()).username}?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎮 Меню управления:", reply_markup=reply_markup)


# Обработчик кнопок меню
async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "list_commands":
        commands = get_all_rp_commands()
        if commands:
            commands_text = "📋 Список RP-команд:\n\n"
            for emoji, action_text, trigger_word in commands:
                commands_text += f"{emoji} {action_text} - триггер: '{trigger_word}'\n"
            await query.edit_message_text(commands_text)
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
            "🛠 Команды модерации (только для админов):\n\n"
            "🔇 Мут:\n"
            "Ответь на сообщение: 'мут 1 час'\n"
            "Формат: мут [число] [секунды/минуты/часы/дни]\n"
            "Примеры: 'мут 30 минут', 'мут 1 день'\n\n"
            "🔊 Размут:\n"
            "Ответь на сообщение: 'размут'\n\n"
            "👢 Кик:\n"
            "Ответь на сообщение: 'кик'\n\n"
            "⚠️ Варны:\n"
            "Ответь на сообщение: '+варн' - выдать варн\n"
            "Ответь на сообщение: '-варн' - снять варн\n"
            "После 3 варнов - автоматический кик"
        )


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
        commands_text = "📋 Список всех RP-команд:\n\n"
        for emoji, action_text, trigger_word in commands:
            commands_text += f"{emoji} {action_text} - триггер: '{trigger_word}'\n"
        await update.message.reply_text(commands_text)
    else:
        await update.message.reply_text("❌ Нет добавленных RP-команд")


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
    print("Бот Карни запущен! Авторазмут активен.")
    application.run_polling()


if __name__ == '__main__':
    main()
