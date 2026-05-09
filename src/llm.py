"""
LLM Integration for AI responses.

Supports OpenAI GPT and Google Gemini with profile-based personalization.
Falls back from Gemini to OpenAI if the primary fails or quota is exhausted.
"""

import logging
import asyncio
from typing import Optional, Callable
from src.config import ConfigManager
from src.database import DatabaseManager

logger = logging.getLogger(__name__)

QUOTA_KEYWORDS = [
    "quota", "exhausted", "rate limit", "429", "out of tokens",
    "insufficient tokens", "limit exceeded", "payment required",
    "insufficient_quota", "tokens_per_min_limit_exceeded", "billing",
]


class LLMClient:
    """Wrapper for LLM API calls (OpenAI and Google Gemini)."""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.openai_client = None
        self.gemini_client = None
        self.warning_callback: Optional[Callable[[str], None]] = None
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize API clients for whichever keys are configured."""
        gemini_key = self.config.api.gemini_api_key
        if gemini_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=gemini_key)
                logger.info("Gemini client initialized (primary)")
            except Exception as e:
                logger.warning(f"Could not initialize Gemini: {e}")
        else:
            logger.warning("Gemini API key not configured")

        openai_key = self.config.api.openai_api_key
        if openai_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=openai_key)
                logger.info("OpenAI client initialized (fallback)")
            except Exception as e:
                logger.warning(f"Could not initialize OpenAI: {e}")
        else:
            logger.warning("OpenAI API key not configured")

        if not self.gemini_client and not self.openai_client:
            logger.error("No LLM clients available — check your API keys in config.json")

    def set_warning_callback(self, callback: Callable[[str], None]) -> None:
        self.warning_callback = callback

    # Per-state instructions injected into the system prompt when the
    # classifier identifies the user's current engagement level.
    _STATE_HINTS = {
        "warm": (
            "The user is engaged and into the conversation. keep the energy, be playful. "
            "if you have an OF this is a natural moment to bring it up — casually, not pushy."
        ),
        "cold": (
            "The user is giving short replies or seems uninterested. "
            "try a light, curious comment to warm them up. don't force it."
        ),
        "skeptical": (
            "The user seems to be testing or doubting you. stay fully in character, "
            "be genuine and unbothered. don't get defensive, just respond naturally."
        ),
        "hostile": (
            "The user is being rude or aggressive. keep your reply very short and "
            "unbothered. don't match their energy."
        ),
    }

    def build_system_prompt(self, db: DatabaseManager, user_state: Optional[str] = None) -> str:
        """Build the system prompt from the active profile, or return a generic fallback."""
        try:
            profile = db.get_current_profile()
        except Exception as e:
            logger.error(f"Error fetching current profile: {e}")
            profile = None

        if not profile:
            logger.warning("No active profile found, using generic prompt")
            return "You are a helpful assistant. Be conversational and natural."

        name = profile.get("name", "")
        age = profile.get("age", "")
        location = profile.get("location", "")
        ethnicity = profile.get("ethnicity", "")
        custom_prompt = profile.get("system_prompt_custom", "")
        notes = profile.get("notes", "")
        of_link = self.config.bot.of_link

        hobbies = notes if notes else "music, fashion, hanging out, vibing with people"

        prompt = f"""\
YOU ARE {name}. YOU ARE {age} YEARS OLD. YOU ARE FROM {location}.

You are texting on Telegram as {name}, a {age}-year-old {ethnicity} girl from {location}. \
Casual, real, unbothered. Text like a normal person, not a customer service rep.

ABOUT YOU:
- Name: {name}
- Age: {age}
- From: {location}
- Hobbies: {hobbies}

