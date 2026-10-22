""" Flasher Version 105.1 (Gene): the quick smoke check for text and layout changes (tools/flasher_tests.py --smoke runs it
with test_v48, test_v50, test_v80 and test_v85): the page loads clean, the version list and its files, the gallery, the
footer and the cache tag. The full suite stays the release check """
import functools, http.server, json, os, re, sys, threading
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8830), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:8830/index.html"
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()

html = open(os.path.join(site, "index.html"), encoding="utf-8").read()
versions = json.load(open(os.path.join(site, "versions.json")))
footer = re.search(r"Flasher Version (\d+(?:\.\d+)?)", html)
tags = re.findall(r"\?v=([\w.-]+)", html)
stable = re.search(r"Version (\d+(?:\.\d+)?)", versions[0]["label"]).group(1)
check("footer names a Flasher Version", footer is not None)
check("one cache tag on style.css, app.js and tour.js", len(tags) == 3 and len(set(tags)) == 1, str(tags))
check("cache tag is <flasher>-fw<firmware>", bool(footer) and bool(tags) and tags[0] == "%s-fw%s" % (footer.group(1), stable), "%s vs %s-fw%s" % (tags[:1], footer and footer.group(1), stable))
for entry in versions:
    path = os.path.join(site, entry["manifest"])
    check("versions.json " + entry["version"] + ": manifest there", os.path.exists(path), entry["manifest"])
    if os.path.exists(path):
        manifest = json.load(open(path))
        parts = [part["path"] for build in manifest.get("builds", []) for part in build.get("parts", [])]
        check("versions.json " + entry["version"] + ": every image there", bool(parts) and all(os.path.exists(os.path.join(site, os.path.dirname(entry["manifest"]), p)) for p in parts), str(parts))
shots = json.load(open(os.path.join(site, "shots", "index.json")))
tour = open(os.path.join(site, "tour.js"), encoding="utf-8").read()
keys = [shot["key"] for shot in shots]
check("every slide has its picture", all(os.path.exists(os.path.join(site, "shots", key + ".jpg")) for key in keys), str(keys))
check("every slide has its tour text", all(re.search(r"^\s*%s: \[" % re.escape(key), tour, re.M) for key in keys), str(keys))
check("ten slides (two rows of five)", len(keys) == 10, str(len(keys)))

with sync_playwright() as p:
    b = p.chromium.launch()
    for width, height in ((1366, 768), (393, 852)):
        tag = str(width)
        pg = b.new_page(viewport={"width": width, "height": height})
        errors, failed = [], []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        # (the outside requests aborted below log "Failed to load resource" with their own URL: not the page's error)
        pg.on("console", lambda m: errors.append(m.text) if (m.type == "error") and not ((m.text.startswith("Failed to load resource"))
              and not (m.location.get("url", "").startswith("http://127.0.0.1:8830"))) else None)
        pg.on("requestfailed", lambda r: failed.append(r.url) if r.url.startswith("http://127.0.0.1:8830") else None)
        # nothing leaves the box (telemetry and the like)
        pg.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda route: route.abort())
        pg.goto(URL); pg.wait_for_timeout(800)
        check(tag + ": footer shows Flasher Version " + (footer.group(1) if footer else "?"), bool(footer) and ("Flasher Version " + footer.group(1)) in pg.inner_text(".flasher-version"))
        check(tag + ": the version line names Version " + stable, ("Version " + stable) in pg.text_content("#version"), pg.text_content("#version").strip())
        pg.locator("#tour").scroll_into_view_if_needed(); pg.wait_for_timeout(800)
        titles = pg.locator(".tour-thumb span").all_inner_texts()
        check(tag + ": gallery thumbs in index.json order", titles == [shot["title"] for shot in shots], str(titles))
        loaded = pg.evaluate("Promise.all([...document.querySelectorAll('.tour-thumb img')].map(i => i.complete ? i : new Promise(r => { i.onload = i.onerror = () => r(i); }))).then(a => a.map(i => i.naturalWidth > 0))")
        check(tag + ": every thumb picture loads", bool(loaded) and all(loaded), str(loaded))
        boxes = pg.evaluate("[...document.querySelectorAll('.tour-thumb')].map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.top + scrollY), Math.round(r.height)]; })")
        rows = sorted(set(top for top, _ in boxes))
        if (width >= 1000):
            check(tag + ": two rows of five", len(rows) == 2 and [top for top, _ in boxes].count(rows[0]) == 5, str(rows))
        check(tag + ": thumbs one height (no title wraps)", len(set(h for _, h in boxes)) == 1, str(sorted(set(h for _, h in boxes))))
        check(tag + ": no sideways scrolling", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        pg.click(".tour-thumb >> nth=0"); pg.wait_for_timeout(500)
        check(tag + ": the first slide opens", pg.is_visible("#tour-modal") and pg.inner_text("#tour-modal-title").startswith(shots[0]["title"] + ": "), pg.inner_text("#tour-modal-title"))
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        check(tag + ": no page errors", not errors, str(errors[:3]))
        check(tag + ": no failed requests", not failed, str(failed[:3]))
        pg.close()
    b.close()
print("FAILURES:", fails); sys.exit(1 if fails else 0)
