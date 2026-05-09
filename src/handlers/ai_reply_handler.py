import asyncio
import logging
import random
import time
from typing import Optional

from pyrogram import Client
from pyrogram.enums import ChatAction, ChatType
from pyrogram.types import Message

from src import interceptor
from src.classifier import predict_state
from src import nsfw_detector
from src.config import ConfigManager
from src.database import DatabaseManager
from src.llm import LLMClient

logger = logging.getLogger(__name__)

_HISTORY_LIMIT = 10   # max messages sent to LLM as context
_RATE_LIMIT_SEC = 8   # minimum seconds between bot replies per chat
_BATCH_WINDOW_SEC = 10  # seconds of silence before processing buffered messages
_MAX_BUFFER = 5        # max messages to accumulate per chat
_TEXT_FACE_COOLDOWN = 5  # bot replies before a text face (:3 :p :<) can appear again
_TEXT_FACES = (":3", ":p", ":<", ":P")

# Minor detection — patterns that suggest the user is under 18
_GREETINGS = {"hi", "hey", "hello", "hii", "hiii", "hiiii", "heyy", "heyyy", "sup", "yo", "hola"}

_MINOR_PATTERNS = (
    "i'm 13", "i'm 14", "i'm 15", "i'm 16", "i'm 17",
    "im 13", "im 14", "im 15", "im 16", "im 17",
    "i am 13", "i am 14", "i am 15", "i am 16", "i am 17",
    "i'm a minor", "im a minor", "i am a minor",
    "i'm underage", "im underage", "i am underage",
    "i'm in middle school", "im in middle school",
    "i'm in 7th", "i'm in 8th", "i'm in 9th",
    "i'm only 13", "i'm only 14", "i'm only 15", "i'm only 16", "i'm only 17",
    "im only 13", "im only 14", "im only 15", "im only 16", "im only 17",
)

_MINOR_REPLY = "hey sorry i only talk to adults, take care"

# Sent when the user replies after the OF link was already dropped.
# After this the bot goes completely silent on that chat.
_FINAL_REPLIES = [
    "i meann just check it out, you'll see lol",
    "it's free btw hahaha just go look",
    "just trust me on this one :p",
    "you'll see what i mean once you check it lol",
]


