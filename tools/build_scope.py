""" Flasher Version 105.1 (Gene): builds tests/scope.json. A trace run (tools/scope_pyhook: every file a suite opens or
imports, the site's files its HTTP server hands the browser included) plus each suite's source (the files it names).
A file at least SHARED of the suites load counts as shared and joins "core" with the hand-picked CORE below.
Usage: python tools/build_scope.py --trace      (the full suite once with tracing, about 2 min, then builds)
       python tools/build_scope.py --from DIR  (builds from an earlier trace) """
import argparse, datetime, fnmatch, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
SHARED = 0.75
CORE = ["index.html", "app.js", "style.css", "vendor/*", "tests/mock.js", "tests/fake-esptool.js", "manifest.json",
        "versions.json", "build_image.py", "tools/flasher_tests.py", "tools/scope.py", "tools/build_scope.py",
        "tools/scope_pyhook/*", "tests/scope.json", ".gitignore",
        # the images: changing one is a release (the full suite)
        "firmware/*", "firmware/**"]
NONE = ["*.md", "tests/README.md", "tools/README.md", "LICENSE.txt", "release_shots.py", "tools/boardsim.py",
        "tools/bump_flasher.py", "tools/live_check.py", "tools/validate_scope.py"]

def tracked():
    return set(subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True).stdout.split())

def suites():
    return sorted(f[:-3] for f in os.listdir(TESTS) if f.startswith("test_") and f.endswith(".py"))

def build(trace_dir):
    files, names = tracked(), suites()
    reads, refs = {}, {}
    for name in names:
        found = set()
        log = os.path.join(trace_dir, name + ".log")
        if os.path.exists(log):
            for line in open(log, errors="replace"):
                path = os.path.normpath(line.strip())
                if path.startswith(ROOT + "/"):
                    rel = path[len(ROOT) + 1:]
                    m = re.match(r"(.*)/__pycache__/(\w+)\.cpython-\d+\.pyc$", rel)
                    rel = (m.group(1) + "/" + m.group(2) + ".py") if (m) else rel
                    if (rel in files):
                        found.add(rel)
        reads[name] = found
        text = open(os.path.join(TESTS, name + ".py"), errors="replace").read()
        refs[name] = set(p for p in files if not p.startswith("tests/test_") and ((p in text) or re.search(r"(?<![\w.-])" + re.escape(os.path.basename(p)) + r"(?![\w-])", text)))
    traced = [n for n in names if reads[n]]
    counts = {}
    for name in names:
        for path in reads[name]:
            counts[path] = counts.get(path, 0) + 1
    shared = sorted(p for p, c in counts.items() if c >= SHARED * max(1, len(traced)) and not p.startswith("tests/test_"))
    core = CORE + [p for p in shared if not any(fnmatch.fnmatchcase(p, g) for g in CORE)]
    mapping = {}
    for name in names:
        for path in reads[name] | refs[name]:
            if (path.startswith("tests/test_") and path.endswith(".py")) or any(fnmatch.fnmatchcase(path, g) for g in core):
                continue
            mapping.setdefault(path, set()).add(name)
    scope = {
        "about": "Flasher Version 105.1: file globs -> the suites that cover them (tools/scope.py). Built by tools/build_scope.py "
                 "from a trace run plus the suites' sources; rebuild after adding a suite or a site file.",
        "built_from": subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "built": datetime.date.today().isoformat(),
        "core": core, "none": NONE, "suites": names,
        # what no trace or source line ties to any file (core included): run on every scoped run
        "global": [n for n in names if not (reads[n] | refs[n])],
        "map": {p: sorted(s) for p, s in sorted(mapping.items())},
        "traced": {n: len(reads[n]) for n in names},
    }
    with open(os.path.join(TESTS, "scope.json"), "w") as file:
        json.dump(scope, file, indent=1)
        file.write("\n")
    print("scope.json: %d suites (%d traced; untraced: %s), %d mapped files, shared by >= %d%%: %s" % (
        len(names), len(traced), ", ".join(n for n in names if not reads[n]) or "none", len(mapping), SHARED * 100, ", ".join(shared) or "none"))

def traceRun(trace_dir):
    os.makedirs(trace_dir, exist_ok=True)
    env = dict(os.environ, GSP32_TRACE_DIR=trace_dir, PYTHONPATH=os.path.join(ROOT, "tools", "scope_pyhook"))
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "flasher_tests.py"), "--full", "--out", os.path.join(trace_dir, "run")], env=env)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--from", dest="source", default="/tmp/flasher-trace")
    a = ap.parse_args()
    if (a.trace):
        traceRun(a.source)
    build(a.source)
