"""
NSFW intent detector using a fine-tuned DistilBERT model.

Runs locally with no API cost. Detects subtle sexual or explicit intent in
messages that would bypass the keyword interceptor — innuendo, indirect
phrasing, coded language.

Model: eliasalbouzidi/distilbert-nsfw-text-classifier
Reported accuracy: ~97.8% F1 on NSFW/SFW binary classification.
"""

import logging

logger = logging.getLogger(__name__)

_pipeline = None
_load_attempted = False

# Minimum confidence before we treat a message as NSFW.
# 0.70 catches coded language (e.g. sexual euphemisms) while avoiding
# innocent messages like "you seem fun" which score below 0.05.
THRESHOLD = 0.70


def _load() -> None:
    global _pipeline, _load_attempted
    if _load_attempted:
        return
    _load_attempted = True
    try:
        from transformers import pipeline as hf_pipeline
        _pipeline = hf_pipeline(
            "text-classification",
            model="eliasalbouzidi/distilbert-nsfw-text-classifier",
            truncation=True,
            max_length=512,
        )
        logger.info("NSFW detector loaded")
    except Exception as e:
        logger.warning(f"Could not load NSFW detector: {e}")
        try:
            from src.bot_server import _log_dll_help

            _log_dll_help(e)
        except Exception:
            pass
        _pipeline = None


def score(text: str) -> float:
    """
    Return a 0-1 confidence that the message contains sexual/NSFW intent.
    Returns 0.0 if the model is unavailable or inference fails.
    """
    if not _load_attempted:
        _load()
    if _pipeline is None:
        return 0.0
    try:
        result = _pipeline(text[:512])[0]
        label = result["label"].upper()
        s = float(result["score"])
        # Handle both named labels ("NSFW"/"SFW") and generic ones ("LABEL_1"/"LABEL_0").
        # For generic labels, LABEL_1 is conventionally the positive (NSFW) class.
        is_nsfw_label = label in ("NSFW", "LABEL_1")
        return s if is_nsfw_label else 1.0 - s
    except Exception as e:
        logger.debug(f"NSFW detector inference error: {e}")
        return 0.0


def is_nsfw(text: str, threshold: float = THRESHOLD) -> bool:
    """Return True if the message crosses the NSFW confidence threshold."""
    return score(text) >= threshold
