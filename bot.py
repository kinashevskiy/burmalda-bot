import asyncio
import logging
import random
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Токен вашого бота
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

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
    if row is None:
        return 1000.0
    conn.close()
    return row[0]

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

# --- Стан поточних ігор у пам'яті ---
games = {}

def create_game_keyboard(user_id: int, reveal_all=False):
    builder = InlineKeyboardBuilder()
    game = games.get(user_id)
    
    for i in range(25):
        if reveal_all:
            text = "💣" if game["board"][i] else "💎"
        else:
            if game["revealed"][i]:
                text = "💎"
            else:
                text = "⬛"
        
        builder.button(text=text, callback_data=f"cell_{i}")
        
    builder.adjust(5)
    
    if not reveal_all:
        builder.button(text="💰 Забрати виграш", callback_data="cashout")
        builder.adjust(5, 5, 5, 5, 5, 1)
        
    return builder.as_markup()

# --- Обробка команд та повідомлень ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    update_user_info(message.from_user)
    balance = get_balance(message.from_user.id)
    text = (
        f"👋 Вітаємо в грі **Міни**!\n\n"
        f"💵 Ваш баланс: **{balance:.2f} грн**\n\n"
        f"📜 **Список команд:**\n"
        f"🔹 `/mine [ставка]` — Почати нову гру (наприклад: `/mine 50`)\n"
        f"🔹 `/leader` або слово **топ** — Переглянути топ гравців\n"
        f"🔹 `/start` — Подивитися баланс і меню"
    )
    await message.answer(text, parse_mode="Markdown")

# Перегляд топу за командою /leader, /top або просто словами "топ" / "top"
@dp.message(Command("leader", "top"))
@dp.message(F.text.lower().in_(["топ", "top", "топчик", "лідери"]))
async def cmd_leader(message: types.Message):
    leaders = get_top_leaders()
    
    if not leaders:
        await message.answer("🏆 Таблиця лідерів поки що порожня!")
        return

    text = "🏆 **Таблиця лідерів за балансом:**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for idx, (first_name, username, balance) in enumerate(leaders, 1):
        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        name = f"@{username}" if username else first_name
        text += f"{medal} **{name}** — {balance:.2f} грн\n"

    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("mine"))
async def cmd_mine(message: types.Message):
    user_id = message.from_user.id
    update_user_info(message.from_user)
    
    if user_id in games:
        await message.answer("⚠️ У вас вже є активна гра! Завершіть її спочатку.")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❌ Вкажіть суму ставки. Наприклад: `/mine 50`", parse_mode="Markdown")
        return

    bet = float(args[1])
    balance = get_balance(user_id)

    if bet <= 0:
        await message.answer("❌ Ставка має бути більшою за 0.")
        return

    if bet > balance:
        await message.answer(f"❌ Недостатньо коштів! Ваш баланс: {balance:.2f} грн")
        return

    # Знімаємо ставку
    update_balance(user_id, -bet)

    # Налаштування гри: від 8 до 15 мін, початковий X = 1.25
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
        f"🎮 **Гра розпочата!**\n\n"
        f"💰 Ставка: **{bet:.2f} грн**\n"
        f"💣 Кількість мін: **{mines_count}**\n"
        f"📈 Початковий коефіцієнт: **x{initial_multiplier:.2f}**\n"
        f"💵 Поточний виграш: **{(bet * initial_multiplier):.2f} грн**"
    )
    
    await message.answer(text, reply_markup=create_game_keyboard(user_id), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cell_"))
async def process_cell_click(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in games:
        await callback.answer("Ця гра вже завершена!", show_alert=True)
        return

    cell_index = int(callback.data.split("_")[1])
    game = games[user_id]

    if game["revealed"][cell_index]:
        await callback.answer("Ця клітинка вже відкрита!")
        return

    # Програш
    if game["board"][cell_index]:
        bet = game["bet"]
        markup = create_game_keyboard(user_id, reveal_all=True)
        del games[user_id]
        
        await callback.message.edit_text(
            f"💥 **БУМ! Ви натрапили на міну!**\n\n"
            f"❌ Втрачена ставка: **{bet:.2f} грн**\n"
            f"💵 Баланс: **{get_balance(user_id):.2f} грн**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    # Безпечна клітинка
    game["revealed"][cell_index] = True
    game["multiplier"] += 0.25  # Додаємо +0.25 до X

    revealed_safe_count = sum(1 for i in range(25) if game["revealed"][i] and not game["board"][i])
    total_safe_cells = 25 - game["mines_count"]

    # Автоматична перемога
    if revealed_safe_count == total_safe_cells:
        win_amount = game["bet"] * game["multiplier"]
        update_balance(user_id, win_amount)
        markup = create_game_keyboard(user_id, reveal_all=True)
        del games[user_id]

        await callback.message.edit_text(
            f"🎉 **НЕЙМОВІРНО! Ви очистили все поле!**\n\n"
            f"🏆 Множник: **x{game['multiplier']:.2f}**\n"
            f"💰 Виграш: **+{win_amount:.2f} грн**\n"
            f"💵 Новий баланс: **{get_balance(user_id):.2f} грн**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    win_amount = game["bet"] * game["multiplier"]
    text = (
        f"💎 **Безпечно!**\n\n"
        f"💰 Ставка: **{game['bet']:.2f} грн**\n"
        f"💣 Мін на полі: **{game['mines_count']}**\n"
        f"📈 Поточний X: **x{game['multiplier']:.2f}** (+0.25)\n"
        f"💵 Можна забрати: **{win_amount:.2f} грн**"
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
        f"💵 Виграно: **+{win_amount:.2f} грн**\n"
        f"💳 Поточний баланс: **{get_balance(user_id):.2f} грн**",
        reply_markup=markup,
        parse_mode="Markdown"
    )

async def main():
    init_db()
    print("Бот успішно запущений!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
