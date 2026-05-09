"""
Parse training data and auto-label each user turn using Gemini or GPT-4o-mini.

Reads conversation files from 'Training data/Conversions' and
'Training data/Reddit Training Data', sends each user message to an LLM
with surrounding context, and writes the result to:
    Training data/labeled_data.csv

Labels: warm | cold | skeptical | hostile

Usage:
    python cli/label_conversations.py
"""

import csv
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).parent.parent
CONV_DIR = ROOT / "Training data" / "Conversions"
REDDIT_DIR = ROOT / "Training data" / "Reddit Training Data"
OUTPUT = ROOT / "Training data" / "labeled_data.csv"

# Speakers who are the bot — their turns become context, not labeled rows
BOT_SPEAKERS = {"Yuki", "Legitimate_Sky_9131"}

LABEL_PROMPT = """\
You are labeling chatbot training data. Classify the USER'S message into one of:
- warm: engaged, curious, flirty, playful, positive, asking follow-up questions
- cold: disengaged, one-word replies, dry, uninterested, ignoring
- skeptical: doubting, testing, asking if it's real/a bot/a scam, demanding proof
- hostile: rude, aggressive, insulting, threatening

Conversation context (most recent last):
{context}

User message to classify:
{message}

Reply with ONLY the single label word. Nothing else."""


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

# Matches any timestamp ending in H:MM AM/PM, handles:
#   "12:51 AM"  "12/8/25, 2:23 PM"  "Yesterday at 12:00 AM"
_TIME_SUFFIX = re.compile(r'.+\d+:\d{2} [AP]M\s*$')


def _has_timestamp(s: str) -> bool:
    return bool(_TIME_SUFFIX.match(s))


def _is_turn_start(lines: list[str], i: int) -> bool:
    """Return True if line i begins a new speaker turn."""
    stripped = lines[i].strip()
    n = len(lines)
    # "Name — <timestamp>" on one line
    if re.match(r'^.+? — ', stripped) and _has_timestamp(stripped):
        return True
    # Name alone, blank, then " — <timestamp>"
    if (stripped and i + 2 < n
            and lines[i + 1].strip() == ''
            and lines[i + 2].strip().startswith('— ')
            and _has_timestamp(lines[i + 2].strip())):
        return True
    return False


def parse_conversions(filepath: pathlib.Path) -> list[dict]:
    """
    Parse Discord/Telegram export files. Handles multiple timestamp formats:
        "Name — HH:MM AM"
        "Name — M/D/YY, H:MM PM"
        "Name — Yesterday at H:MM AM"
        "Name\\n\\n — HH:MM AM"  (name on separate line)
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    n = len(lines)
    turns = []
    i = 0

    while i < n:
        stripped = lines[i].strip()

        # "Yuki — 12/8/25, 2:23 PM" or "Yuki — 12:51 AM" — name and time on same line
        m = re.match(r'^(.+?) — ', stripped)
        if m and _has_timestamp(stripped):
            speaker = m.group(1).strip()
            i += 1
            msg_lines = []
            while i < n and not _is_turn_start(lines, i):
                if lines[i].strip():
                    msg_lines.append(lines[i].strip())
                i += 1
            if msg_lines:
                turns.append({"speaker": speaker, "text": " ".join(msg_lines)})
            continue

        # "marco\n\n — 12:50 AM" — name then blank then time on next line
        if (stripped
                and i + 2 < n
                and lines[i + 1].strip() == ''
                and lines[i + 2].strip().startswith('— ')
                and _has_timestamp(lines[i + 2].strip())):
            speaker = stripped
            i += 3
            msg_lines = []
            while i < n and not _is_turn_start(lines, i):
                if lines[i].strip():
                    msg_lines.append(lines[i].strip())
                i += 1
            if msg_lines:
                turns.append({"speaker": speaker, "text": " ".join(msg_lines)})
            continue

        i += 1

    return turns


def parse_reddit(filepath: pathlib.Path) -> list[dict]:
    """
    Parse Reddit DM exports with format:
        Username\nHH:MM AM\nmessage\n[User Avatar]\n...
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = [l.strip() for l in text.splitlines()]
    n = len(lines)

    time_re = re.compile(r'^\d{1,2}:\d{2} [AP]M$')
    date_re = re.compile(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}$')
    skip = {"User Avatar"}

    turns = []
    i = 0

    while i < n:
        line = lines[i]

        if not line or line in skip or date_re.match(line):
            i += 1
            continue

        # Username is followed immediately by a time line
        if i + 1 < n and time_re.match(lines[i + 1]):
            speaker = line
            i += 2
            msg_lines = []
            while i < n:
                next_line = lines[i]
                if not next_line or next_line in skip or date_re.match(next_line):
                    break
                if i + 1 < n and time_re.match(lines[i + 1]):
                    break
                msg_lines.append(next_line)
                i += 1
            if msg_lines:
                turns.append({"speaker": speaker, "text": " ".join(msg_lines)})
            continue

        i += 1

    return turns


# ---------------------------------------------------------------------------
# LLM clients
# ---------------------------------------------------------------------------

