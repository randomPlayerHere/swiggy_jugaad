// The "under the hood" panel: live status, the pantry model with each
// item's decay curve, and a timeline of every LLM hop and tool call.
// Listens to chat.js over App's event bus; never talks to the chat itself.

(() => {
  const brainEl = document.getElementById("brain");
  const pillsEl = document.getElementById("status-pills");
  const countsEl = document.getElementById("bucket-counts");
  const pantryEl = document.getElementById("pantry-list");
  const feedEl = document.getElementById("activity-feed");
  const liveTag = document.getElementById("live-tag");

  // ------------------------------------------------------------ status

  async function refreshStatus() {
    try {
      const status = await (await fetch("/api/status")).json();
      App.status = status;
      renderStatus(status);
      App.emit("status", status);
    } catch {
      /* the chat surfaces server trouble; the panel just keeps its last view */
    }
  }

  function renderStatus(status) {
    const pills = [];
    const h = status.household;
    pills.push(
      h
        ? `<span class="pill">🏠 <b>${plural(h.household_size, "person", "people")}</b> · ${escapeHtml(dietLabel(h.diet))}</span>`
        : `<span class="pill">🏠 not onboarded yet</span>`
    );

    const swiggy = status.swiggy || {};
    if (!swiggy.token_set) {
      pills.push(`<span class="pill bad"><span class="dot"></span>Swiggy: not signed in</span>`);
    } else if (swiggy.expires_at) {
      const days = (new Date(swiggy.expires_at) - Date.now()) / 86400000;
      pills.push(
        days > 0
          ? `<span class="pill ok"><span class="dot"></span>Swiggy MCP · token valid <b>${formatDays(days)}</b></span>`
          : `<span class="pill bad"><span class="dot"></span>Swiggy token expired</span>`
      );
    } else {
      pills.push(`<span class="pill ok"><span class="dot"></span>Swiggy MCP</span>`);
    }

    if (status.orders_source === "replay") {
      pills.push(`<span class="pill note" title="Order history is replayed from data/demo_orders.json; addresses, search, cart and checkout are live">📼 sample order history</span>`);
    }

    const model = String(status.model || "").split("/").pop();
    if (model) pills.push(`<span class="pill">🧠 NIM · <b>${escapeHtml(model)}</b></span>`);

    pillsEl.innerHTML = pills.join("");
  }

  // ------------------------------------------------------------ pantry

  let previous = new Map(); // name -> "bucket|pace", to flash what changed
  let firstPantryRender = true;

  async function refreshPantry() {
    try {
      renderPantry(await (await fetch("/api/pantry")).json());
    } catch {
      /* keep the last view */
    }
  }

  function sparkline(item) {
    const W = 88, H = 28, pad = 3;
    const life = Math.max(item.life_days, 0.05);
    const tMax = Math.max(life * 1.3, item.age_days * 1.08);
    const C = (t) => Math.exp(-LN20 * (t / life) ** 2);
    const x = (t) => pad + (t / tMax) * (W - 2 * pad);
    const y = (c) => pad + (1 - c) * (H - 2 * pad);

    let curve = "";
    const N = 36;
    for (let i = 0; i <= N; i++) {
      const t = (tMax * i) / N;
      curve += `${i ? "L" : "M"}${x(t).toFixed(1)} ${y(C(t)).toFixed(1)}`;
    }
    const area = `${curve}L${x(tMax).toFixed(1)} ${H - pad}L${x(0).toFixed(1)} ${H - pad}Z`;
    const nowX = x(Math.min(item.age_days, tMax)).toFixed(1);
    const nowY = y(item.confidence).toFixed(1);

    return `<svg class="spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">
      <line class="guide" x1="${pad}" x2="${W - pad}" y1="${y(0.7)}" y2="${y(0.7)}"/>
      <line class="guide" x1="${pad}" x2="${W - pad}" y1="${y(0.3)}" y2="${y(0.3)}"/>
      <path d="${area}" fill="currentColor" opacity="0.13"/>
      <path d="${curve}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
      <circle cx="${nowX}" cy="${nowY}" r="3.4" fill="currentColor" stroke="#11131c" stroke-width="1.6"/>
    </svg>`;
  }

  function renderPantry({ items, counts }) {
    countsEl.innerHTML = items.length
      ? `<span class="count likely">${counts.likely} likely</span><span class="count maybe">${counts.maybe} maybe</span><span class="count out">${counts.out} out</span>`
      : "";

    if (!items.length) {
      pantryEl.innerHTML = `<div class="empty">No pantry yet.<br/>Ask the assistant to <b>sync your Instamart orders</b> and the model will start inferring what's still in your kitchen.</div>`;
      previous = new Map();
      firstPantryRender = false;
      return;
    }

    const cascade = previous.size === 0 && !firstPantryRender;
    const next = new Map();
    pantryEl.innerHTML = items
      .map((item, i) => {
        const key = `${item.bucket}|${item.pace}`;
        next.set(item.name, key);
        const changed = previous.size > 0 && previous.get(item.name) !== key;
        const cls = [item.bucket, changed ? "flash" : "", cascade ? "enter" : ""].join(" ");
        const delay = cascade ? ` style="animation-delay:${Math.min(i * 35, 900)}ms"` : "";
        const flags = [
          item.is_out ? `<span class="p-flag">reported out</span>` : "",
          item.pace !== 1 ? `<span class="p-flag pace">pace ×${item.pace}</span>` : "",
        ].join("");
        const pct = Math.round(item.confidence * 100);
        return `<div class="pantry-row ${cls}"${delay} title="${escapeHtml(item.category)} · confidence ${pct}%">
          <div class="p-emoji">${itemEmoji(item.name, item.category)}</div>
          <div class="p-main">
            <div class="p-name">${escapeHtml(prettyName(item.name))}${flags}</div>
            <div class="p-meta">bought ${formatDays(item.age_days)} ago · lasts ~${formatDays(item.life_days)} · ${escapeHtml(item.category.replace("_", " "))}</div>
            <div class="p-bar"><i style="width:${item.is_out ? 0 : pct}%"></i></div>
          </div>
          ${sparkline(item)}
          <div class="p-pct">${item.is_out ? "out" : `${pct}%`}</div>
        </div>`;
      })
      .join("");
    previous = next;
    firstPantryRender = false;
  }

  // ------------------------------------------------------------ activity

  let turnEl = null;
  let runningStep = null;
  let ticker = null;

  function emptyFeed() {
    feedEl.innerHTML = `<div class="empty">Every LLM hop and tool call the agent makes shows up here, live.</div>`;
  }

  function scrollFeed() {
    feedEl.scrollTop = feedEl.scrollHeight;
  }

  function startStep(kind, label) {
    finishStep(); // defensive: steps are strictly sequential
    const el = document.createElement("div");
    el.className = `step ${kind} running`;
    el.innerHTML = `<span class="node"></span><div class="step-line"><span class="step-label">${escapeHtml(label)}</span><span class="step-ms">0.0s</span></div>`;
    turnEl.appendChild(el);
    const started = performance.now();
    const msEl = el.querySelector(".step-ms");
    ticker = setInterval(() => (msEl.textContent = formatMs(Math.round(performance.now() - started))), 100);
    runningStep = el;
    scrollFeed();
    return el;
  }

  function finishStep({ label, ms, ok = true, summary = "", detail = null } = {}) {
    if (!runningStep) return;
    clearInterval(ticker);
    const el = runningStep;
    runningStep = null;
    el.classList.remove("running");
    el.classList.add(ok ? "ok" : "fail");
    if (label) el.querySelector(".step-label").textContent = label;
    if (ms != null) el.querySelector(".step-ms").textContent = formatMs(ms);
    if (summary) {
      const s = document.createElement("div");
      s.className = "step-summary";
      s.textContent = summary;
      el.appendChild(s);
    }
    if (detail) {
      const d = document.createElement("details");
      d.innerHTML = `<summary>raw</summary><pre>${escapeHtml(JSON.stringify(detail, null, 2))}</pre>`;
      el.appendChild(d);
    }
    scrollFeed();
  }

  App.on("turn:start", ({ text }) => {
    if (feedEl.querySelector(".empty")) feedEl.innerHTML = "";
    turnEl = document.createElement("div");
    turnEl.className = "turn";
    turnEl.innerHTML = `<div class="turn-head">› <b>“${escapeHtml(text)}”</b></div>`;
    feedEl.appendChild(turnEl);
    liveTag.textContent = "working";
    liveTag.classList.add("on");
    scrollFeed();
  });

  App.on("agent:event", (evt) => {
    if (!turnEl) return;
    switch (evt.type) {
      case "llm_start":
        startStep("llm", evt.hop === 0 ? "LLM reading the message" : `LLM hop ${evt.hop + 1}: reading tool results`);
        break;
      case "llm_end": {
        const model = String(evt.model || "").split("/").pop();
        finishStep({ label: evt.hop === 0 ? `LLM decided · ${model}` : `LLM hop ${evt.hop + 1} · ${model}`, ms: evt.ms });
        break;
      }
      case "tool_start": {
        const meta = toolMeta(evt.tool);
        const el = startStep("tool", `${meta.icon} ${meta.running}…`);
        el.dataset.args = JSON.stringify(evt.args || {});
        break;
      }
      case "tool_end": {
        const meta = toolMeta(evt.tool);
        const args = runningStep ? JSON.parse(runningStep.dataset.args || "{}") : {};
        finishStep({
          label: `${meta.icon} ${meta.done}`,
          ms: evt.ms,
          ok: evt.ok,
          summary: toolSummary(evt.tool, evt.result),
          detail: { tool: evt.tool, args, result: evt.result },
        });
        break;
      }
      case "reply":
      case "error": {
        finishStep({ ok: false });
        const el = document.createElement("div");
        el.className = `step reply-step ${evt.type === "reply" ? "ok" : "fail"}`;
        el.innerHTML = `<span class="node"></span><div class="step-line"><span class="step-label">${
          evt.type === "reply" ? "💬 Replied to the household" : `⚠️ Turn ended: ${escapeHtml(evt.kind || "error")}`
        }</span></div>`;
        turnEl.appendChild(el);
        scrollFeed();
        break;
      }
    }
  });

  App.on("turn:end", () => {
    finishStep({ ok: false });
    liveTag.textContent = "idle";
    liveTag.classList.remove("on");
    turnEl = null;
    refreshPantry();
    refreshStatus();
  });

  App.on("reset", () => {
    finishStep({ ok: false });
    turnEl = null;
    emptyFeed();
    refreshPantry();
    refreshStatus();
  });

  // ------------------------------------------------------------ small screens

  document.getElementById("brain-toggle").addEventListener("click", () => brainEl.classList.add("open"));
  document.getElementById("brain-close").addEventListener("click", () => brainEl.classList.remove("open"));

  emptyFeed();
  refreshStatus();
  refreshPantry();
})();
