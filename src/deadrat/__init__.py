import requests
import time
import logging
import os
import sys
import inspect
from typing import Dict, List, Optional, Callable, Any, Union, Tuple

# --- Type Aliases ---
MessagePayload = Dict[str, Any]
CommandHandler = Callable[..., None]
MessageHandler = Callable[["Message"], None]
GenericEventHandler = Callable[..., Any]
EventDecorator = Callable[[GenericEventHandler], GenericEventHandler]

DEFAULT_API_URL = "https://s1.deadrat.exelus.space/api/bot"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("deadrat_bot_framework")


class SentMessage:
    """
    Represents a message that the bot has successfully sent.
    Allows editing or deleting the message later.

    Args:
        data (dict): The raw JSON payload returned by the API after sending.
        bot (Bot): The Bot instance that sent this message.
        initial_text (str, optional): The original text content of the message.
    """

    def __init__(
        self, data: MessagePayload, bot: "Bot", initial_text: Optional[str] = None
    ) -> None:
        self.bot: "Bot" = bot
        self.id: Optional[str] = data.get("id")
        self.timestamp: Optional[float] = data.get("timestamp")
        self.text: Optional[str] = initial_text

    def edit(self, new_text: str) -> bool:
        """
        Edits this message with new text.

        Args:
            new_text (str): The new text content for the message.

        Returns:
            bool: True if the edit was successful, False otherwise.
        """
        if self.bot.edit_message(self, new_text):
            self.text = new_text
            return True
        return False

    def delete(self) -> bool:
        """
        Deletes this message from the chat.

        Returns:
            bool: True if the deletion was successful, False otherwise.
        """
        return self.bot.delete_message(self)

    def __repr__(self) -> str:
        return f"<SentMessage id={self.id}>"


class Author:
    """
    Represents the author of a message.

    Args:
        data (dict): The raw JSON payload containing author information.

    Attributes:
        id (str): The unique ID of the user.
        username (str): The display name of the user.
    """

    def __init__(self, data: MessagePayload) -> None:
        self.id: Optional[str] = data.get("author_id")
        self.username: Optional[str] = data.get("username")

    def __repr__(self) -> str:
        return f"<Author username='{self.username}'>"


class Message:
    """
    Represents a message received by the bot.
    Contains methods to reply directly to this message.

    Args:
        data (dict): The raw JSON payload for the message.
        bot (Bot): The Bot instance that received this message.

    Attributes:
        text (str): The full text content of the message.
        author (Author): The author of the message.
        reply_to_message (Message | None): The message object this message is replying to (if any).
        command (str | None): The command trigger (e.g., "/start") if present.
        args (list[str]): List of arguments following the command.
    """

    def __init__(self, data: MessagePayload, bot: "Bot") -> None:
        self.bot: "Bot" = bot
        self.id: Optional[str] = data.get("id")
        self.author: Author = Author(data)
        self.text: str = data.get("text", "").strip()
        self.timestamp: Optional[float] = data.get("timestamp")
        self.raw: MessagePayload = data

        self.command: Optional[str] = None
        self.args: List[str] = []
        parts = self.text.split(" ", 1)
        if parts:
            self.command = parts[0].lower()
            if len(parts) > 1:
                self.args = parts[1].split()

        reply_data: Optional[MessagePayload] = data.get("replyToMessage")
        if reply_data:
            self.reply_to_message: Optional["Message"] = Message(reply_data, self.bot)
        else:
            self.reply_to_message: Optional["Message"] = None

    def reply(
        self, text: Optional[str] = None, image_url: Optional[str] = None
    ) -> Optional[SentMessage]:
        """
        Replies directly to this message.

        Args:
            text (str, optional): The text content for the reply.
            image_url (str, optional): A URL to an image to include in the reply.

        Returns:
            SentMessage | None: A SentMessage object on success, or None on failure.
        """
        return self.bot.send_message(
            text=text, image_url=image_url, reply_to_id=self.id
        )

    def reply_with_file(
        self, file_path: str, text: Optional[str] = None
    ) -> Optional[SentMessage]:
        """
        Uploads a local file and replies with it.

        Args:
            file_path (str): The local path to the file to upload.
            text (str, optional): Optional text to accompany the file.

        Returns:
            SentMessage | None: A SentMessage object on success, or None on failure.
        """
        url = self.bot.upload_file(file_path)
        if url:
            return self.reply(text=text, image_url=url)
        return None

    def __repr__(self) -> str:
        return f"<Message from {self.author.username}: {self.text[:20]}...>"


