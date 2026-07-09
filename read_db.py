import sqlite3
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot

# Загружаем токен для красивых имён
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def export_history_to_file():
    bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

    # Подключаемся к базе данных
    conn = sqlite3.connect("nastya_memory.db")
    cursor = conn.cursor()

    # Сортируем сначала по user_id, а внутри него — по времени отправки
    cursor.execute("""
        SELECT timestamp, user_id, role, content 
        FROM messages 
        ORDER BY user_id ASC, timestamp ASC
    """)
    rows = cursor.fetchall()
    conn.close() # Теперь закрываем базу только после того, как ВСЁ забрали

    if not rows:
        print("База данных пуста, нечего записывать.")
        return

    user_cache = {}
    output_filename = "chat_logs.txt"
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Открываем файл в режиме 'w' (перезапись при каждом запуске)
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f" СГРУППИРОВАННЫЙ ЛОГ ПЕРЕПИСКИ (Обновлено: {current_time})\n")
        f.write("=" * 80 + "\n\n")

        current_user_id = None

        for timestamp, user_id, role, content in rows:
            # Если начался новый пользователь, делаем красивый визуальный разделитель
            if user_id != current_user_id:
                current_user_id = user_id
                
                # Узнаем имя пользователя
                if user_id not in user_cache and bot:
                    try:
                        chat = await bot.get_chat(user_id)
                        name = f"@{chat.username}" if chat.username else f"{chat.first_name or ''} {chat.last_name or ''}".strip()
                        user_cache[user_id] = name
                    except Exception:
                        user_cache[user_id] = f"Пользователь [{user_id}]"
                elif not bot:
                    user_cache[user_id] = f"ID: {user_id}"

                f.write(f"\n\n{'#' * 20} ДИАЛОГ С ПОЛЬЗОВАТЕЛЕМ: {user_cache[user_id]} (ID: {user_id}) {'#' * 20}\n\n")

            # Форматируем отправителя
            sender = f"👤 {user_cache[user_id]}" if role == "user" else "🎀 Настя"
            
            # Записываем сообщение в файл
            f.write(f"[{timestamp}] {sender}:\n{content}\n")
            f.write("-" * 50 + "\n")

    print(f"✅ Лог успешно перезаписан и сохранен в файл: {output_filename}")

if __name__ == "__main__":
    asyncio.run(export_history_to_file())