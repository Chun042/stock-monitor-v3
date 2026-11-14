CREATE TABLE IF NOT EXISTS devices (
  device_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  subscription_json TEXT NOT NULL,
  preferences_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devices_updated ON devices(updated_at);

CREATE TABLE IF NOT EXISTS watchlists (
  owner_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL CHECK (market IN ('TW','US')),
  display_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(owner_id, symbol, market)
);
CREATE INDEX IF NOT EXISTS idx_watchlists_symbol ON watchlists(symbol, market);

CREATE TABLE IF NOT EXISTS holdings (
  owner_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL CHECK (market IN ('TW','US')),
  quantity REAL NOT NULL CHECK (quantity > 0),
  average_cost REAL NOT NULL CHECK (average_cost >= 0),
  currency TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(owner_id, symbol, market)
);
CREATE INDEX IF NOT EXISTS idx_holdings_owner ON holdings(owner_id);
