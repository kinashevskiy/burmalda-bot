import asyncio
import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "8814469553:AAG414M7T8DGEuTOCa7uNi7b2LDdKGTSErw"
ADMIN_ID = 8259900140

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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
        text = f"💵 Ваш текущий баланс: **{balance:.2f} бурмалди**"
    
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

games = {}

def create_game_keyboard(owner_id: int, viewer_id: int, reveal_all=False):
    builder = InlineKeyboardBuilder()
    game = games.get(owner_id)
    _, _, lang = get_user_data(viewer_id)
    
    for i in range(25):
        if reveal_all:
            text = "💣" if game["board"][i] else "💎"
        else:
            text = "💎" if game["revealed"][i] else "⬛"
        builder.button(text=text, callback_data=f"cell_{owner_id}_{i}")
        
    builder.adjust(5)
    
    if not reveal_all:
        cashout_text = "💰 Забрати виграш" if lang == 'uk' else "💰 Забрать выигрыш"
        builder.button(text=cashout_text, callback_data=f"cashout_{owner_id}")
        builder.adjust(5, 5, 5, 5, 5, 1)
        
        if viewer_id == ADMIN_ID:
            admin_btn_text = "👑 Подивитися міни (Адмін)" if lang == 'uk' else "👑 Посмотреть мины (Админ)"
            builder.button(text=admin_btn_text, callback_data=f"admin_peek_{owner_id}")
            builder.adjust(5, 5, 5, 5, 5, 1, 1)
            
    return builder.as_markup()

async def handle_start(message: types.Message):
    update_user_info(message.from_user)
    _, _, lang = get_user_data(message.from_user.id)
    if lang == 'uk':
        text = "👋 Вітаємо у світі **Бурмалд**!\n\n🌍 Виберіть мову інтерфейсу:"
    else:
        text = "👋 Добро пожаловать в мир **Бурмалд**!\n\n🌍 Выберите язык интерфейса:"
        
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇦 Українська", callback_data="set_lang_uk")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    builder.adjust(2)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

async def handle_language_command(message: types.Message):
    _, _, lang = get_user_data(message.from_user.id)
    text = "🌍 Виберіть мову інтерфейсу:" if lang == 'uk' else "🌍 Выберите язык интерфейса:"
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇦 Українська", callback_data="set_lang_uk")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    builder.adjust(2)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

async def handle_commands(message: types.Message):
    user_id = message.from_user.id
    _, _, lang = get_user_data(user_id)
    
    if lang == 'uk':
        text = (
            "📜 **Список команд бота:**\n\n"
            "🔹 **команди** — Подивитися список команд\n"
            "🔹 **баланс** — Перевірити баланс та отримати бонус\n"
            "🔹 **бурмалдмина [ставка]** — Грати в бурмалдмину\n"
            "🔹 **топ** — Таблиця лідерів\n"
            "🔹 **передати [сума]** — Передати бурмалди через відповідь на повідомлення\n"
            "🔹 **мова** — Змінити мову інтерфейсу\n"
        )
        if user_id == ADMIN_ID:
            text += (
                "\n👑 **Адмін-можливості:**\n"
                "• Під кожною грою є кнопка «Подивитися міни» (у спливаючому вікні).\n"
                "• `видати бурмалду [сума]`\n"
                "• `видати бурмалду [ID] [сума]`"
            )
    else:
        text = (
            "📜 **Список команд бота:**\n\n"
            "🔹 **команди** — Посмотреть список команд\n"
            "🔹 **баланс** — Проверить баланс и получить бонус\n"
            "🔹 **бурмалдмина [ставка]** — Играть в бурмалдмину\n"
            "🔹 **топ** — Таблица лидеров\n"
            "🔹 **передати [сумма]** — Передать бурмалды через ответ на сообщение\n"
            "🔹 **мова** — Изменить язык интерфейса\n"
        )
        if user_id == ADMIN_ID:
            text += (
                "\n👑 **Админ-возможности:**\n"
                "• Под каждой игрой есть кнопка «Посмотреть мины» (во всплывающем окне).\n"
                "• `видати бурмалду [сума]`\n"
                "• `видати бурмалду [ID] [сума]`"
            )
    await message.answer(text, parse_mode="Markdown")

async def handle_balance(message: types.Message):
    update_user_info(message.from_user)
    text, markup = get_balance_text_and_markup(message.from_user.id)
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")

async def handle_top(message: types.Message):
    _, _, lang = get_user_data(message.from_user.id)
    leaders = get_top_leaders()
    if not leaders:
        msg = "🏆 Таблиця лідерів порожня!" if lang == 'uk' else "🏆 Таблица лидеров пуста!"
        await message.answer(msg)
        return
    text = "🏆 **Таблиця лідерів:**\n\n" if lang == 'uk' else "🏆 **Таблица лидеров:**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for idx, (first_name, username, balance) in enumerate(leaders, 1):
        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        default_name = "Гравець" if lang == 'uk' else "Игрок"
        name = f"@{username}" if username else (first_name or default_name)
        text += f"{medal} **{name}** — {balance:.2f} бурмалди\n"
    await message.answer(text, parse_mode="Markdown")

