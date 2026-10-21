# Flasher tools

The fast path for small flasher page updates (text, layout, a tour slide): about 5 minutes. How-to:
`/workspace/bots/code-projects/gsp32/FAST-FLASHER-UPDATES.md`.

    python release_shots.py --sim --only ai     # reshoot slides from a box-local board (no board, tunnel or cleanup)
    python tools/bump_flasher.py                 # Flasher Version N+1: footer, cache tag, the tests that pin them
    python tools/flasher_tests.py --smoke        # ~20 s; the full suite (no --smoke, ~2 min) is the release check
    python tools/live_check.py --since <before>  # after the push: Pages serves the commit, then one headless look

- `boardsim.py`: the shipped GSP32 commit's web UI on the MicroPython simulator (mpsim), shaped like the dev board in
  the screenshot browser. `python tools/boardsim.py` serves it on http://127.0.0.1:8890 to look around.
- `release_shots.py` without `--sim` still shoots from the dev board (http://192.168.2.101, or its tunnel URL): use it for
  releases where the board itself changed.

## Scoped runs

    python tools/flasher_tests.py --changed [BASE]   # suites tests/scope.json ties to the changed files, plus smoke
    python tools/flasher_tests.py --changed --dry-run  # just print the pick and why
    python tools/flasher_tests.py --full             # everything: still required before a Beta or Stable release
    python tools/flasher_tests.py --check-scope      # warns about files or suites the mapping doesn't know

BASE defaults to the last commit a full run passed on (or origin/main). Core files (index.html, app.js, style.css,
tour.js, shots/, manifests, versions.json, firmware/, tests/mock.js, the runner and the mapping) run everything, and so
does any file the mapping doesn't know. Every page suite loads index/app/style/tour, so scoping mostly helps for
test-only and tooling changes; text or layout changes keep using --smoke for the fast loop.
Rebuild the mapping after adding suites or page files:
`python tools/build_scope.py --trace` (one traced full run, ~2 min), or `--from DIR` for an existing trace.
`python tools/validate_scope.py COMMIT ...` replays real commits through the pick.
