// GSP32 flasher board telemetry. Stores no IP, MAC or user agent.
const ORIGIN = "https://genereese.github.io";

const cors = { "Access-Control-Allow-Origin": ORIGIN, "Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400", "Vary": "Origin" };
const json = (o, s = 200, h = {}) => new Response(JSON.stringify(o), { status: s, headers: { "Content-Type": "application/json", ...h } });

const str = (v, n) => typeof v === "string" ? v.replace(/[^\w .:+\-()\/]/g, "").trim().slice(0, n) || null : null;
const int = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi ? v : null;
const KEYS = new Set(["chip", "revision", "cores", "flash_mb", "psram", "crystal_mhz", "usb_bridge", "compatible", "flasher_version", "browser"]);
const BROWSERS = new Set(["chrome", "edge", "opera", "brave", "other"]);

function clean(b) {
  if (!b || typeof b !== "object" || Array.isArray(b)) return null;
  for (const k of Object.keys(b)) if (!KEYS.has(k)) return null;
  const chip = str(b.chip, 32);
  if (!chip || typeof b.compatible !== "boolean") return null;
  const br = typeof b.browser === "string" ? b.browser.toLowerCase() : null;
  return {
    chip, revision: str(b.revision, 16), cores: int(b.cores, 1, 8), flash_mb: int(b.flash_mb, 0, 128),
    psram: str(b.psram, 24), crystal_mhz: int(b.crystal_mhz, 1, 100), usb_bridge: str(b.usb_bridge, 64),
    compatible: b.compatible ? 1 : 0, flasher_version: str(b.flasher_version, 16),
    browser: br && BROWSERS.has(br) ? br : (br ? "other" : null),
  };
}

// Rate limits (V84): per client per hour and per endpoint, plus a burst limit. The client is a SHA-256 of its IP with
// a salt (secret RL_SALT, else a fixed one) and the UTC day, so a key changes every day and is never written. The
// hourly counts live only in this isolate's memory and drop when the hour ends; the burst limit is Cloudflare's
// rate-limit binding (RL, 10 per minute) when it is bound. Nothing about the client is stored in D1.
const HOURLY = { log: 30, visit: 30, install: 10 };
const counts = new Map();
let countsHour = -1;
async function clientKey(req, env) {
  const ip = req.headers.get("cf-connecting-ip") || "";
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode((env.RL_SALT || "gsp32-rl") + "|" + Math.floor(Date.now() / 86_400_000) + "|" + ip));
  return btoa(String.fromCharCode(...new Uint8Array(d).slice(0, 12)));
}
async function limited(req, env, kind) {
  const key = await clientKey(req, env);
  if (env.RL) {
    try { const { success } = await env.RL.limit({ key }); if (!success) return true; } catch { /* binding unavailable */ }
  }
  const hour = Math.floor(Date.now() / 3_600_000);
  if (env.LIMITER) {
    // One Durable Object per hashed client: its counts are in memory only (no storage calls) and every request from
    // that client reaches the same one, wherever it lands
    try {
      const stub = env.LIMITER.get(env.LIMITER.idFromName(key));
      const r = await stub.fetch("https://limiter/hit?kind=" + kind + "&hour=" + hour);
      const { n } = await r.json();
      return n > HOURLY[kind];
    } catch { /* fall back to this isolate's memory */ }
  }
  if (hour !== countsHour) { counts.clear(); countsHour = hour; }
  const k = kind + ":" + key, n = (counts.get(k) || 0) + 1;
  counts.set(k, n);
  return n > HOURLY[kind];
}
// Hourly counts for one hashed client, in memory only (never written to storage); gone when the hour changes or the
// object is evicted
export class Limiter {
  constructor() { this.hour = -1; this.counts = {}; }
  async fetch(req) {
    const u = new URL(req.url), hour = Number(u.searchParams.get("hour")), kind = u.searchParams.get("kind") || "";
    if (hour !== this.hour) { this.hour = hour; this.counts = {}; }
    this.counts[kind] = (this.counts[kind] || 0) + 1;
    return new Response(JSON.stringify({ n: this.counts[kind] }), { headers: { "Content-Type": "application/json" } });
  }
}
const tooMany = () => json({ error: "rate" }, 429, { ...cors, "Retry-After": String(3600 - Math.floor(Date.now() / 1000) % 3600) });

