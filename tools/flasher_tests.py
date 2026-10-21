""" Flasher Version 105 (Gene): runs the flasher's suites (tests/test_*.py) side by side, one log each, and a summary.
A suite fails on any of: a non-zero exit code, a FAIL line (check() prints "FAIL <name>"), a non-zero closing count
("FAILURES: 2", "FAILS 2", "fails 2", "60 passed 1 failed"), a Python traceback, no closing count at all (it stopped
early) or no PASS line. The exit code alone hid a failing check before (test_page's three-digit version check).
Usage: python tools/flasher_tests.py [--smoke] [--jobs 8] [--out DIR] [suite ...]
  --smoke   the quick check for text and layout changes (SMOKE below, about 20 s); the full suite is the release check """
import argparse, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(HERE, "tests")
PYTHON = os.environ.get("TEST_PYTHON", "/workspace/pw-venv/bin/python")
# The page loads clean, the version list, the gallery, the footer and the cache tag
SMOKE = ["test_smoke", "test_v48", "test_v50", "test_v80", "test_v85"]
# Seconds alone (Flasher Version 104 run), so the long ones start first
TIMES = {"test_v61": 97, "test_v75": 93, "test_recover_flow": 71, "test_page": 53, "test_v79": 53, "test_s3_boardinfo": 52,
         "test_v43_1": 46, "test_button_row": 43, "test_v42_1": 37, "test_boot_loop_label": 35, "test_v43_2": 35}
FAIL_LINE = re.compile(r"^FAIL\b(?!S)", re.M)
COUNT = re.compile(r"^(?:FAILURES:|FAILS|fails)\s+(\d+)\s*$|^(\d+) passed (\d+) failed\s*$", re.M)

def verdict(code, text):
    """ "ok", or why the suite failed """
    reasons = []
    if (code != 0):
        reasons.append("exit %d" % code)
    fails = FAIL_LINE.findall(text)
    if (fails):
        reasons.append("%d FAIL line%s" % (len(fails), "" if len(fails) == 1 else "s"))
    counts = COUNT.findall(text)
    if not (counts):
        reasons.append("no closing count (stopped early?)")
    elif any(int(a or c or 0) for a, _, c in counts):
        reasons.append("count says failed")
    if ("Traceback (most recent call last)" in text):
        reasons.append("traceback")
    if not (re.search(r"^PASS ", text, re.M)):
        reasons.append("no PASS line")
    return "ok" if not (reasons) else "FAIL (" + ", ".join(reasons) + ")"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", default="/tmp/flasher-tests")
    ap.add_argument("suites", nargs="*")
    a = ap.parse_args()
    names = a.suites or (SMOKE if (a.smoke) else sorted(f[:-3] for f in os.listdir(TESTS) if f.startswith("test_") and f.endswith(".py")))
    names = [n[:-3] if n.endswith(".py") else n for n in names]
    names.sort(key=lambda n: -TIMES.get(n, 20))
    os.makedirs(a.out, exist_ok=True)
    for old in os.listdir(a.out):
        if old.endswith(".log"):
            os.remove(os.path.join(a.out, old))
    started = time.time()

    def one(name):
        t = time.time()
        log_path = os.path.join(a.out, name + ".log")
        env = dict(os.environ)
        # the flasher's suites need no keys; none is passed on
        for key in [k for k in env if k.endswith(("_API_KEY", "_TOKEN"))]:
            env.pop(key)
        with open(log_path, "w") as log:
            try:
                code = subprocess.run([PYTHON, name + ".py"], cwd=TESTS, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900).returncode
            except subprocess.TimeoutExpired:
                code = -9
        return name, verdict(code, open(log_path, errors="replace").read()), time.time() - t

    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        results = list(pool.map(one, names))
    passes = sum(len(re.findall(r"^PASS ", open(os.path.join(a.out, n + ".log"), errors="replace").read(), re.M)) for n in names)
    bad = [r for r in results if r[1] != "ok"]
    lines = ["%-24s %6.1f s  %s" % (name, seconds, result) for name, result, seconds in results]
    summary = "%s: %d suites, %d checks passed, %d suites failed, wall %.0f s" % ("smoke" if (a.smoke) else "flasher suite", len(results), passes, len(bad), time.time() - started)
    open(os.path.join(a.out, "summary.txt"), "w").write("\n".join(lines + [summary]) + "\n")
    for name, result, _ in bad:
        print("  FAILED: %s %s (log %s)" % (name, result, os.path.join(a.out, name + ".log")))
    print(summary)
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