def init_clients():
    """Load Gemini and OpenAI clients from config. Returns (gemini_model, openai_client)."""
    sys.path.insert(0, str(ROOT))
    from src.config import ConfigManager
    cfg = ConfigManager()

    gemini_model = None
    openai_client = None

    if cfg.api.gemini_api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=cfg.api.gemini_api_key)
            gemini_model = genai.GenerativeModel("gemini-2.0-flash")
            print("Gemini ready (primary)")
        except Exception as e:
            print(f"Gemini init failed: {e}")
    else:
        print("No Gemini key found — skipping")

    if cfg.api.openai_api_key:
        try:
            from openai import OpenAI
            openai_client = OpenAI(api_key=cfg.api.openai_api_key)
            print("GPT-4o-mini ready (fallback)")
        except Exception as e:
            print(f"OpenAI init failed: {e}")
    else:
        print("No OpenAI key found — skipping")

    if not gemini_model and not openai_client:
        print("No LLM available. Add an API key to config.json.")
        sys.exit(1)

    return gemini_model, openai_client


_HOSTILE_WORDS = {"idiot", "stupid", "fuck", "scam", "bitch", "shut up", "moron", "loser", "ugly"}
_SKEPTICAL_WORDS = {"bot", "real person", "fake", "scammer", "is this real", "prove", "verify", "ai ", " ai"}


def _heuristic_label(message: str) -> str:
    """Rule-based fallback when both LLMs are unavailable."""
    lower = message.lower()
    if any(w in lower for w in _HOSTILE_WORDS):
        return "hostile"
    if any(w in lower for w in _SKEPTICAL_WORDS):
        return "skeptical"
    if len(message.strip()) <= 8 or len(message.strip().split()) <= 1:
        return "cold"
    return "warm"


def _parse_label(text: str, message: str) -> str:
    label = text.strip().lower().split()[0] if text.strip() else ""
    return label if label in {"warm", "cold", "skeptical", "hostile"} else _heuristic_label(message)


def _is_quota_error(err: str) -> bool:
    return any(w in err for w in ("quota", "429", "exhausted", "rate_limit", "rate limit", "billing"))


def label_turn(gemini_model, openai_client, message: str, context: list[str]) -> str:
    ctx = "\n".join(context[-4:]) if context else "(start of conversation)"
    prompt = LABEL_PROMPT.format(context=ctx, message=message)

    # Try Gemini first
    if gemini_model:
        try:
            response = gemini_model.generate_content(prompt)
            if response and response.text:
                return _parse_label(response.text, message)
        except Exception as e:
            err = str(e).lower()
            if _is_quota_error(err):
                print("  Gemini quota hit — switching to GPT-4o-mini for remaining rows")
            else:
                print(f"  Gemini error: {e}")

    # Fallback to GPT-4o-mini
    if openai_client:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=5,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content or ""
            return _parse_label(text, message)
        except Exception as e:
            print(f"  OpenAI error: {e}")

    return _heuristic_label(message)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def collect_turns() -> list[dict]:
    rows = []

    for filepath in sorted(CONV_DIR.glob("*.txt")):
        turns = parse_conversions(filepath)
        source = filepath.name
        context = []
        for turn in turns:
            speaker = turn["speaker"]
            text = turn["text"]
            if speaker in BOT_SPEAKERS:
                context.append(f"Bot: {text}")
            else:
                rows.append({
                    "source": source,
                    "speaker": speaker,
                    "text": text,
                    "context": json.dumps(context[-4:]),
                })
                context.append(f"User: {text}")

    for filepath in sorted(REDDIT_DIR.glob("*.txt")):
        turns = parse_reddit(filepath)
        source = filepath.name
        context = []
        for turn in turns:
            speaker = turn["speaker"]
            text = turn["text"]
            if speaker in BOT_SPEAKERS:
                context.append(f"Bot: {text}")
            else:
                rows.append({
                    "source": source,
                    "speaker": speaker,
                    "text": text,
                    "context": json.dumps(context[-4:]),
                })
                context.append(f"User: {text}")

    return rows


def _safe_print(s: str) -> None:
    """Print a string, replacing any characters the terminal can't display."""
    print(s.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
        sys.stdout.encoding or "utf-8", errors="replace"
    ))


def main():
    print("Collecting turns from training data...")
    rows = collect_turns()
    print(f"Found {len(rows)} user turns to label.")

    if not rows:
        print("No turns found. Check that Training data/ folders contain .txt files.")
        sys.exit(1)

    # Resume from existing file if present (skip already-labeled rows)
    existing = set()
    labeled = []
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        with open(OUTPUT, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                labeled.append(row)
                existing.add(row["text"])
        print(f"Resuming — {len(labeled)} rows already labeled.")

    remaining = [r for r in rows if r["text"] not in existing]
    if not remaining:
        print("All rows already labeled. Nothing to do.")
    else:
        gemini_model, openai_client = init_clients()
        print(f"\nLabeling {len(remaining)} rows...\n")

        fieldnames = ["text", "context", "label", "source"]
        mode = "a" if labeled else "w"
        with open(OUTPUT, mode, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if mode == "w":
                writer.writeheader()

            for idx, row in enumerate(remaining):
                context = json.loads(row["context"])
                label = label_turn(gemini_model, openai_client, row["text"], context)
                record = {
                    "text": row["text"],
                    "context": row["context"],
                    "label": label,
                    "source": row["source"],
                }
                writer.writerow(record)
                f.flush()
                labeled.append(record)

                preview = row["text"][:55]
                _safe_print(f"  [{idx + 1}/{len(remaining)}] {label:10s} | {preview}")
                time.sleep(0.3)

    counts = {}
    for row in labeled:
        counts[row["label"]] = counts.get(row["label"], 0) + 1

    print(f"\nDone. {len(labeled)} total rows in {OUTPUT}")
    print(f"Label distribution: {counts}")
    print("\nReview the CSV, correct any wrong labels, then run:")
    print("  python cli/train_classifier.py")


if __name__ == "__main__":
    main()
