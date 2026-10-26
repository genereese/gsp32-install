# Install page tests (Playwright, fake Web Serial board)

Run them all side by side with `python tools/flasher_tests.py` (about 2 minutes; the release check), or the quick
subset for text and layout changes with `python tools/flasher_tests.py --smoke` (about 20 s: test_smoke, test_v48,
test_v50, test_v80, test_v85). The runner fails a suite on a FAIL line or a non-zero count too, not only on its exit code.

    python tests/test_smoke.py        # Flasher Version 105: page loads clean, versions.json and its files, gallery, footer, cache tag

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
    python tests/test_v101.py             # Version 101: Disconnect at the right end of the Install GSP32 row (slides in once connected, gone while installing), closes the port with the board left running; phone layout
    python tests/test_s3_boardinfo.py     # S3 native USB (0x303A): BOOT/RST guide when the reset or the port fails, the port picked again (or taken when it comes back), read in download mode without a reset, install, restart onto GSP32's port, Wi-Fi without board info; other bridges unchanged
    python tests/test_s3_crashproof.py    # Flasher Version 105: a Chromium-like port (close order, locked streams, stalled writes): never the tab-killing new readable after a dropped close; writes bounded and aborted; esptool-js stopped after a connect timeout; a stuck port asks for an unplug
    python tests/test_v107_classic.py     # Flasher Version 107: the S3 fixes only on native USB (0x303A); on a classic port the REAL esptool-js against espemu.js (an ESP32 ROM + stub) makes the same port calls as Flasher 104, clean and with line faults; the Classic copies are 104's verbatim
    python tests/test_v110.py             # Flasher Version 110: after a native-USB install, Checking cannot sit there (Tap RST / pick the new port, then Next / Set Up Wi-Fi); the console stays usable during that check (Cancel too); the post-install guide offers Set Up Wi-Fi Instead. A classic port still locks the console
    python tests/test_gspc_v123.py        # Flasher Version 115.7: GSP32-C Beta V123 is its own pick, first, V122-V117 kept; it loads manifest-gspc-v123.json and firmware/gspc-v123 (improv: true); the note mentions the Package Manager
    python tests/test_gspc_v122.py        # Flasher Version 115.6: GSP32-C Beta V122 is its own pick, first, V121-V117 kept; it loads manifest-gspc-v122.json and firmware/gspc-v122 (improv: true); the note mentions the AI Helper
    python tests/test_gspc_v121.py        # Flasher Version 115.5: GSP32-C Beta V121 is its own pick, first, V120-V117 kept; it loads manifest-gspc-v121.json and firmware/gspc-v121 (improv: true); the note mentions Settings and Improv
    python tests/test_gspc_v120.py        # Flasher Version 115.4: GSP32-C Beta V120 is its own pick, first, V119, V118 and V117 kept; it loads manifest-gspc-v120.json and firmware/gspc-v120; the note mentions the file manager
    python tests/test_gspc_v119.py        # Flasher Version 115.3: GSP32-C Beta V119 is its own pick, first, V118 and V117 kept; it loads manifest-gspc-v119.json and firmware/gspc-v119; the note mentions live pages
    python tests/test_gspc_v118.py        # Flasher Version 115.2: one Release option per GSP32-C Beta in versions.json (V118 and V117 side by side, newest first), each loads its own manifest and firmware folder; the old GSP32 options are unchanged

`mock.js` is a fake board on Web Serial (Improv answers, boot lines on an RTS reset; `window.__ets` also prints the
ROM's `ets ...` line like a real ESP32), `fake-esptool.js` stands in for esptool-js. `espemu.js` (Flasher Version 107) is an ESP32 ROM and flasher stub behind a
Chromium-like port for the real vendored esptool-js, recording every port call. Needs Playwright with Chromium.
Screenshots go to a temp folder (or `SHOTS`).
