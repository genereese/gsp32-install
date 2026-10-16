CREATE TABLE IF NOT EXISTS boards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  chip TEXT, revision TEXT, cores INTEGER, flash_mb INTEGER, psram TEXT,
  crystal_mhz INTEGER, usb_bridge TEXT, compatible INTEGER NOT NULL,
  flasher_version TEXT, browser TEXT, country TEXT
);
CREATE INDEX IF NOT EXISTS boards_ts ON boards(ts);
-- Short-lived rate-limit buckets: salted, truncated SHA-256 of the IP + minute. Rows older than 2 min are deleted.
CREATE TABLE IF NOT EXISTS rl (k TEXT PRIMARY KEY, n INTEGER NOT NULL, t INTEGER NOT NULL);
-- Hourly page-visit counts only: UTC hour bucket (epoch hours) + page path. No IP, UA or MAC.
CREATE TABLE IF NOT EXISTS visits (
  hour INTEGER NOT NULL,
  path TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (hour, path)
);