class Bot:
    """
    The main Bot class that orchestrates API communication and message handling.

    Args:
        api_key (str): Your unique API key for authentication.
        base_url (str, optional): The base URL for the bot API endpoint.
                                  Defaults to the official DeadRat API.
    """

    def __init__(self, api_key: str, base_url: str = DEFAULT_API_URL) -> None:
        self.api_key: str = api_key
        self.base_url: str = base_url.rstrip("/")
        self.root_url: str = self.base_url.replace("/bot", "")

        self.session: requests.Session = requests.Session()
        self.session.headers.update({"x-api-key": self.api_key})

        self.command_handlers: Dict[str, Tuple[CommandHandler, bool]] = {}
        self.message_handlers: List[MessageHandler] = []
        self.event_handlers: Dict[str, Optional[GenericEventHandler]] = {
            "startup": None,
            "shutdown": None,
            "connection_error": None,
            "error": None,
        }

        self.last_ts: float = 0.0

    # --- API Actions ---

    def upload_file(self, file_path: str) -> Optional[str]:
        """
        Uploads a file to the server.

        Args:
            file_path (str): The local path to the file.

        Returns:
            str | None: The URL of the uploaded file on success, otherwise None.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        url = f"{self.root_url}/upload"
        try:
            with open(file_path, "rb") as f:
                files = {"file": f}
                resp = self.session.post(url, files=files)
            if resp.status_code == 200:
                return resp.json().get("file_url")
            else:
                logger.error(f"Upload failed ({resp.status_code}): {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None

    def send_message(
        self,
        text: Optional[str] = None,
        image_url: Optional[str] = None,
        reply_to_id: Optional[str] = None,
    ) -> Optional[SentMessage]:
        """
        Sends a message to the chat.

        Args:
            text (str, optional): The text content of the message.
            image_url (str, optional): A URL to an image to be included in the message.
            reply_to_id (str, optional): The ID of the message to reply to.

        Returns:
            SentMessage | None: A SentMessage object on success, or None on failure.
        """
        try:
            payload: Dict[str, Any] = {}
            if text:
                payload["text"] = text
            if image_url:
                payload["imageUrl"] = image_url
            if reply_to_id:
                payload["replyTo"] = reply_to_id

            resp = self.session.post(f"{self.base_url}/send", json=payload)
            if resp.status_code == 200:
                return SentMessage(resp.json(), self, initial_text=text)
            else:
                logger.error(f"Send failed ({resp.status_code}): {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Send error: {e}")
            return None

    def edit_message(self, target: Union[SentMessage, str], new_text: str) -> bool:
        """
        Edits an existing message.

        Args:
            target (SentMessage | str): The SentMessage object or the message ID string to edit.
            new_text (str): The new text content.

        Returns:
            bool: True on success, False on failure.
        """
        msg_id = target.id if isinstance(target, SentMessage) else target
        if not msg_id:
            return False
        try:
            resp = self.session.put(
                f"{self.base_url}/edit/{msg_id}", json={"text": new_text}
            )
            return resp.status_code == 200
        except Exception:
            return False

    def delete_message(self, target: Union[SentMessage, str]) -> bool:
        """
        Deletes a message.

        Args:
            target (SentMessage | str): The SentMessage object or the message ID string to delete.

        Returns:
            bool: True on success, False on failure.
        """
        msg_id = target.id if isinstance(target, SentMessage) else target
        if not msg_id:
            return False
        try:
            resp = self.session.delete(f"{self.base_url}/delete/{msg_id}")
            return resp.status_code == 200
        except Exception:
            return False

    # --- Decorators for registering handlers ---

    def command(self, trigger: str) -> Callable[[CommandHandler], CommandHandler]:
        """
        Decorator: Registers a function to handle a specific command.

        Example:
            ```python
            @bot.command("/start")
            def start(msg):
                msg.reply("Hello!")
            ```

        Args:
            trigger (str): The command string (e.g., "/start" or "!help").
        """

        def decorator(func: CommandHandler) -> CommandHandler:
            sig = inspect.signature(func)
            params = sig.parameters
            wants_args = len(params) == 2

            if len(params) > 2:
                logger.warning(
                    f"Command '{trigger}' handler has {len(params)} args. "
                    f"Only the first 2 will be used (Message, List[str])."
                )

            self.command_handlers[trigger] = (func, wants_args)
            return func

        return decorator

    def on_message(self) -> Callable[[MessageHandler], MessageHandler]:
        """
        Decorator: Registers a handler for all non-command messages.

        Example:
            ```python
            @bot.on_message()
            def echo(msg):
                msg.reply(msg.text)
            ```
        """

        def decorator(func: MessageHandler) -> MessageHandler:
            self.message_handlers.append(func)
            return func

        return decorator

    def event(self, event_name: str) -> EventDecorator:
        """
        Decorator: Registers a handler for lifecycle events.

        Example:
            ```python
            @bot.event("startup")
            def on_start():
                print("Bot started!")
            ```

        Args:
            event_name (str): The event type. Options: `'startup'`, `'shutdown'`, `'error'`.
        """

        def decorator(func: GenericEventHandler) -> GenericEventHandler:
            if event_name in self.event_handlers:
                self.event_handlers[event_name] = func
            else:
                logger.warning(f"Unknown event type: {event_name}")
            return func

        return decorator

    def _trigger(self, event_name: str, *args: Any) -> None:
        """Internal method to safely execute an event handler."""
        handler = self.event_handlers.get(event_name)
        if handler:
            try:
                handler(*args)
            except Exception as e:
                logger.error(f"Error in '{event_name}' handler: {e}")

    # --- Main Run Loop ---

    def run(self) -> None:
        """
        Starts the bot's main loop using long polling.

        This method blocks execution until the bot is stopped (Ctrl+C).
        It handles connection errors and automatic reconnections.
        """
        logger.info(f"🤖 Connecting to {self.base_url}...")
        try:
            resp = self.session.get(
                f"{self.base_url}/updates", params={"after_ts": 0.0}, timeout=5
            )
            if resp.status_code == 200:
                initial_messages: List[MessagePayload] = resp.json()
                if initial_messages:
                    self.last_ts = initial_messages[-1]["timestamp"] + 0.000001
                    logger.info(f"✅ Synced. Last TS: {self.last_ts}")
                else:
                    self.last_ts = time.time()
            else:
                self.last_ts = time.time()
        except Exception:
            self.last_ts = time.time()

        self._trigger("startup")
        logger.info("🚀 Listening (Long Polling)...")

        try:
            while True:
                try:
                    resp = self.session.get(
                        f"{self.base_url}/updates",
                        params={"after_ts": self.last_ts},
                        timeout=25,
                    )

                    if resp.status_code == 200:
                        messages: List[MessagePayload] = resp.json()
                        for msg_data in messages:
                            self.last_ts = msg_data["timestamp"]
                            msg = Message(msg_data, self)

                            logger.info(f"[{msg.author.username}]: {msg.text}")

                            cmd_triggered = False
                            handler_data = self.command_handlers.get(msg.command)

                            if handler_data:
                                func, wants_args = handler_data
                                try:
                                    if wants_args:
                                        func(msg, msg.args)
                                    else:
                                        func(msg)
                                except Exception as e:
                                    logger.error(
                                        f"Error in command handler for '{msg.command}': {e}"
                                    )
                                    self._trigger("error", e, msg)

                                cmd_triggered = True

                            if not cmd_triggered:
                                for handler in self.message_handlers:
                                    handler(msg)

                    elif resp.status_code == 403:
                        logger.critical("⛔ Invalid API Key")
                        break
                    else:
                        logger.warning(f"Server returned: {resp.status_code}")
                        time.sleep(2)

                except requests.exceptions.ReadTimeout:
                    continue
                except requests.exceptions.ConnectionError:
                    logger.error("Connection lost.")
                    self._trigger("connection_error")
                    time.sleep(5)
                except Exception as e:
                    logger.error(f"Loop error: {e}")
                    self._trigger("error", e)
                    time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Stopping bot...")
            self._trigger("shutdown")
            sys.exit(0)
