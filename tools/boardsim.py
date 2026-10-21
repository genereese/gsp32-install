""" Flasher Version 105 (Gene): a box-local GSP32 board for the tour screenshots, no board, tunnel or cleanup.
The real web UI (the GSP32 commit the flasher ships, from versions.json) runs on the MicroPython simulator (mpsim, the
same one the GSP32 suites use) with a fresh flash dir, so every page and API answers as on a board. A few answers are
then shaped like the dev board's (a real ESP32 with the web UI frozen into the firmware), in the screenshot browser only:
  /api/stats   heap and flash in the dev board's range (the simulator's heap is a host heap, its flash holds the
  /api/pages   web UI's own files that a real board has in its firmware), Web UI Load like a board's (a host answers
               in no time); /api/pages carries the same four values for the start page's graphs
  /api/stats   also the uptime of a board that has run for hours (the simulator has just booted)
  /api/console without the simulator's own line about Wi-Fi power saving (its WLAN stub has no PM_NONE)
And once it has booted, the modules the firmware freezes (board.py, pages.py, gsp_*.py, gspnow*.py) leave the flash dir
(they are imported by then), so Files lists main.py and sandbox.py as on a board. Restarting main.py on this board can
then fail (it imports board again): it is for screenshots and a look around, not for running programs.
Usage: python tools/boardsim.py [--port 8890] [--gsp32 DIR] [--ref REF]   (serves until Ctrl-C; release_shots.py --sim
starts and stops its own) """
import argparse, json, os, random, shutil, signal, subprocess, sys, tempfile, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = os.environ.get("CODE_PROJECTS", "/workspace/bots/code-projects")
SIM = os.path.join(os.environ.get("CODE_TOOLS", os.path.join(CODE, "tools")), "mpsim")
GSP32 = os.environ.get("GSP32_DIR", os.path.join(CODE, "bench", "wt-v106"))
# What the dev board (COM4, ESP32-D0WD-V3, GSP32 Version 106) reports: /api/stats on 2026-10-21
DEV = {"heap_total": 72000, "heap_used": 35088, "flash_total": 1507328, "flash_free": 1355776, "rssi": -71}
UPTIME_S = 9 * 3600 + 20 * 60
# The modules GSP32's firmware freezes (firmware/stage_webui.py; mpsim's run.sh --frozen leaves out the same ones)
FROZEN = {"board.py", "pages.py", "gspnow.py", "gspnow_pair.py", "gsp_ssd1306.py", "gsp_lcd.py", "gsp_tm1637.py", "gsp_bme280.py"}

def shippedRef():
    """ The GSP32 commit the flasher installs: versions.json's first (default) entry """
    with open(os.path.join(HERE, "versions.json")) as file:
        return json.load(file)[0]["version"]

