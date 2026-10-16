-- Hourly page-visit counts only: UTC hour bucket (epoch hours) + page path. No IP, UA or MAC.
CREATE TABLE IF NOT EXISTS visits (
  hour INTEGER NOT NULL,
  path TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (hour, path)
);
