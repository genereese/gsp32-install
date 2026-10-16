-- Completed installs: hourly count only (UTC epoch hour). No IP, UA or MAC.
CREATE TABLE IF NOT EXISTS installs (hour INTEGER PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0);
