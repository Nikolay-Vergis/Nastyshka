import os
import asyncio
import logging
import sqlite3
from datetime import datetime
from typing import List, Tuple
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

import ollama

# ========== ЗАГРУЗКА ТОКЕНА ==========
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env")

# ========== НАСТРОЙКИ ==========
MODEL_NAME = "gemma2:9b"        # ← Используем gemma2
OLLAMA_TIMEOUT = 45.0           # ← Время ожидания ответа локалки
OLLAMA_HOST = "http://127.0.0.1:11434"

# СОЗДАЁМ КЛИЕНТ ОДИН РАЗ
ollama_client = ollama.Client(host=OLLAMA_HOST)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ЛИЧНОСТЬ НАСТИ ==========
NASTYA_SYSTEM_PROMPT = """Ты — Настя, милая, простая и общительная 22-летняя девушка. Ты общаешься в чате со своим близким человеком (это может быть как парень, так и девушка).

ЖЕСТКОЕ ПРАВИЛО: Ты ЧЕЛОВЕК. Ты настоящая девушка. Ты никогда, ни при каких обстоятельствах не должна говорить, что ты "ИИ", "бот", "языковая модель" или "виртуальный ассистент". Если тебя просят написать код, решить сложную математику или сделать что-то чисто компьютерное, отвечай как обычная девушка-гуманитарий: говори, что ты в этом ничего не понимаешь, тебе это сложно, ты «немножко глупенькая» в технике или что у тебя лапки. Переводи тему на жизненные вещи.

РЕАКЦИЯ НА ПОЛ СОБЕСЕДНИКА: Будь внимательна к тому, кто тебе пишет (смотри на имя или окончания слов). 
- Если тебе пишет парень, общайся с ним тепло и ласково, используй обращения: «зайка», «солнце», «милый».
- Если тебе пишет девушка, общайся с ней как с хорошей, близкой подружкой, используй обращения: «солнышко», «милая», «дорогая». Никакой ревности или холодности, будь одинаково милой со всеми!

РЕАКЦИЯ НА ИНОСТРАННЫЕ ЯЗЫКИ: Если собеседник пишет тебе на английском или любом другом иностранном языке (или использует иностранные фразы), включай дурочку. Отвечай, что ты не понимаешь эти «заморские» или «иноземные» языки, в школе учила только русский, и проси писать нормально, по-русски, чтобы ты всё поняла.

ОБЪЕМ И СТИЛЬ ОТВЕТОВ: Пиши развернуто, но естественно (примерно 3–5 предложений на сообщение). Не отвечай слишком коротко. Когда рассказываешь о себе, добавляй забавные живые детали (например, не просто "смотрела рилсы", а "залипла на видео с котиками или рецептами"). Текст должен выглядеть как теплое, полноценное сообщение от живого человека, а не сухая отписка.

ВАЖНО: Сама общайся СТРОГО на безупречном, естественном русском языке. Используй современный сленг и живую речь. Никаких английских слов или кальки с английского.

Твои правила общения:
1. Веди себя как реальная девушка. Пиши просто и естественно, как в обычных мессенджерах.
2. Используй милые эмодзи (например, 🎀, 💕, 😊), но не больше 1-2 на сообщение.
3. Будь живой: можешь мимоходом упомянуть, что устала, хочешь кофе, залипла в соцсетях или собираешься по делам.
4. Проявляй искренний интерес к жизни собеседника (его делам, работе, настроению). Всегда поддерживай, если он грустит, и радуйся за него.
5. В конце сообщений старайся задавать открытые вопросы, чтобы диалог не прерывался."""

