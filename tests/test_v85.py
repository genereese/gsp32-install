""" Flasher V85 (Gene): the Release dropdown, first in the install step. Stable is the default; Beta installs the
versions.json entry with "channel": "beta", and says None Right Now (disabled) when there is none """
import sys, http.server, threading, functools, os, json
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.environ.get("V85_SHOTS", "")
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8785), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
stable = [e for e in json.load(open(os.path.join(site, "versions.json"))) if e.get("channel", "stable") == "stable"]
# Version 99: the Stable entry's number from versions.json (Version 85 until V99 became Stable)
import re
STABLE = "Version " + re.search(r"Version (\d+(?:\.\d+)?)", stable[0]["label"]).group(1)
with_beta = stable + [{"version": "beta123", "manifest": "manifest.json", "label": "Version 86 (beta123), beta", "channel": "beta"}]
def show(pg):
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)
with sync_playwright() as p:
    b = p.chromium.launch()
    for label, versions in (("no beta", stable), ("beta", with_beta)):
        pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
        pg.route("**/vendor/esptool-js-0.5.7.js", lambda r, _q=None: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
        pg.route("**/versions.json", lambda r, _req=None, v=versions: r.fulfill(body=json.dumps(v), content_type="application/json"))
        pg.goto("http://127.0.0.1:8785/index.html"); pg.wait_for_timeout(500)
        check(label + ": Stable is the default", pg.input_value("#release-channel") == "stable" and pg.text_content("#version").strip() == STABLE, pg.text_content("#version"))
        first = pg.evaluate("document.querySelector('[data-step=prep] h3').nextElementSibling.querySelector('select')?.id")
        check(label + ": dropdown first in the install step", first == "release-channel")
        disabled = pg.evaluate("document.querySelector('#release-channel option[value=beta]').disabled")
        field_hidden = pg.evaluate("document.querySelector('.release-field').hidden")
        if label == "no beta":
            check("no beta: plain Beta, disabled and hidden", disabled and pg.evaluate("document.querySelector('#release-channel option[value=beta]').hidden") and pg.text_content("#release-channel option[value=beta]").strip() == "Beta")
            # Version 106 (Gene): Stable alone: the Release dropdown is hidden, the version line stays
            check("no beta: Stable alone, the Release dropdown is hidden; Installs Version N shows", field_hidden and pg.is_visible("#version") if pg.is_visible("[data-step=prep]") else field_hidden)
        else:
            check("beta: Beta enabled, Release shown", (not disabled) and (not field_hidden))
            show(pg); pg.select_option("#release-channel", "beta"); pg.wait_for_timeout(300)
            check("beta: plain Version 86, no note", pg.text_content("#version").strip() == "Version 86" and pg.locator("#beta-note").count() == 0, pg.text_content("#version"))
            if SHOTS:
                pg.locator("#wizard").screenshot(path=SHOTS + "/flasher-release-beta.png")
            pg.select_option("#release-channel", "stable"); pg.wait_for_timeout(300)
            check("beta: back to Stable", pg.text_content("#version").strip() == STABLE)
            if SHOTS:
                pg.locator("#wizard").screenshot(path=SHOTS + "/flasher-release-stable.png")
        pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
