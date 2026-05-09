"""
Telegram Bot Server - Manages Pyrogram client and message handlers.
"""

import logging
import asyncio
import pathlib
import shutil
import sys
import builtins
from typing import Optional, Callable
from pyrogram import Client, filters
from pyrogram.errors import PhoneCodeInvalid, PhoneCodeExpired

from src.database import DatabaseManager
from src.config import ConfigManager
from src.llm import LLMClient
from src.handlers.ai_reply_handler import AIReplyHandler
from src import classifier, nsfw_detector

logger = logging.getLogger(__name__)

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 5  # seconds; doubles each attempt (5, 10, 20, 40, 80)

_verification_callback: Optional[Callable[[str], Optional[str]]] = None
_original_input = builtins.input


class VerificationInputCancelled(Exception):
    """GUI auth prompt dismissed or empty while stdin is not a TTY (typical frozen .exe)."""


def _log_dll_help(exc: BaseException) -> None:
    if sys.platform != "win32":
        return
    msg = str(exc).lower()
    if "1114" in msg or "c10.dll" in msg or ("dll" in msg and "fail" in msg):
        logger.warning(
            "Native ML DLL load failed — install **Microsoft Visual C++ Redistributable x64** "
            "(2015–2022) from Microsoft, restart the app, and try again."
        )


def set_verification_callback(callback: Callable[[str], Optional[str]]):
    """Route Pyrogram login prompts (SMS/app code, 2FA password, etc.) through the GUI."""

    global _verification_callback
    _verification_callback = callback

    def custom_input(prompt: str = "") -> str:
        if _verification_callback is None:
            return _original_input(prompt)

        p = prompt or ""
        logger.info("Telegram login input requested (GUI)")
        logger.debug("Prompt excerpt: %s", p[:160].replace("\n", " ").strip())

        result = _verification_callback(p)
        if result:
            return result

        if sys.stdin and sys.stdin.isatty():
            return _original_input(prompt)

        raise VerificationInputCancelled(
            "Verification was cancelled or the field was left empty. "
            "Close and reopen the app to try again."
        )

    builtins.input = custom_input


def clear_verification_callback():
    """Restore stdin behaviour and drop the GUI verification hook (e.g. on app close)."""
    global _verification_callback
    _verification_callback = None
    builtins.input = _original_input


class TelegramBotServer:
    """Manages the Pyrogram client lifecycle and AI message handling."""

    def __init__(self, db: DatabaseManager, config: ConfigManager, warning_callback=None, stop_event=None, pause_flag=None):
        self.db = db
        self.config = config
        self.client: Optional[Client] = None
        self.llm_client: Optional[LLMClient] = None
        self.ai_handler: Optional[AIReplyHandler] = None
        self.is_running = False
        self.warning_callback = warning_callback
        self.stop_event = stop_event
        self.pause_flag = pause_flag  # callable returning bool, or None

    async def start(self, verify_only: bool = False) -> bool:
        """Start the bot. If verify_only=True, authenticate and exit without listening."""
        try:
            logger.warning(
                "Running in USER ACCOUNT mode — recipients will not know this is automated. "
                "Keep session files secure."
            )

            if not self._validate_credentials():
                logger.error("Missing Telegram credentials — check config.json")
                return False

            if not verify_only:
                self.llm_client = LLMClient(self.config)
                if self.warning_callback:
                    self.llm_client.set_warning_callback(self.warning_callback)

            self._create_pyrogram_client()

            if not verify_only:
                self.ai_handler = AIReplyHandler(self.db, self.llm_client, self.config, pause_flag=self.pause_flag)
                self._register_handlers()

            logger.info("Starting Telegram client...")
            await self.client.start()
            self.is_running = True

            if verify_only:
                logger.info("Authentication successful")
                await self.stop()
                return True

            logger.info("Bot started — listening for messages")

            asyncio.create_task(self._prewarm_models())

            while True:
                if self.stop_event and self.stop_event.is_set():
                    logger.info("Stop signal received, shutting down")
                    break
                await asyncio.sleep(1)

            await self.stop()
            return True

        except asyncio.CancelledError:
            return False
        except Exception as e:
            logger.error(f"Bot error: {e}", exc_info=True)
            raise  # let run_bot_async decide whether to retry

    def _validate_credentials(self) -> bool:
        t = self.config.telegram
        return bool(t and t.api_id and t.api_hash and t.phone_number)

    def _create_pyrogram_client(self) -> None:
        t = self.config.telegram

        # Prefer api_id/api_hash from the active account in the DB so that
        # credentials entered in the Accounts tab are used directly.
        api_id = t.api_id
        api_hash = t.api_hash
        phone = t.phone_number
        try:
            account = self.db.get_current_account()
            if account:
                if account.get("api_id"):
                    api_id = int(account["api_id"])
                if account.get("api_hash"):
                    api_hash = account["api_hash"]
                if account.get("phone"):
                    phone = account["phone"]
        except Exception as e:
            logger.debug(f"Could not read active account from DB: {e}")

        # Use a per-account session file derived from the phone number.
        # Migrate the legacy telegram_bot.session if it exists and the new one does not.
        phone_digits = "".join(c for c in (phone or "") if c.isdigit())
        session_name = f"session_{phone_digits}" if phone_digits else "telegram_bot"
        sessions_dir = pathlib.Path(self.config.database.session_dir)
        old_session = sessions_dir / "telegram_bot.session"
        new_session = sessions_dir / f"{session_name}.session"
        if old_session.exists() and not new_session.exists():
            shutil.copy2(old_session, new_session)
            logger.debug(f"Migrated legacy session to {new_session.name}")

        self.client = Client(
            name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone,
            workdir=self.config.database.session_dir,
        )

    async def _prewarm_models(self) -> None:
        """Load ML models in the background so the first message isn't delayed."""
        try:
            await asyncio.to_thread(classifier._load)
            await asyncio.to_thread(nsfw_detector._load)
        except Exception as e:
            logger.debug(f"Model pre-warm failed: {e}")

    def _register_handlers(self) -> None:
        @self.client.on_message(filters.private & filters.incoming)
        async def handle_private_message(client, message):
            await self.ai_handler.handle_message(client, message)

        logger.info("Message handlers registered")

    async def stop(self) -> None:
        try:
            if self.client is not None:
                if self.is_running:
                    await self.client.stop()
                else:
                    # client exists but start() never completed — disconnect the raw connection
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                self.is_running = False
                logger.info("Bot stopped")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")


