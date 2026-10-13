""" Version 46: regenerates the "What You Get" screenshots in shots/ from the DEV board (never Gene's board) on each release.
Usage: release_shots.py [http://192.168.2.22]   (needs playwright: /workspace/review/venv/bin/python release_shots.py)
Pages that answer 404 (an app switched off on the dev board) are skipped and left out of shots/index.json """
import json, os, sys, urllib.request
from playwright.sync_api import sync_playwright

BOARD = (sys.argv[1] if len(sys.argv) > 1 else "http://192.168.2.22").rstrip("/")
assert "192.168.2.228" not in BOARD, "never Gene's board"
HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = [("home", "/", "Home and Graphs"), ("files", "/board", "File Manager"), ("editor", "/edit?path=/main.py", "Code Editor"),
         ("pins", "/app/pins", "Pin Panel"), ("console", "/console", "Web Console"), ("libraries", "/app/libraries", "Libraries"),
         ("backup", "/app/backup", "Backup"), ("settings", "/settings", "Settings")]

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
    for key, path, title in SHOTS:
        if not answers(path):
            print("skipped", path)
            continue
        page.goto(BOARD + path, wait_until="load", timeout=30000)
        page.wait_for_timeout(25000 if key == "home" else 2500)
        page.screenshot(path=os.path.join(HERE, "shots", key + ".jpg"), type="jpeg", quality=72)
        done.append({"key": key, "title": title})
        print("shot", path)
    browser.close()
with open(os.path.join(HERE, "shots", "index.json"), "w") as file:
    json.dump(done, file, indent=1)
