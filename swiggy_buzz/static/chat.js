const chatEl = document.getElementById("chat");
const composer = document.getElementById("composer");
const input = document.getElementById("composer-input");
const sendBtn = document.getElementById("composer-send");
const subtitle = document.getElementById("brand-subtitle");

function scrollToBottom() {
  chatEl.scrollTop = chatEl.scrollHeight;
}

function addBubble(text, who, { error = false } = {}) {
  const row = document.createElement("div");
  row.className = `row ${who}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble" + (error ? " error" : "");
  bubble.textContent = text;
  row.appendChild(bubble);
  chatEl.appendChild(row);
  scrollToBottom();
  return row;
}

function addTypingBubble() {
  const row = document.createElement("div");
  row.className = "row bot";
  row.id = "typing-row";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
  row.appendChild(bubble);
  chatEl.appendChild(row);
  scrollToBottom();
}

function removeTypingBubble() {
  const row = document.getElementById("typing-row");
  if (row) row.remove();
}

function addCard(innerHtml) {
  const wrap = document.createElement("div");
  wrap.className = "card-wrap";
  wrap.innerHTML = `<div class="card">${innerHtml}</div>`;
  chatEl.appendChild(wrap);
  scrollToBottom();
}

const BUCKET_LABEL = { likely: "likely", maybe: "maybe", out: "out" };

function renderPantryCard(items) {
  if (!items || items.length === 0) return;
  const chips = items
    .map(
      (i) =>
        `<span class="chip ${i.bucket}">${escapeHtml(i.name)} · ${BUCKET_LABEL[i.bucket] || i.bucket}</span>`
    )
    .join("");
  addCard(`
    <div class="card-title">🧺 Pantry status</div>
    <div class="pantry-grid">${chips}</div>
  `);
}

function renderRecipeCard(recipes) {
  if (!recipes || recipes.length === 0) return;
  const items = recipes
    .map((r) => {
      const missing = r.missing_ingredients && r.missing_ingredients.length
        ? escapeHtml(r.missing_ingredients.join(", "))
        : '<span class="none">nothing missing — ready to cook</span>';
      return `
        <div class="recipe-item">
          <div class="recipe-name">${escapeHtml(r.name)}</div>
          <div class="recipe-missing">Missing: ${missing}</div>
        </div>`;
    })
    .join("");
  addCard(`
    <div class="card-title">🍳 Recipe ideas</div>
    <div class="recipe-list">${items}</div>
  `);
}

function renderCartCard(cart) {
  if (!cart) return;
  const lines = (cart.kept || [])
    .map(
      (l) => `
      <div class="cart-line">
        <span class="cart-line-name">${escapeHtml(l.name)} <span class="cart-line-qty">×${l.qty}</span></span>
        <span class="cart-line-price">₹${l.price}</span>
      </div>`
    )
    .join("");
  const dropped = (cart.dropped || []).length
    ? `<div class="cart-dropped">Left out to stay under ₹1000: ${escapeHtml(
        cart.dropped.map((l) => l.name).join(", ")
      )}</div>`
    : "";
  addCard(`
    <div class="card-title">🛒 Cart staged</div>
    <div class="cart-lines">${lines}</div>
    <div class="cart-total"><span>Total</span><span>₹${cart.total}</span></div>
    ${dropped}
  `);
}

function renderOrderCard(order) {
  if (!order || order.error) return;
  const droppedNote = (order.dropped_for_cap || []).length
    ? `<div class="order-meta">Dropped for cap: ${escapeHtml(order.dropped_for_cap.join(", "))}</div>`
    : "";
  addCard(`
    <div class="order-card">
      <div class="order-check">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <path d="M4 12.5l5 5L20 6.5" stroke="white" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="order-title">Order placed!</div>
      <div class="order-meta">Order <span class="order-id">#${escapeHtml(String(order.order_id))}</span> · ₹${order.total} · COD</div>
      ${droppedNote}
    </div>
  `);
}

const CARD_RENDERERS = {
  get_pantry_status: renderPantryCard,
  suggest_recipes: renderRecipeCard,
  start_gap_order: renderCartCard,
  confirm_gap_order: renderOrderCard,
};

function renderEvents(events) {
  for (const evt of events || []) {
    const renderer = CARD_RENDERERS[evt.tool];
    if (renderer) renderer(evt.result);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadGreeting() {
  try {
    const res = await fetch("/api/greeting");
    const data = await res.json();
    addBubble(data.message, "bot");
  } catch (e) {
    addBubble("Hey! Ready when you are.", "bot");
  }
}

function setBusy(busy) {
  input.disabled = busy;
  sendBtn.disabled = busy;
  subtitle.textContent = busy ? "typing…" : "pantry assistant";
}

async function sendMessage(text) {
  addBubble(text, "user");
  setBusy(true);
  addTypingBubble();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    removeTypingBubble();
    addBubble(data.reply || "…", "bot");
    renderEvents(data.events);
  } catch (e) {
    removeTypingBubble();
    addBubble("Couldn't reach the server — is it still running?", "bot", { error: true });
  } finally {
    setBusy(false);
    input.focus();
  }
}

composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendMessage(text);
});

loadGreeting();
input.focus();
