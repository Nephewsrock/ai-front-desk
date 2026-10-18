# classifier.py - fast message sorter for the AI Front Desk (Phase 2)
#
# What this does:
#   Every visitor message gets a quick yes/no check from a SMALL, FAST model
#   (qwen3:1.7b - answers in about a second, so the visitor barely waits):
#       "faq"   - normal front-desk question -> hand it to the big model
#                 (qwen3:32b) exactly like before
#       "human" - this one needs a real person at the shop
#
#   Tony's rule (2026-10-18): WHEN IN DOUBT, SEND IT TO THE HUMAN.
#   So if the small model is unsure, or anything goes wrong, we say "human".
#   Sending too much to the shop is harmless; the AI guessing wrong on
#   something sensitive is not.
#
# Drop this file in the brain folder right next to server.py.
# The small model must be pulled first:
#   ollama pull qwen3:1.7b

import json
import os
from datetime import datetime

import requests

# --- Settings (change these if you need to) -------------------------------
OLLAMA_URL = "http://localhost:11434"
CLASSIFIER_MODEL = "qwen3:1.7b"   # the small, fast model
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", CLASSIFIER_MODEL)

# What the visitor sees when their message gets sent to the shop.
# Plain and honest: the AI doesn't want to guess wrong on their problem.
HANDOFF_REPLY = (
    "That one's best for the shop itself - I don't want to guess wrong on it. "
    "Can I grab your name and number and have them call you back?"
)

# --- The sorting instructions ----------------------------------------------
#
# This is the whole "brain" of the classifier. A few examples teach the
# small model the difference, including the tricky pair Tony called out:
#   "how much are brakes?"      -> FAQ (quote from the price list)
#   "you overcharged me for brakes" -> HUMAN (billing dispute)

SORT_PROMPT = """You sort customer chat messages for an auto repair shop into two buckets.
Reply with exactly one word: HUMAN or FAQ.

HUMAN = a real person at the shop must handle this:
- complaints or angry customers
- billing disputes ("you charged me too much")
- tow requests or breakdowns (urgent)
- questions about a car already in the shop ("is my car done?")
- warranty arguments
- anything sensitive or unclear

FAQ = normal front-desk questions:
- hours, address, phone number
- services and prices ("how much are brakes?")
- booking requests

Examples:
"what are your hours on saturday?" -> FAQ
"how much are brakes?" -> FAQ
"do you do brake jobs?" -> FAQ
"can I book for tomorrow morning?" -> FAQ
"you overcharged me for brakes" -> HUMAN
"my truck broke down on the highway, can you tow me?" -> HUMAN
"is my civic done yet? dropped it off yesterday" -> HUMAN
"your mechanic scratched my bumper" -> HUMAN

Now sort this message. One word only, HUMAN or FAQ:
"""


def classify_message(message):
    """Return "human" or "faq" for one visitor message.

    Defaults to "human" whenever anything is unclear or goes wrong.
    """
    try:
        resp = requests.post(
            OLLAMA_URL + "/api/generate",
            json={
                "model": CLASSIFIER_MODEL,
                "prompt": SORT_PROMPT + '"' + message.strip() + '"',
                "stream": False,
                # No "thinking" chatter - we want one word back, fast.
                # (qwen3 thinks by default in Ollama; "think": False skips it.)
                "options": {"temperature": 0.0},
                "think": False,
                "keep_alive": "30m",
            },
            timeout=30,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip().upper()
    except requests.RequestException:
        # Ollama isn't reachable. Fail safe: send it to the human.
        # The handoff reply needs no model, so this path always works.
        return "human"

    if "HUMAN" in answer:
        return "human"
    if "FAQ" in answer:
        return "faq"
    # The model mumbled something else. When in doubt: human.
    return "human"


def log_escalation(shop_id, session_id, message, shops_dir):
    """Write one JSON line per escalated message so the shop can review
    everything the AI punted to them. shops_dir is the brain folder's
    shops/ directory."""
    log_path = os.path.join(shops_dir, shop_id, "escalations.log")
    record = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "session": session_id,
        "message": message,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# --- Quick self-test --------------------------------------------------------
# Run:  python classifier.py
# Needs Ollama running with qwen3:1.7b pulled. Watch each test land in the
# right bucket before you wire this into server.py.

if __name__ == "__main__":
    tests = [
        ("what are your hours on saturday?", "faq"),
        ("how much is an oil change?", "faq"),
        ("do you do brake jobs?", "faq"),
        ("can I book for tomorrow morning?", "faq"),
        ("you charged me $200 too much on my invoice", "human"),
        ("my car broke down on I-24, can you tow me?", "human"),
        ("is my camry done yet? dropped it off yesterday", "human"),
        ("your mechanic scratched my bumper, I want to complain", "human"),
        ("what about the warranty on the alternator you replaced", "human"),
        ("how much are brakes?", "faq"),
        ("you overcharged me for brakes", "human"),
    ]
    print("Classifier self-test (model: %s)" % CLASSIFIER_MODEL)
    ok = 0
    for message, expected in tests:
        got = classify_message(message)
        mark = "OK " if got == expected else "MISS"
        if got == expected:
            ok += 1
        print("[%s] expected=%-5s got=%-5s  %s" % (mark, expected, got, message))
    print("%d of %d correct" % (ok, len(tests)))