function eq(a, b) { if (a.length !== b.length) return false; let r = 0; for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i); return r === 0; }

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/log") {
      if (req.headers.get("Origin") !== ORIGIN) return json({ error: "origin" }, 403);
      if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
      if (req.method !== "POST") return json({ error: "method" }, 405, cors);
      if (await limited(req, env, "log")) return tooMany();
      const text = await req.text();
      if (text.length > 1024) return json({ error: "size" }, 413, cors);
      let r; try { r = clean(JSON.parse(text)); } catch { r = null; }
      if (!r) return json({ error: "invalid" }, 400, cors);
      const c = req.cf?.country; const country = typeof c === "string" && /^[A-Z0-9]{2}$/.test(c) ? c : null;
      await env.DB.prepare("INSERT INTO boards (ts,chip,revision,cores,flash_mb,psram,crystal_mhz,usb_bridge,compatible,flasher_version,browser,country) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)")
        .bind(Date.now(), r.chip, r.revision, r.cores, r.flash_mb, r.psram, r.crystal_mhz, r.usb_bridge, r.compatible, r.flasher_version, r.browser, country).run();
      return json({ ok: true }, 200, cors);
    }
    if (url.pathname === "/visit") {
      if (req.headers.get("Origin") !== ORIGIN) return json({ error: "origin" }, 403);
      if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
      if (req.method !== "POST") return json({ error: "method" }, 405, cors);
      if (await limited(req, env, "visit")) return tooMany();
      const text = await req.text();
      if (text.length > 256) return json({ error: "size" }, 413, cors);
      let path = "/";
      if (text) {
        let b; try { b = JSON.parse(text); } catch { return json({ error: "invalid" }, 400, cors); }
        if (!b || typeof b !== "object" || Array.isArray(b) || Object.keys(b).some(k => k !== "path")) return json({ error: "invalid" }, 400, cors);
        if (b.path !== undefined) {
          if (typeof b.path !== "string") return json({ error: "invalid" }, 400, cors);
          path = b.path.replace(/[^\w.\/-]/g, "").slice(0, 64) || "/";
          if (!path.startsWith("/")) path = "/" + path;
        }
      }
      const hour = Math.floor(Date.now() / 3_600_000);
      await env.DB.prepare("INSERT INTO visits (hour,path,n) VALUES (?,?,1) ON CONFLICT(hour,path) DO UPDATE SET n=n+1").bind(hour, path).run();
      return json({ ok: true }, 200, cors);
    }
    if (url.pathname === "/install") {
      if (req.headers.get("Origin") !== ORIGIN) return json({ error: "origin" }, 403);
      if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
      if (req.method !== "POST") return json({ error: "method" }, 405, cors);
      if (await limited(req, env, "install")) return tooMany();
      const text = await req.text();
      if (text.length > 64 || (text && text.trim() !== "{}")) return json({ error: "invalid" }, 400, cors);
      const hour = Math.floor(Date.now() / 3_600_000);
      await env.DB.prepare("INSERT INTO installs (hour,n) VALUES (?,1) ON CONFLICT(hour) DO UPDATE SET n=n+1").bind(hour).run();
      return json({ ok: true }, 200, cors);
    }
    if (url.pathname === "/visits" && req.method === "GET") {
      const auth = req.headers.get("Authorization") || "";
      if (!env.READ_KEY || !eq(auth, "Bearer " + env.READ_KEY)) return json({ error: "unauthorized" }, 401);
      const hours = Math.min(Math.max(parseInt(url.searchParams.get("hours") || "24", 10) || 24, 1), 24 * 90);
      const now = Math.floor(Date.now() / 3_600_000), from = now - hours + 1;
      const [v, bd, ins, paths] = await Promise.all([
        env.DB.prepare("SELECT hour, SUM(n) n FROM visits WHERE hour >= ? GROUP BY hour").bind(from).all(),
        env.DB.prepare("SELECT ts / 3600000 hour, COUNT(*) n FROM boards WHERE ts >= ? GROUP BY 1").bind(from * 3_600_000).all(),
        env.DB.prepare("SELECT hour, n FROM installs WHERE hour >= ?").bind(from).all(),
        env.DB.prepare("SELECT path, SUM(n) visits FROM visits WHERE hour >= ? GROUP BY 1 ORDER BY 2 DESC LIMIT 20").bind(from).all(),
      ]);
      const map = new Map();
      for (let h = from; h <= now; h++) map.set(h, { hour: new Date(h * 3_600_000).toISOString(), visits: 0, boards: 0, installs: 0 });
      for (const [res, k] of [[v, "visits"], [bd, "boards"], [ins, "installs"]]) for (const r of res.results) if (map.has(r.hour)) map.get(r.hour)[k] = r.n;
      const hourly = [...map.values()];
      const sum = k => hourly.reduce((a, r) => a + r[k], 0);
      const total = { visits: sum("visits"), boards: sum("boards"), installs: sum("installs") };
      total.install_rate_pct = total.visits ? Math.round(1000 * total.installs / total.visits) / 10 : null;
      return json({ hours, total, hourly, paths: paths.results });
    }
    if (url.pathname === "/summary" && req.method === "GET") {
      const auth = req.headers.get("Authorization") || "";
      if (!env.READ_KEY || !eq(auth, "Bearer " + env.READ_KEY)) return json({ error: "unauthorized" }, 401);
      const q = s => env.DB.prepare(s).all().then(x => x.results);
      const [total, boards, bridges, countries] = await Promise.all([
        q("SELECT COUNT(*) n, SUM(compatible) compatible FROM boards"),
        q("SELECT chip, flash_mb, psram, compatible, COUNT(*) n FROM boards GROUP BY 1,2,3,4 ORDER BY n DESC"),
        q("SELECT usb_bridge, COUNT(*) n FROM boards GROUP BY 1 ORDER BY n DESC LIMIT 20"),
        q("SELECT country, COUNT(*) n FROM boards GROUP BY 1 ORDER BY n DESC LIMIT 30"),
      ]);
      return json({ total: total[0], boards, bridges, countries });
    }
    return json({ error: "not found" }, 404);
  },
};
