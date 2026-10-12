# Install page tests (Playwright, fake Web Serial board)

    python tests/test_page.py         # the page: steps, install, Wi-Fi, console, layout (59 checks)
    python tests/test_button_row.py   # hotfix fe97719: the button row always comes back (success, failure, reboot)
    python tests/test_wifi_wait.py    # Version 37: Open GSP32 Web UI waits greyed for Wi-Fi, fades to blue, no shift
    python tests/test_version.py      # Version 39: GSP32 Found names the version even when the Ready line was missed

`mock.js` is a fake board on Web Serial (Improv answers, boot lines on an RTS reset; `window.__ets` also prints the
ROM's `ets ...` line like a real ESP32), `fake-esptool.js` stands in for esptool-js. Needs Playwright with Chromium.
Screenshots go to a temp folder (or `SHOTS`).
