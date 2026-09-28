// The phone: a chat over /api/chat/stream. Text bubbles, a typing
// indicator that names what the agent is doing, cards for tool results,
// and quick replies. Every agent event is also forwarded to brain.js.

(() => {
  const chatEl = document.getElementById("chat");
  const composer = document.getElementById("composer");
  const input = document.getElementById("composer-input");
  const sendBtn = document.getElementById("composer-send");
  const subtitle = document.getElementById("brand-subtitle");
  const quickEl = document.getElementById("quick-replies");
  const newChatBtn = document.getElementById("new-chat");
  const clockEl = document.getElementById("status-time");

  const IDLE_SUBTITLE = "your kitchen, inferred";
  const START_ONBOARD = ["2 of us, vegetarian", "Just me, I eat everything"];
  const START = ["Sync my Instamart orders", "What can I cook tonight?", "What's running low?"];
  const PERISHABLE = ["milk", "curd", "paneer", "bread", "egg", "tomato", "onion", "potato"];

  let busy = false;
  let onboarded = false;

  // ?privacy blurs street addresses in cards, for screen recordings.
  if (new URLSearchParams(location.search).has("privacy")) document.body.classList.add("privacy");

  function tickClock() {
    clockEl.textContent = new Date()
      .toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
      .replace(/\s?[ap]\.?m\.?$/i, "");
  }

  function scrollToBottom() {
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  // ------------------------------------------------------------ bubbles

  function addBubble(text, who, { error = false } = {}) {
    const row = document.createElement("div");
    row.className = `row ${who}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble" + (error ? " error" : "");
    bubble.innerHTML = renderRich(text);
    row.appendChild(bubble);
    chatEl.appendChild(row);
    scrollToBottom();
  }

  function addTyping() {
    const row = document.createElement("div");
    row.className = "row bot";
    row.innerHTML = `<div class="bubble"><span class="typing"><span class="typing-dots"><span></span><span></span><span></span></span><span class="typing-label"></span></span></div>`;
    chatEl.appendChild(row);
    scrollToBottom();
    const label = row.querySelector(".typing-label");
    return {
      setLabel(text) {
        if (label.textContent === text) return;
        label.textContent = text;
        label.style.animation = "none";
        void label.offsetWidth; // restart the fade-in
        label.style.animation = "";
        scrollToBottom();
      },
      remove() {
        row.remove();
      },
    };
  }

  function addCard(html, className = "") {
    const wrap = document.createElement("div");
    wrap.className = "card-wrap";
    wrap.innerHTML = `<div class="card ${className}">${html}</div>`;
    chatEl.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  // Any element with data-say sends that text as the household's message.
  function sayButton(text, label, className = "btn") {
    return `<button type="button" class="${className}" data-say="${escapeHtml(text)}">${label}</button>`;
  }

  // ------------------------------------------------------------ cards

  function renderHouseholdCard(r) {
    addCard(
      `<div class="event-card">
        <div class="event-icon">🏠</div>
        <div>
          <div class="event-title">Household saved</div>
          <div class="event-sub">${plural(r.household_size, "person", "people")} · ${escapeHtml(dietLabel(r.diet))}. Decay and recipes now tune to this.</div>
        </div>
      </div>`,
      "flush"
    );
  }

  function renderSyncCard(r) {
    const sub =
      r.orders_seen === 0
        ? "No recent orders found."
        : r.orders_ingested === 0
          ? "Already up to date — nothing new since the last sync."
          : "Every product classified; non-food filtered out.";
    addCard(`
      <div class="card-title">📦 Instamart history synced</div>
      <div class="event-sub">${sub}</div>
      <div class="stat-row">
        <div class="stat"><b>${r.orders_seen}</b><span>orders read</span></div>
        <div class="stat"><b>${r.items_added}</b><span>pantry updates</span></div>
        <div class="stat"><b>${r.non_food}</b><span>non-food skipped</span></div>
      </div>
    `);
  }

  function renderPantryCard(items) {
    if (!items || !items.length) return;
    const order = { likely: 0, maybe: 1, out: 2 };
    const sorted = [...items].sort((a, b) => order[a.bucket] - order[b.bucket]);
    const MAX = 16;
    const chips = sorted
      .slice(0, MAX)
      .map((i) => `<span class="chip ${i.bucket}">${itemEmoji(i.name)} ${escapeHtml(prettyName(i.name))}</span>`)
      .join("");
    const more = sorted.length > MAX ? `<span class="chip more">+${sorted.length - MAX} more</span>` : "";
    addCard(`
      <div class="card-title">🧺 Probably in your kitchen <span class="hint">inferred, not seen</span></div>
      <div class="pantry-grid">${chips}${more}</div>
      <div class="legend">
        <span><i style="background:var(--success)"></i>likely</span>
        <span><i style="background:var(--warn)"></i>maybe</span>
        <span><i style="background:#b0b3bd"></i>probably out</span>
      </div>
    `);
  }

  function renderRecipeCard(recipes) {
    if (!recipes || !recipes.length) return;
    const items = recipes
      .map((r) => {
        const missing = r.missing_ingredients || [];
        const total = r.ingredients_total || missing.length;
        const owned = Math.max(0, total - missing.length);
        const meter = Array.from({ length: total }, (_, i) => `<i class="${i < owned ? "on" : ""}"></i>`).join("");
        const tags = (r.tags || []).slice(0, 2).map((t) => `<span class="tag">${escapeHtml(t.replace(/_/g, " "))}</span>`).join("");
        const missingLine = missing.length
          ? `Missing: ${escapeHtml(missing.map(prettyName).join(", "))}`
          : `<span class="ready">✓ Nothing missing — ready to cook</span>`;
        const action = missing.length
          ? sayButton(`Order the missing items for ${r.name}`, `Order ${missing.length} missing`, "link-btn")
          : "";
        return `
          <div class="recipe-item">
            <div class="recipe-top">
              <span class="recipe-name">${escapeHtml(r.name)}</span>
              ${r.prep_time_minutes ? `<span class="recipe-time">⏱ ${r.prep_time_minutes} min</span>` : ""}
            </div>
            <div class="owned-meter">${meter}</div>
            <div class="recipe-meta"><strong>${owned} of ${total}</strong> ingredients probably on hand</div>
            <div class="recipe-missing">${missingLine}</div>
            <div class="recipe-actions"><div class="tags">${tags}</div>${action}</div>
          </div>`;
      })
      .join("");
    addCard(`
      <div class="card-title">🍳 You could cook <span class="hint">ranked by what you own</span></div>
      <div class="recipe-list">${items}</div>
    `);
  }

  function addressMessage(address, allAddresses) {
    const tag = (address.tag || "").trim();
    const tagIsUnique = tag && allAddresses.filter((a) => (a.tag || "").trim().toLowerCase() === tag.toLowerCase()).length === 1;
    if (tagIsUnique) return `Deliver to my ${tag} address`;
    const snippet = String(address.address || "").split(",").slice(0, 2).join(",").trim();
    return `Deliver to ${snippet || address.id}`;
  }

  function addressIcon(tag) {
    const t = String(tag || "").toLowerCase();
    if (t.includes("home")) return "🏠";
    if (t.includes("work") || t.includes("office")) return "💼";
    return "📍";
  }

  function renderAddressCard(addresses) {
    if (!addresses || !addresses.length) return;
    const items = addresses
      .map(
        (a) => `
        <button type="button" class="address-item" data-say="${escapeHtml(addressMessage(a, addresses))}">
          <span class="address-icon">${addressIcon(a.tag)}</span>
          <span>
            <div class="address-tag">${escapeHtml(a.tag || "Saved address")}</div>
            <div class="address-line">${escapeHtml(a.address || "")}</div>
          </span>
        </button>`
      )
      .join("");
    addCard(`
      <div class="card-title">📍 Deliver where? <span class="hint">picked fresh every order</span></div>
      <div class="address-list">${items}</div>
    `);
  }

  function renderCartCard(cart) {
    if (!cart) return;
    const kept = cart.kept || [];
    const lines = kept
      .map(
        (l) => `
        <div class="cart-line">
          <span class="cart-line-name">${escapeHtml(l.name)} <span class="cart-line-qty">×${l.qty}</span>
            <span class="cart-line-for">for ${escapeHtml(prettyName(l.ingredient))}</span></span>
          <span class="cart-line-price">${rupees(l.price * l.qty)}</span>
        </div>`
      )
      .join("");

    const dropped = (cart.dropped || []).length
      ? `<div class="cart-notice dropped">Left out to stay under the ₹1000 cap: <strong>${escapeHtml(cart.dropped.map((l) => l.name).join(", "))}</strong></div>`
      : "";

    const unresolved = (cart.unresolved || [])
      .map((u) => {
        const alts = (u.alternatives || [])
          .map((a) =>
            sayButton(
              `Use ${a.name} for ${prettyName(u.ingredient).toLowerCase()}`,
              `${escapeHtml(a.name)}${a.size ? ` · ${escapeHtml(a.size)}` : ""} · ${rupees(a.price)}`,
              "alt-chip"
            )
          )
          .join("");
        return `<div class="cart-notice unresolved">
          Couldn't find <strong>${escapeHtml(prettyName(u.ingredient))}</strong>${alts ? " — pick an alternative, or skip it:" : "."}
          ${alts ? `<div class="alt-list">${alts}</div>` : ""}
        </div>`;
      })
      .join("");

    const total = Number(cart.total) || 0;
    const capPct = Math.min(100, (total / 1000) * 100);
    const actions = kept.length
      ? `<div class="btn-row">
          ${sayButton("I'd like to change something in the cart", "Change")}
          ${sayButton("Yes, place the order", `Place order · ${rupees(total)}`, "btn primary")}
        </div>`
      : "";

    addCard(`
      <div class="card-title">🛒 Cart ready <span class="hint">not ordered yet</span></div>
      ${kept.length ? `<div class="cart-lines">${lines}</div>` : ""}
      ${kept.length ? `<div class="cart-total"><span>Total</span><span>${rupees(total)}</span></div>
      <div class="cap-meter"><i style="width:${capPct}%"></i></div>
      <div class="cap-label"><span>₹1000 order cap</span><span>${rupees(Math.max(0, 1000 - total))} headroom</span></div>` : ""}
      ${dropped}
      ${unresolved}
      ${actions}
      ${kept.length ? `<div class="card-note">Cash on delivery · delivered right away · nothing is ordered until you say yes</div>` : ""}
    `);
  }

  function confetti() {
    const colors = ["#fc8019", "#1ba672", "#fbbf24", "#60a5fa", "#f472b6"];
    return Array.from({ length: 18 }, (_, i) => {
      const angle = (Math.PI * 2 * i) / 18 + Math.random() * 0.3;
      const dist = 70 + Math.random() * 70;
      return `<span class="confetti" style="background:${colors[i % colors.length]};--dx:${Math.cos(angle) * dist}px;--dy:${Math.sin(angle) * dist * 0.8 + 30}px;--r:${Math.round(Math.random() * 540 - 270)}deg;animation-delay:${Math.random() * 0.15}s"></span>`;
    }).join("");
  }

  function renderOrderCard(order) {
    if (!order || order.error) return;
    const id = order.order_id ? `Order <span class="order-id">#${escapeHtml(String(order.order_id))}</span> · ` : "";
    const dropped = (order.dropped_for_cap || []).length
      ? `<div class="order-meta" style="margin-top:6px">Left out for the cap: ${escapeHtml(order.dropped_for_cap.join(", "))}</div>`
      : "";
    addCard(
      `${confetti()}
      <div class="order-check">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none"><path d="M4 12.5l5 5L20 6.5" stroke="white" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
      <div class="order-title">Order placed on Instamart</div>
      <div class="order-meta">${id}${rupees(order.total)} · Cash on delivery</div>
      ${dropped}`,
      "order-card"
    );
  }

  function renderCorrectionCard(r, args) {
    if (!r || r.error) return;
    const name = prettyName(r.canonical_name);
    const faster = (args || {}).direction === "ran_out_early";
    addCard(
      `<div class="event-card">
        <div class="event-icon">🧠</div>
        <div>
          <div class="event-title">Learned: ${escapeHtml(name)} ${faster ? "goes faster" : "lasts longer"} in your home</div>
          <div class="event-sub">Personal pace now ×${r.new_pace_multiplier}${faster ? ", marked as out" : ""}. Future estimates bend to match.</div>
        </div>
      </div>`,
      "flush"
    );
  }

  function renderAuthCard(text) {
    addCard(
      `<div class="card-title">🔌 Swiggy needs you to sign in again</div>
      <div class="event-sub">${escapeHtml(text.split(/\s*Re-run|\n/)[0])}</div>
      <code>uv run scripts/swiggy_login.py</code>`,
      "auth-card"
    );
  }

  const CARD_RENDERERS = {
    onboard_user: renderHouseholdCard,
    sync_orders: renderSyncCard,
    get_pantry_status: renderPantryCard,
    suggest_recipes: renderRecipeCard,
    list_addresses: renderAddressCard,
    start_gap_order: renderCartCard,
    confirm_gap_order: renderOrderCard,
    record_item_correction: renderCorrectionCard,
  };

  function renderCards(cards) {
    for (const [tool, { result, args }] of cards) {
      // Recipes already say what's missing; a pantry card on top is clutter.
      if (tool === "get_pantry_status" && cards.has("suggest_recipes")) continue;
      const render = CARD_RENDERERS[tool];
      if (render) render(result, args);
    }
  }

  // ------------------------------------------------------------ quick replies

  function setChips(list) {
    quickEl.innerHTML = list.map((t) => `<button type="button" class="qr" data-say="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join("");
  }

  function suggestionsFor(turn) {
    const final = turn.final;
    if (!final || final.type === "error") return final && final.kind === "auth" ? [] : ["Try that again"];
    const get = (tool) => (turn.cards.get(tool) || {}).result;

    if (get("confirm_gap_order")) return ["What can I cook tonight?", "Check my pantry"];
    const cart = get("start_gap_order");
    if (cart && (cart.kept || []).length) return ["Yes, place the order", "Remove something", "Cancel"];
    if (get("list_addresses")) return [];
    const recipes = get("suggest_recipes");
    if (recipes && recipes.length) {
      const withGap = recipes.find((r) => (r.missing_ingredients || []).length);
      return [withGap && `Order what's missing for ${withGap.name}`, "Something quicker?", "What's running low?"].filter(Boolean);
    }
    const pantry = get("get_pantry_status");
    if (pantry && pantry.length) {
      const likely = new Set(pantry.filter((i) => i.bucket === "likely").map((i) => i.name));
      const fresh = PERISHABLE.find((name) => likely.has(name));
      return ["What can I cook tonight?", fresh && `We ran out of ${prettyName(fresh).toLowerCase()} early`].filter(Boolean);
    }
    if (get("sync_orders")) return ["What can I cook tonight?", "What's running low?"];
    if (get("record_item_correction")) return ["What can I cook tonight?", "Check my pantry"];
    if (get("onboard_user")) return ["Sync my Instamart orders", "What can I cook tonight?"];
    return onboarded ? START : START_ONBOARD;
  }

  // ------------------------------------------------------------ talking to the server

  async function streamChat(text, onEvent) {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        const data = chunk
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim())
          .join("");
        if (data) onEvent(JSON.parse(data));
      }
    }
  }

  function setBusy(value) {
    busy = value;
    input.disabled = value;
    sendBtn.disabled = value;
    newChatBtn.disabled = value;
    subtitle.textContent = value ? "thinking…" : IDLE_SUBTITLE;
    subtitle.classList.toggle("busy", value);
    for (const el of document.querySelectorAll("[data-say]")) el.disabled = value || el.dataset.used === "1";
  }

  async function sendMessage(text) {
    if (busy || !text.trim()) return;
    addBubble(text, "user");
    setChips([]);
    setBusy(true);
    const typing = addTyping();
    typing.setLabel("Thinking");
    App.emit("turn:start", { text });

    const turn = { cards: new Map(), final: null };
    let lastArgs = {};
    try {
      await streamChat(text, (evt) => {
        App.emit("agent:event", evt);
        if (evt.type === "llm_start") {
          typing.setLabel(evt.hop === 0 ? "Thinking" : "Putting it together");
        } else if (evt.type === "tool_start") {
          lastArgs = evt.args || {};
          typing.setLabel(`${toolMeta(evt.tool).running}…`);
        } else if (evt.type === "tool_end" && evt.ok) {
          turn.cards.set(evt.tool, { result: evt.result, args: lastArgs });
          if (evt.tool === "onboard_user") onboarded = true;
        } else if (evt.type === "reply" || evt.type === "error") {
          turn.final = evt;
        }
      });
    } catch {
      turn.final = { type: "error", kind: "network", text: "Couldn't reach the server — is it still running?" };
    }
    if (!turn.final) {
      turn.final = { type: "error", kind: "network", text: "The connection dropped before I could answer — try again?" };
    }

    typing.remove();
    if (turn.final.type === "error" && turn.final.kind === "auth") {
      renderAuthCard(turn.final.text);
    } else {
      addBubble(turn.final.text || "…", "bot", { error: turn.final.type === "error" });
    }
    renderCards(turn.cards);
    setBusy(false);
    setChips(suggestionsFor(turn));
    scrollToBottom(); // the chips row just took space from the chat
    App.emit("turn:end", turn);
    input.focus();
  }

  // ------------------------------------------------------------ wiring

  function onSay(e) {
    const el = e.target.closest("[data-say]");
    if (!el || busy) return;
    // A card's buttons are one-shot: its choice has been made.
    const card = el.closest(".card");
    if (card) for (const b of card.querySelectorAll("[data-say]")) b.dataset.used = "1";
    sendMessage(el.dataset.say);
  }

  chatEl.addEventListener("click", onSay);
  quickEl.addEventListener("click", onSay);

  composer.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendMessage(text);
  });

  async function greet() {
    let message = "Hey! Ready when you are.";
    try {
      const data = await (await fetch("/api/greeting")).json();
      message = data.message;
      onboarded = Boolean(data.onboarded);
    } catch {
      /* fall back to the generic hello */
    }
    addBubble(message, "bot");
    setChips(onboarded ? START : START_ONBOARD);
  }

  // A reload starts a fresh conversation server-side too, so the model never
  // remembers turns the screen no longer shows.
  async function newChat() {
    if (busy) return;
    try {
      await fetch("/api/reset", { method: "POST" });
    } catch {
      /* greet() will surface a dead server */
    }
    chatEl.innerHTML = "";
    App.emit("reset");
    await greet();
    input.focus();
  }

  newChatBtn.addEventListener("click", newChat);

  tickClock();
  setInterval(tickClock, 15000);
  newChat();
})();
