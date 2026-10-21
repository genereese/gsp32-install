""" Version 46: regenerates the "What You Get" screenshots in shots/ from the DEV board (never Gene's board) on each release.
Usage: release_shots.py [http://192.168.2.101]   (needs playwright: /workspace/pw-venv/bin/python release_shots.py)
Pages that answer 404 (an app switched off on the dev board) are skipped and left out of shots/index.json
Version 106 (Gene): the current web UI: the Experiment menu (Sandbox, Examples) and the editor with Split on
Flasher Version 104 (Gene): the AI Helper first (its panel open on the start page with a short exchange), no Settings slide.
That exchange is MOCKED in this screenshot browser only: a fake key in its localStorage, the provider's fetch answered
here (never sent; every provider host is also blocked), nothing applied (no snapshot on the board). No key on the board """
import json, os, sys, urllib.request
from playwright.sync_api import sync_playwright

BOARD = (sys.argv[1] if len(sys.argv) > 1 else "http://192.168.2.101").rstrip("/")
assert ("192.168.2.100" not in BOARD) and ("192.168.2.228" not in BOARD), "never Gene's board"
HERE = os.path.dirname(os.path.abspath(__file__))
# key, page, title; the editor opens with Split on (the live page next to the code)
SHOTS = [("ai", "/", "AI Helper"), ("home", "/", "Home Page"), ("files", "/board", "File Manager"), ("editor", "/edit?path=/main.py", "Code Editor"),
         ("sandbox", "/sandbox", "Sandbox"), ("examples", "/examples", "Examples"), ("pins", "/app/pins", "Pin Panel"),
         ("console", "/console", "Web Console"), ("libraries", "/app/libraries", "Libraries"), ("backup", "/app/backup", "Backup")]

FAKE_KEY = "xai-screenshot-not-a-real-key"
ASK = "Make the LED blink on its own every 250 ms"
PROVIDERS = ("api.x.ai", "generativelanguage.googleapis.com", "api.openai.com", "api.anthropic.com")
# The page's fetch to the provider answered in the browser, streamed like the real thing (OpenAI-style deltas, as xAI sends)
MOCK = """(() => { try { localStorage.setItem('gsp32-ai-key:xai', %s); } catch (e) {}
  const real = window.fetch;
  window.fetch = function (url, opts) {
    if (!/^https:\\/\\/(api\\.x\\.ai|generativelanguage|api\\.openai|api\\.anthropic)/.test(String(url))) return real.apply(this, arguments);
    const plan = window.mockPlan || [], enc = new TextEncoder();
    const stream = new ReadableStream({start(c) { let i = 0; (function next() {
      if (i >= plan.length) { c.enqueue(enc.encode('data: [DONE]\\n\\n')); c.close(); return; }
      const chunk = plan[i++]; setTimeout(() => { c.enqueue(enc.encode('data: ' + JSON.stringify(chunk) + '\\n\\n')); next(); }, 40); })(); }});
    return Promise.resolve(new Response(stream, {status: 200, headers: {'Content-Type': 'text/event-stream'}}));
  }; })();"""

def aiReply(board_main):
    """ What the AI Helper would propose for ASK: the start blink on and 250 ms, the rest of main.py as it is """
    edited = board_main.replace("BLINK_MS = 500", "BLINK_MS = 250", 1).replace("blink = False", "blink = True", 1)
    assert edited != board_main, "the board's main.py isn't the factory one"
    text = ("Blinking now starts by itself at 250 ms: BLINK_MS is 250 and blink starts True. The Blink button and the "
            "Blink Speed slider on Examples still work.\n\n```file:/main.py\n" + edited + "```\n")
    return [{"choices": [{"delta": {"content": text[i:i + 40]}}]} for i in range(0, len(text), 40)]

def shootAI(browser):
    """ The AI Helper panel on the start page, with the mocked exchange (nothing is applied) """
    page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    for host in PROVIDERS:
        page.route("https://%s/**" % host, lambda route: route.abort())
    page.add_init_script(MOCK % json.dumps(FAKE_KEY))
    board_main = urllib.request.urlopen(BOARD + "/api/download?path=/main.py", timeout=15).read().decode()
    page.goto(BOARD + "/", wait_until="load", timeout=30000)
    page.click("#helper-button"); page.wait_for_selector("#ai-input", timeout=15000); page.wait_for_timeout(800)
    page.evaluate("p => window.mockPlan = p", aiReply(board_main))
    page.fill("#ai-input", ASK); page.keyboard.press("Enter")
    page.wait_for_selector("#ai-panel .ai-apply", timeout=30000); page.wait_for_timeout(2500)
    # The exchange whole, Apply buttons included: the panel's static intro note left out of the shot
    page.evaluate("() => { const note = document.querySelector('#ai-panel .ai-intro'); if (note) note.style.display = 'none'; }")
    page.fill("#ai-input", ""); page.wait_for_timeout(400)
    return page

def answers(path):
    try:
        return urllib.request.urlopen(BOARD + path, timeout=15).status == 200
    except Exception:
        return False

os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
done = []
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    page.goto(BOARD + "/style.css")
    page.evaluate("localStorage.setItem('editorSplit', '1'); localStorage.setItem('editorSplitShare', '0.5')")
    for key, path, title in SHOTS:
        if (key == "ai"):
            shot = shootAI(browser)
            shot.screenshot(path=os.path.join(HERE, "shots", key + ".jpg"), type="jpeg", quality=72)
            shot.close()
            done.append({"key": key, "title": title})
            print("shot AI Helper (mocked exchange)")
            continue
        if not answers(path):
            print("skipped", path)
            continue
        if (key == "editor"):
            # Split shows the start page next to main.py (not whichever page came before)
            page.evaluate("sessionStorage.setItem('splitPage:/main.py', '/')")
        page.goto(BOARD + path, wait_until="load", timeout=30000)
        page.wait_for_timeout(25000 if key in ("home", "examples") else 6000 if key == "editor" else 2500)
        page.screenshot(path=os.path.join(HERE, "shots", key + ".jpg"), type="jpeg", quality=72)
        done.append({"key": key, "title": title})
        print("shot", path)
    browser.close()
with open(os.path.join(HERE, "shots", "index.json"), "w") as file:
    json.dump(done, file, indent=1)
