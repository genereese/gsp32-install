""" GSP32-C Beta V124 (Gene, 2026-10-26): V124 is its own Release pick in the GSP32-C group, first, with V123, V122, V121,
V120, V119, V118 and V117 kept as they were. It shows its name and no GSP32-C note (removed in Flasher 115.20) and
installs manifest-gspc-v124.json from firmware/gspc-v124/ (its builds say improv: true); the GSP32 picks are unchanged """
import sys, http.server, threading, functools, os, json, re
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8824), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)

versions = json.load(open(os.path.join(site, "versions.json")))
gc = [e for e in versions if e.get("channel") == "gspc-beta"]
check("GSP32-C entries V124, V123, V122, V121, V120, V119, V118, V117 (V124 added, the others kept)", [re.search(r"V(\d+)", e["label"]).group(1) for e in gc] == ["128", "127", "127", "127", "126", "125", "124", "123", "122", "121", "120", "119", "118", "117"], str([e["label"] for e in gc]))
for e in gc:
    m = json.load(open(os.path.join(site, e["manifest"])))
    parts = [p["path"] for b in m["builds"] for p in b["parts"]]
    check(e["label"] + ": manifest names it", m["version"] == e["label"], m["version"])
    check(e["label"] + ": five chips' images there", len(m["builds"]) == 5 and all(os.path.exists(os.path.join(site, p)) for p in parts), str(parts))
    want_dir = "firmware/gspc-v128/" if "V128" in e["label"] else "firmware/gspc-v127.3/" if "V127.3" in e["label"] else "firmware/gspc-v127.2/" if "V127.2" in e["label"] else "firmware/gspc-v127.1/" if "V127.1" in e["label"] else "firmware/gspc-v126/" if "V126" in e["label"] else "firmware/gspc-v125/" if "V125" in e["label"] else "firmware/gspc-v124/" if "V124" in e["label"] else "firmware/gspc-v123/" if "V123" in e["label"] else "firmware/gspc-v122/" if "V122" in e["label"] else "firmware/gspc-v121/" if "V121" in e["label"] else "firmware/gspc-v120/" if "V120" in e["label"] else "firmware/gspc-v119/" if "V119" in e["label"] else "firmware/gspc-v118/" if "V118" in e["label"] else "firmware/gspc/"
    check(e["label"] + ": its own firmware folder " + want_dir, all(p.startswith(want_dir) for p in parts), str(parts))
    if "V124" in e["label"] or "V123" in e["label"] or "V122" in e["label"] or "V121" in e["label"]:
        check(e["label"] + ": every build says improv", all(b.get("improv") is True for b in m["builds"]))
    check(e["label"] + ": offsets 4096 (ESP32) and 0", all(p["offset"] == (4096 if b["chipFamily"] == "ESP32" else 0) for b in m["builds"] for p in b["parts"]))

def show(pg):
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r, _q=None: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    asked = []
    pg.on("request", lambda r: asked.append(r.url))
    pg.goto("http://127.0.0.1:8824/index.html"); pg.wait_for_timeout(600)
    opts = pg.evaluate("[...document.querySelectorAll('#gspc-group option')].map(o => [o.value, o.textContent, o.disabled, o.hidden])")
    check("GSP32-C group lists V121, V120, V119, V118, V117", [o[:2] for o in opts][6:] == [["gspc-124", "GSP32-C Beta V124"], ["gspc-123", "GSP32-C Beta V123"], ["gspc-122", "GSP32-C Beta V122"], ["gspc-121", "GSP32-C Beta V121"], ["gspc-120", "GSP32-C Beta V120"], ["gspc-119", "GSP32-C Beta V119"], ["gspc-118", "GSP32-C Beta V118"], ["gspc-117", "GSP32-C Beta V117"]], str(opts))
    check("all GSP32-C options usable", all(not o[2] and not o[3] for o in opts))
    check("GSP32-C group shown", not pg.evaluate("document.getElementById('gspc-group').hidden"))
    check("GSP32 picks unchanged: Stable default, Beta there", pg.input_value("#release-channel") == "stable"
          and pg.evaluate("[...document.querySelectorAll('#release-channel > option')].map(o => o.value).join()") == "stable,beta,previous")
    check("Flasher 115.20: no GSP32-C note element at all", pg.locator("#gspc-note").count() == 0)
    show(pg)
    for key, name in (("gspc-124", "GSP32-C Beta V124"), ("gspc-123", "GSP32-C Beta V123"), ("gspc-122", "GSP32-C Beta V122"), ("gspc-121", "GSP32-C Beta V121"), ("gspc-120", "GSP32-C Beta V120"), ("gspc-119", "GSP32-C Beta V119"), ("gspc-118", "GSP32-C Beta V118"), ("gspc-117", "GSP32-C Beta V117")):
        pg.select_option("#release-channel", key); pg.wait_for_timeout(300)
        check(key + ": Installs " + name, pg.text_content("#version").strip() == name, pg.text_content("#version"))
        check(key + ": no note under the picker, the yellow erase box mentions Backup", pg.locator("#gspc-note").count() == 0 and "Backup" in pg.text_content("label[for=erase-ok]"))
    pg.select_option("#release-channel", "stable"); pg.wait_for_timeout(300)
    check("back to Stable: still no note", pg.locator("#gspc-note").count() == 0)
    # The pick that installs: tick, start, and see which manifest the page loads
    pg.select_option("#release-channel", "gspc-124"); pg.wait_for_timeout(300)
    asked.clear()
    pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(3000)
    man = [u for u in asked if "manifest" in u]
    check("gspc-124 installs manifest-gspc-v124.json", any("manifest-gspc-v124.json" in u for u in man) and not any(("manifest-gspc-v123.json" in u or "manifest-gspc-v122.json" in u or "manifest-gspc-v121.json" in u or "manifest-gspc-v120.json" in u or "manifest-gspc-beta.json" in u or "manifest-gspc-v118.json" in u or "manifest-gspc-v119.json" in u) for u in man), str(man))
    img = [u for u in asked if u.endswith(".bin")]
    check("gspc-124 loads firmware/gspc-v124 images", bool(img) and all("/firmware/gspc-v124/" in u for u in img), str(img))
    pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
