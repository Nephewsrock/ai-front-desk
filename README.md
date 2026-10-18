# AI Front Desk

A $299/month done-for-you AI receptionist for auto repair shops. Tony builds it,
hosts it on his own rig, and the shop just gets customers answered, quoted, and booked.

## The big picture

Three channels, one shared "brain" (this server + the shop's config):

1. **Web chat widget** (Phase 1 — built, working). A chat box on the shop's website.
2. **Missed-call text-back** (Phase 2 — designed). Shop misses a call, the AI texts the caller.
3. **Voice answering** (Phase 3 — designed). The AI picks up the phone.

Phases 2 and 3 plug into the same brain: same shop config, same model, same booking log.
Only the "ears and mouth" change (website text box → SMS → phone call).

## What's in this folder

```
ai-front-desk/
  README.md            this file
  brain/
    server.py          the brain: Flask server, talks to local Ollama
    requirements.txt   pip install -r requirements.txt
    shops/
      sample-auto-repair/
        config.yaml    the shop's facts: name, hours, services, prices, booking rules
        bookings.log   created automatically: one JSON line per booking taken
  widget/
    widget.js          the embeddable chat box (no libraries needed)
    demo.html          a demo page to try the widget locally
```

## How the brain works

1. A visitor types in the widget. The widget POSTs to `/chat` with the shop id,
   a session id, and the message.
2. The server loads `shops/<shop-id>/config.yaml` and turns it into instructions
   for the AI model (shop name, hours, services with exact prices, booking rules).
3. The local Ollama model (qwen3:32b) writes the reply. It only quotes prices from
   the config — it never invents numbers.
4. When the model has collected all five booking details (name, phone, vehicle,
   service, preferred time), it ends its reply with a `BOOKING:` line. The server
   spots that line, saves the booking to `bookings.log`, and strips the line so
   the visitor never sees it.

Chat history is kept in memory per visitor (forgotten if the server restarts).
If Ollama isn't running, visitors get a polite "please call us at ___" message
with the shop's real phone number from the config.

## Running it on Tony's rig (Windows)

1. Install Python deps (one time):
   ```
   pip install -r requirements.txt
   ```
2. Make sure Ollama is running and the model is pulled:
   ```
   ollama pull qwen3:32b
   ```
3. Start the brain:
   ```
   python server.py
   ```
   It listens on port 8100 (localhost only).

4. Expose it with Caddy (same pattern as the existing chat server). Add to the Caddyfile:
   ```
   frontdesk.nobodywatchingai.duckdns.org {
       reverse_proxy 127.0.0.1:8100
   }
   ```
   Then `caddy reload`. (If you use DuckDNS, make sure its updater is running so the
   subdomain resolves.)

5. The shop pastes one line into their website before `</body>`:
   ```html
   <script src="https://frontdesk.nobodywatchingai.duckdns.org/widget.js"
           data-server="https://frontdesk.nobodywatchingai.duckdns.org"
           data-shop="sample-auto-repair"></script>
   ```
   `widget.js` is served from the `widget/` folder — point Caddy at it or copy the
   file to the shop's own site. Either works.

## Adding a new shop

1. Copy `brain/shops/sample-auto-repair/` to `brain/shops/<shop-id>/`.
2. Edit the new `config.yaml`: real name, address, phone, hours, services, prices.
3. Give the shop their one-line snippet with `data-shop="<shop-id>"`.

No code changes, no restart. The next chat message picks up the new config.

## Bookings

Every completed booking appends one line to `shops/<shop-id>/bookings.log`, e.g.:

```json
{"when_logged": "2026-10-15T14:02:11", "name": "Jane Smith", "phone": "615-555-0123", "vehicle": "2019 Honda Civic", "service": "oil change", "preferred_time": "Friday morning"}
```

For Phase 1 the shop reads this file (Tony can show them). Calendar integration
comes later.

## Limits (honest list)

- The brain runs on Tony's home rig. If the rig is off or asleep, the widget
  shows the "please call us" fallback. See "The 24/7 question" below.
- One model serves all shops; each shop's answers come from its own config.
- Chat history is in-memory only (fine for a chat box; SMS/voice will key
  sessions by phone number in Phase 2/3).

## The 24/7 question (not decided)

The sell sheet says "answers your shop's calls 24/7." That's only true if the rig
is always on when a customer messages. Options, no decision made:

- **Leave the rig on 24/7.** Simplest. Costs electricity, fan noise, Windows updates
  can still reboot it (set active hours / pause updates).
- **A small always-on box per shop later.** A cheap mini PC at the shop running
  the brain. Real money, real hassle — only if a shop demands it.
- **Cloud VPS.** Breaks the zero-overhead rule and the "your data stays local"
  pitch. Not recommended.

Until Phase 3 (voice) exists, trim the "answers your shop's calls" line from the
sell sheet — Phase 1 is web chat only.
