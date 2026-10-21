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
