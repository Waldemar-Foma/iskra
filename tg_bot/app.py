import logging
import sqlite3
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters, ConversationHandler
)
import hashlib

# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = "mytoken"

# Состояния для разговора (регистрация)
NAME, EMAIL, PASSWORD, CONFIRM_PASSWORD = range(4)

# Состояния для добавления телефона
ADD_PHONE = range(1)

# Тарифы подписок
SUBSCRIPTIONS = {
    "basic": {
        "name": "Базовая", 
        "price": "500₽/мес", 
        "emoji": "🌱",
        "days": 30,
        "price_value": 500
    },
    "premium": {
        "name": "Премиум", 
        "price": "1000₽/мес", 
        "emoji": "⭐",
        "days": 30,
        "price_value": 1000
    },
    "vip": {
        "name": "VIP", 
        "price": "2500₽/мес", 
        "emoji": "👑",
        "days": 30,
        "price_value": 2500
    }
}

# Создание базы данных
def init_database():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Таблица пользователей с обновленной структурой
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            mail TEXT,
            password TEXT,
            phone TEXT,
            registered_date TEXT,
            subscription_tier TEXT,
            subscription_start TEXT,
            subscription_end TEXT,
            is_active INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()
    print("База данных инициализирована")

# Функции для работы с БД
def get_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_email(email):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE mail = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def register_user(user_id, username, full_name, email, password):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    registered_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, full_name, mail, password, registered_date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, username, full_name, email, password, registered_date))
    
    conn.commit()
    conn.close()

def update_user_phone(user_id, phone):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users 
        SET phone = ?
        WHERE user_id = ?
    ''', (phone, user_id))
    
    conn.commit()
    conn.close()

def update_subscription(user_id, tier):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    now = datetime.now()
    subscription_start = now.strftime("%Y-%m-%d %H:%M:%S")
    subscription_end = (now + timedelta(days=SUBSCRIPTIONS[tier]["days"])).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        UPDATE users 
        SET subscription_tier = ?, subscription_start = ?, subscription_end = ?, is_active = 1
        WHERE user_id = ?
    ''', (tier, subscription_start, subscription_end, user_id))
    
    conn.commit()
    conn.close()

