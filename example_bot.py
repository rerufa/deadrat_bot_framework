import time
import os
from typing import List
from deadrat import Bot, Message

# --- Конфигурация ---
API_KEY = "YOUR_API_KEY"
# CUSTOM_URL = "http://localhost:8080/api/bot"

# Инициализация
bot = Bot(API_KEY)
# bot = Bot(API_KEY, base_url=CUSTOM_URL)


# --- 1. События жизненного цикла (Events) ---

@bot.event("startup")
def on_start():
    print(">>> Бот запущен! Создаю временный файл для тестов...")
    with open("test_file.txt", "w") as f:
        f.write("Это тестовый файл, отправленный ботом.")


@bot.event("shutdown")
def on_stop():
    print(">>> Бот выключается. Удаляю временный файл...")
    if os.path.exists("test_file.txt"):
        os.remove("test_file.txt")
    print(">>> Пока!")


@bot.event("error")
def on_error(e: Exception, msg: Message = None):
    # Этот хендлер ловит ошибки внутри других функций
    print(f"!!! Произошла ошибка: {e}")
    if msg:
        try:
            msg.reply(f"⚠️ Произошла ошибка: {e}")
        except:
            pass


# --- 2. Команды (Commands) ---

# Простая команда без аргументов
@bot.command("/ping")
def ping_handler(msg: Message):
    user = msg.author.username
    print(f"Пинг от {user}")
    msg.reply(f"Pong, {user}! 🏓\nID сообщения: {msg.id}")


# Команда с аргументами
@bot.command("/echo")
def echo_handler(msg: Message, args: List[str]):
    if not args:
        msg.reply("Эй, напиши что-нибудь после команды! Пример: /echo Привет")
        return

    text_to_repeat = " ".join(args)
    msg.reply(f"📢 Ты сказал: {text_to_repeat}")


# Команда с отправкой картинки
@bot.command("/file")
def file_handler(msg: Message):
    msg.reply("Загружаю файл...")
    # Отправка локального файла
    if os.path.exists("test_file.jpeg"):
        msg.reply_with_file("test_file.jpeg", text="Вот твой файл!")
    else:
        msg.reply("Ошибка: тестовый файл не найден.")


# Демонстрация интерактивности (Редактирование и Удаление)
@bot.command("/magic")
def magic_handler(msg: Message):
    # 1. Отправляем сообщение и сохраняем объект SentMessage
    sent = msg.reply("⏳ Считаю до 3...")

    if sent:
        time.sleep(1)
        # 2. Редактируем отправленное сообщение
        sent.edit("⏳ Считаю до 2...")
        time.sleep(1)
        sent.edit("⏳ Считаю до 1...")
        time.sleep(1)
        sent.edit("💥 ПУФ! Сообщение исчезнет через секунду!")
        time.sleep(1)

        # 3. Удаляем сообщение
        deleted = sent.delete()
        if deleted:
            print("Сообщение успешно удалено.")


# Демонстрация вызова ошибки (для проверки @bot.event("error"))
@bot.command("/crash")
def crash_handler(msg: Message):
    # Деление на ноль вызовет ошибку, которую поймает on_error
    x = 1 / 0


# --- 3. Обработка всех остальных сообщений ---

@bot.on_message()
def talk_handler(msg: Message):
    # Игнорируем свои же команды, если они вдруг сюда попадут (хотя не должны)
    if msg.text.startswith("/"):
        return

    # Ответ на конкретные слова
    text = msg.text.lower()

    if "привет" in text:
        msg.reply("Здарова! 👋")
    elif "info" in text:
        # Ответ на реплаи
        if msg.reply_to_message:
            target = msg.reply_to_message.author.username
            msg.reply(f"Ты ответил пользователю {target}")
        else:
            msg.reply("Это просто сообщение, не реплай.")
    else:
        # Просто логируем
        print(f"Получено сообщение без команды: {msg.text}")


# Запуск
if __name__ == "__main__":
    bot.run()