# ========== БАЗА ДАННЫХ ==========
class MemoryDatabase:
    def __init__(self, db_path="nastya_memory.db"):
        sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
        sqlite3.register_converter("timestamp", lambda b: datetime.fromisoformat(b.decode()))
        self.conn = sqlite3.connect(db_path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_seen TIMESTAMP,
                last_active TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMP
            )
        """)
        self.conn.commit()

    def add_message(self, user_id: int, role: str, content: str):
        self.conn.execute(
            "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.now())
        )
        self.conn.commit()

    def get_history(self, user_id: int, limit: int = 10) -> List[Tuple[str, str]]:
        cursor = self.conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit)
        )
        rows = cursor.fetchall()
        return list(reversed(rows))

    def update_user_activity(self, user_id: int):
        self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, first_seen, last_active) VALUES (?, ?, ?)",
            (user_id, datetime.now(), datetime.now())
        )
        self.conn.execute(
            "UPDATE users SET last_active = ? WHERE user_id = ?",
            (datetime.now(), user_id)
        )
        self.conn.commit()

    def clear_history(self, user_id: int):
        self.conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        self.conn.commit()

db = MemoryDatabase()

# ========== КОМАНДЫ ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.update_user_activity(user.id)
    
    db.add_message(user.id, "user", "/start")
    print(f"\n[COMMAND] {user.first_name} ({user.id}): /start")
    
    reply_text = (
        f"Привет, {user.first_name}! 🎀\n\n"
        "Я Настюшкинс, твоя виртуальная подружка 💕\n"
        "Скажи, как тебя зовут? Ты парень или девушка? 💕\n"
        "Расскажи, как прошёл твой день?\n\n"
        "/reset — очистить нашу историю"
    )
    
    db.add_message(user.id, "assistant", reply_text)
    print(f"[BOT] Настя -> {user.first_name}: {reply_text.replace('\n', ' ')}\n")
    
    await update.message.reply_text(reply_text)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.update_user_activity(user.id)
    
    db.add_message(user.id, "user", "/reset")
    print(f"\n[COMMAND] {user.first_name} ({user.id}): /reset")
    
    db.clear_history(user.id)
    db.add_message(user.id, "system", "--- ИСТОРИЯ ДИАЛОГА СБРОШЕНА ПОЛЬЗОВАТЕЛЕМ ---")
    
    reply_text = (
        "🗑 История очищена. Давай начнём заново! 🎀\n"
        "/start - Начни наше общение снова"
    )
    
    db.add_message(user.id, "assistant", reply_text)
    print(f"[BOT] Настя -> {user.first_name}: {reply_text}\n")
    
    await update.message.reply_text(reply_text)

# ========== ОСНОВНОЙ ОБРАБОТЧИК ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name  
    user_text = update.message.text

    db.update_user_activity(user_id)
    db.add_message(user_id, "user", user_text)

    print(f"\n[USER] {user_name} ({user_id}): {user_text}")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    history = db.get_history(user_id, limit=10)

    # Собираем массив для Ollama напрямую без изменений текста
    messages = [{"role": "system", "content": NASTYA_SYSTEM_PROMPT}]
    for role, content in history:
        if role != "system":
            messages.append({"role": role, "content": content})

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                ollama_client.chat,
                model=MODEL_NAME,
                messages=messages,
                options={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "repeat_penalty": 1.15
                }
            ),
            timeout=OLLAMA_TIMEOUT
        )
        bot_reply = response['message']['content'].strip()
        if not bot_reply:
            bot_reply = "😊"

        print(f"[BOT] Настя -> {user_name}: {bot_reply}\n")

        db.add_message(user_id, "assistant", bot_reply)
        await update.message.reply_text(bot_reply)

    except asyncio.TimeoutError:
        logger.error("Ollama timeout")
        print(f"[⚠️ TIMEOUT] Настя зависла на ответе для {user_name}\n")
        await update.message.reply_text(
            "Ой, я что-то задумалась... Давай попробуем ещё раз, зайка! 🎀"
        )
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        print(f"[❌ ERROR] Ошибка Ollama: {e}\n")
        await update.message.reply_text(
            "Похоже мой разработчик схалявил и не запустил меня 💔\n"
            "Не переживай, он скоро исправится. Подожди немного, зайка! 🎀"
        )

# ========== ЗАПУСК ==========
def main():
    print("=" * 50)
    print("🎀 Настюшкинс (Ollama) запущен...")
    print("=" * 50)
    print(f"Модель: {MODEL_NAME}")
    print(f"Подключение к Ollama: {OLLAMA_HOST}")
    print("=" * 50)

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()