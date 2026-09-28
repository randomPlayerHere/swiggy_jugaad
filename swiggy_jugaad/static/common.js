// Shared by chat.js (the phone) and brain.js (the under-the-hood panel):
// a tiny event bus between the two, formatting helpers, and how each tool
// call is described to a human.

const App = (() => {
  const listeners = {};
  return {
    on(type, fn) {
      (listeners[type] ||= []).push(fn);
    },
    emit(type, payload) {
      for (const fn of listeners[type] || []) fn(payload);
    },
    status: null, // last /api/status, set by brain.js
  };
})();

const LN20 = Math.log(20);

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

// Escape first, then allow **bold** only. The prompt asks for no markdown,
// but a stray pair of asterisks shouldn't show up raw on camera.
function renderRich(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function prettyName(canonical) {
  const s = String(canonical || "").replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const ITEM_EMOJI = {
  milk: "🥛", curd: "🥣", paneer: "🧀", cheese: "🧀", butter: "🧈", cream: "🥛",
  onion: "🧅", tomato: "🍅", potato: "🥔", garlic: "🧄", ginger: "🫚", green_chilli: "🌶️",
  coriander: "🌿", mint: "🌿", spinach: "🥬", cauliflower: "🥦", cabbage: "🥬", carrot: "🥕",
  capsicum: "🫑", brinjal: "🍆", okra: "🥒", peas: "🫛", cucumber: "🥒", lemon: "🍋",
  banana: "🍌", apple: "🍎", mushroom: "🍄", bread: "🍞", pav: "🍞", bun: "🍞", egg: "🥚",
  rice: "🍚", atta: "🌾", maida: "🌾", suji: "🌾", besan: "🌾", poha: "🍚", oats: "🥣",
  toor_dal: "🫘", moong_dal: "🫘", chana_dal: "🫘", urad_dal: "🫘", masoor_dal: "🫘", rajma: "🫘", chole: "🫘",
  oil: "🫗", ghee: "🧈", salt: "🧂", sugar: "🍬", tea: "🍵", coffee: "☕",
  biscuit: "🍪", namkeen: "🥨", chips: "🍟", chocolate: "🍫", noodles: "🍜", cornflakes: "🥣",
};
const CATEGORY_EMOJI = {
  dairy: "🥛", produce: "🥬", bread: "🍞", eggs: "🥚", rice_grains: "🌾",
  pulses: "🫘", oil: "🫗", spices: "🌶️", snacks: "🍪",
};

function itemEmoji(name, category) {
  return ITEM_EMOJI[name] || CATEGORY_EMOJI[category] || "🛒";
}

const DIET_LABEL = { vegan: "vegan", veg: "vegetarian", egg: "eggetarian", non_veg: "non-veg" };

function dietLabel(diet) {
  return DIET_LABEL[diet] || diet || "any diet";
}

function formatDays(days) {
  if (days < 1) return `${Math.max(1, Math.round(days * 24))}h`;
  if (days < 10) return `${days.toFixed(1).replace(/\.0$/, "")}d`;
  return `${Math.round(days)}d`;
}

function formatMs(ms) {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function rupees(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `₹${n % 1 === 0 ? n : n.toFixed(2)}` : "₹—";
}

function plural(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

// How each tool call reads to a human: in the phone's typing bubble while
// it runs (`running`), and in the brain panel's activity feed once done.
const TOOL_META = {
  onboard_user: {
    icon: "🏠",
    running: "Saving your household",
    done: "Saved household profile",
    summary: (r) => `${plural(r.household_size, "person", "people")} · ${dietLabel(r.diet)}`,
  },
  get_household_profile: {
    icon: "🪪",
    running: "Checking your profile",
    done: "Read household profile",
    summary: (r) => (r && r.household_size ? `${plural(r.household_size, "person", "people")} · ${dietLabel(r.diet)}` : "not onboarded yet"),
  },
  list_addresses: {
    icon: "📍",
    running: "Fetching your Swiggy addresses",
    done: "Fetched saved addresses · Swiggy MCP",
    summary: (r) => plural((r || []).length, "address", "addresses"),
  },
  sync_orders: {
    icon: "📦",
    running: "Pulling your Instamart orders",
    done: "Synced Instamart order history",
    summary: (r) =>
      `${plural(r.orders_ingested, "new order")} · ${plural(r.items_added, "pantry update")} · ${r.non_food} non-food skipped`,
  },
  get_pantry_status: {
    icon: "🧮",
    running: "Scoring your pantry",
    done: "Scored pantry with the decay model",
    summary: (r) => {
      const count = (b) => (r || []).filter((i) => i.bucket === b).length;
      return `${count("likely")} likely · ${count("maybe")} maybe · ${count("out")} out`;
    },
  },
  suggest_recipes: {
    icon: "🍳",
    running: "Ranking recipes against your pantry",
    done: "Ranked recipes by what's owned",
    summary: (r) => (r || []).map((x) => x.name).join(" · ") || "no matches",
  },
  start_gap_order: {
    icon: "🛒",
    running: "Searching Instamart & building your cart",
    done: "Searched Instamart · staged cart",
    summary: (r) => {
      const parts = [`${plural((r.kept || []).length, "item")} · ${rupees(r.total)}`];
      if ((r.dropped || []).length) parts.push(`${r.dropped.length} over cap`);
      if ((r.unresolved || []).length) parts.push(`${r.unresolved.length} not found`);
      return parts.join(" · ");
    },
  },
  confirm_gap_order: {
    icon: "✅",
    running: "Placing your order on Swiggy",
    done: "Placed COD order · Swiggy MCP",
    summary: (r) => `${r.order_id ? `#${r.order_id} · ` : ""}${rupees(r.total)} · cash on delivery`,
  },
  record_item_correction: {
    icon: "🧠",
    running: "Learning from your correction",
    done: "Tuned personal pace",
    summary: (r) => `${prettyName(r.canonical_name)} · pace ×${r.new_pace_multiplier}`,
  },
};

function toolMeta(tool) {
  return TOOL_META[tool] || { icon: "🔧", running: "Working", done: tool, summary: () => "" };
}

function toolSummary(tool, result) {
  if (result && typeof result === "object" && !Array.isArray(result) && result.error) return result.error;
  try {
    return toolMeta(tool).summary(result);
  } catch {
    return "";
  }
}