class BoardSim:
    def __init__(self, port=8890, gsp32=GSP32, ref=None):
        self.port, self.gsp32, self.ref = port, gsp32, ref or shippedRef()
        self.url = "http://127.0.0.1:%d" % port
        self.tmp = tempfile.mkdtemp(prefix="gsp32-boardsim-")
        self.proc = None

    def start(self):
        project = os.path.join(self.tmp, "project")
        os.makedirs(project)
        # The committed tree only (git archive): never a local config.json, webui_auth.json or webui_ai.json
        archive = subprocess.run(["git", "-C", self.gsp32, "archive", self.ref], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", project], input=archive, check=True)
        for name in ("firmware", "tests", "notes"):
            shutil.rmtree(os.path.join(project, name), ignore_errors=True)
        for name in ("config.json", "webui_auth.json", "webui_ai.json"):
            assert not os.path.exists(os.path.join(project, name)), name + " in the GSP32 tree"
        # The firmware's build info (the status bar's "Version N"; stage_webui.py writes it into a real build). MODULES
        #  stays empty: nothing here is frozen, so the web UI keeps (and never tidies away) its file system copies
        commit = subprocess.run(["git", "-C", self.gsp32, "rev-parse", "--short", self.ref], capture_output=True, text=True).stdout.strip()
        built = subprocess.run(["git", "-C", self.gsp32, "log", "-1", "--format=%cs", self.ref], capture_output=True, text=True).stdout.strip()
        version = open(os.path.join(project, "VERSION")).read().strip() if os.path.exists(os.path.join(project, "VERSION")) else ""
        license_text = open(os.path.join(project, "LICENSE.txt"), encoding="utf-8").read() if os.path.exists(os.path.join(project, "LICENSE.txt")) else ""
        with open(os.path.join(project, "webui_frozen.py"), "w") as info:
            info.write('MODULES = ()\nCOMMIT = "%s"\nHEAP_KB = ""\nVERSION = "%s"\nBUILT = "%s"\nLICENSE = %r\n' % (commit, version, built, license_text))
        self.version = version
        env = dict(os.environ, MPSIM_DIR=os.path.join(self.tmp, "sim"), MPSIM_HEAP="2m", MPSIM_FLASH_KB="4096",
                   MPSIM_RSSI=str(DEV["rssi"]), MPSIM_IP="192.168.2.101", MPSIM_LOG_GPIO="0")
        self.log = open(os.path.join(self.tmp, "sim.log"), "w")
        self.proc = subprocess.Popen([os.path.join(SIM, "run.sh"), project, str(self.port)], env=env, stdout=self.log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(300):
            try:
                urllib.request.urlopen(self.url + "/style.css", timeout=2).read()
                break
            except Exception:
                if (self.proc.poll() is not None):
                    raise RuntimeError("the simulator stopped: " + open(self.log.name).read()[-800:])
                time.sleep(0.1)
        else:
            raise RuntimeError("the simulator didn't answer on " + self.url)
        # A fresh board asks for a password first; the dev board has none (Open Access), so the same here
        data = urllib.parse.urlencode({"no_password": "1"}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(self.url + "/set_password", data=data), timeout=10).read()
        except Exception:
            pass
        stats = json.loads(urllib.request.urlopen(self.url + "/api/stats", timeout=10).read())
        assert stats.get("main_state") == "running", stats
        flash = os.path.join(self.tmp, "sim", "flash")
        for name in FROZEN:
            if os.path.exists(os.path.join(flash, name)):
                os.remove(os.path.join(flash, name))
        return self

    def stop(self):
        if (self.proc) and (self.proc.poll() is None):
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

class Shaper:
    """ The simulator's numbers mapped into the dev board's range (they still move with the simulator's own) """

    def __init__(self):
        self.rng = random.Random(106)
        self.dev_ram = round(DEV["heap_used"] * 100 / DEV["heap_total"])
        self.dev_flash = round((DEV["flash_total"] - DEV["flash_free"]) * 100 / DEV["flash_total"])

    def load(self, value):
        busy = max(1, min(30, int(self.rng.gauss(6, 2)))) if (self.rng.random() > 0.04) else self.rng.randint(18, 28)
        return max(value or 0, busy)

    def ram(self, percent):
        # the simulator's 2 MB host heap sits near 10 %: the board's 49 %, moving a third as much
        return max(1, min(95, round(self.dev_ram + (percent - 10) / 3)))

def shapeLikeDevBoard(context, board_url):
    """ Playwright routes on a browser context: the answers above shaped like the dev board's (the board is untouched) """
    shaper = Shaper()

    def fulfillJSON(route, response, body):
        headers = dict(response.headers)
        headers.pop("content-length", None)
        route.fulfill(status=response.status, headers=headers, body=json.dumps(body), content_type="application/json")

    def stats(route):
        response = route.fetch()
        try:
            body = response.json()
        except Exception:
            return route.fulfill(response=response)
        if ("heap_total" in body):
            percent = shaper.ram(body["heap_used"] * 100 / max(1, body["heap_total"]))
            body["heap_total"] = DEV["heap_total"]
            body["heap_used"] = int(DEV["heap_total"] * percent / 100)
            body["heap_free"] = body["heap_total"] - body["heap_used"]
            body["flash_total"], body["flash_free"] = DEV["flash_total"], DEV["flash_free"]
            body["webui_busy"] = shaper.load(body.get("webui_busy"))
            # a board that has been up a while, like the dev board in its shots (not one booted a minute ago)
            body["uptime_s"] = body.get("uptime_s", 0) + UPTIME_S
        fulfillJSON(route, response, body)

    def pages(route):
        response = route.fetch()
        try:
            body = response.json()
        except Exception:
            return route.fulfill(response=response)
        values = body.get("values") if isinstance(body, dict) else None
        if isinstance(values, dict):
            for name, change in (("ram", shaper.ram), ("flash", lambda v: shaper.dev_flash), ("load", shaper.load)):
                item = values.get(name)
                if isinstance(item, dict):
                    if isinstance(item.get("v"), (int, float)):
                        item["v"] = change(item["v"])
                    if isinstance(item.get("h"), list):
                        item["h"] = [float(change(v)) for v in item["h"]]
        fulfillJSON(route, response, body)

    def console(route):
        response = route.fetch()
        text = response.text()
        text = "\n".join(line for line in text.split("\n") if not line.startswith("Wi-Fi power saving not set"))
        headers = dict(response.headers)
        headers.pop("content-length", None)
        route.fulfill(status=response.status, headers=headers, body=text)

    context.route(board_url + "/api/stats*", stats)
    context.route(board_url + "/api/pages?*", pages)
    context.route(board_url + "/api/console*", console)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8890)
    ap.add_argument("--gsp32", default=GSP32)
    ap.add_argument("--ref")
    a = ap.parse_args()
    # A plain kill (SIGTERM) stops the simulator too, not just this script
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    with BoardSim(a.port, a.gsp32, a.ref) as sim:
        print("GSP32 %s on %s (Ctrl-C stops it; the dev-board shaping is in release_shots.py's browser only)" % (sim.ref, sim.url), flush=True)
        try:
            while (sim.proc.poll() is None):
                time.sleep(1)
        except KeyboardInterrupt:
            pass
