# Install page tests (Playwright, fake Web Serial board)

    python tests/test_page.py         # the page: steps, install, Wi-Fi, console, layout (59 checks)
    python tests/test_button_row.py   # hotfix fe97719: the button row always comes back (success, failure, reboot)
    python tests/test_wifi_wait.py    # Version 37: Open GSP32 Web UI waits greyed for Wi-Fi, fades to blue, no shift
    python tests/test_version.py      # Version 39: GSP32 Found names the version even when the Ready line was missed
    python tests/test_v42_1.py       # Version 42.1: design tokens, boot loop keeps Install, Recover, leave warning, countdown
    python tests/test_v42.py         # Version 42: 15 px text, console unchanged, smaller Wi-Fi rows, blue pulse while erasing
    python tests/test_v43_1.py       # Version 43.1: Improv only while the board listens, Change Wi-Fi on a set-up board, no credentials to a quiet board, status under the buttons
    python tests/test_v43_2.py       # Version 43.2: Wi-Fi steps under the status line, status pulses during waits, older GSP32 named on Change Wi-Fi, softer tab warning, Wi-Fi Connected! link kept
    python tests/test_v61.py         # Version 61: connect time limits and retry, Recover note fix, Busy ... console box
    python tests/test_v64.py         # Version 64: always 115200, no speed tests, status Installing Version N (45%), one retry after a write error
    python tests/test_v75.py         # Version 75: console pinned at Install, time left, Next step to Wi-Fi, versions.json on Get Started, new slides
    python tests/test_v79.py         # Version 79+/80: two builds (ESP32, ESP32-S3) in one manifest, picked by the chip; other chips refused
    python tests/test_v85.py         # Version 85: Release dropdown (Stable default, Beta from a versions.json entry with "channel": "beta")

`mock.js` is a fake board on Web Serial (Improv answers, boot lines on an RTS reset; `window.__ets` also prints the
ROM's `ets ...` line like a real ESP32), `fake-esptool.js` stands in for esptool-js. Needs Playwright with Chromium.
Screenshots go to a temp folder (or `SHOTS`).
