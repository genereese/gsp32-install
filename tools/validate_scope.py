""" Flasher Version 105.1: replays real commits through the scoped choice: the suites --changed would pick for each
commit's site files alone, against the suites that commit had to touch (their test files changed with it) and the
suites named as failed for it (--failed COMMIT=test_page,...). Misses are reported.
Usage: python tools/validate_scope.py COMMIT [COMMIT ...] [--failed COMMIT=suite,suite] """
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scope, flasher_tests

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("commits", nargs="+")
    ap.add_argument("--failed", action="append", default=[])
    a = ap.parse_args()
    failed = dict((c, n.split(",")) for c, n in (item.split("=", 1) for item in a.failed))
    names = sorted(f[:-3] for f in os.listdir(scope.TESTS) if f.startswith("test_") and f.endswith(".py"))
    misses = 0
    for commit in a.commits:
        files = scope.git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).split()
        title = scope.git("log", "-1", "--format=%h %s", commit).strip()[:90]
        sources = [f for f in files if not (f.startswith("tests/test_") and f.endswith(".py"))]
        expect = set(n for n in names if scope.suiteFile(n) in files) | set(failed.get(commit, []))
        full, chosen, _ = scope.choose(sources, names, flasher_tests.SMOKE)
        # a test-only commit: its suites run because their own files changed
        missing = [] if not (sources) else sorted(s for s in expect if s not in chosen)
        misses += len(missing)
        print("%s\n  site files: %s\n  pick: %s\n  had to touch / failed: %s\n  %s" % (
            title, ", ".join(sources) or "(none)", "FULL RUN (%d suites)" % len(names) if (full) else "%d suites: %s" % (len(chosen), ", ".join(sorted(chosen))),
            ", ".join(sorted(expect)) or "(none)", ("MISSED: " + ", ".join(missing)) if (missing) else "ok: all covered" if (sources) else "test-only: its own suites run"))
    print("misses: %d" % misses)
    sys.exit(1 if misses else 0)

if __name__ == "__main__":
    main()
