import asyncio
import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "8814469553:AAG414M7T8DGEuTOCa7uNi7b2LDdKGTSErw"
ADMIN_ID = 8259900140

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Робота з базою даних SQLite ---
def init_db():
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 1000.0,
            last_bonus TEXT,
            language TEXT DEFAULT 'ru'
        )
    """)
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if "first_name" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    if "last_bonus" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_bonus TEXT")
    if "language" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'ru'")
        
    conn.commit()
    conn.close()

def update_user_info(user: types.User):
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, username, first_name, balance, language)
        VALUES (?, ?, ?, 1000.0, 'ru')
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    """, (user.id, user.username, user.first_name))
    conn.commit()
    conn.close()

def get_user_data(user_id: int):
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, last_bonus, language FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0], row[1], row[2]
    return 1000.0, None, 'ru'

def set_user_language(user_id: int, lang: str):
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def update_balance(user_id: int, amount: float):
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_top_leaders(limit=10):
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, username, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- Перевірка доступності бонуса ---
def check_bonus_available(last_bonus_str) -> bool:
    if not last_bonus_str:
        return True
    last_bonus_time = datetime.fromisoformat(last_bonus_str)
    next_available = last_bonus_time + timedelta(hours=1)
    return datetime.now() >= next_available

def get_balance_text_and_markup(user_id: int):
    balance, last_bonus, lang = get_user_data(user_id)
    is_bonus_ready = check_bonus_available(last_bonus)

    if lang == 'uk':
        text = f"💵 Ваш поточний баланс: **{balance:.2f} бурмалди**"
    else:
        text = f"💵 Ваш текущий баланс: **{balance:.2f} бурмалды**"
    
    builder = InlineKeyboardBuilder()
    if is_bonus_ready:
        bonus_text = "🎁 Отримати бонус (500 💵)" if lang == 'uk' else "🎁 Получить бонус (500 💵)"
        builder.button(text=bonus_text, callback_data="claim_bonus")
        text += "\n\n🎁 " + ("Вам доступний щогодинний бонус!" if lang == 'uk' else "Вам доступен ежечасный бонус!")
    else:
        last_bonus_time = datetime.fromisoformat(last_bonus)
        next_available = last_bonus_time + timedelta(hours=1)
        diff = next_available - datetime.now()
        left_minutes = int(diff.total_seconds() // 60) + 1
        text += f"\n\n⏳ " + (f"Наступний бонус через: **{left_minutes} хв.**" if lang == 'uk' else f"Следующий бонус через: **{left_minutes} мин.**")

    return text, builder.as_markup()

# --- Стан ігор ---
games = {}

def create_game_keyboard(user_id: int, reveal_all=False):
    builder = InlineKeyboardBuilder()
    game = games.get(user_id)
    
    for i in range(25):
        if reveal_all:
            text = "💣" if game["board"][i] else "💎"
        else:
            text = "💎" if game["revealed"][i] else "⬛"
        
        builder.button(text=text, callback_data=f"cell_{i}")
        
    builder.adjust(5)
    
    if not reveal_all:
        builder.button(text="💰 Забрати виграш", callback_data="cashout")
        builder.adjust(5, 5, 5, 5, 5, 1)
        
    return builder.as_markup()

# --- Логіка команд та мови ---

async def handle_start(message: types.Message):
    update_user_info(message.from_user)
    _, _, lang = get_user_data(message.from_user.id)
    
    if lang == 'uk':
        text = (
            "👋 Вітаємо у світі **Бурмалд**!\n\n"
            "🌍 Виберіть мову інтерфейсу:"
        )
    else:
        text = (
            "👋 Добро пожаловать в мир **Бурмалд**!\n\n"
            "🌍 Выберите язык интерфейса:"
        )
        
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇦 Українська", callback_data="set_lang_uk")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    builder.adjust(2)

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

async def handle_language_command(message: types.Message):
    _, _, lang = get_user_data(message.from_user.id)
    if lang == 'uk':
        text = "🌍 Виберіть мову інтерфейсу:"
    else:
        text = "🌍 Выберите язык интерфейса:"
        
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇦 Українська", callback_data="set_lang_uk")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    builder.adjust(2)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

async def handle_commands(message: types.Message):
    _, _, lang = get_user_data(message.from_user.id)
    if lang == 'uk':
        text = (
            f"📜 **Список команд бота:**\n\n"
            f"🔹 **команди** — Подивитися список команд\n"
            f"🔹 **баланс** — Перевірити баланс та отримати бонус\n"
            f"🔹 **бурмалдмина [ставка]** — Грати в бурмалдмину (наприклад: `бурмалдмина 50`)\n"
            f"🔹 **топ** — Таблиця лідерів\n"
            f"🔹 **передати [сума]** — Передати бурмалди гравцю через відповідь (reply) на його повідомлення\n"
            f"🔹 **мова** — Змінити мову інтерфейсу\n\n"
            f"👑 **Адмін-команди:**\n"
            f"• `видатибурмалду [сума]` — собі\n"
            f"• `видатибурмалду [ID] [сума]` — іншому гравцю"
        )
    else:
        text = (
            f"📜 **Список команд бота:**\n\n"
            f"🔹 **команди** — Посмотреть список команд\n"
            f"🔹 **баланс** — Проверить баланс и получить бонус\n"
            f"🔹 **бурмалдмина [ставка]** — Играть в бурмалдмину (например: `бурмалдмина 50`)\n"
            f"🔹 **топ** — Таблица лидеров\n"
            f"🔹 **передати [сумма]** — Передать бурмалды игроку через ответ (reply) на его сообщение\n"
            f"🔹 **мова** — Изменить язык интерфейса\n\n"
            f"👑 **Админ-команды:**\n"
            f"• `видатибурмалду [сума]` — себе\n"
            f"• `видатибурмалду [ID] [сума]` — другому игроку"
        )
    await message.answer(text, parse_mode="Markdown")

async def handle_balance(message: types.Message):
    update_user_info(message.from_user)
    text, markup = get_balance_text_and_markup(message.from_user.id)
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")

async def handle_top(message: types.Message):
    leaders = get_top_leaders()
    if not leaders:
        await message.answer("🏆 Таблиця лідерів порожня!")
        return

    text = "🏆 **Таблиця лідерів:**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for idx, (first_name, username, balance) in enumerate(leaders, 1):
        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        name = f"@{username}" if username else (first_name or "Гравець")
        text += f"{medal} **{name}** — {balance:.2f} бурмалди\n"

    await message.answer(text, parse_mode="Markdown")

# --- ПЕРЕДАЧА БУРМАЛД ЧЕРЕЗ ВІДПОВІДЬ ( REPLY ) ---
async def handle_give_burmalda(message: types.Message):
    update_user_info(message.from_user)
    _, _, lang = get_user_data(message.from_user.id)
    
    if not message.reply_to_message:
        msg = "⚠️ Щоб передати бурмалди, відповідайте (reply) цією командою на повідомлення гравця!" if lang == 'uk' else "⚠️ Для передачи бурмалд ответьте (reply) этой командой на сообщение игрока!"
        await message.reply(msg)
        return

    sender_id = message.from_user.id
    target_user = message.reply_to_message.from_user
    target_id = target_user.id

    if sender_id == target_id:
        msg = "❌ Ви не можете передавати бурмалди самому собі!" if lang == 'uk' else "❌ Вы не можете передавать бурмалды самому себе!"
        await message.reply(msg)
        return

    if target_user.is_bot:
        msg = "❌ Не можна передавати бурмалди ботам!" if lang == 'uk' else "❌ Нельзя передавать бурмалды ботам!"
        await message.reply(msg)
        return

    update_user_info(target_user)

    args = message.text.split()
    amount = None
    for part in args:
        try:
            val = float(part)
            if val > 0:
                amount = val
                break
        except ValueError:
            continue

    if not amount:
        msg = "❌ Вкажіть коректну суму для передачі. Приклад: `передати 50`" if lang == 'uk' else "❌ Укажите корректную сумму. Пример: `передати 50`"
        await message.reply(msg, parse_mode="Markdown")
        return

    sender_balance, _, _ = get_user_data(sender_id)
    if sender_balance < amount:
        msg = f"❌ У вас недостатньо коштів! Ваш баланс: {sender_balance:.2f} бурмалди." if lang == 'uk' else f"❌ У вас недостаточно средств! Ваш баланс: {sender_balance:.2f} бурмалди."
        await message.reply(msg)
        return

    update_balance(sender_id, -amount)
    update_balance(target_id, amount)

    new_sender_balance, _, _ = get_user_data(sender_id)
    target_name = target_user.first_name or "Гравець"

    if lang == 'uk':
        await message.reply(
            f"✅ Успішна передача!\n"
            f"👤 Ви передали **{amount:.2f} бурмалди** гравцю {target_name}!\n"
            f"💰 Ваш залишок: **{new_sender_balance:.2f} бурмалди**",
            parse_mode="Markdown"
        )
    else:
        await message.reply(
            f"✅ Успешная передача!\n"
            f"👤 Вы передали **{amount:.2f} бурмалди** игроку {target_name}!\n"
            f"💰 Ваш остаток: **{new_sender_balance:.2f} бурмалди**",
            parse_mode="Markdown"
        )

async def handle_giveburmalda(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас немає прав адміна!")
        return

    args = message.text.split()
    
    if len(args) == 2:
        try:
            amount = float(args[1])
        except ValueError:
            await message.answer("❌ Введіть коректну суму!")
            return
        
        target_id = message.from_user.id
        update_balance(target_id, amount)
        balance, _, _ = get_user_data(target_id)
        await message.answer(f"✅ Ви нарахували собі **{amount:.2f} бурмалди**!\nНовий баланс: **{balance:.2f} бурмалди**", parse_mode="Markdown")
        return

    if len(args) >= 3 and args[1].isdigit():
        target_id = int(args[1])
        try:
            amount = float(args[2])
        except ValueError:
            await message.answer("❌ Введіть коректну суму!")
            return

        update_balance(target_id, amount)
        balance, _, _ = get_user_data(target_id)
        await message.answer(f"✅ Нараховано **{amount:.2f} бурмалди** користувачу `{target_id}`!\nНовий баланс: **{balance:.2f} бурмалди**", parse_mode="Markdown")
        return

    await message.answer("❌ Формат:\nДля себе: `видатибурмалду [сума]`\nДля іншого: `видатибурмалду [ID] [сума]`", parse_mode="Markdown")

async def handle_burmaldmine(message: types.Message):
    user_id = message.from_user.id
    update_user_info(message.from_user)
    _, _, lang = get_user_data(user_id)
    
    if user_id in games:
        msg = "⚠️ У вас вже є активна гра!" if lang == 'uk' else "⚠️ У вас уже есть активная игра!"
        await message.answer(msg)
        return

    args = message.text.split()
    if len(args) < 2:
        msg = "❌ Вкажіть ставку. Наприклад: `бурмалдмина 50`" if lang == 'uk' else "❌ Укажите ставку. Например: `бурмалдмина 50`"
        await message.answer(msg, parse_mode="Markdown")
        return

    try:
        bet = float(args[1])
    except ValueError:
        msg = "❌ Введіть числову ставку!" if lang == 'uk' else "❌ Введите числовую ставку!"
        await message.answer(msg)
        return

    balance, _, _ = get_user_data(user_id)

    if bet <= 0 or bet > balance:
        msg = f"❌ Некоректна ставка або недостатньо бурмалди! Баланс: {balance:.2f}" if lang == 'uk' else f"❌ Некорректная ставка или недостаточно бурмалди! Баланс: {balance:.2f}"
        await message.answer(msg)
        return

    update_balance(user_id, -bet)

    mines_count = 9
    initial_multiplier = 1.25

    board = [True] * mines_count + [False] * (25 - mines_count)
    random.shuffle(board)

    games[user_id] = {
        "bet": bet,
        "mines_count": mines_count,
        "multiplier": initial_multiplier,
        "board": board,
        "revealed": [False] * 25
    }

    if lang == 'uk':
        text = (
            f"🎮 **Бурмалдмину розпочато!**\n\n"
            f"💰 Ставка: **{bet:.2f} бурмалди**\n"
            f"💣 Мін: **{mines_count}**\n"
            f"📈 Початковий коефіцієнт: **x{initial_multiplier:.2f}**\n"
            f"💵 Виграш: **{(bet * initial_multiplier):.2f} бурмалди**"
        )
    else:
        text = (
            f"🎮 **Бурмалдмина начата!**\n\n"
            f"💰 Ставка: **{bet:.2f} бурмалди**\n"
            f"💣 Мин: **{mines_count}**\n"
            f"📈 Начальный коэффициент: **x{initial_multiplier:.2f}**\n"
            f"💵 Выигрыш: **{(bet * initial_multiplier):.2f} бурмалди**"
        )
    
    await message.answer(text, reply_markup=create_game_keyboard(user_id), parse_mode="Markdown")


# --- Реєстрація обробників ---

@dp.message(Command("start"))
async def cmd_start_slash(message: types.Message):
    await handle_start(message)

@dp.message(F.text.casefold().in_({"старт", "start"}))
async def cmd_start_text(message: types.Message):
    await handle_start(message)


@dp.message(Command("commands"))
async def cmd_commands_slash(message: types.Message):
    await handle_commands(message)

@dp.message(F.text.casefold().in_({"команди", "commands"}))
async def cmd_commands_text(message: types.Message):
    await handle_commands(message)


@dp.message(Command("balance"))
async def cmd_balance_slash(message: types.Message):
    await handle_balance(message)

@dp.message(F.text.casefold().in_({"баланс", "balance"}))
async def cmd_balance_text(message: types.Message):
    await handle_balance(message)


@dp.message(Command("top"))
async def cmd_top_slash(message: types.Message):
    await handle_top(message)

@dp.message(F.text.casefold().in_({"топ", "top"}))
async def cmd_top_text(message: types.Message):
    await handle_top(message)


@dp.message(Command("giveburmalda"))
async def cmd_give_slash(message: types.Message):
    await handle_giveburmalda(message)

@dp.message(F.text.casefold().startswith(("видатибурмалду", "giveburmalda")))
async def cmd_give_text(message: types.Message):
    await handle_giveburmalda(message)


@dp.message(Command("передати"))
async def cmd_передати_slash(message: types.Message):
    await handle_give_burmalda(message)

@dp.message(F.text.casefold().startswith("передати"))
async def cmd_передати_text(message: types.Message):
    await handle_give_burmalda(message)


@dp.message(Command("burmaldmine"))
async def cmd_mine_slash(message: types.Message):
    await handle_burmaldmine(message)

@dp.message(F.text.casefold().startswith(("бурмалдмина", "burmaldmine")))
async def cmd_mine_text(message: types.Message):
    await handle_burmaldmine(message)


@dp.message(Command("мова"))
async def cmd_lang_slash(message: types.Message):
    await handle_language_command(message)

@dp.message(F.text.casefold().in_({"мова", "язык", "language"}))
async def cmd_lang_text(message: types.Message):
    await handle_language_command(message)


# --- Callback-запити (зміна мови, бонуси, гра) ---

@dp.callback_query(F.data.startswith("set_lang_"))
async def process_set_language(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.split("_")[2]
    set_user_language(user_id, lang)
    
    if lang == 'uk':
        await callback.answer("✅ Мову успішно змінено на Українську!", show_alert=True)
        text = "🇺🇦 Мову змінено на Українську. Використовуйте команду **команди** для перегляду списку команд."
    else:
        await callback.answer("✅ Язык успешно изменен на Русский!", show_alert=True)
        text = "🇷🇺 Язык изменен на Русский. Используйте команду **команди** для просмотра списка команд."
        
    await callback.message.edit_text(text, parse_mode="Markdown")

@dp.callback_query(F.data == "claim_bonus")
async def process_claim_bonus(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    _, last_bonus, lang = get_user_data(user_id)

    if not check_bonus_available(last_bonus):
        msg = "⏳ Цей бонус ще недоступний!" if lang == 'uk' else "⏳ Этот бонус еще недоступен!"
        await callback.answer(msg, show_alert=True)
        return

    now = datetime.now()
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + 500, last_bonus = ? WHERE user_id = ?", (now.isoformat(), user_id))
    conn.commit()
    conn.close()

    msg = "🎉 Ви успішно отримали 500 бурмалди!" if lang == 'uk' else "🎉 Вы успешно получили 500 бурмалди!"
    await callback.answer(msg, show_alert=False)
    
    text, markup = get_balance_text_and_markup(user_id)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cell_"))
async def process_cell_click(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in games:
        await callback.answer("Гра завершена!", show_alert=True)
        return

    cell_index = int(callback.data.split("_")[1])
    game = games[user_id]
    _, _, lang = get_user_data(user_id)

    if game["revealed"][cell_index]:
        msg = "Клітинка вже відкрита!" if lang == 'uk' else "Ячейка уже открыта!"
        await callback.answer(msg)
        return

    if game["board"][cell_index]:
        bet = game["bet"]
        markup = create_game_keyboard(user_id, reveal_all=True)
        del games[user_id]
        balance, _, _ = get_user_data(user_id)
        
        if lang == 'uk':
            await callback.message.edit_text(
                f"💥 **БУМ! Ви натрапили на міну!**\n\n"
                f"❌ Втрачено: **{bet:.2f} бурмалди**\n"
                f"💵 Баланс: **{balance:.2f} бурмалди**",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text(
                f"💥 **БУМ! Вы наступили на мину!**\n\n"
                f"❌ Потеряно: **{bet:.2f} бурмалди**\n"
                f"💵 Баланс: **{balance:.2f} бурмалди**",
                reply
