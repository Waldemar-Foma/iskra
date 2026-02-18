import logging
import sqlite3
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters, ConversationHandler
)
from werkzeug.security import generate_password_hash, check_password_hash
import json

# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = ""

# Состояния
NAME, EMAIL, PASSWORD, CONFIRM_PASSWORD, SITE, CHECK_PASS, ADD_PHONE, ADD_NAME, LOGIN = range(9)

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

# Функции для работы с БД
def get_user(user_id):
    conn = sqlite3.connect('instance/iskra.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_email(email):
    conn = sqlite3.connect('instance/iskra.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def register_user(user_id, username, usernametg, full_name, email, password_hash, is_active, created_at, last_active, preferences):
    conn = sqlite3.connect('instance/iskra.db')
    cursor = conn.cursor()
        
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, usernametg, full_name, email, password_hash, is_active, created_at, last_active, preferences)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, usernametg, full_name, email, password_hash, is_active, created_at, last_active, preferences))
    
    conn.commit()
    conn.close()

def update_user_phone(user_id, phone):
    conn = sqlite3.connect('instance/iskra.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users 
        SET phone = ?
        WHERE user_id = ?
    ''', (phone, user_id))
    
    conn.commit()
    conn.close()

def update_subscription(user_id, tier):
    conn = sqlite3.connect('instance/iskra.db')
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
    conn = sqlite3.connect('instance/iskra.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        end_date = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
        return end_date > datetime.now()
    return False

def get_subscription_days_left(user_id):
    conn = sqlite3.connect('instance/iskra.db')
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    keyboard = [
        [InlineKeyboardButton("Уже есть аккаунт", callback_data="connect_prof")],
        [InlineKeyboardButton("Создать новый аккаунт", callback_data="new_prof")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    existing_user = get_user(user_id)
    
    if existing_user:
        # Пользователь уже зарегистрирован
        await show_main_menu(update, context)
    else:
        # Начинаем регистрацию
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"У тебя уже есть аккаунт на сайте или ты хочешь зарегестрироваться?.",
            reply_markup=reply_markup
        )

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинаем процесс регистрации"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Шаг 1/4: Введите ваше полное имя (ФИ или ФИО):"
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
    
    context.user_data['password'] = generate_password_hash(password)
    
    
    await update.message.reply_text(
        f"✅ Пароль принят\n\n"
        f"Шаг 4/4: Подтвердите пароль (введите его еще раз):"
    )
    return CONFIRM_PASSWORD

async def register_confirm_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение пароля и завершение регистрации"""
    confirm_password = update.message.text
    user = update.effective_user
    
    if check_password_hash(context.user_data['password'], confirm_password):
        await update.message.reply_text(
            "❌ Пароли не совпадают. Пожалуйста, введите пароль еще раз для подтверждения:"
        )
        return CONFIRM_PASSWORD
    
    # Регистрируем пользователя в БД
    register_user(
        user_id=user.id,
        username=user.first_name,
        usernametg=user.username,
        full_name=context.user_data['full_name'],
        email=context.user_data['email'],
        password_hash=context.user_data['password'],
        is_active='0',
        created_at=datetime.utcnow(),
        last_active=datetime.utcnow(),
        preferences=json.dumps({
                'theme': 'dark',
                'notifications': True,
                'language': 'ru'
            })
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

async def start_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинаем процесс входа в существующий аккаунт"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📧 Введите ваш email, зарегистрированный на сайте:"
    )
    return SITE

def check_email_exists(email):
    conn = sqlite3.connect('instance/iskra.db')
    cursor = conn.cursor()
    
    # Проверяем существование email
    cursor.execute("SELECT COUNT(*) FROM users WHERE email = ?", (email,))
    count = cursor.fetchone()[0]
    
    conn.close()
    
    return count > 0

async def check_mail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mail = update.message.text.lower()

    if check_email_exists(mail):
        await update.message.reply_text(
            f"✅ Ваш аккаунт существует!\n\n"
            f"Теперь ведите свой пароль для доступа:"
        )
        context.user_data["mail"] = mail
        return CHECK_PASS
    else:
        await update.message.reply_text(
            f"✅ Ваш аккаунт несуществует!\n\n"
            f"Попробуйте ещё раз:"
        )
        return SITE

async def check_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text

    conn = sqlite3.connect('instance/iskra.db')
    cursor = conn.cursor()

    email=context.user_data['mail']

    # Получаем пользователя и его пароль
    cursor.execute(
        "SELECT password_hash FROM users WHERE email = ?", 
        (email,)
    )
    password_hash = cursor.fetchone()
    conn.close()
    
    if check_password_hash(password_hash[0], password):
        await update.message.reply_text(
            f"✅Вы подтвердили, что это ваш аккаунт!\n\n"
            f"Осталось только добавить ваше ФИ(О) и вам будет доступен бот:"
        )
        return ADD_NAME
    else:
        await update.message.reply_text(
            f"Пароль неправильный.\n\n"
            f"Попробуйте ещё раз:"
        )
        return CHECK_PASS
    
def update_user_name(full_name, email, user):
    conn = sqlite3.connect('instance/iskra.db')
    cursor = conn.cursor()
    user_id = user.id
    usernametg=user.username
    cursor.execute('''
        UPDATE users 
        SET user_id = ?, usernametg = ?, full_name = ?
        WHERE email = ?
    ''', (user_id, usernametg, full_name, email))
    
    conn.commit()
    conn.close()

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняем имя пользователя"""
    name = update.message.text
    is_valid, message = validate_name(name)
    user = update.effective_user

    if not is_valid:
        await update.message.reply_text(
            f"❌ {message}\n\n"
            f"Попробуйте еще раз:"
        )
        return ADD_NAME
    
    email=context.user_data['mail']

    # Сохраняем имя в БД
    update_user_name(name, email, user)
    
    await update.message.reply_text(
        "✅ ФИ(О) успешно сохранено!"
    )
    
    existing_user = get_user_by_email(email)
    
    if existing_user:
        # Пользователь уже зарегистрирован
        await show_main_menu(update, context)
    
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
    elif callback_data.startswith("connect_prof"):
        await query.edit_message_text(
            f"Рады снова вас видеть, укажите ваш email, чтобы мы могли вас узнать:"
        )
        return LOGIN
    elif callback_data.startswith("new_prof"):
        await query.edit_message_text(
            f"Шаг 1/4: Введите ваше полное имя (ФИ или ФИО):"
        )
        return NAME
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
                f"📝 ФИО: {user_data[4]}\n"
                f"📧 Email: {user_data[5]}\n"
            )
            
            # Добавляем телефон если есть
            if user_data[7]:  # phone
                profile_text += f"📱 Телефон: {user_data[7]}\n"
            else:
                profile_text += f"📱 Телефон: не указан\n"
                        
            if is_active and days_left > 0:
                tier = user_data[8]
                sub_info = SUBSCRIPTIONS.get(tier, {"emoji": "📦", "name": "Неизвестно"})
                
                profile_text += (
                    f"✅ Статус подписки: АКТИВНА\n"
                    f"🎁 Тариф: {sub_info['emoji']} {sub_info['name']}\n"
                    f"⏳ Осталось дней: {days_left}\n"
                    f"📅 Действует до: {user_data[10]}"
                )
            else:
                profile_text += "❌ У вас нет активной подписки"
            
            keyboard = []
            if not user_data[7]:  # если нет телефона
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
        f"📝 ФИО: {user_data[4]}\n"
        f"📧 Email: {user_data[5]}\n"
    )
    
    # Добавляем телефон если есть
    if user_data[7]:  # phone
        profile_text += f"📱 Телефон: {user_data[7]}\n"
    else:
        profile_text += f"📱 Телефон: не указан\n"
                
    if is_active and days_left > 0:
        tier = user_data[8]
        sub_info = SUBSCRIPTIONS.get(tier, {"emoji": "📦", "name": "Неизвестно"})
        
        profile_text += (
            f"✅ Статус подписки: АКТИВНА\n"
            f"🎁 Тариф: {sub_info['emoji']} {sub_info['name']}\n"
            f"⏳ Осталось дней: {days_left}\n"
            f"📅 Действует до: {user_data[10]}"
        )
    else:
        profile_text += "❌ У вас нет активной подписки"
    
    keyboard = []
    if not user_data[7]:  # если нет телефона
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
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчик регистрации (диалог)
    reg_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_registration, pattern="^new_prof$")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],
            CONFIRM_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="registration_conversation"
    )
    
    # Обработчик входа в существующий аккаунт
    login_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_login, pattern="^connect_prof$")],
        states={
            LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_login)],
            SITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_mail)],
            CHECK_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_pass)],
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="login_conversation"
    )
    
    # Обработчик добавления телефона
    phone_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_phone, pattern="^add_phone$")],
        states={
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)]
        },
        fallbacks=[CommandHandler('cancel', cancel_add_phone)],
        name="phone_conversation"
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(reg_conv_handler)
    application.add_handler(login_conv_handler)
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
