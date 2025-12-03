import unittest
from unittest.mock import MagicMock, patch, mock_open
from deadrat import Bot, Message, SentMessage, Author


class TestDeadRatFramework(unittest.TestCase):

    def setUp(self):
        """Создаем бота перед каждым тестом"""
        self.api_key = "test_key"
        self.bot = Bot(self.api_key)
        # Мокаем сессию, чтобы не делать реальных запросов
        self.bot.session = MagicMock()

    # --- ТЕСТЫ ВСПОМОГАТЕЛЬНЫХ КЛАССОВ ---

    def test_author_init(self):
        data = {"author_id": "123", "username": "RatKing"}
        author = Author(data)
        self.assertEqual(author.id, "123")
        self.assertEqual(author.username, "RatKing")
        self.assertIn("RatKing", repr(author))

    def test_sent_message(self):
        data = {"id": "msg_100", "timestamp": 12345.0}
        sent = SentMessage(data, self.bot, "initial text")

        self.assertEqual(sent.id, "msg_100")
        self.assertEqual(sent.text, "initial text")
        self.assertIn("msg_100", repr(sent))

        # Тест edit (успех)
        self.bot.edit_message = MagicMock(return_value=True)
        self.assertTrue(sent.edit("new text"))
        self.assertEqual(sent.text, "new text")
        self.bot.edit_message.assert_called_with(sent, "new text")

        # Тест delete
        self.bot.delete_message = MagicMock(return_value=True)
        self.assertTrue(sent.delete())
        self.bot.delete_message.assert_called_with(sent)

    def test_message_parsing(self):
        # 1. Обычное сообщение
        data = {
            "id": "1",
            "author_id": "u1",
            "username": "User",
            "text": "Hello world",
            "timestamp": 1.0,
        }
        msg = Message(data, self.bot)
        self.assertEqual(msg.text, "Hello world")
        self.assertEqual(
            msg.command, "hello"
        )  # command парсится как первое слово lower()
        self.assertEqual(msg.args, ["world"])
        self.assertIsNone(msg.reply_to_message)
        self.assertIn("User", repr(msg))

        # 2. Сообщение с реплаем
        reply_data = {"id": "0", "text": "old", "author_id": "u2", "username": "Old"}
        data["replyToMessage"] = reply_data
        msg_reply = Message(data, self.bot)
        self.assertIsInstance(msg_reply.reply_to_message, Message)
        self.assertEqual(msg_reply.reply_to_message.text, "old")

    def test_message_actions(self):
        msg = Message({"id": "1", "text": "hi"}, self.bot)

        # Тест reply
        self.bot.send_message = MagicMock(return_value="sent_obj")
        res = msg.reply("response", "http://img")
        self.bot.send_message.assert_called_with(
            text="response", image_url="http://img", reply_to_id="1"
        )
        self.assertEqual(res, "sent_obj")

        # Тест reply_with_file
        self.bot.upload_file = MagicMock(return_value="http://url")
        msg.reply_with_file("path/to/file", "caption")
        self.bot.upload_file.assert_called_with("path/to/file")
        self.bot.send_message.assert_called_with(
            text="caption", image_url="http://url", reply_to_id="1"
        )

    # --- ТЕСТЫ МЕТОДОВ API БОТА ---

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=b"data")
    def test_upload_file(self, mock_file, mock_exists):
        # 1. Файл не существует
        mock_exists.return_value = False
        self.assertIsNone(self.bot.upload_file("fake.txt"))

        # 2. Успешная загрузка
        mock_exists.return_value = True
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"file_url": "http://suc.cess"}
        self.bot.session.post.return_value = mock_resp

        url = self.bot.upload_file("real.txt")
        self.assertEqual(url, "http://suc.cess")

        # 3. Ошибка сервера
        mock_resp.status_code = 500
        self.assertIsNone(self.bot.upload_file("real.txt"))

    def test_send_message_api(self):
        # Успех
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "10"}
        self.bot.session.post.return_value = mock_resp

        res = self.bot.send_message("hi")
        self.assertIsInstance(res, SentMessage)
        self.assertEqual(res.id, "10")

        # Ошибка
        mock_resp.status_code = 400
        self.assertIsNone(self.bot.send_message("hi"))

    def test_edit_delete_api(self):
        sent = SentMessage({"id": "1"}, self.bot)

        # Edit успех
        self.bot.session.put.return_value.status_code = 200
        self.assertTrue(self.bot.edit_message(sent, "new"))

        # Edit провал (например, нет ID)
        self.assertFalse(self.bot.edit_message("", "new"))

        # Delete успех
        self.bot.session.delete.return_value.status_code = 200
        self.assertTrue(self.bot.delete_message(sent))

    # --- ТЕСТЫ ДЕКОРАТОРОВ И ХЕНДЛЕРОВ ---

    def test_command_registration(self):
        # 1. Один аргумент (msg)
        @self.bot.command("/start")
        def start(msg):
            pass

        self.assertIn("/start", self.bot.command_handlers)
        func, wants_args = self.bot.command_handlers["/start"]
        self.assertFalse(wants_args)

        # 2. Два аргумента (msg, args)
        @self.bot.command("/echo")
        def echo(msg, args):
            pass

        func, wants_args = self.bot.command_handlers["/echo"]
        self.assertTrue(wants_args)

    def test_on_message_registration(self):
        @self.bot.on_message()
        def handler(msg):
            pass

        self.assertIn(handler, self.bot.message_handlers)

    def test_event_registration(self):
        @self.bot.event("startup")
        def on_start():
            pass

        self.assertEqual(self.bot.event_handlers["startup"], on_start)

        # Неизвестный эвент (должен логировать warning, но не падать)
        @self.bot.event("unknown")
        def unknown():
            pass

        # Проверяем, что не добавился
        self.assertNotIn("unknown", self.bot.event_handlers)

    def test_trigger_event(self):
        mock_handler = MagicMock()
        self.bot.event_handlers["startup"] = mock_handler
        self.bot._trigger("startup")
        mock_handler.assert_called_once()

    # --- ТЕСТ MAIN LOOP (bot.run) ---

    def test_run_logic(self):
        """
        Самый сложный тест. Симулируем ответы Long Polling и остановку цикла.
        """
        # Сценарий ответов session.get:
        # 1. Синхронизация (пустой список или история)
        # 2. Приходит сообщение с командой "/cmd"
        # 3. Приходит сообщение без команды
        # 4. KeyboardInterrupt (чтобы выйти из while True)

        resp_sync = MagicMock()
        resp_sync.status_code = 200
        resp_sync.json.return_value = []  # Пустая история

        resp_msg = MagicMock()
        resp_msg.status_code = 200
        resp_msg.json.return_value = [
            {
                "id": "1",
                "text": "/cmd arg",
                "timestamp": 10.0,
                "username": "u1",
            },  # Команда
            {
                "id": "2",
                "text": "just text",
                "timestamp": 11.0,
                "username": "u1",
            },  # Просто текст
        ]

        # Настраиваем мок сессии на последовательные ответы
        # 1-й вызов - sync, 2-й - сообщения, 3-й - имитация выключения
        self.bot.session.get.side_effect = [resp_sync, resp_msg, KeyboardInterrupt]

        # Мокаем хендлеры
        mock_cmd = MagicMock()
        self.bot.command_handlers["/cmd"] = (mock_cmd, True)  # Ждет аргументы

        mock_msg_handler = MagicMock()
        self.bot.message_handlers.append(mock_msg_handler)

        mock_startup = MagicMock()
        self.bot.event_handlers["startup"] = mock_startup

        mock_shutdown = MagicMock()
        self.bot.event_handlers["shutdown"] = mock_shutdown

        # Запускаем run. Ожидаем SystemExit (так как bot.run делает sys.exit(0))
        with self.assertRaises(SystemExit):
            self.bot.run()

        # ПРОВЕРКИ:

        # 1. Startup сработал
        mock_startup.assert_called_once()

        # 2. Команда обработалась
        mock_cmd.assert_called_once()
        # Проверяем аргументы вызова команды (Message, ["arg"])
        call_args = mock_cmd.call_args
        self.assertIsInstance(call_args[0][0], Message)
        self.assertEqual(call_args[0][1], ["arg"])

        # 3. Обычное сообщение обработалось
        mock_msg_handler.assert_called()  # Вызывается и для команды (если cmd_triggered=False), и для текста
        # В нашей логике, если команда сработала, обычный хендлер НЕ вызывается для этого сообщения.
        # Значит mock_msg_handler должен быть вызван 1 раз (для сообщения id=2)
        self.assertEqual(mock_msg_handler.call_count, 1)
        self.assertEqual(mock_msg_handler.call_args[0][0].text, "just text")

        # 4. Shutdown сработал
        mock_shutdown.assert_called_once()

    def test_run_403_error(self):
        # Тест невалидного токена
        resp_403 = MagicMock()
        resp_403.status_code = 403

        # Сразу возвращаем 403 при попытке получить апдейты
        self.bot.session.get.return_value = resp_403

        # Цикл должен прерваться (break) без SystemExit
        self.bot.run()
        # Если метод завершился без зависания и ошибок - тест пройден


if __name__ == "__main__":
    unittest.main()
