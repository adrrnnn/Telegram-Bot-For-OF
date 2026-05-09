"""
Conversion funnel interceptor.

Scans incoming messages for high-intent patterns (photo requests, meetups, etc.)
and runs a quick yes/no LLM check to confirm the intent before firing a scripted
redirect response.  Returns None when the message should pass to the normal LLM.
"""

import logging
import random
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_TRIGGERS: dict[str, list[str]] = {
    "photo_request": [
        "send pic", "send me pic", "send a pic", "show me a pic",
        "send photo", "send me photo", "show me photo", "show photo",
        "send nude", "send me nude", "nudes", "naked pic",
        "pic of you", "pics of you", "photo of you",
        "show me you", "show yourself", "show ur body",
    ],
    "sext_request": [
        "sext", "sexting", "dirty talk", "talk dirty",
        "sexual", "roleplay", "role play", "erotic",
        "describe yourself", "what are you wearing",
    ],
    "meetup_request": [
        "meet up", "meetup", "meet me", "come over",
        "hook up", "hookup", "hang out irl", "hangout irl",
        "meet in person", "in person", " irl", "in real life",
        "visit you", "pick you up", "take you out",
    ],
    "other_platform": [
        "snapchat", "snap", "add my snap", "what's your snap",
        "whats your snap", "instagram", "what's your insta",
        "whats your insta", "kik", "whatsapp",
        "your number", "phone number", "what's your number",
        "text me", "call me",
    ],
    "of_refusal": [
        "not doing onlyfans", "don't do onlyfans", "dont do onlyfans",
        "not subscribing", "wont subscribe", "won't subscribe",
        "not paying", "no onlyfans", "skip the onlyfans",
        "not interested in onlyfans", "don't want onlyfans",
        "forget the onlyfans", "pass on onlyfans",
        "not into onlyfans", "i don't want that",
    ],
}

_QUESTIONS: dict[str, str] = {
    "photo_request": (
        "Does this message ask a girl to personally send photos, selfies, nudes, "
        "or pictures of herself? Answer only: yes or no."
    ),
    "sext_request": (
        "Does this message ask for sexting, dirty talk, sexual roleplay, "
        "or explicit sexual conversation? Answer only: yes or no."
    ),
    "meetup_request": (
        "Does this message ask for a physical meetup, in-person date, hookup, "
        "or to meet in real life? Answer only: yes or no."
    ),
    "other_platform": (
        "Does this message ask for a Snapchat username, Instagram, phone number, "
        "WhatsApp, or any other social media contact? Answer only: yes or no."
    ),
    "of_refusal": (
        "Is this person refusing, declining, or saying they won't subscribe "
        "to OnlyFans? Answer only: yes or no."
    ),
}

_SCRIPTS: dict[str, list[str]] = {
    "photo_request": [
        "i keep that kind of stuff on another site lol :3",
        "not here hahahah i only post that stuff on my of",
        "i meann i do have that kind of content, just not here tho",
    ],
    "sext_request": [
        "hahahah i don't really do that here, more of an of thing :p",
        "i meann that's more of a different platform conversation lol",
        "not really my thing on here, only on of hehehe",
    ],
    "meetup_request": [
        "i wouldn't really discuss that here lol",
        "hahahah i don't do that kind of thing through here tbh",
        "i meann that's not really something i do :p",
    ],
    "other_platform": [
        "i don't really give those out tbh",
        "i'm not active on other apps like that lol",
        "i kinda just keep everything here or on my of",
    ],
    "of_refusal": [
        "that's fine lol, that's just the only place i post that stuff tho",
        "no worries, just where i keep everything",
        "all good hahah, just the only place i really use",
    ],
}

# ISP blurred-media lines (used when the user sends a photo/video)
ISP_LINES: list[str] = [
    "it's not loading on my end lol, send it on my of tho",
    "hahahah it's all blurred on here, try sending it on my of",
    "weird it won't load, send it on my of instead",
]

# Loose signals that alone don't confirm intent but warrant an LLM scan.
# Kept as multi-word or specific enough to avoid substring false positives
# (e.g. "hot" was removed because it fires inside "hotdog", "hotel", etc.)
_LOOSE_SIGNALS = {
    "fuck", "sex", "sexy", "ur hot", "so hot", "looking hot", "body", "naked", "nude",
    "meet", "come here", "visit", "hookup", "hook up",
    "send me", "show me", "pic", "photo",
    "snap", "insta", "number", "contact",
    "onlyfans", "only fans", "not paying", "not subscribing",
}

# Single catch-all question for the LLM fallback scan
_CATCHALL_QUESTION = (
    "Does this message ask for a physical meetup, sex, nudes, explicit content, "
    "another social media contact, or refuse to subscribe to OnlyFans? Answer only: yes or no."
)


def _flag_category(text: str) -> Optional[str]:
    """Return the first matching trigger category, or None."""
    lower = text.lower()
    for category, patterns in _TRIGGERS.items():
        for pattern in patterns:
            if pattern in lower:
                logger.debug(f"Keyword match '{pattern}' -> category '{category}'")
                return category
    return None


def _has_loose_signal(text: str) -> bool:
    """Return True if the message contains any loose signal worth scanning."""
    lower = text.lower()
    return any(signal in lower for signal in _LOOSE_SIGNALS)


async def check(
    message_text: str,
    verify_fn: Callable[[str, str], Awaitable[bool]],
) -> Optional[tuple[str, str]]:
    """
    Scan a message for conversion-funnel triggers.

    1. Keyword scan — fast path, catches explicit patterns.
    2. If no keyword match but loose signals present, run a catch-all LLM scan.
    3. LLM intent verification before firing any scripted response.
    Returns (category, scripted_reply) if confirmed, else None.
    """
    category = _flag_category(message_text)

    if not category:
        # Fallback: loose signal detected → ask LLM if this is worth intercepting
        if not _has_loose_signal(message_text):
            return None

        flagged = await verify_fn(message_text, _CATCHALL_QUESTION)
        if not flagged:
            return None

        # LLM confirmed something — now identify the specific category for the right script
        for cat, question in _QUESTIONS.items():
            confirmed = await verify_fn(message_text, question)
            if confirmed:
                category = cat
                break
        else:
            category = "meetup_request"

        logger.debug(f"Fallback LLM scan caught category '{category}': {message_text[:60]}")
    else:
        confirmed = await verify_fn(message_text, _QUESTIONS[category])
        if not confirmed:
            logger.debug(f"Intent check rejected '{category}' for: {message_text[:60]}")
            return None

    reply = random.choice(_SCRIPTS[category])
    logger.debug(f"Funnel intercept: {category}")
    return (category, reply)
