""" Flasher Version 105.1 (Gene): scoped test runs. tests/scope.json maps the site's files to the suites that cover them
(built by tools/build_scope.py from a trace run plus the suites' sources). tools/flasher_tests.py --changed [BASE]:
  - a file in "core" (index.html, app.js, style.css, the esptool vendor copy, the fake board, manifest.json and
    versions.json, the build script, the runner and this mapping, and whatever nearly every suite loads) runs everything;
  - a changed suite runs itself; a mapped file runs its suites; a file in "none" (docs, the screenshot tools) runs nothing
    extra; a file the mapping doesn't know runs everything (and is warned about);
  - suites nothing ties to a file (no trace, no source reference) are global and always run; a suite that loads only
    core files runs with the full run and when its own file changes; the smoke suites always run.
Releases (a new Beta or Stable on the flasher) still run the full suite (--full) """
import fnmatch, json, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
SCOPE_FILE = os.path.join(TESTS, "scope.json")
STATE = os.path.join(os.path.expanduser("~"), ".cache", "gsp32-scope", "flasher-last-full")

def git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True).stdout

def load():
    with open(SCOPE_FILE) as file:
        return json.load(file)

def matches(path, globs):
    return any(fnmatch.fnmatchcase(path, glob) for glob in globs)

def lastFull():
    try:
        return open(STATE).read().strip() or None
    except OSError:
        return None

def recordFull():
    head = git("rev-parse", "HEAD").strip()
    if (head):
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        open(STATE, "w").write(head + "\n")

def changedFiles(base=None):
    """ (base, files changed from base to the working tree, untracked included); default base: where HEAD leaves
    origin/main, or with nothing there the last full-run commit """
    if not (base):
        base = git("merge-base", "HEAD", "origin/main").strip() or "origin/main"
        if not (git("diff", "--name-only", base).strip()) and not (git("ls-files", "--others", "--exclude-standard").strip()) and (lastFull()):
            base = lastFull()
    files = set(git("diff", "--name-only", "--no-renames", base).split())
    files |= set(git("ls-files", "--others", "--exclude-standard").split())
    return base, sorted(files)

def suiteFile(name):
    return "tests/" + name + ".py"

def choose(files, suites, smoke, scope=None):
    """ (full, {suite: [reasons]}, notes) """
    scope = scope or load()
    chosen, notes, full = {}, [], []
    for path in files:
        if matches(path, scope["core"]):
            full.append(path + " (core)")
            continue
        if path in [suiteFile(s) for s in suites]:
            chosen.setdefault(path[6:-3], []).append("its own file changed")
            continue
        hits = [s for glob, names in scope["map"].items() if fnmatch.fnmatchcase(path, glob) for s in names if s in suites]
        if (hits):
            for s in hits:
                chosen.setdefault(s, []).append("covers " + path)
            continue
        if matches(path, scope["none"]):
            notes.append("%s: no suite covers it (docs, screenshot tools)" % path)
            continue
        full.append(path + " (not in tests/scope.json)")
    if (full):
        return True, {s: ["full run: " + ", ".join(full)] for s in suites}, notes
    for s in suites:
        if (s in scope.get("global", [])) or (s not in scope.get("suites", [])):
            chosen.setdefault(s, []).append("global (nothing ties it to a file)")
    for s in smoke:
        if (s in suites):
            chosen.setdefault(s, []).append("smoke")
    return False, chosen, notes

def coverageWarnings(suites, scope=None):
    scope = scope or load()
    warnings = []
    globs = list(scope["map"]) + scope["core"] + scope["none"]
    for path in git("ls-files").split():
        if path.startswith("tests/test_") and path.endswith(".py"):
            continue
        if not matches(path, globs):
            warnings.append("not in tests/scope.json (a change to it runs the full suite): " + path)
    known = set(scope.get("suites", []))
    for s in suites:
        if (s not in known):
            warnings.append("suite not in tests/scope.json (rebuild it: tools/build_scope.py --trace): tests/%s.py" % s)
    return warnings
