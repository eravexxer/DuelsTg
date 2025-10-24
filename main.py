import os
import asyncio
import sqlite3
import logging
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения Railway
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not found!")
    exit(1)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация БД
def init_db():
    conn = sqlite3.connect('duel.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER,
            chat_id INTEGER,
            username TEXT,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            gold INTEGER DEFAULT 100,
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Класс для работы с дуэлями
class DuelManager:
    def __init__(self):
        self.active_duels = {}
    
    def create_duel(self, chat_id, initiator_id, target_id, initiator_name, target_name, bet=0):
        duel_id = f"{chat_id}_{initiator_id}_{target_id}_{datetime.now().timestamp()}"
        self.active_duels[duel_id] = {
            'initiator_id': initiator_id,
            'target_id': target_id,
            'initiator_name': initiator_name,
            'target_name': target_name,
            'chat_id': chat_id,
            'bet': bet,
            'created_at': datetime.now(),
            'round': 1,
            'initiator_ready': False,
            'target_ready': False,
            'initiator_hit': False,
            'target_hit': False,
            'winner': None
        }
        
        # Автоматическое удаление дуэли через 60 секунд
        asyncio.create_task(self.remove_duel_after_timeout(duel_id, 60))
        return duel_id
    
    async def remove_duel_after_timeout(self, duel_id, timeout=60):
        await asyncio.sleep(timeout)
        if duel_id in self.active_duels:
            duel = self.active_duels[duel_id]
            if not duel['winner']:
                self.remove_duel(duel_id)
    
    def get_duel(self, duel_id):
        return self.active_duels.get(duel_id)
    
    def make_shot(self, duel_id, user_id):
        if duel_id not in self.active_duels:
            return None
        
        duel = self.active_duels[duel_id]
        
        if user_id == duel['initiator_id']:
            duel['initiator_ready'] = True
        elif user_id == duel['target_id']:
            duel['target_ready'] = True
        
        if duel['initiator_ready'] and duel['target_ready']:
            duel['initiator_hit'] = random.random() <= 0.25
            duel['target_hit'] = random.random() <= 0.25
            
            if duel['initiator_hit'] and not duel['target_hit']:
                duel['winner'] = duel['initiator_id']
                return 'initiator_win'
            elif duel['target_hit'] and not duel['initiator_hit']:
                duel['winner'] = duel['target_id']
                return 'target_win'
            elif duel['initiator_hit'] and duel['target_hit']:
                duel['winner'] = random.choice([duel['initiator_id'], duel['target_id']])
                return 'both_hit'
            else:
                duel['round'] += 1
                duel['initiator_ready'] = False
                duel['target_ready'] = False
                return 'next_round'
        
        return 'waiting'
    
    def remove_duel(self, duel_id):
        if duel_id in self.active_duels:
            del self.active_duels[duel_id]

duel_manager = DuelManager()

# Класс для работы с пользователями
class UserManager:
    def __init__(self):
        self.conn = sqlite3.connect('duel.db', check_same_thread=False)
    
    def get_or_create_user(self, user_id, chat_id, username):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT * FROM users WHERE user_id = ? AND chat_id = ?',
            (user_id, chat_id)
        )
        user = cursor.fetchone()
        
        if not user:
            cursor.execute(
                'INSERT INTO users (user_id, chat_id, username) VALUES (?, ?, ?)',
                (user_id, chat_id, username)
            )
            self.conn.commit()
            cursor.execute(
                'SELECT * FROM users WHERE user_id = ? AND chat_id = ?',
                (user_id, chat_id)
            )
            user = cursor.fetchone()
        
        return user
    
    def update_stats(self, user_id, chat_id, won=True):
        cursor = self.conn.cursor()
        
        if won:
            cursor.execute(
                'UPDATE users SET wins = wins + 1, points = points + 1, exp = exp + 10 WHERE user_id = ? AND chat_id = ?',
                (user_id, chat_id)
            )
        else:
            cursor.execute(
                'UPDATE users SET losses = losses + 1, points = points - 1, exp = exp + 5 WHERE user_id = ? AND chat_id = ?',
                (user_id, chat_id)
            )
        
        self.conn.commit()

user_manager = UserManager()