async def run_bot_async(
    db: DatabaseManager,
    config: ConfigManager,
    verify_only: bool = False,
    warning_callback=None,
    stop_event=None,
    pause_flag=None,
) -> bool:
    """
    Run the bot with automatic reconnection on failure.

    On a clean stop (stop_event set) or verify_only run, exits immediately.
    On unexpected disconnects, retries up to _MAX_RETRIES times with
    exponential backoff before giving up.
    """
    if verify_only:
        server = TelegramBotServer(db, config, warning_callback=warning_callback, stop_event=stop_event)
        try:
            return await server.start(verify_only=True)
        except VerificationInputCancelled as e:
            logger.warning("%s", e)
            return False
        except PhoneCodeInvalid:
            logger.warning("Incorrect verification code — please try again")
            return False
        except PhoneCodeExpired:
            logger.warning("Verification code expired — a new code has been sent, please try again")
            return False
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False
        finally:
            await server.stop()

    attempt = 0
    while attempt < _MAX_RETRIES:
        # Check stop before each attempt
        if stop_event and stop_event.is_set():
            logger.info("Stop requested before reconnect attempt")
            return True

        if attempt > 0:
            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(f"Reconnecting in {delay}s (attempt {attempt}/{_MAX_RETRIES})")
            # Wait for the delay but bail early if stop is requested
            for _ in range(delay):
                if stop_event and stop_event.is_set():
                    return True
                await asyncio.sleep(1)

        server = TelegramBotServer(db, config, warning_callback=warning_callback, stop_event=stop_event, pause_flag=pause_flag)
        try:
            await server.start(verify_only=False)

            # If we get here the bot ran and stopped cleanly (stop_event was set)
            return True

        except KeyboardInterrupt:
            logger.info("Bot interrupted by user")
            return False

        except PhoneCodeInvalid:
            logger.warning("Incorrect verification code — please enter the code again when prompted")
            # Don't count as a failed connection attempt — retry immediately

        except PhoneCodeExpired:
            logger.warning("Verification code expired — a new code has been sent, please try again when prompted")
            # Don't count as a failed connection attempt — retry immediately

        except Exception as e:
            logger.error(f"Bot disconnected: {e}")
            attempt += 1

        finally:
            await server.stop()

    logger.error(f"Bot failed to stay connected after {_MAX_RETRIES} attempts — giving up")
    if warning_callback:
        warning_callback(
            f"Bot lost connection and could not reconnect after {_MAX_RETRIES} attempts.\n"
            "Check your internet connection and restart the bot."
        )
    return False
