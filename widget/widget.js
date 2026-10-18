/* AI Front Desk - chat widget (Phase 1)
 *
 * How a shop uses it: paste ONE line into their website, just before </body>:
 *
 *   <script src="https://YOUR-SERVER/widget.js"
 *           data-server="https://YOUR-SERVER"
 *           data-shop="sample-auto-repair"></script>
 *
 * That is the whole install. No other files, no libraries, no build step.
 * The widget draws a chat button in the corner; clicking it opens the chat box.
 */
(function () {
  "use strict";

  // Read settings from the <script> tag that loaded this file.
  var tag = document.currentScript;
  var SERVER = (tag.getAttribute("data-server") || "").replace(/\/$/, "");
  var SHOP = tag.getAttribute("data-shop") || "";
  var COLOR = tag.getAttribute("data-color") || "#1a56db"; // button color

  if (!SERVER || !SHOP) {
    console.error("AI Front Desk widget: data-server and data-shop are required.");
    return;
  }

  var sessionId = "web-" + Math.random().toString(36).slice(2, 12);
  var shopName = "Front Desk";
  var open = false;

  // --- Build the chat UI -------------------------------------------------
  var btn = document.createElement("button");
  btn.textContent = "Chat";
  btn.setAttribute("aria-label", "Chat with us");
  btn.style.cssText =
    "position:fixed;bottom:20px;right:20px;z-index:9999;" +
    "background:" + COLOR + ";color:#fff;border:none;border-radius:999px;" +
    "padding:14px 22px;font-size:16px;cursor:pointer;font-family:sans-serif;" +
    "box-shadow:0 4px 14px rgba(0,0,0,0.25);";

  var panel = document.createElement("div");
  panel.style.cssText =
    "position:fixed;bottom:80px;right:20px;z-index:9999;display:none;" +
    "width:340px;max-width:calc(100vw - 40px);height:460px;max-height:70vh;" +
    "background:#fff;border-radius:12px;overflow:hidden;flex-direction:column;" +
    "box-shadow:0 8px 30px rgba(0,0,0,0.25);font-family:sans-serif;";

  var head = document.createElement("div");
  head.style.cssText =
    "background:" + COLOR + ";color:#fff;padding:12px 16px;font-size:16px;font-weight:bold;";

  var msgs = document.createElement("div");
  msgs.style.cssText =
    "flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px;";

  var form = document.createElement("form");
  form.style.cssText = "display:flex;border-top:1px solid #ddd;";

  var input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Type your message...";
  input.setAttribute("aria-label", "Type your message");
  input.style.cssText = "flex:1;border:none;padding:12px;font-size:15px;outline:none;";

  var send = document.createElement("button");
  send.type = "submit";
  send.textContent = "Send";
  send.style.cssText =
    "background:" + COLOR + ";color:#fff;border:none;padding:0 18px;" +
    "font-size:15px;cursor:pointer;";

  form.appendChild(input);
  form.appendChild(send);
  panel.appendChild(head);
  panel.appendChild(msgs);
  panel.appendChild(form);
  document.body.appendChild(btn);
  document.body.appendChild(panel);

  function addMsg(text, mine) {
    var div = document.createElement("div");
    div.textContent = text;
    div.style.cssText =
      "max-width:85%;padding:9px 12px;border-radius:12px;font-size:15px;line-height:1.4;" +
      (mine
        ? "align-self:flex-end;background:" + COLOR + ";color:#fff;"
        : "align-self:flex-start;background:#f1f1f1;color:#111;");
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  // Ask the server for the shop name + greeting, then show the greeting.
  fetch(SERVER + "/shop-info?shop=" + encodeURIComponent(SHOP))
    .then(function (r) { return r.json(); })
    .then(function (info) {
      if (info.shop_name) { shopName = info.shop_name; head.textContent = shopName; }
      if (info.greeting) { addMsg(info.greeting, false); }
    })
    .catch(function () { head.textContent = shopName; });
  head.textContent = shopName;

  btn.addEventListener("click", function () {
    open = !open;
    panel.style.display = open ? "flex" : "none";
    if (open) { input.focus(); }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) { return; }
    input.value = "";
    addMsg(text, true);

    fetch(SERVER + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shop: SHOP, session_id: sessionId, message: text }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        addMsg(data.reply || "Sorry, something went wrong. Please call the shop.", false);
      })
      .catch(function () {
        addMsg("Sorry, I'm having trouble right now. Please call the shop.", false);
      });
  });
})();
