# AI Front Desk - brain server (Phase 1: web chat widget)
#
# What this does:
#   1. A visitor types in the chat widget on a shop's website.
#   2. The widget sends the message here:  POST /chat
#   3. This server loads that shop's config (name, hours, services, prices),
#      asks the local Ollama model what to say, and sends the reply back.
#   4. When the model has collected a full booking (name, phone, vehicle,
#      service, preferred time), this server saves it to that shop's
#      bookings.log file so the shop can follow up.
#
# Run it:
#   pip install -r requirements.txt
#   python server.py
# It listens on port 8100. Ollama must be running on this same machine
# (http://localhost:11434) with the model pulled, e.g.:
#   ollama pull qwen3:32b

import json
import os
import re
from datetime import datetime

import requests
import yaml
from flask import Flask, jsonify, request
from classifier import classify_message, log_escalation, HANDOFF_REPLY


# --- Settings (change these if you need to) -------------------------------
PORT = 8100                       # port this server listens on
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:32b"        # change with:  set OLLAMA_MODEL=... (see below)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL)

# Folder that holds one subfolder per shop, each with a config.yaml.
# server.py lives in brain/, so shops/ sits right next to it.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHOPS_DIR = os.path.join(BASE_DIR, "shops")

app = Flask(__name__)

# The widget runs on the shop's website (a different origin), so the browser
# demands CORS headers or it blocks the chat messages outright.
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# Chat history, kept in memory per visitor:  { "shop-id|session-id": [messages] }
# (If the server restarts, old chats are forgotten. That's fine for phase 1.)
histories = {}

# Shop configs, loaded once then cached. Edit a config.yaml and it applies
# to the NEXT message -- no restart needed (we check the file's timestamp).
config_cache = {}


def load_shop_config(shop_id):
    """Read shops/<shop_id>/config.yaml. Returns (config_dict, error_string)."""
    path = os.path.join(SHOPS_DIR, shop_id, "config.yaml")
    if not os.path.isfile(path):
        return None, "unknown shop: %s" % shop_id
    stamp = os.path.getmtime(path)
    cached = config_cache.get(shop_id)
    if cached and cached["stamp"] == stamp:
        return cached["config"], None
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config_cache[shop_id] = {"stamp": stamp, "config": config}
    return config, None


def build_system_prompt(config):
    """Turn the shop's config into instructions for the AI model."""
    lines = []
    lines.append("You are the friendly front desk for %s, an auto repair shop in %s."
                 % (config["shop_name"], config["town"]))
    lines.append("Address: %s" % config["address"])
    lines.append("Phone: %s" % config["phone"])
    h = config["hours"]
    lines.append("Hours: Mon-Fri %s, Saturday %s, Sunday %s."
                 % (h["monday_friday"], h["saturday"], h["sunday"]))
    lines.append("")
    lines.append("Services and flat prices you may quote (quote these exact numbers):")
    for s in config["services"]:
        note = (" (%s)" % s["note"]) if s.get("note") else ""
        lines.append("- %s: $%.2f%s" % (s["name"], s["price"], note))
    lines.append("")
    b = config["booking"]
    lines.append("Booking: %s" % b["slots"])
    lines.append("To book someone you need: %s" % b["needs"])
    lines.append(b["promise"])
    lines.append("")
    lines.append("Rules:")
    lines.append("- Talk like a real front-desk person: short, plain, friendly. No sales talk.")
    lines.append("- Only quote the prices listed above. Never guess or invent a price.")
    lines.append("- If asked about something not listed, say you don't have a price on that "
                 "and offer to have the shop call them back (then collect name and phone).")
    lines.append("- Collect booking details one or two questions at a time, not all at once.")
    lines.append("- When you have ALL FIVE (name, phone, vehicle year/make/model, service, "
                 "preferred day/time), end your reply with this exact line on its own:")
    lines.append("  BOOKING: name | phone | vehicle | service | preferred time")
    lines.append("  (Example: BOOKING: Jane Smith | 615-555-0123 | 2019 Honda Civic | oil change | Friday morning)")
    lines.append("- Never show the BOOKING line unless you truly have all five pieces.")
    return "\n".join(lines)


def ask_ollama(messages):
    """Send the conversation to the local Ollama model, return its reply text."""
    resp = requests.post(
        OLLAMA_URL + "/api/chat",
        json={"model": OLLAMA_MODEL, "messages": messages, "stream": False, "keep_alive": "30m"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def save_booking(shop_id, booking):
    """Append one booking as a JSON line to shops/<shop_id>/bookings.log."""
    log_path = os.path.join(SHOPS_DIR, shop_id, "bookings.log")
    record = {"when_logged": datetime.now().isoformat(timespec="seconds")}
    record.update(booking)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


BOOKING_RE = re.compile(r"^BOOKING:\s*(.+)$", re.MULTILINE)


@app.route("/shop-info", methods=["GET"])
def shop_info():
    """The widget calls this first to get the shop name and greeting."""
    shop_id = request.args.get("shop", "")
    config, err = load_shop_config(shop_id)
    if err:
        return jsonify({"error": err}), 404
    return jsonify({
        "shop_name": config["shop_name"],
        "greeting": config.get("greeting", "Hi! How can I help you?"),
    })


@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    """Main endpoint. Body: {"shop": "...", "session_id": "...", "message": "..."}"""
    if request.method == "OPTIONS":
        # Browser preflight check -- the after_request handler adds the
        # CORS headers, so just answer OK.
        return "", 200
    data = request.get_json(force=True)
    shop_id = data.get("shop", "")
    session_id = data.get("session_id", "default")
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400

    config, err = load_shop_config(shop_id)
    if err:
        return jsonify({"error": err}), 404

    # Phase 2: quick sort - sensitive messages go to the shop, not the AI.
    if classify_message(message) == "human":
        log_escalation(shop_id, session_id, message, SHOPS_DIR)
        return jsonify({"reply": HANDOFF_REPLY})

    key = shop_id + "|" + session_id
    history = histories.get(key)
    if history is None:
        # First message in this chat: start with the system instructions.
        history = [{"role": "system", "content": build_system_prompt(config)}]
        histories[key] = history
    # Keep history from growing forever: system prompt + last 20 turns.
    history = [history[0]] + history[1:][-20:]

    history.append({"role": "user", "content": message})

    try:
        reply = ask_ollama(history)
    except requests.RequestException:
        # Ollama isn't reachable. Don't leave the visitor hanging.
        return jsonify({
            "reply": "Sorry, I'm having trouble right now. Please call us at %s and we'll take care of you."
                     % config["phone"]
        }), 503

    history.append({"role": "assistant", "content": reply})

    # Did the model finish a booking? Look for the BOOKING: line.
    match = BOOKING_RE.search(reply)
    if match:
        parts = [p.strip() for p in match.group(1).split("|")]
        if len(parts) == 5:
            save_booking(shop_id, {
                "name": parts[0],
                "phone": parts[1],
                "vehicle": parts[2],
                "service": parts[3],
                "preferred_time": parts[4],
            })
            # Strip the BOOKING line so the visitor never sees it.
            reply = BOOKING_RE.sub("", reply).strip()

    return jsonify({"reply": reply})


if __name__ == "__main__":
    print("AI Front Desk brain starting on port %d ..." % PORT)
    print("Ollama model: %s (%s)" % (OLLAMA_MODEL, OLLAMA_URL))
    app.run(host="127.0.0.1", port=PORT)