class AIReplyHandler:
    """Processes incoming private messages and generates AI replies."""

    def __init__(self, db: DatabaseManager, llm_client: LLMClient, config: ConfigManager, pause_flag=None):
        self.db = db
        self.llm = llm_client
        self.config = config
        self._pause_flag = pause_flag  # callable returning bool, or None
        self._recent_messages: dict[int, list[str]] = {}
        # Last time we sent a reply per chat (monotonic seconds).
        self._last_reply_at: dict[int, float] = {}
        # Per-chat message buffer (accumulates text while the timer is running).
        self._buffer: dict[int, list[str]] = {}
        # The most recent Message object per chat (we reply to this one).
        self._buffer_message: dict[int, Message] = {}
        # Pending asyncio tasks — one per chat, cancelled on each new message.
        self._pending: dict[int, asyncio.Task] = {}
        # Tracks recent bot replies per chat for text face cooldown enforcement.
        self._bot_reply_history: dict[int, list[str]] = {}
        # Set after an interceptor deflect — next message from that chat drops the OF link.
        self._of_link_pending: dict[int, bool] = {}

    async def handle_message(self, client: Client, message: Message) -> bool:
        """
        Entry point for every incoming private message.

        Text messages are buffered for _BATCH_WINDOW_SEC seconds so that
        rapid follow-up messages (double/triple texting) are grouped into a
        single reply.  Media messages and funnel-state transitions bypass the
        buffer and are handled immediately.
        """
        try:
            if message.chat.type != ChatType.PRIVATE:
                return False
            if message.outgoing:
                return False
            if self._pause_flag and self._pause_flag():
                return False

            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            user_name = message.from_user.first_name if message.from_user else "User"
            account_id = self._get_account_id()
            logger.debug(f"Incoming message from {user_name} (user_id={user_id})")

            # ── Test account: reset funnel on greeting so re-testing doesn't need a DB wipe ──
            test_ids = self.config.bot.test_user_ids or []
            if user_id and user_id in test_ids:
                msg_lower = (message.text or "").strip().lower()
                if msg_lower in _GREETINGS:
                    self.db.execute_update(
                        "UPDATE conversations SET funnel_done = 0, of_link_sent = 0 WHERE user_id = ? AND account_id = ?",
                        (user_id, account_id),
                    )
                    self._bot_reply_history.pop(chat_id, None)
                    self._recent_messages.pop(chat_id, None)
                    self._of_link_pending.pop(chat_id, None)
                    logger.debug(f"Test account {user_id}: conversation reset on greeting")

            # ── Funnel state (fast DB read, no processing) ───────────────────
            funnel_state = self.db.get_funnel_state(user_id, account_id) if user_id else "active"
            if funnel_state == "done":
                return False

            # ── Minor detection — send one closing message then go silent ────
            text_preview = (message.text or message.caption or "").lower()
            if any(pattern in text_preview for pattern in _MINOR_PATTERNS):
                if user_id:
                    self.db.set_funnel_done(user_id, account_id)
                await asyncio.sleep(random.uniform(1.5, 3.0))
                await message.reply(_MINOR_REPLY)
                self._last_reply_at[chat_id] = time.monotonic()
                logger.info(f"Minor detected — chat {chat_id} closed")
                return True

            # ── Closing state → one final reply, bypass rate limit + buffer ────
            if funnel_state == "closing":
                self.db.set_funnel_done(user_id, account_id)
                final = random.choice(_FINAL_REPLIES)
                await asyncio.sleep(random.uniform(1.0, 2.5))
                await self._simulate_typing(client, message, final)
                await message.reply(final)
                self._last_reply_at[chat_id] = time.monotonic()
                logger.info(f"Final reply sent to {user_name}, chat {chat_id} closed")
                return True

            # ── Media without text → ISP line, bypass buffer ─────────────────
            has_media = bool(
                message.photo
                or message.video
                or message.audio
                or message.document
                or message.voice
                or message.sticker
            )
            if has_media and not message.text and not message.caption:
                isp_line = random.choice(interceptor.ISP_LINES)
                await asyncio.sleep(random.uniform(6.0, 12.0))
                await message.reply(isp_line)
                self._last_reply_at[chat_id] = time.monotonic()
                return True

            text = message.text or message.caption or ""
            if not text:
                return False

            # ── Buffer and schedule ──────────────────────────────────────────
            buf = self._buffer.setdefault(chat_id, [])
            buf.append(text)
            if len(buf) > _MAX_BUFFER:
                # Keep only the most recent messages if someone really spams
                self._buffer[chat_id] = buf[-_MAX_BUFFER:]

            # Always point at the latest message so we reply to the last one
            self._buffer_message[chat_id] = message

            # Cancel the existing timer and start a fresh one
            old_task = self._pending.get(chat_id)
            if old_task and not old_task.done():
                old_task.cancel()

            self._pending[chat_id] = asyncio.create_task(
                self._wait_and_reply(client, chat_id, user_id, user_name, account_id)
            )
            return True

        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            return False

    async def _wait_and_reply(
        self,
        client: Client,
        chat_id: int,
        user_id: Optional[int],
        user_name: str,
        account_id: int,
    ) -> None:
        """
        Wait _BATCH_WINDOW_SEC seconds then process all buffered messages
        as a single combined reply.  Cancelled and restarted if a new message
        arrives during the wait.
        """
        try:
            await asyncio.sleep(_BATCH_WINDOW_SEC)
        except asyncio.CancelledError:
            return  # new message arrived, a fresh task was already scheduled

        # If the bot replied very recently, wait out the remainder of the rate-limit
        # window before sending.  This replaces the old early-drop so messages are
        # never lost — they are just held briefly.
        remaining = _RATE_LIMIT_SEC - (time.monotonic() - self._last_reply_at.get(chat_id, 0))
        if remaining > 0:
            try:
                await asyncio.sleep(remaining)
            except asyncio.CancelledError:
                return

        # Drain the buffer
        messages = self._buffer.pop(chat_id, [])
        message = self._buffer_message.pop(chat_id, None)
        self._pending.pop(chat_id, None)

        if not messages or not message:
            return

        combined_text = "\n".join(messages)
        if len(messages) > 1:
            logger.info(f"Batched {len(messages)} messages from {user_name}")
        else:
            logger.info(f"Message from {user_name}")
        if self.config.bot.debug_logging:
            logger.debug(f"Content: {combined_text[:120]}")

        await self._reply_pipeline(client, message, combined_text, chat_id, user_id, user_name, account_id)

    async def _reply_pipeline(
        self,
        client: Client,
        message: Message,
        text: str,
        chat_id: int,
        user_id: Optional[int],
        user_name: str,
        account_id: int,
    ) -> None:
        """
        Full reply pipeline: interceptor → classifier → LLM → send.
        Called after the batch window expires with the combined message text.
        """
        try:
            self.db.expire_old_conversations()

            # ── Pending OF link drop (fires on the message after a deflect) ──
            # Route through the LLM so the reply addresses what the user said
            # while naturally including the OF link — not a blank hardcoded line.
            pending_of = self._of_link_pending.pop(chat_id, False)

            # ── Funnel interceptor ───────────────────────────────────────────
            funnel = await interceptor.check(text, self.llm.classify_intent)
            if funnel:
                category, scripted_reply = funnel
                await asyncio.sleep(random.uniform(1.0, 2.5))
                await self._simulate_typing(client, message, scripted_reply)
                await message.reply(scripted_reply)
                logger.info(f"Funnel reply [{category}] to {user_name}")

                self._store_conversation(message, scripted_reply, account_id, text)
                self._last_reply_at[chat_id] = time.monotonic()

                if category == "of_refusal":
                    if user_id:
                        self.db.set_funnel_done(user_id, account_id)
                    logger.info(f"Chat {chat_id} marked done (OF declined)")
                else:
                    # Queue the OF link for the next message so the deflect
                    # lands first and the link follows naturally on their reply.
                    if self.config.bot.of_link:
                        self._of_link_pending[chat_id] = True
                    self._check_closing(chat_id, user_id, account_id, scripted_reply)
                return

            # ── Normal LLM path ──────────────────────────────────────────────
            history_mem = self._recent_messages.setdefault(chat_id, [])
            history_mem.append(text)
            if len(history_mem) > 5:
                history_mem.pop(0)

            user_state = predict_state(history_mem)
            if user_state:
                logger.debug(f"Classifier state: {user_state}")

            history = []
            if user_id and account_id:
                history = self.db.get_recent_messages(user_id, account_id, limit=_HISTORY_LIMIT)
                if history:
                    logger.debug(f"Loaded {len(history)} messages of history")

            read_delay = random.uniform(
                self.config.bot.read_delay_min,
                self.config.bot.read_delay_max,
            )
            await asyncio.sleep(read_delay)

            # Check for subtle NSFW intent that bypassed the keyword interceptor.
            # If the model is confident enough and the OF link hasn't been sent
            # yet, hint the LLM to drop it naturally in this reply.
            of_link_sent = self.db.execute_query(
                "SELECT of_link_sent FROM conversations WHERE user_id = ? AND account_id = ?",
                (user_id, account_id),
            )
            already_sent = bool(of_link_sent and of_link_sent[0]["of_link_sent"])
            hint_of = bool(self.config.bot.of_link) and not already_sent and (
                pending_of or nsfw_detector.is_nsfw(text)
            )
            if hint_of:
                reason = "post-deflect pending" if pending_of else "NSFW detector"
                logger.debug(f"OF hint triggered for {user_name} ({reason})")

            response_text = await self.llm.generate_response(
                text,
                self.db,
                user_state=user_state,
                history=history,
                hint_of=hint_of,
            )

            if not response_text:
                logger.warning(f"No response generated for {user_name}")
                return

            response_text = self._clean_reply(chat_id, response_text)
            await self._simulate_typing(client, message, response_text)
            await message.reply(response_text)
            self._record_bot_reply(chat_id, response_text)
            if pending_of:
                logger.info(f"OF link dropped to {user_name} (post-deflect)")
            else:
                logger.info(f"Replied to {user_name}")
            self._last_reply_at[chat_id] = time.monotonic()

            self._store_conversation(message, response_text, account_id, text)
            self._check_closing(chat_id, user_id, account_id, response_text)

        except Exception as e:
            logger.error(f"Error in reply pipeline: {e}")

    def _clean_reply(self, chat_id: int, text: str) -> str:
        """Post-process LLM reply to enforce style rules the prompt alone can't guarantee."""
        # Remove exclamation marks
        text = text.replace("!", "")

        recent = self._bot_reply_history.get(chat_id, [])

        # Strip text face if one appeared in the last _TEXT_FACE_COOLDOWN replies
        recent_text = " ".join(recent[-_TEXT_FACE_COOLDOWN:]).lower()
        if any(face.lower() in recent_text for face in _TEXT_FACES):
            for face in _TEXT_FACES:
                text = text.replace(face, "").replace(face.lower(), "")
            text = text.strip().rstrip(",").strip()

        # Strip trailing question if the last 2 replies already had one
        recent_window = recent[-3:]
        question_count = sum(1 for r in recent_window if r.rstrip().endswith("?"))
        if question_count >= 2 and text.rstrip().endswith("?"):
            # Remove the last sentence that ends with a question mark
            sentences = text.rstrip().rsplit(",", 1)
            if len(sentences) > 1:
                text = sentences[0].strip()
            else:
                # Try splitting on a space before the question
                parts = text.rstrip("?").rsplit(None, 4)
                if len(parts) > 3:
                    text = " ".join(parts[:-2]).strip().rstrip(",").strip()

        return text.strip()

    def _record_bot_reply(self, chat_id: int, text: str) -> None:
        """Keep a rolling window of recent bot replies for cooldown checks."""
        history = self._bot_reply_history.setdefault(chat_id, [])
        history.append(text)
        if len(history) > _TEXT_FACE_COOLDOWN + 2:
            history.pop(0)

    def _check_closing(
        self, chat_id: int, user_id: Optional[int], account_id: int, reply_text: str
    ) -> None:
        """If the reply included the OF link, persist the closing state to DB."""
        of_link = self.config.bot.of_link
        if of_link and of_link in reply_text and user_id:
            self.db.set_funnel_closing(user_id, account_id)
            logger.debug(f"Chat {chat_id} entered closing state (OF link sent)")

    def _get_account_id(self) -> int:
        """Return the active account's DB id, falling back to 1."""
        try:
            account = self.db.get_current_account()
            if account:
                return account["id"]
        except Exception:
            pass
        return 1

    async def _simulate_typing(
        self, client: Client, message: Message, response_text: str
    ) -> None:
        """Show a typing indicator for a duration proportional to response length."""
        typing_speed = 18  # chars per second
        max_delay = self.config.bot.max_typing_delay
        duration = len(response_text) / typing_speed
        duration = min(duration * random.uniform(0.8, 1.2), max_delay)

        elapsed = 0.0
        while elapsed < duration:
            await client.send_chat_action(message.chat.id, ChatAction.TYPING)
            tick = min(4.0, duration - elapsed)
            await asyncio.sleep(tick)
            elapsed += tick

    def _store_conversation(
        self,
        message: Message,
        reply_text: str,
        account_id: int,
        text: Optional[str] = None,
    ) -> None:
        """Persist the user message and bot reply to the database."""
        user_id = message.from_user.id if message.from_user else None
        user_text = text or message.text or message.caption or ""
        timeout = self.config.bot.conversation_timeout

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                row = cursor.execute(
                    "SELECT id FROM conversations WHERE user_id = ? AND account_id = ?",
                    (user_id, account_id),
                ).fetchone()

                if row:
                    conversation_id = row[0]
                    cursor.execute(
                        """UPDATE conversations
                           SET state = 'ACTIVE',
                               last_activity_at = datetime('now'),
                               timeout_until = datetime('now', ? || ' seconds')
                           WHERE id = ?""",
                        (str(timeout), conversation_id),
                    )
                else:
                    cursor.execute(
                        """INSERT INTO conversations
                               (user_id, account_id, chat_id, chat_type, state,
                                last_activity_at, timeout_until)
                           VALUES (?, ?, ?, 'private', 'ACTIVE',
                                   datetime('now'), datetime('now', ? || ' seconds'))""",
                        (user_id, account_id, message.chat.id, str(timeout)),
                    )
                    conversation_id = cursor.lastrowid

                entries = []
                if len(user_text) > 2:
                    entries.append((conversation_id, user_id, user_text, "text", message.id))
                if len(reply_text) > 2:
                    entries.append((conversation_id, account_id, reply_text, "text", None))

                if entries:
                    cursor.executemany(
                        """INSERT INTO messages
                               (conversation_id, sender_id, text, message_type, telegram_message_id)
                           VALUES (?, ?, ?, ?, ?)""",
                        entries,
                    )

        except Exception as e:
            logger.error(f"Error storing conversation: {e}")
