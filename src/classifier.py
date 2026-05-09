"""
Conversation state classifier.

Predicts engagement state (warm/cold/skeptical/hostile) from recent user messages.
Falls back gracefully if the model hasn't been trained yet.
"""

import logging
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_PATH = pathlib.Path(__file__).parent.parent / "classifier" / "model.pkl"

_model = None
_embedder = None
_loaded = False

# Explicit keyword rules for classes that are rare in training data.
# These take priority over the ML model's prediction.
_HOSTILE_KEYWORDS = {"idiot", "stupid", "moron", "loser", "bitch", "fuck off", "shut up"}
_SKEPTICAL_KEYWORDS = {
    "are you a bot", "is this real", "is this a bot", "are you real",
    "fake", "scam", "scammer", "prove it", "verify", "npc", "ai generated",
    "chatgpt", "you're a bot", "ur a bot",
}


def _load() -> None:
    global _model, _embedder, _loaded
    if _loaded:
        return
    _loaded = True

    if not MODEL_PATH.exists():
        logger.debug(
            "No classifier model found. "
            "Run 'python cli/label_conversations.py' then 'python cli/train_classifier.py' to build one."
        )
        return

    try:
        import joblib
        from sentence_transformers import SentenceTransformer

        data = joblib.load(MODEL_PATH)
        _model = data["model"]
        _embedder = SentenceTransformer(data["embedder"])
        logger.info(f"Classifier loaded. Classes: {data.get('classes')}, trained on {data.get('trained_on')} examples.")
    except Exception as e:
        logger.warning(f"Could not load classifier model: {e}")
        try:
            from src.bot_server import _log_dll_help

            _log_dll_help(e)
        except Exception:
            pass
        # Ensure model stays None so predict_state returns None cleanly
        _model = None
        _embedder = None


def _keyword_check(text: str) -> Optional[str]:
    """Override for hostile/skeptical — reliable even when training data is sparse."""
    lower = text.lower()
    if any(kw in lower for kw in _HOSTILE_KEYWORDS):
        return "hostile"
    if any(kw in lower for kw in _SKEPTICAL_KEYWORDS):
        return "skeptical"
    return None


def predict_state(messages: list[str]) -> Optional[str]:
    """Return predicted state from recent messages, or None if unavailable."""
    try:
        if not messages:
            return None

        combined = " | ".join(m.strip() for m in messages[-3:] if m.strip())
        if not combined:
            return None

        # Keyword rules take priority — they're more reliable than the model
        # for rare classes that are underrepresented in training data
        keyword_result = _keyword_check(combined)
        if keyword_result:
            logger.debug(f"Conversation state (keyword): '{keyword_result}'")
            return keyword_result

        _load()

        if _model is None or _embedder is None:
            return None

        embedding = _embedder.encode([combined])
        label = _model.predict(embedding)[0]
        confidence = float(_model.predict_proba(embedding).max())

        if confidence < 0.55:
            logger.debug(f"Classifier confidence too low ({confidence:.2f}), skipping")
            return None

        logger.debug(f"Conversation state (model): '{label}' (confidence {confidence:.2f})")
        return label

    except Exception as e:
        logger.warning(f"Classifier prediction failed: {e}")
        return None
