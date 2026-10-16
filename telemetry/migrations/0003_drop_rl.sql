-- V84: rate limits no longer touch D1 (hashed IPs only in memory or the rate-limit binding)
DROP TABLE IF EXISTS rl;
