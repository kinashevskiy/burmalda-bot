import asyncio
import logging
import os
import random
import sqlite3
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
            balance REAL DEFAULT 1000.0
        )
    """)
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if "first_name" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    
    conn.commit()
    conn.close()

def update_user_info(user: types.User):
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, username, first_name, balance)
        VALUES (?, ?, ?, 1000.0)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    """, (user.id, user.username, user.first_name))
    conn.commit()
    conn.close()

def get_balance(user_id: int) -> float:
    conn = sqlite3.connect("burmalda.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 1000.0

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

# --- Логіка команд українською ---

async def handle_start(message: types.Message):
    update_user_info(message.from_user)
    balance = get_balance(message.from_user.id)
    text = (
        f"👋 Вітаємо у світі **Бурмалд**!\n\n"
        f"💵 Ваш баланс: **{balance:.2f} бурмалд**\n\n"
        f"📜 Напишіть слово **команди**, щоб переглянути список доступних команд."
    )
    await message.answer(text, parse_mode="Markdown")

async def handle_commands(message: types.Message):
    text = (
        f"📜 **Список команд бота:**\n\n"
        f"🔹 **команди** — Подивитися список команд\n"
        f"🔹 **бурмалдмина [ставка]** — Грати в бурмалдмину (наприклад: `бурмалдмина 50`)\n"
        f"🔹 **топ** — Таблиця лідерів\n"
        f"🔹 **баланс** — Перевірити баланс\n\n"
        f"👑 **Адмін-команди:**\n"
        f"• `видатибурмалду [сума]` — собі\n"
        f"• `видатибурмалду [ID] [сума]` — іншому гравцю"
    )
    await message.answer(text, parse_mode="Markdown")

async def handle_balance(message: types.Message):
    update_user_info(message.from_user)
    balance = get_balance(message.from_user.id)
    await message.answer(f"💵 Ваш поточний баланс: **{balance:.2f} бурмалд**", parse_mode="Markdown")

async def handle_top(message: types.Message):
    leaders = get_top_leaders()
    if not leaders:
        await message.answer("🏆 Таблиця лідерів порожня!")
        return

    text = "🏆 **Таблиця лідерів (Бурмазди):**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for idx, (first_name, username, balance) in enumerate(leaders, 1):
        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        name = f"@{username}" if username else (first_name or "Гравець")
        text += f"{medal} **{name}** — {balance:.2f} бурмалд\n"

    await message.answer(text, parse_mode="Markdown")

async def handle_giveburmalda(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас немає прав адміна!")
        return

    args = message.text.split()
    
    # Видача собі: видатибурмалду [сума]
    if len(args) == 2:
        try:
            amount = float(args[1])
        except ValueError:
            await message.answer("❌ Введіть коректну суму!")
            return
        
        target_id = message.from_user.id
        update_balance(target_id, amount)
        new_bal = get_balance(target_id)
        await message.answer(f"✅ Ви нарахували собі **{amount:.2f} бурмалд**!\nНовий баланс: **{new_bal:.2f} бурмалд**", parse_mode="Markdown")
        return

    # Видача іншому: видатибурмалду [ID] [сума]
    if len(args) >= 3 and args[1].isdigit():
        target_id = int(args[1])
        try:
            amount = float(args[2])
        except ValueError:
            await message.answer("❌ Введіть коректну суму!")
            return

        update_balance(target_id, amount)
        new_bal = get_balance(target_id)
        await message.answer(f"✅ Нараховано **{amount:.2f} бурмалд** користувачу `{target_id}`!\nНовий баланс: **{new_bal:.2f} бурмалд**", parse_mode="Markdown")
        return

    await message.answer("❌ Формат:\nДля себе: `видатибурмалду [сума]`\nДля іншого: `видатибурмалду [ID] [сума]`", parse_mode="Markdown")

async def handle_burmaldmine(message: types.Message):
    user_id = message.from_user.id
    update_user_info(message.from_user)
    
    if user_id in games:
        await message.answer("⚠️ У вас вже є активна гра!")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❌ Вкажіть ставку. Наприклад: `бурмалдмина 50`", parse_mode="Markdown")
        return

    bet = float(args[1])
    balance = get_balance(user_id)

    if bet <= 0 or bet > balance:
        await message.answer(f"❌ Некоректна ставка або недостатньо бурмалд! Баланс: {balance:.2f}")
        return

    update_balance(user_id, -bet)

    mines_count = random.randint(8, 15)
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

    text = (
        f"🎮 **Бурмалдмину розпочато!**\n\n"
        f"💰 Ставка: **{bet:.2f} бурмалд**\n"
        f"💣 Мін: **{mines_count}**\n"
        f"📈 Початковий коефіцієнт: **x{initial_multiplier:.2f}**\n"
        f"💵 Виграш: **{(bet * initial_multiplier):.2f} бурмалд**"
    )
    
    await message.answer(text, reply_markup=create_game_keyboard(user_id), parse_mode="Markdown")


# --- Реєстрація обробників (слова українською та стандартні слеші) ---

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


@dp.message(Command("burmaldmine"))
async def cmd_mine_slash(message: types.Message):
    await handle_burmaldmine(message)

@dp.message(F.text.casefold().startswith(("бурмалдмина", "burmaldmine")))
async def cmd_mine_text(message: types.Message):
    await handle_burmaldmine(message)


# --- Callback-запити (кнопки) ---

@dp.callback_query(F.data.startswith("cell_"))
async def process_cell_click(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in games:
        await callback.answer("Гра завершена!", show_alert=True)
        return

    cell_index = int(callback.data.split("_")[1])
    game = games[user_id]

    if game["revealed"][cell_index]:
        await callback.answer("Клітинка вже відкрита!")
        return

    if game["board"][cell_index]:
        bet = game["bet"]
        markup = create_game_keyboard(user_id, reveal_all=True)
        del games[user_id]
        
        await callback.message.edit_text(
            f"💥 **БУМ! Ви натрапили на міну!**\n\n"
            f"❌ Втрачено: **{bet:.2f} бурмалд**\n"
            f"💵 Баланс: **{get_balance(user_id):.2f} бурмалд**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    game["revealed"][cell_index] = True
    game["multiplier"] += 0.25

    revealed_safe_count = sum(1 for i in range(25) if game["revealed"][i] and not game["board"][i])
    total_safe_cells = 25 - game["mines_count"]

    if revealed_safe_count == total_safe_cells:
        win_amount = game["bet"] * game["multiplier"]
        update_balance(user_id, win_amount)
        markup = create_game_keyboard(user_id, reveal_all=True)
        del games[user_id]

        await callback.message.edit_text(
            f"🎉 **НЕЙМОВІРНО! Ви відкрили всі безпечні клітинки!**\n\n"
            f"🏆 Множник: **x{game['multiplier']:.2f}**\n"
            f"💰 Виграш: **+{win_amount:.2f} бурмалд**\n"
            f"💵 Баланс: **{get_balance(user_id):.2f} бурмалд**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    win_amount = game["bet"] * game["multiplier"]
    text = (
        f"💎 **Безпечно!**\n\n"
        f"💰 Ставка: **{game['bet']:.2f} бурмалд**\n"
        f"💣 Мін: **{game['mines_count']}**\n"
        f"📈 Множник: **x{game['multiplier']:.2f}** (+0.25)\n"
        f"💵 Виграш: **{win_amount:.2f} бурмалд**"
    )
    
    await callback.message.edit_text(text, reply_markup=create_game_keyboard(user_id), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "cashout")
async def process_cashout(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in games:
        await callback.answer("Гра не знайдена!", show_alert=True)
        return

    game = games[user_id]
    win_amount = game["bet"] * game["multiplier"]
    update_balance(user_id, win_amount)
    
    markup = create_game_keyboard(user_id, reveal_all=True)
    multiplier = game["multiplier"]
    del games[user_id]

    await callback.message.edit_text(
        f"💰 **Виграш забрано!**\n\n"
        f"📈 Множник: **x{multiplier:.2f}**\n"
        f"💵 Забрано: **+{win_amount:.2f} бурмалд**\n"
        f"💳 Баланс: **{get_balance(user_id):.2f} бурмалд**",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# --- Веб-сервер Render ---
async def handle_ping(request):
    return web.Response(text="OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    init_db()
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущений!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
