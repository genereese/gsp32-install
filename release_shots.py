""" Version 46: regenerates the "What You Get" screenshots in shots/ from the DEV board (never Gene's board) on each release.
Usage: release_shots.py [http://192.168.2.101]   (needs playwright: /workspace/pw-venv/bin/python release_shots.py)
Pages that answer 404 (an app switched off on the dev board) are skipped and left out of shots/index.json
Version 106 (Gene): the current web UI: the Experiment menu (Sandbox, Examples) and the editor with Split on
Flasher Version 104 (Gene): the AI Helper first (its panel open on the start page with a short exchange), no Settings slide.
That exchange is MOCKED in this screenshot browser only: a fake key in its localStorage, the provider's fetch answered
here (never sent; every provider host is also blocked), nothing applied (no snapshot on the board). No key on the board
Flasher Version 105 (Gene): the fast path. --sim shoots from a box-local board (tools/boardsim.py: the shipped GSP32
commit on the simulator, shaped like the dev board), with no board, tunnel or cleanup; --only shoots just the named slides
(the others stay as they are). The dev board (the default, or its URL) stays the way for releases.
Usage: release_shots.py [http://192.168.2.101 | --sim [--gsp32 DIR] [--ref REF]] [--only ai,home,...] """
import argparse, json, os, sys, time, urllib.request
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))
import boardsim

ap = argparse.ArgumentParser()
ap.add_argument("board", nargs="?", default="http://192.168.2.101")
ap.add_argument("--sim", action="store_true", help="a box-local board (tools/boardsim.py), not the dev board")
ap.add_argument("--gsp32", default=boardsim.GSP32, help="with --sim: the GSP32 git checkout")
ap.add_argument("--ref", help="with --sim: the GSP32 commit (default: the one versions.json ships)")
ap.add_argument("--port", type=int, default=8890, help="with --sim: its port")
ap.add_argument("--only", default="", help="comma-separated slide keys to shoot (the rest are kept)")
ap.add_argument("--out", default=os.path.join(HERE, "shots"), help="where the pictures go (default shots/)")
ARGS = ap.parse_args()
BOARD = ARGS.board.rstrip("/")
assert ("192.168.2.100" not in BOARD) and ("192.168.2.228" not in BOARD), "never Gene's board"
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

def shootAI(context):
    """ The AI Helper panel on the start page, with the mocked exchange (nothing is applied) """
    page = context.new_page()
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
        # read whole: a request cut off midway is logged on the board's console (and shows in the Web Console slide)
        response = urllib.request.urlopen(BOARD + path, timeout=15)
        response.read()
        return response.status == 200
    except Exception:
        return False

WAIT_MS = {"home": 25000, "examples": 25000, "editor": 6000}
SIM_GRAPH_WAIT_S = 62

def shoot(only):
    """ Shoots the slides in only (all when empty) into ARGS.out; returns the keys that are skipped (404) """
    os.makedirs(ARGS.out, exist_ok=True)
    skipped = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
        if (ARGS.sim):
            boardsim.shapeLikeDevBoard(context, BOARD)
        page = context.new_page()
        page.goto(BOARD + "/style.css")
        page.evaluate("localStorage.setItem('editorSplit', '1'); localStorage.setItem('editorSplitShare', '0.5')")
        # The live graphs need their time: on the box-local board they fill in their own tabs while the rest is shot
        #  (the dev board gets one page at a time, as before)
        waiting = []
        # On the box-local board the graph pages open first, in their own tabs, and get a minute (the dev board has
        #  hours of points; a fresh simulator needs that long to fill the graphs' width)
        order = [shot for shot in SHOTS if (ARGS.sim) and (WAIT_MS.get(shot[0], 0) > 10000)]
        order += [shot for shot in SHOTS if shot not in order]
        for key, path, title in order:
            if (only) and (key not in only):
                continue
            target = os.path.join(ARGS.out, key + ".jpg")
            if (key == "ai"):
                shot = shootAI(context)
                shot.screenshot(path=target, type="jpeg", quality=72); shot.close()
                print("shot AI Helper (mocked exchange)", flush=True)
                continue
            if not (answers(path)):
                print("skipped", path); skipped.append(key)
                continue
            if (key == "editor"):
                # Split shows the start page next to main.py (not whichever page came before)
                page.evaluate("sessionStorage.setItem('splitPage:/main.py', '/')")
            tab = context.new_page() if (ARGS.sim and WAIT_MS.get(key, 0) > 10000) else page
            tab.goto(BOARD + path, wait_until="load", timeout=30000)
            if (tab is not page):
                waiting.append((time.time() + SIM_GRAPH_WAIT_S, tab, target, path))
                continue
            tab.wait_for_timeout(WAIT_MS.get(key, 2500))
            tab.screenshot(path=target, type="jpeg", quality=72)
            print("shot", path, flush=True)
        for due, tab, target, path in waiting:
            tab.wait_for_timeout(max(0, int((due - time.time()) * 1000)))
            tab.screenshot(path=target, type="jpeg", quality=72)
            print("shot", path, flush=True)
        browser.close()
    return skipped

def main():
    global BOARD
    only = [key for key in ARGS.only.split(",") if key]
    unknown = [key for key in only if key not in [shot[0] for shot in SHOTS]]
    assert not (unknown), "no such slide: " + ", ".join(unknown)
    started = time.time()
    sim = None
    if (ARGS.sim):
        sim = boardsim.BoardSim(ARGS.port, ARGS.gsp32, ARGS.ref).start()
        BOARD = sim.url
        print("box-local board: GSP32 %s on %s" % (sim.ref, BOARD), flush=True)
    try:
        skipped = shoot(only)
    finally:
        if (sim):
            sim.stop()
    # index.json: every slide in SHOTS order whose picture is there (a slide shot from a board without its app drops out)
    if (os.path.abspath(ARGS.out) == os.path.abspath(os.path.join(HERE, "shots"))):
        done = [{"key": key, "title": title} for key, _, title in SHOTS
                if (key not in skipped) and os.path.exists(os.path.join(ARGS.out, key + ".jpg"))]
        with open(os.path.join(HERE, "shots", "index.json"), "w") as file:
            json.dump(done, file, indent=1)
    print("done in %.0f s" % (time.time() - started))

main()
