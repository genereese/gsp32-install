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
    python tests/test_v79.py         # Version 79+/80: two builds (ESP32, ESP32-S3) in one manifest, picked by the chip; other chips refused. Version 92: ESP32-C3 on Beta only (Stable shows a short note), C3 rev < v0.3 refused
    python tests/test_v85.py         # Version 85: Release dropdown (Stable default, Beta from a versions.json entry with "channel": "beta")
    python tests/test_false_disconnect.py  # Serial line noise (Framing/Break/Parity/Overrun) keeps reading; a real unplug closes the port and brings Get Started back
    python tests/test_reset_order.py      # Reset into the bootloader: tight first on Linux, classic elsewhere, USB-JTAG for native USB; then classic, tight, USB-JTAG per attempt; what worked is remembered
    python tests/test_recover_flow.py     # Install note only once writing starts; Recover/Install GSP32 only for a connected board with that MAC (or a boot loop); other firmware: Install GSP32; Get Started survives a port that will not open; greyed buttons say why
    python tests/test_verify_console.py   # MD5 check after writing (retry once, never Installed unverified); console paints per frame, 500 lines, boot-loop output held back; corrupted-app boot errors mean Recover/Install GSP32
    python tests/test_unreadable.py       # Output at another speed (factory firmware): console stays at 115200, one updating "not readable" line, never broken, Install GSP32
    python tests/test_boot_loop_label.py  # Restart loop without an image error is not called "no bootable firmware"; every broken state reads Recover/Install GSP32 in full
    python tests/test_write_retry.py      # Noise or MD5 failure during a write: reconnect and write again, 3 writes in all; plain final message; boot-loop fold lasts until esptool takes the port

`mock.js` is a fake board on Web Serial (Improv answers, boot lines on an RTS reset; `window.__ets` also prints the
ROM's `ets ...` line like a real ESP32), `fake-esptool.js` stands in for esptool-js. Needs Playwright with Chromium.
Screenshots go to a temp folder (or `SHOTS`).