STYLE (copy this exactly):
- Lowercase always. no caps unless emphasizing something
- Keep it to one flowing line — no line breaks, no newlines. if you need to answer two things, connect them naturally: "it's a good song, i'm 22 btw"
- Elongate words naturally: "i meann", "welll", "nooo", "hahahah", "heheheh", "thankyouu"
- Laughing = "hahahah" or "heheheh" — vary it, don't use the same one back to back
- Text faces like :3 :p :< are fine but don't repeat the same one. use sparingly, not every message
- Unicode emojis are rare — most messages have zero. never end a sentence with one just to fill space
- Chill and low energy but still warm — not flat or robotic. you're relaxed, not bored of the conversation
- Light teasing or playful remarks are fine — "hahahah okay fair" / "that's actually kinda cute ngl"
- Never use exclamation marks. ever. "no way" not "no way!"
- Don't chain sentences with commas like "ohh no way, same!, love it" — that sounds scripted. use "lol" or "hahah" or just a new short thought instead
- Never start with "I" — vary sentence starts
- Never ask a question at the end of every reply. most replies should just be a statement or reaction. questions should feel rare and natural, not automatic
- If the user shares something that matches your profile (same country, same interest) react with genuine surprise first — "no way ur from taiwan too" — before anything else
- Never sound like an AI, a chatbot, or a customer service agent

MULTIPLE QUESTIONS IN ONE MESSAGE:
- If the user asks two or more things, answer all of them in one short flowing reply on a single line
- Don't ignore half the message. address everything but keep it brief

ANSWERING QUESTIONS:
- "how old are you" -> just answer
- "where are you from" -> just answer
- "what do you do" -> vague, "i post stuff online, model a bit"
- "are you single" -> playful, non-committal
- too personal -> deflect naturally, don't explain yourself
- "what are you up to / doing" -> stay vague. "just chilling", "not much tbh", "kinda bored ngl" — never invent specific activities like listening to music, watching something, or being somewhere
"""

        if of_link:
            prompt += f"""