# Клавиатуры
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="⚔️ Вызвать на дуэль", callback_data="how_to_duel")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton(text="📖 Правила", callback_data="rules")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_duel_keyboard(duel_id):
    keyboard = [
        [InlineKeyboardButton(text="🔫 ВЫСТРЕЛИТЬ!", callback_data=f"shoot_{duel_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Команды
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_manager.get_or_create_user(message.from_user.id, message.chat.id, 
                                  message.from_user.username or message.from_user.first_name)
    
    text = (
        "🎯 **GunDuel Bot**\n\n"
        "Дуэли с 25% шансом попадания!\n\n"
        "**Как играть:**\n"
        "Ответь на сообщение командой `/duel`"
    )
    
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode='Markdown')

@dp.message(Command("duel"))
async def duel_command(message: types.Message):
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        await create_duel(message, message.from_user, target_user, 0)
    else:
        await message.answer("❌ Ответь на сообщение командой `/duel`", parse_mode='Markdown')

async def create_duel(message: types.Message, initiator: types.User, target: types.User, bet: int = 0):
    if initiator.id == target.id:
        await message.reply("❌ Нельзя вызвать самого себя!")
        return
    
    if target.is_bot:
        await message.reply("❌ Нельзя вызвать бота!")
        return
    
    initiator_name = initiator.username or initiator.first_name
    target_name = target.username or target.first_name
    
    duel_id = duel_manager.create_duel(
        message.chat.id,
        initiator.id,
        target.id,
        initiator_name,
        target_name,
        bet
    )
    
    user_manager.get_or_create_user(initiator.id, message.chat.id, initiator_name)
    user_manager.get_or_create_user(target.id, message.chat.id, target_name)
    
    duel_text = (
        f"⚔️ **ДУЭЛЬ НАЧАЛАСЬ!**\n\n"
        f"🔫 {initiator_name} vs {target_name}\n"
        f"🎯 Шанс попадания: 25%\n"
        f"💥 Дуэль идет до победы!\n\n"
        f"**РАУНД 1** - нажмите кнопку ВЫСТРЕЛИТЬ!"
    )
    
    await message.reply(duel_text, reply_markup=get_duel_keyboard(duel_id), parse_mode='Markdown')

@dp.callback_query(F.data == "how_to_duel")
async def process_how_to_duel(callback: types.CallbackQuery):
    await callback.message.answer("🎯 Ответь на сообщение пользователя командой `/duel`", parse_mode='Markdown')

@dp.callback_query(F.data == "my_stats")
async def process_my_stats(callback: types.CallbackQuery):
    user_stats = user_manager.get_or_create_user(callback.from_user.id, callback.message.chat.id, callback.from_user.first_name)
    await callback.message.answer(
        f"📊 **Статистика**\n\n"
        f"🏆 Побед: {user_stats[3]}\n"
        f"💀 Поражений: {user_stats[4]}\n"
        f"🎯 Очков: {user_stats[5]}\n"
        f"💰 Золото: {user_stats[6]}",
        parse_mode='Markdown'
    )

@dp.callback_query(F.data.startswith("shoot_"))
async def process_shoot(callback: types.CallbackQuery):
    duel_id = callback.data.replace("shoot_", "")
    user_id = callback.from_user.id
    
    duel = duel_manager.get_duel(duel_id)
    if not duel:
        await callback.answer('Дуэль завершена!', show_alert=True)
        return
    
    if user_id not in [duel['initiator_id'], duel['target_id']]:
        await callback.answer('Вы не участник!', show_alert=True)
        return
    
    result = duel_manager.make_shot(duel_id, user_id)
    
    if result == 'waiting':
        await callback.answer('Ждем соперника...', show_alert=False)
        participants_text = (
            f"🔫 **РАУНД {duel['round']}**\n\n"
            f"Участники:\n"
            f"• {duel['initiator_name']} {'✅' if duel['initiator_ready'] else '❌'}\n"
            f"• {duel['target_name']} {'✅' if duel['target_ready'] else '❌'}\n\n"
            f"Ожидаем второго участника..."
        )
        await callback.message.edit_text(participants_text, reply_markup=get_duel_keyboard(duel_id))
    
    elif result == 'next_round':
        await callback.answer('Оба промахнулись!', show_alert=False)
        round_text = (
            f"💥 **РАУНД {duel['round']}**\n\n"
            f"Оба промахнулись!\n"
            f"Следующий раунд..."
        )
        await callback.message.edit_text(round_text, reply_markup=get_duel_keyboard(duel_id))
    
    elif result in ['initiator_win', 'target_win', 'both_hit']:
        if result == 'initiator_win':
            winner_id = duel['initiator_id']
            loser_id = duel['target_id']
            winner_name = duel['initiator_name']
            loser_name = duel['target_name']
        else:
            winner_id = duel['target_id']
            loser_id = duel['initiator_id']
            winner_name = duel['target_name']
            loser_name = duel['initiator_name']
        
        user_manager.update_stats(winner_id, duel['chat_id'], won=True)
        user_manager.update_stats(loser_id, duel['chat_id'], won=False)
        
        result_text = f"🎯 **ПОБЕДИТЕЛЬ: {winner_name}**\n\nДуэль завершена за {duel['round']} раундов!"
        await callback.message.edit_text(result_text, reply_markup=get_main_keyboard())
        duel_manager.remove_duel(duel_id)

async def main():
    logger.info("🚀 Bot starting on Railway...")
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())