def check_subscription(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        end_date = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
        return end_date > datetime.now()
    return False

def get_subscription_days_left(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        end_date = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if end_date > now:
            delta = end_date - now
            return delta.days
    return 0

# Функции валидации
def validate_name(full_name):
    if re.search(r'[a-zA-Z]', full_name):
        return False, "ФИ(О) должно быть на русском"
        
    if ' ' not in full_name.strip():
        return False, "Введите ФИ(О) через пробел"
    
    words = full_name.strip().split()
    if len(words) < 2:
        return False, "Введите хотя бы фамилию и имя"
   
    return True, 'Данные коректны'
   
def validate_email(email):
    """Проверка корректности email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """
    Проверка пароля:
    - от 8 до 16 символов
    - буквы (кириллица)
    - цифры
    - спец символы
    """
    if len(password) < 8 or len(password) > 16:
        return False, "Пароль должен быть от 8 до 16 символов"
    
    # Проверка наличия латиницы
    if not re.search(r'[a-zA-Z]', password):
        return False, "Пароль должен содержать хотя бы одну букву латиницы"
    
    # Проверка наличия цифр
    if not re.search(r'\d', password):
        return False, "Пароль должен содержать хотя бы одну цифру"
    
    # Проверка наличия спецсимволов
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Пароль должен содержать хотя бы один специальный символ"
    
    return True, "Пароль корректный"

def validate_phone(phone):
    """Простая валидация телефона (можно расширить)"""
    # Удаляем все нецифровые символы
    digits = re.sub(r'\D', '', phone)
    # Проверяем, что длина от 10 до 15 цифр
    return 10 <= len(digits) <= 15

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    
    # Проверяем, зарегистрирован ли пользователь
    existing_user = get_user(user_id)
    
    if existing_user:
        # Пользователь уже зарегистрирован
        await show_main_menu(update, context)
    else:
        # Начинаем регистрацию
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"Для начала работы нам нужно зарегистрироваться.\n\n"
            f"Шаг 1/4: Введите ваше полное имя (ФИ или ФИО):"
        )
        return NAME

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем имя пользователя"""
    full_name = update.message.text.strip()
    
    is_valid, message = validate_name(full_name)
    
    if not is_valid:
        await update.message.reply_text(
            f"❌ {message}\n\n"
            f"Попробуйте еще раз:"
        )
        return NAME
    
    context.user_data['full_name'] = full_name
    
    await update.message.reply_text(
        f"✅ Имя сохранено: {full_name}\n\n"
        f"Шаг 2/4: Введите ваш email адрес:"
    )
    return EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем email пользователя"""
    email = update.message.text.strip().lower()
    
    # Валидация email
    if not validate_email(email):
        await update.message.reply_text(
            "❌ Некорректный email. Пожалуйста, введите корректный адрес (например: name@domain.com):"
        )
        return EMAIL
    
    # Проверяем, не занят ли email
    existing_user = get_user_by_email(email)
    if existing_user:
        await update.message.reply_text(
            "❌ Этот email уже зарегистрирован. Пожалуйста, введите другой email:"
        )
        return EMAIL
    
    context.user_data['email'] = email
    
    await update.message.reply_text(
        f"✅ Email сохранен: {email}\n\n"
        f"Шаг 3/4: Придумайте пароль\n\n"
        f"Требования к паролю:\n"
        f"• от 8 до 16 символов\n"
        f"• буквы латиницы\n"
        f"• цифры\n"
        f"• специальные символы (!@#$%^&*)\n\n"
        f"Введите пароль:"
    )
    return PASSWORD

async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем пароль"""
    password = update.message.text
    
    # Валидация пароля
    is_valid, message = validate_password(password)
    
    if not is_valid:
        await update.message.reply_text(
            f"❌ {message}\n\n"
            f"Попробуйте еще раз:"
        )
        return PASSWORD
    
    context.user_data['password'] = hash_password(password)
    
    
    await update.message.reply_text(
        f"✅ Пароль принят\n\n"
        f"Шаг 4/4: Подтвердите пароль (введите его еще раз):"
    )
    return CONFIRM_PASSWORD

async def register_confirm_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение пароля и завершение регистрации"""
    confirm_password = hash_password(update.message.text)
    user = update.effective_user
    
    if confirm_password != context.user_data['password']:
        await update.message.reply_text(
            "❌ Пароли не совпадают. Пожалуйста, введите пароль еще раз для подтверждения:"
        )
        return CONFIRM_PASSWORD
    
    # Регистрируем пользователя в БД
    register_user(
        user_id=user.id,
        username=user.username,
        full_name=context.user_data['full_name'],
        email=context.user_data['email'],
        password=context.user_data['password']
    )
    
    await update.message.reply_text(
        "✅ Регистрация успешно завершена!\n\n"
        "Теперь вы можете пользоваться всеми возможностями бота.\n"
        "В личном кабинете вы сможете добавить номер телефона."
    )
    
    # Показываем главное меню
    await show_main_menu(update, context)
    
    # Очищаем данные пользователя
    context.user_data.clear()
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена регистрации"""
    await update.message.reply_text(
        "Регистрация отменена. Для начала работы используйте /start"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📋 Тарифы", callback_data="show_tariffs")],
        [InlineKeyboardButton("👤 Личный кабинет", callback_data="profile")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            f"👋 С возвращением, {user.first_name}!\n\n"
            f"Что хотите сделать?",
            reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            f"👋 С возвращением, {user.first_name}!\n\n"
            f"Что хотите сделать?",
            reply_markup=reply_markup
        )

async def start_add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинаем процесс добавления телефона"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📱 Введите ваш номер телефона в любом формате\n"
        "(например: +7 999 123-45-67 или 89991234567):"
    )
    return ADD_PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняем телефон пользователя"""
    phone = update.message.text
    user_id = update.effective_user.id
    
    if not validate_phone(phone):
        await update.message.reply_text(
            "❌ Некорректный номер телефона. Пожалуйста, введите корректный номер:"
        )
        return ADD_PHONE
    
    # Сохраняем телефон в БД
    update_user_phone(user_id, phone)
    
    await update.message.reply_text(
        "✅ Номер телефона успешно сохранен!"
    )
    
    # Возвращаемся в главное меню
    await show_main_menu(update, context)
    
    return ConversationHandler.END

async def cancel_add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена добавления телефона"""
    await update.message.reply_text(
        "Добавление телефона отменено."
    )
    await show_main_menu(update, context)
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = update.effective_user.id
    
    if callback_data == "show_tariffs":
        # Показываем тарифы
        keyboard = [
            [InlineKeyboardButton(
                f"{info['emoji']} {info['name']} - {info['price']}", 
                callback_data=f"subscribe_{tier}"
            )]
            for tier, info in SUBSCRIPTIONS.items()
        ]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📊 Доступные тарифы:\n\n"
            "Выберите подходящий вариант:",
            reply_markup=reply_markup
        )
    
    elif callback_data.startswith("subscribe_"):
        tier = callback_data.replace("subscribe_", "")
        
        if tier in SUBSCRIPTIONS:
            sub_info = SUBSCRIPTIONS[tier]
            
            # Обновляем подписку в БД
            update_subscription(user_id, tier)
            
            # Сообщение об успешной оплате
            days_left = get_subscription_days_left(user_id)
            
            success_text = (
                f"✅ ОПЛАТА УСПЕШНО ВЫПОЛНЕНА!\n\n"
                f"Тариф: {sub_info['emoji']} {sub_info['name']}\n"
                f"Стоимость: {sub_info['price']}\n"
                f"Срок действия: {days_left} дней\n\n"
                f"💫 Спасибо за покупку! Это демонстрационная версия бота, "
                f"поэтому оплата не была списана."
            )
            
            keyboard = [
                [InlineKeyboardButton("👤 Личный кабинет", callback_data="profile")],
                [InlineKeyboardButton("🔙 К тарифам", callback_data="show_tariffs")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(success_text, reply_markup=reply_markup)
    
    elif callback_data == "profile":
        # Личный кабинет
        user = update.effective_user
        user_data = get_user(user_id)
        
        if user_data:
            days_left = get_subscription_days_left(user_id)
            is_active = check_subscription(user_id)
            
            profile_text = (
                f"👤 ЛИЧНЫЙ КАБИНЕТ\n\n"
                f"📝 ФИО: {user_data[2]}\n"
                f"📧 Email: {user_data[3]}\n"
            )
            
            # Добавляем телефон если есть
            if user_data[5]:  # phone
                profile_text += f"📱 Телефон: {user_data[5]}\n"
            else:
                profile_text += f"📱 Телефон: не указан\n"
            
            profile_text += f"📅 Дата регистрации: {user_data[6]}\n\n"
            
            if is_active and days_left > 0:
                tier = user_data[7]
                sub_info = SUBSCRIPTIONS.get(tier, {"emoji": "📦", "name": "Неизвестно"})
                
                profile_text += (
                    f"✅ Статус подписки: АКТИВНА\n"
                    f"🎁 Тариф: {sub_info['emoji']} {sub_info['name']}\n"
                    f"⏳ Осталось дней: {days_left}\n"
                    f"📅 Действует до: {user_data[9]}"
                )
            else:
                profile_text += "❌ У вас нет активной подписки"
            
            keyboard = []
            if not user_data[5]:  # если нет телефона
                keyboard.append([InlineKeyboardButton("📱 Добавить телефон", callback_data="add_phone")])
            
            keyboard.extend([
                [InlineKeyboardButton("💰 Купить подписку", callback_data="show_tariffs")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(profile_text, reply_markup=reply_markup)
    
    elif callback_data == "add_phone":
        # Создаем ConversationHandler для добавления телефона
        await query.edit_message_text(
            "📱 Введите ваш номер телефона в любом формате\n"
            "(например: +7 999 123-45-67 или 89991234567):"
        )
        return ADD_PHONE
    
    elif callback_data == "help":
        help_text = (
            "📋 ДОСТУПНЫЕ КОМАНДЫ:\n\n"
            "/start - Начать работу\n"
            "/menu - Главное меню\n"
            "/profile - Личный кабинет\n"
            "/tariffs - Тарифы\n"
            "/help - Помощь\n\n"
            "📌 Как это работает:\n"
            "1. Зарегистрируйтесь (ФИО, email, пароль)\n"
            "2. Добавьте телефон в личном кабинете\n"
            "3. Выберите тариф\n"
            "4. Оплатите (демо-режим)\n"
            "5. Пользуйтесь подпиской"
        )
        
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup)
    
    elif callback_data == "main_menu":
        await show_main_menu(update, context)

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /profile"""
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("Сначала зарегистрируйтесь через /start")
        return
    
    days_left = get_subscription_days_left(user_id)
    is_active = check_subscription(user_id)
    
    profile_text = (
        f"👤 ЛИЧНЫЙ КАБИНЕТ\n\n"
        f"📝 ФИО: {user_data[2]}\n"
        f"📧 Email: {user_data[3]}\n"
    )
    
    # Добавляем телефон если есть
    if user_data[5]:  # phone
        profile_text += f"📱 Телефон: {user_data[5]}\n"
    else:
        profile_text += f"📱 Телефон: не указан\n"
    
    profile_text += f"📅 Дата регистрации: {user_data[6]}\n\n"
    
    if is_active and days_left > 0:
        tier = user_data[7]
        sub_info = SUBSCRIPTIONS.get(tier, {"emoji": "📦", "name": "Неизвестно"})
        
        profile_text += (
            f"✅ Статус подписки: АКТИВНА\n"
            f"🎁 Тариф: {sub_info['emoji']} {sub_info['name']}\n"
            f"⏳ Осталось дней: {days_left}\n"
            f"📅 Действует до: {user_data[9]}"
        )
    else:
        profile_text += "❌ У вас нет активной подписки"
    
    keyboard = []
    if not user_data[5]:  # если нет телефона
        keyboard.append([InlineKeyboardButton("📱 Добавить телефон", callback_data="add_phone")])
    
    keyboard.extend([
        [InlineKeyboardButton("💰 Купить подписку", callback_data="show_tariffs")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(profile_text, reply_markup=reply_markup)

async def tariffs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /tariffs"""
    keyboard = [
        [InlineKeyboardButton(
            f"{info['emoji']} {info['name']} - {info['price']}", 
            callback_data=f"subscribe_{tier}"
        )]
        for tier, info in SUBSCRIPTIONS.items()
    ]
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 Доступные тарифы:", reply_markup=reply_markup)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /menu"""
    await show_main_menu(update, context)

def main() -> None:
    """Запуск бота"""
    # Инициализируем базу данных
    init_database()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчик регистрации (диалог)
    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],
            CONFIRM_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm_password)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Обработчик добавления телефона
    phone_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_phone, pattern="^add_phone$")],
        states={
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)]
        },
        fallbacks=[CommandHandler('cancel', cancel_add_phone)]
    )
    
    # Регистрируем обработчики
    application.add_handler(reg_conv_handler)
    application.add_handler(phone_conv_handler)
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("tariffs", tariffs_command))
    application.add_handler(CommandHandler("help", menu_command))
    
    # Регистрируем обработчик callback-запросов (кроме add_phone, который уже обработан)
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^(?!add_phone$).*$"))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()