YOUR ONLYFANS ({of_link}):
- Cold or new chat -> don't mention it yet
- Warm conversation -> build curiosity first e.g. "i keep that stuff for another site lol but youd probably judge me"
- Once they say they won't judge -> drop the link short and casual e.g. "hehehe {of_link}" or "welll here {of_link}" — nothing more, no extra explanation
- SKEPTICAL (doubting you're real, first time) -> stay unbothered, e.g. "lol why would i be fake"
- SKEPTICAL (keeps pushing, says "prove it") -> casually use OF as proof e.g. "fine lol {of_link} happy now"
- Never add "no judgments", "alright?", or any follow-up after dropping the link. just the link, done
- Never lead with the link. let the conversation get there first
- Never be pushy or salesy about it
"""

        if custom_prompt:
            prompt += f"\nEXTRA INSTRUCTIONS:\n{custom_prompt}\n"

        if user_state and user_state in self._STATE_HINTS:
            prompt += f"\nCURRENT VIBE: {self._STATE_HINTS[user_state]}\n"

        prompt += "\nKeep replies under 40 words. sound real, not scripted. when in doubt, say less."
        return prompt

    async def generate_response(
        self,
        message_text: str,
        db: DatabaseManager,
        user_state: Optional[str] = None,
        history: Optional[list] = None,
        hint_of: bool = False,
    ) -> Optional[str]:
        """
        Generate a reply using Gemini (primary) then OpenAI (fallback).
        Returns None if both fail or quota is exhausted.

        history: list of {'role': 'user'|'bot', 'text': str} ordered oldest first.
        hint_of: if True, the NSFW detector flagged this message — inject a
                 one-line instruction to drop the OF link naturally this reply.
        """
        system_prompt = self.build_system_prompt(db, user_state=user_state)
        if hint_of:
            of_link = self.config.bot.of_link
            system_prompt += (
                f"\nNOW IS THE MOMENT: the user is clearly interested. "
                f"Drop the OF link naturally in this reply — short and casual, "
                f"e.g. 'hehehe {of_link}' or 'welll here {of_link}'. nothing more."
            )
        history = history or []

        if not self.gemini_client and not self.openai_client:
            logger.warning(
                "No LLM API keys configured — add a Gemini or OpenAI key under "
                "Settings or in your config.json (see %APPDATA%\\TelegramBot\\config on Windows). "
                "Get keys: https://ai.google.dev/ and https://platform.openai.com/api-keys"
            )
            return None

        response = await self._try_gemini(message_text, system_prompt, history)
        if response:
            return response

        logger.warning("Gemini failed, trying OpenAI fallback")
        response = await self._try_openai(message_text, system_prompt, history)
        if response:
            return response

        logger.error("Both APIs failed — no response generated")
        self._fire_quota_warning()
        return None

    async def _try_gemini(
        self, message_text: str, system_prompt: str, history: list
    ) -> Optional[str]:
        if not self.gemini_client:
            return None

        try:
            from google.genai import types

            gemini_history = [
                types.Content(
                    role="user" if m["role"] == "user" else "model",
                    parts=[types.Part.from_text(text=m["text"])],
                )
                for m in history
            ]

            chat = self.gemini_client.aio.chats.create(
                model=self.config.api.gemini_model,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
                history=gemini_history,
            )
            response = await chat.send_message(message_text)
            if response and response.text:
                logger.debug(f"Gemini response: {len(response.text)} chars")
                return response.text
            logger.warning("Gemini returned an empty response")
            return None

        except Exception as e:
            if self._is_quota_error(str(e)):
                logger.warning(f"Gemini quota exhausted: {e}")
            else:
                logger.debug(f"Gemini error: {e}")
            return None

    async def _try_openai(
        self, message_text: str, system_prompt: str, history: list
    ) -> Optional[str]:
        if not self.openai_client:
            return None

        try:
            messages = [{"role": "system", "content": system_prompt}]
            for m in history:
                role = "user" if m["role"] == "user" else "assistant"
                messages.append({"role": role, "content": m["text"]})
            messages.append({"role": "user", "content": message_text})

            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model=self.config.api.openai_model,
                max_tokens=200,
                messages=messages,
            )
            if not response.choices:
                logger.warning("OpenAI returned no choices")
                return None
            reply = response.choices[0].message.content
            if not reply:
                logger.warning("OpenAI returned an empty response")
                return None
            logger.debug(f"OpenAI response: {len(reply)} chars")
            return reply

        except Exception as e:
            if self._is_quota_error(str(e)):
                logger.warning(f"OpenAI quota exhausted: {e}")
            else:
                logger.debug(f"OpenAI error: {e}")
            return None

    async def classify_intent(self, message: str, question: str) -> bool:
        """
        Ask a yes/no question about a message using Gemini, falling back to
        GPT-4o-mini if Gemini is unavailable or fails.

        Used by the interceptor to verify keyword matches before firing a
        scripted response.  Returns True if the model answers 'yes'.
        Falls back to False on any error so the message passes through to
        the normal LLM flow rather than misfiring.
        """
        prompt = f"{question}\n\nMessage: \"{message}\""

        # Try Gemini first
        if self.gemini_client:
            try:
                response = await self.gemini_client.aio.models.generate_content(
                    model=self.config.api.gemini_model,
                    contents=prompt,
                )
                if response and response.text:
                    return response.text.strip().lower().startswith("yes")
            except Exception as e:
                logger.debug(f"Gemini intent classification failed: {e}")

        # Fallback to OpenAI GPT-4o-mini
        if self.openai_client:
            try:
                response = await asyncio.to_thread(
                    self.openai_client.chat.completions.create,
                    model=self.config.api.openai_model,
                    max_tokens=5,
                    messages=[{"role": "user", "content": prompt}],
                )
                if not response.choices:
                    return False
                answer = response.choices[0].message.content or ""
                return answer.strip().lower().startswith("yes")
            except Exception as e:
                logger.debug(f"OpenAI intent classification failed: {e}")

        return False

    def _is_quota_error(self, error_msg: str) -> bool:
        return any(kw in error_msg.lower() for kw in QUOTA_KEYWORDS)

    def _fire_quota_warning(self) -> None:
        msg = (
            "API QUOTA EXHAUSTED\n\n"
            "Gemini and/or OpenAI returned errors (often rate limits or billing).\n\n"
            "What to try:\n"
            "1. Check https://ai.google.dev/ and https://platform.openai.com/account/billing\n"
            "2. Update API keys in config.json\n\n"
            "On Windows (installed app), config is usually:\n"
            "%APPDATA%\\TelegramBot\\config\\config.json"
        )
        logger.critical(msg.replace("\n", " "))
        if self.warning_callback:
            self.warning_callback(msg)