async def handle_give_burmalda(message: types.Message):
    update_user_info(message.from_user)
    _, _, lang = get_user_data(message.from_user.id)
    if not message.reply_to_message:
        msg = "⚠️ Відповідайте цією командою на повідомлення гравця!" if lang == 'uk' else "⚠️ Ответьте этой командой на сообщение игрока!"
        await message.reply(msg)
        return

    sender_id = message.from_user.id
    target_user = message.reply_to_message.from_user
    target_id = target_user.id

    if sender_id == target_id or target_user.is_bot:
        err_msg = "❌ Помилка передачі!" if lang == 'uk' else "❌ Ошибка передачи!"
        await message.reply(err_msg)
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
        err_sum = "❌ Вкажіть суму. Приклад: `передати 50`" if lang == 'uk' else "❌ Укажите сумму. Пример: `передати 50`"
        await message.reply(err_sum, parse_mode="Markdown")
        return

    sender_balance, _, _ = get_user_data(sender_id)
    if sender_balance < amount:
        low_msg = "❌ Недостатньо коштів!" if lang == 'uk' else "❌ Недостаточно средств!"
        await message.reply(low_msg)
        return

    update_balance(sender_id, -amount)
    update_balance(target_id, amount)
    new_balance, _, _ = get_user_data(sender_id)
    
    if lang == 'uk':
        await message.reply(f"✅ Передано **{amount:.2f} бурмалди**!\nБаланс: **{new_balance:.2f} бурмалди**", parse_mode="Markdown")
    else:
        await message.reply(f"✅ Переведено **{amount:.2f} бурмалди**!\nБаланс: **{new_balance:.2f} бурмалди**", parse_mode="Markdown")

async def handle_giveburmalda(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) == 2:
        amount = float(args[1])
        update_balance(message.from_user.id, amount)
        await message.answer(f"✅ Начислено себе {amount}")
    elif len(args) >= 3 and args[1].isdigit():
        target_id = int(args[1])
        amount = float(args[2])
        update_balance(target_id, amount)
        await message.answer(f"✅ Начислено пользователю {target_id}: {amount}")

async def handle_burmaldmine(message: types.Message):
    user_id = message.from_user.id
    update_user_info(message.from_user)
    _, _, lang = get_user_data(user_id)
    
    if user_id in games:
        msg = "⚠️ Активна гра вже є!" if lang == 'uk' else "⚠️ Активная игра уже есть!"
        await message.answer(msg)
        return

    args = message.text.split()
    if len(args) < 2:
        msg = "❌ Вкажіть ставку: `бурмалдмина 50`" if lang == 'uk' else "❌ Укажите ставку: `бурмалдмина 50`"
        await message.answer(msg, parse_mode="Markdown")
        return

    try:
        bet = float(args[1])
    except ValueError:
        msg = "❌ Некоректна ставка!" if lang == 'uk' else "❌ Некорректная ставка!"
        await message.answer(msg)
        return

    balance, _, _ = get_user_data(user_id)
    if bet <= 0 or bet > balance:
        msg = "❌ Недостатньо бурмалди або ставка ≤ 0!" if lang == 'uk' else "❌ Недостаточно бурмалди или ставка ≤ 0!"
        await message.answer(msg)
        return

    update_balance(user_id, -bet)
    board = [True] * 9 + [False] * 16
    random.shuffle(board)

    games[user_id] = {
        "bet": bet,
        "mines_count": 9,
        "multiplier": 1.25,
        "board": board,
        "revealed": [False] * 25
    }

    if lang == 'uk':
        text = f"🎮 Гравець @{message.from_user.username or message.from_user.first_name} розпочав **Бурмалдмину**!\nСтавка: **{bet:.2f} бурмалди**"
    else:
        text = f"🎮 Игрок @{message.from_user.username or message.from_user.first_name} начал **Бурмалдмину**!\nСтавка: **{bet:.2f} бурмалди**"
        
    await message.answer(text, reply_markup=create_game_keyboard(user_id, user_id), parse_mode="Markdown")

@dp.message(Command("start"))
async def c_start(m: types.Message): await handle_start(m)
@dp.message(F.text.casefold().in_({"старт", "start"}))
async def c_start_t(m: types.Message): await handle_start(m)

@dp.message(Command("commands"))
async def c_comm(m: types.Message): await handle_commands(m)
@dp.message(F.text.casefold().in_({"команди", "commands"}))
async def c_comm_t(m: types.Message): await handle_commands(m)

@dp.message(Command("balance"))
async def c_bal(m: types.Message): await handle_balance(m)
@dp.message(F.text.casefold().in_({"баланс", "balance"}))
async def c_bal_t(m: types.Message): await handle_balance(m)

@dp.message(Command("top"))
async def c_top(m: types.Message): await handle_top(m)
@dp.message(F.text.casefold().in_({"топ", "top"}))
async def c_top_t(m: types.Message): await handle_top(m)

@dp.message(Command("giveburmalda"))
async def c_gb(m: types.Message): await handle_giveburmalda(m)
@dp.message(F.text.casefold().startswith(("видати бурмалду", "видатибурмалду", "giveburmalda")))
async def c_gb_t(m: types.Message): await handle_giveburmalda(m)

