import asyncio
import sqlite3
import random
import time
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# === НАЛАШТУВАННЯ ===
TOKEN = "8814469553:AAEhx7dTIpsk_o-6v-37PYnxu3sByPsCkz4"
ADMIN_IDS = [8259900140]

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === БАЗА ДАНИХ ===
conn = sqlite3.connect("burmalda.db")
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 1000,
    last_bonus INTEGER DEFAULT 0
)
''')
conn.commit()

active_mines = {}

def get_user(user_id, username):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)", (user_id, username, 1000))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    return user

def update_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def calculate_multiplier(mines_count, opened_count):
    if opened_count == 0:
        return 1.0
    safe_tiles = 25 - mines_count
    prob = 1.0
    for i in range(opened_count):
        prob *= (safe_tiles - i) / (25 - i)
    raw_mult = 0.95 / prob
    return round(raw_mult, 2)

# === МЕНЮ ТА КОМАНДИ ===

@dp.message(Command("help"))
@dp.message(Command("start"))
@dp.message(F.text.lower().in_(["команды", "команди", "помощь", "допомога", "меню"]))
async def cmd_help(message: types.Message):
    get_user(message.from_user.id, message.from_user.username or "Гравець")
    
    help_text = (
        "💎 **Ігровий Бот — BURMALDA** 💎\n\n"
        "📊 **Основні команди:**\n"
        "🔹 `баланс` — Перевірити свій рахунок\n"
        "🔹 `бонус` — Отримати щогодинний бонус (500 💰)\n"
        "🔹 `передати бурмалду [сума]` — Переказати бурмалду гравцю (відповіддю на його повідомлення)\n\n"
        "🎮 **Ігри:**\n"
        "💣 `бурмалдмина [ставка]` — Гра в мінне поле 5x5\n"
        "   *(Кількість мін визначається випадково від 1 до 10!)*\n\n"
        "👑 **Адмін-команди:**\n"
        "🛠 `видати бурмалду [сума]` — Нарахувати кошти (тільки для адміна)"
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(F.text.lower() == "баланс")
async def cmd_balance(message: types.Message):
    user = get_user(message.from_user.id, message.from_user.username or "Гравець")
    await message.answer(f"💳 Ваш баланс: **{user[2]}** бурмалди 💰", parse_mode="Markdown")

@dp.message(F.text.lower() == "бонус")
async def cmd_bonus(message: types.Message):
    user = get_user(message.from_user.id, message.from_user.username or "Гравець")
    current_time = int(time.time())
    cooldown = 3600
    
    if current_time - user[3] >= cooldown:
        cursor.execute("UPDATE users SET balance = balance + 500, last_bonus = ? WHERE user_id = ?", (current_time, message.from_user.id))
        conn.commit()
        await message.answer("🎁 Ви отримали щогодинний бонус: **500** бурмалди!", parse_mode="Markdown")
    else:
        left_time = (cooldown - (current_time - user[3])) // 60
        await message.answer(f"⏳ Бонус можна забрати через **{left_time}** хв.", parse_mode="Markdown")

@dp.message(F.text.lower().startswith("передати бурмалду"))
async def cmd_transfer(message: types.Message):
    if not message.reply_to_message:
        await message.answer("⚠️ Цю команду треба писати **у відповідь (reply)** на повідомлення гравця!")
        return

    args = message.text.split()
    if len(args) < 3 or not args[2].isdigit():
        await message.answer("⚠️ Формат: `передати бурмалду [сума]` (у відповідь на повідомлення)", parse_mode="Markdown")
        return

    amount = int(args[2])
    sender = get_user(message.from_user.id, message.from_user.username or "Гравець")
    recipient = get_user(message.reply_to_message.from_user.id, message.reply_to_message.from_user.username or "Гравець")

    if sender[0] == recipient[0]:
        await message.answer("❌ Не можна передавати бурмалду самому собі!")
        return

    if sender[2] < amount or amount <= 0:
        await message.answer("❌ У вас недостатньо бурмалди!")
        return

    update_balance(sender[0], -amount)
    update_balance(recipient[0], amount)
    
    target_name = message.reply_to_message.from_user.username
    target_str = f"@{target_name}" if target_name else message.reply_to_message.from_user.first_name
    await message.answer(f"✅ Ви успішно передали **{amount}** бурмалди користувачу {target_str}!", parse_mode="Markdown")

@dp.message(F.text.lower().startswith("видати бурмалду"))
async def cmd_give_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.text.split()
    if len(args) < 3 or not args[2].isdigit():
        await message.answer("⚠️ Напишіть: `видати бурмалду [сума]`", parse_mode="Markdown")
        return

    amount = int(args[2])
    get_user(message.from_user.id, message.from_user.username or "Адмін")
    update_balance(message.from_user.id, amount)
    await message.answer(f"👑 **Адмін-режим:** Нараховано **{amount}** бурмалди!", parse_mode="Markdown")

# === МІННЕ ПОЛЕ (5x5, ВИПАДКОВА КІЛЬКІСТЬ МІН) ===

@dp.message(F.text.lower().startswith("бурмалдмина"))
async def cmd_mines(message: types.Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Формат: `бурмалдмина [ставка]`\n*Приклад:* `бурмалдмина 100`", parse_mode="Markdown")
        return

    bet = int(args[1])
    user = get_user(message.from_user.id, message.from_user.username or "Гравець")

    if bet <= 0 or user[2] < bet:
        await message.answer("❌ Недостатньо бурмалди для такої ставки!")
        return

    if message.from_user.id in active_mines:
        await message.answer("⚠️ У вас вже є активна гра в міни!")
        return

    update_balance(message.from_user.id, -bet)
    
    # Випадкова кількість мін від 1 до 10
    mines_count = random.randint(1, 10)
    mines_pos = set(random.sample(range(25), mines_count))
    
    active_mines[message.from_user.id] = {
        "bet": bet, 
        "mines_count": mines_count,
        "mines": mines_pos, 
        "opened": set()
    }

    text = (
        f"💣 **Гра «Міни» 5x5**\n"
        f"👤 Гравець: {message.from_user.first_name}\n"
        f"💰 Ставка: **{bet}** | ❓ Міни: **Випадково (1–10)**\n"
        f"📈 Множник: **1.0x**"
    )

    await message.answer(text, reply_markup=get_mines_keyboard(message.from_user.id), parse_mode="Markdown")

def get_mines_keyboard(user_id, show_all=False):
    kb = []
    game = active_mines.get(user_id, {})
    mines = game.get("mines", set())
    opened = game.get("opened", set())

    for row in range(5):
        row_buttons = []
        for col in range(5):
            idx = row * 5 + col
            if show_all:
                if idx in mines:
                    btn_text = "💥"
                elif idx in opened:
                    btn_text = "💎"
                else:
                    btn_text = "▫️"
                cb = "ignore"
            else:
                if idx in opened:
                    btn_text = "💎"
                    cb = "ignore"
                else:
                    btn_text = "🟦"
                    cb = f"mine_{idx}"

            row_buttons.append(InlineKeyboardButton(text=btn_text, callback_data=cb))
        kb.append(row_buttons)

    if not show_all and len(opened) > 0:
        mult = calculate_multiplier(game["mines_count"], len(opened))
        win_amt = int(game["bet"] * mult)
        kb.append([InlineKeyboardButton(text=f"💰 Забрати {win_amt} бурмалди ({mult}x)", callback_data="mine_cashout")])

    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.callback_query(F.data.startswith("mine_"))
async def process_mine_click(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines:
        await callback.answer("Гра закінчена або відкрита іншим гравцем!", show_alert=True)
        return

    game = active_mines[user_id]
    action = callback.data.split("_")[1]

    if action == "cashout":
        opened_cnt = len(game["opened"])
        mult = calculate_multiplier(game["mines_count"], opened_cnt)
        win_amount = int(game["bet"] * mult)
        update_balance(user_id, win_amount)

        text = (
            f"🎉 **Ви забрали виграш!**\n"
            f"💰 Виграно: **{win_amount}** бурмалди ({mult}x)!\n"
            f"💣 На полі було мін: **{game['mines_count']}**"
        )
        await callback.message.edit_text(text, reply_markup=get_mines_keyboard(user_id, show_all=True), parse_mode="Markdown")
        del active_mines[user_id]
        return

    pos = int(action)

    if pos in game["mines"]:
        text = (
            f"💥 **БУМ!** Ви підірвалися на міні!\n"
            f"💸 Втрачено: **{game['bet']}** бурмалди.\n"
            f"💣 Всього на полі було мін: **{game['mines_count']}**"
        )
        await callback.message.edit_text(text, reply_markup=get_mines_keyboard(user_id, show_all=True), parse_mode="Markdown")
        del active_mines[user_id]
    else:
        game["opened"].add(pos)
        opened_cnt = len(game["opened"])
        max_safe = 25 - game["mines_count"]

        if opened_cnt == max_safe:
            mult = calculate_multiplier(game["mines_count"], opened_cnt)
            win_amount = int(game["bet"] * mult)
            update_balance(user_id, win_amount)

            text = (
                f"🏆 **ПЕРЕМОГА!** Відкрито всі безпечні клітинки!\n"
                f"💰 Ваш виграш: **{win_amount}** бурмалди ({mult}x)!\n"
                f"💣 На полі було мін: **{game['mines_count']}**"
            )
            await callback.message.edit_text(text, reply_markup=get_mines_keyboard(user_id, show_all=True), parse_mode="Markdown")
            del active_mines[user_id]
        else:
            mult = calculate_multiplier(game["mines_count"], opened_cnt)
            text = (
                f"💣 **Гра «Міни» 5x5**\n"
                f"👤 Гравець: {callback.from_user.first_name}\n"
                f"💰 Ставка: **{game['bet']}** | ❓ Міни: **Сховано**\n"
                f"💎 Відкрито клітинок: **{opened_cnt}** | 📈 Множник: **{mult}x**"
            )
            await callback.message.edit_text(text, reply_markup=get_mines_keyboard(user_id), parse_mode="Markdown")

async def main():
    print("Бот успішно запущений!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())