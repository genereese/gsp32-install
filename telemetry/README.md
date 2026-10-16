# GSP32 flasher telemetry

Cloudflare Worker + D1 that records which boards people try to flash, so firmware work can target the most common ones.

- Worker: `gsp32-telemetry` at https://gsp32-telemetry.genereese.workers.dev
- D1: `gsp32-telemetry` (tables `boards`, `rl`; see `schema.sql`)
- Secrets: `READ_KEY` (bearer key for /summary), `RL_SALT`

## Privacy
Stored: chip info, compatibility, flasher version, coarse browser name, and country from `request.cf.country`.
Never stored: IP, MAC, user agent. Rate limiting uses a salted, truncated hash of the IP per minute, deleted after ~2 minutes.

## API
`POST /log` (Origin must be `https://genereese.github.io`, JSON body < 1 KB, 10/min per IP)

```json
{
  "chip": "ESP32-S3",          // required, string <= 32
  "compatible": true,          // required, boolean
  "revision": "v0.2",          // string <= 16
  "cores": 2,                  // int 1-8
  "flash_mb": 16,              // int 0-128
  "psram": "8MB",              // string <= 24
  "crystal_mhz": 40,           // int 1-100
  "usb_bridge": "303a:1001 USB JTAG/serial", // "VID:PID name", <= 64
  "flasher_version": "79",     // string <= 16
  "browser": "chrome"          // chrome|edge|opera|brave|other
}
```
Unknown keys or missing required fields -> 400; bad origin -> 403; too big -> 413; rate limited -> 429. Out-of-range numbers are stored as null; strings are stripped to `[A-Za-z0-9_ .:+-()/]` and truncated.

`GET /summary` with `Authorization: Bearer <READ_KEY>` -> totals, counts by chip/flash/psram/compatible, top USB bridges, top countries.

`POST /visit` (same Origin rule, 10/min per IP) body optional `{"path":"/gsp32-install/"}` -> increments the UTC-hour bucket for that path. Stores only hour + path + count.

`POST /install` (same Origin rule, body empty or `{}`) -> increments the completed-install count for the UTC hour. Count only.

`GET /visits?hours=N` (bearer READ_KEY required, 401 otherwise; N 1-2160, default 24) -> `{hours,total:{visits,boards,installs,install_rate_pct},hourly:[{hour,visits,boards,installs}],paths}`. boards = connect-probe rows from /log; installs = completed installs from /install; install_rate_pct = installs/visits.

## Deploy
```
export CLOUDFLARE_ACCOUNT_ID=3d102f222e99f035a8c29073fe6e6300 CLOUDFLARE_API_TOKEN=...
npx wrangler@3 d1 execute gsp32-telemetry --remote --file schema.sql
npx wrangler@3 d1 migrations apply gsp32-telemetry --remote
npx wrangler@3 deploy
```
