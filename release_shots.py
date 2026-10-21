""" Version 46: regenerates the "What You Get" screenshots in shots/ from the DEV board (never Gene's board) on each release.
Usage: release_shots.py [http://192.168.2.101]   (needs playwright: /workspace/pw-venv/bin/python release_shots.py)
Pages that answer 404 (an app switched off on the dev board) are skipped and left out of shots/index.json
Version 106 (Gene): the current web UI: the Experiment menu (Sandbox, Examples) and the editor with Split on """
import json, os, sys, urllib.request
from playwright.sync_api import sync_playwright

BOARD = (sys.argv[1] if len(sys.argv) > 1 else "http://192.168.2.101").rstrip("/")
assert ("192.168.2.100" not in BOARD) and ("192.168.2.228" not in BOARD), "never Gene's board"
HERE = os.path.dirname(os.path.abspath(__file__))
# key, page, title; the editor opens with Split on (the live page next to the code)
SHOTS = [("home", "/", "Home Page"), ("files", "/board", "File Manager"), ("editor", "/edit?path=/main.py", "Code Editor"),
         ("sandbox", "/sandbox", "Sandbox"), ("examples", "/examples", "Examples"), ("pins", "/app/pins", "Pin Panel"),
         ("console", "/console", "Web Console"), ("libraries", "/app/libraries", "Libraries"), ("backup", "/app/backup", "Backup"),
         ("settings", "/settings", "Settings")]

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
