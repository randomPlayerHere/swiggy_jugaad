-- SQLite schema for swiggy_buzz. Applied via init_db(); every statement is
-- idempotent so it can run on each startup.

CREATE TABLE IF NOT EXISTS users (
    user_id           INTEGER PRIMARY KEY,  -- Telegram chat id
    household_size    INTEGER NOT NULL DEFAULT 1,
    diet              TEXT,                 -- veg / non-veg / vegan / jain
    address_confirmed INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pantry_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(user_id),
    canonical_name    TEXT NOT NULL,
    category          TEXT NOT NULL,        -- keys into config.DEFAULT_DECAY_DAYS
    last_purchased_at TEXT NOT NULL,
    purchase_qty      REAL,
    decay_lambda      REAL,                 -- personal pace multiplier m (see pantry_engine/MATH.md); NULL = 1.0
    UNIQUE (user_id, canonical_name)
);

CREATE TABLE IF NOT EXISTS corrections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(user_id),
    canonical_name TEXT NOT NULL,
    direction      TEXT NOT NULL CHECK (direction IN ('ran_out_early', 'lasted_longer')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_cache (
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    order_id   TEXT NOT NULL,
    raw_json   TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, order_id)
);

CREATE INDEX IF NOT EXISTS idx_pantry_items_user ON pantry_items(user_id);
CREATE INDEX IF NOT EXISTS idx_corrections_user_item
    ON corrections(user_id, canonical_name);