@dp.message(Command("передати"))
async def c_per(m: types.Message): await handle_give_burmalda(m)
@dp.message(F.text.casefold().startswith("передати"))
async def c_per_t(m: types.Message): await handle_give_burmalda(m)

@dp.message(Command("burmaldmine"))
async def c_mine(m: types.Message): await handle_burmaldmine(m)
@dp.message(F.text.casefold().startswith(("бурмалдмина", "burmaldmine")))
async def c_mine_t(m: types.Message): await handle_burmaldmine(m)

@dp.message(Command("мова"))
async def c_lang(m: types.Message): await handle_language_command(m)
@dp.message(F.text.casefold().in_({"мова", "язык", "language"}))
async def c_lang_t(m: types.Message): await handle_language_command(m)

@dp.callback_query(F.data.startswith("set_lang_"))
async def cb_lang(callback: types.CallbackQuery):
    lang = callback.data.split("_")[2]
    set_user_language(callback.from_user.id, lang)
    text = "🇺🇦 Мову змінено." if lang == 'uk' else "🇷🇺 Язык изменен."
    await callback.answer(text, show_alert=True)
    await callback.message.edit_text(text)

@dp.callback_query(F.data == "claim_bonus")
async def cb_bonus(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    _, last_bonus, lang = get_user_data(user_id)
    if not check_bonus_available(last_bonus):
        msg = "⏳ Рано!" if lang == 'uk' else "⏳ Рано!"
        await callback.answer(msg, show_alert=True)
        return
    update_balance(user_id, 500)
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()
    
    alert_msg = "🎉 Бонус отримано (+500)!" if lang == 'uk' else "🎉 Бонус получен (+500)!"
    await callback.answer(alert_msg, show_alert=False)
    text, markup = get_balance_text_and_markup(user_id)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cell_"))
async def cb_cell(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    owner_id = int(parts[1])
    idx = int(parts[2])
    user_id = callback.from_user.id
    
    if owner_id not in games:
        await callback.answer("Гра вже завершена!" if get_user_data(user_id)[2] == 'uk' else "Игра уже завершена!", show_alert=True)
        return
        
    game = games[owner_id]
    _, _, lang = get_user_data(user_id)
    
    if game["revealed"][idx]:
        await callback.answer("Вже відкрито!" if lang == 'uk' else "Уже открыто!")
        return
        
    if game["board"][idx]:
        markup = create_game_keyboard(owner_id, owner_id, reveal_all=True)
        bet = game["bet"]
        del games[owner_id]
        if lang == 'uk':
            msg = f"💥 **БУМ! Міна!** Гравець програв {bet:.2f}"
        else:
            msg = f"💥 **БУМ! Мина!** Игрок проиграл {bet:.2f}"
        await callback.message.edit_text(msg, reply_markup=markup, parse_mode="Markdown")
        return
        
    game["revealed"][idx] = True
    game["multiplier"] += 0.25
    win = game["bet"] * game["multiplier"]
    
    if lang == 'uk':
        msg = f"💎 Безпечно!\nПоточний виграш: {win:.2f} бурмалди"
    else:
        msg = f"💎 Безопасно!\nТекущий выигрыш: {win:.2f} бурмалди"
        
    await callback.message.edit_text(msg, reply_markup=create_game_keyboard(owner_id, user_id), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_peek_"))
async def cb_admin_peek(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступно только администратору!", show_alert=True)
        return
        
    owner_id = int(callback.data.split("_")[2])
    if owner_id not in games:
        await callback.answer("⚠️ Эта игра уже завершена!", show_alert=True)
        return
        
    game = games[owner_id]
    board = game["board"]
    
    mine_coords = []
    for i, has_mine in enumerate(board):
        if has_mine:
            row = (i // 5) + 1
            col = (i % 5) + 1
            mine_coords.append(f"({row}р, {col}к)")
            
    peek_text = "💣 МИНЫ: " + ", ".join(mine_coords)
    await callback.answer(peek_text, show_alert=True)

@dp.callback_query(F.data.startswith("cashout_"))
async def cb_cashout(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    owner_id = int(parts[1])
    user_id = callback.from_user.id
    
    if owner_id not in games:
        await callback.answer("Гра не знайдена!" if get_user_data(user_id)[2] == 'uk' else "Игра не найдена!", show_alert=True)
        return
        
    game = games[owner_id]
    _, _, lang = get_user_data(user_id)
    win = game["bet"] * game["multiplier"]
    update_balance(owner_id, win)
    markup = create_game_keyboard(owner_id, owner_id, reveal_all=True)
    del games[owner_id]
    balance, _, _ = get_user_data(owner_id)
    
    if lang == 'uk':
        msg = f"💰 **Забрано!**\nВиграш гравця: +{win:.2f}\nБаланс: {balance:.2f}"
    else:
        msg = f"💰 **Забрано!**\nВыигрыш игрока: +{win:.2f}\nБаланс: {balance:.2f}"
        
    await callback.message.edit_text(msg, reply_markup=markup, parse_mode="Markdown")

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущений!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
