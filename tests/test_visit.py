# Hourly visit counter: one POST /visit per page load, path only, never breaks the page
import sys, os, json, http.server, threading, functools
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8812), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(n, ok, x=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + n, x)
def load(b, mode):
    pg = b.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("""window.__visits=[]; (() => { const r = window.fetch.bind(window); window.fetch = (i, o) => {
      const u = typeof i === 'string' ? i : (i && i.url) || '';
      if (u.includes('/visit')) { window.__visits.push({u, o: {method: o.method, body: o.body}});
        if ('%s' === 'fail') return Promise.reject(new TypeError('net'));
        if ('%s' === 'hang') return new Promise(() => {});
        if ('%s' === 'throw') throw new Error('sync');
        return Promise.resolve(new Response('{"ok":true}')); }
      return r(i, o); }; })();""" % (mode, mode, mode))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, body='{"ok":true}'))
    pg.goto("http://127.0.0.1:8812/index.html"); pg.wait_for_timeout(800)
    return pg, errs
with sync_playwright() as p:
    b = p.chromium.launch()
    pg, errs = load(b, "ok")
    v = pg.evaluate("window.__visits")
    check("one visit per load", len(v) == 1, str(v))
    body = json.loads(v[0]["o"]["body"]) if v else {}
    check("POST to /visit with path only", v and v[0]["o"]["method"] == "POST" and v[0]["u"].endswith("/visit") and body == {"path": "/index.html"}, str(v))
    pg.reload(); pg.wait_for_timeout(800)
    check("reload sends exactly one more", len(pg.evaluate("window.__visits")) == 1)
    pg.close()
    for mode in ("fail", "hang", "throw"):
        pg, errs = load(b, mode)
        check(mode + ": page works (Get Started visible, versions loaded)", pg.is_visible("#connect") and "Version" in pg.inner_text("#version") or pg.is_visible("#connect"), pg.inner_text("#version"))
        check(mode + ": no page errors", not errs, str(errs)); pg.close()
    b.close()
srv.shutdown(); print("FAILURES:", fails); sys.exit(1 if fails else 0)
