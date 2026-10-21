""" Flasher Version 105 (Gene): after a push, waits until GitHub Pages serves the pushed files, then one headless look.
1. Every site file changed since REF (default: origin/main before the push is unknown here, so HEAD~1) is fetched from
   Pages with a fresh query string (past the CDN cache) until its bytes match the commit; deleted ones until they 404.
2. One page load: no page errors, no console errors, no failed requests (telemetry aside), every thumb loads, the
   footer and cache tag match index.html; a screenshot of the gallery goes to --shot.
Usage: python tools/live_check.py [--since REF] [--timeout 600] [--shot /tmp/live-tour.png] """
import argparse, os, re, subprocess, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://genereese.github.io/gsp32-install/"
# Repo files Pages serves that the page uses (tests, tools and notes are not checked)
SKIP = re.compile(r"^(tests/|tools/|firmware/)|\.md$|^release_shots\.py$|^build_image\.py$")

def git(*args):
    return subprocess.run(["git", "-C", HERE] + list(args), capture_output=True, check=True).stdout

def fetch(path):
    url = SITE + path + "?live=%d" % (time.time() * 1000)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b""
    except Exception:
        return None, b""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="HEAD~1")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--shot", default="/tmp/live-flasher-tour.png")
    a = ap.parse_args()
    started = time.time()
    head = git("rev-parse", "--short", "HEAD").decode().strip()
    lines = git("diff", "--name-status", "--no-renames", a.since, "HEAD").decode().splitlines()
    files = {}
    for line in lines:
        status, path = line.split("\t", 1)
        if not (SKIP.search(path)):
            files[path] = None if status == "D" else git("show", "HEAD:" + path)
    files.setdefault("index.html", git("show", "HEAD:index.html"))
    print("%s: waiting for %d file(s) on Pages: %s" % (head, len(files), ", ".join(sorted(files))), flush=True)
    waiting = dict(files)
    while (waiting):
        for path, body in list(waiting.items()):
            status, live = fetch(path)
            if ((body is None) and (status == 404)) or ((body is not None) and (status == 200) and (live == body)):
                del waiting[path]
        if not (waiting):
            break
        if (time.time() - started > a.timeout):
            sys.exit("live_check: still not live after %d s: %s" % (a.timeout, ", ".join(sorted(waiting))))
        time.sleep(5)
    print("all live after %.0f s" % (time.time() - started), flush=True)

    from playwright.sync_api import sync_playwright
    html = files["index.html"].decode("utf-8")
    footer = re.search(r"Flasher Version (\d+(?:\.\d+)?)", html).group(1)
    tag = re.search(r"\?v=([\w.-]+)", html).group(1)
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors, failed = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed.append(r.url) if ("telemetry" not in r.url) else None)
        page.goto(SITE + "?nc=%d" % time.time(), wait_until="load"); page.wait_for_timeout(2500)
        live_html = page.content()
        if (live_html.count("?v=" + tag) != 3):
            problems.append("cache tag %s on %d of 3 files" % (tag, live_html.count("?v=" + tag)))
        if ("Flasher Version " + footer) not in page.inner_text(".flasher-version"):
            problems.append("footer: " + page.inner_text(".flasher-version"))
        page.locator("#tour").scroll_into_view_if_needed(); page.wait_for_timeout(1500)
        thumbs = page.locator(".tour-thumb span").all_inner_texts()
        loaded = page.evaluate("[...document.querySelectorAll('.tour-thumb img')].map(i => i.complete && i.naturalWidth > 0)")
        if not (loaded) or not all(loaded):
            problems.append("thumbs not loaded: %s" % loaded)
        page.locator("#tour").screenshot(path=a.shot)
        browser.close()
    problems += ["page error: " + e for e in errors] + ["failed request: " + f for f in failed]
    print("footer Flasher Version %s, cache tag %s, %d slides: %s" % (footer, tag, len(thumbs), ", ".join(thumbs)))
    print("gallery screenshot: " + a.shot)
    if (problems):
        print("PROBLEMS:\n  " + "\n  ".join(problems))
        sys.exit(1)
    print("live check ok in %.0f s" % (time.time() - started))

if __name__ == "__main__":
    main()
