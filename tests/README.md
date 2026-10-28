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
    python tests/test_reset_order.py      # Reset into the bootloader: tight first on Linux, classic elsewhere, USB-JTAG for native USB; then classic, tight, USB-JTAG per attempt (Flasher 115.17: on a CP210x the gentle reset, EN low 300 ms and GPIO 0 held 700 ms, takes the USB-JTAG slot); what worked is remembered
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
    python tests/test_flasher_11526.py    # Flasher Version 115.26: no Ctrl-C before Wi-Fi setup (classic rule; the GSP32-C console hook takes Improv while main.py runs) and takeSerialBytes drops a REPL-echoed "IMPROV" at once, so the first scan lists networks (V132 (a)); plus V130 Stable + V132 Beta picks (V131 Beta replaced, 404), rollbacks 404, board naming
    python tests/test_gspc_v129.py        # Flasher Version 115.22: GSP32-C Beta V129 is its own pick, first, V128-V117 kept; it loads manifest-gspc-v129.json and firmware/gspc-v129 with Erase and Install (no update flag); no note text
    python tests/test_gspc_v128.py        # Flasher Version 115.21: GSP32-C Beta V128 is its own pick, first, V127.3-V117 kept; it loads manifest-gspc-v128.json and firmware/gspc-v128 with Erase and Install (no update flag); no note text
    python tests/test_gspc_v1273.py       # Flasher Version 115.16: GSP32-C Beta V127.3 is its own pick, first, V127.2-V117 kept; it loads manifest-gspc-v127.3.json and firmware/gspc-v127.3; no GSP32-C note since 115.20
    python tests/test_clean_install.py    # Flasher Version 115.19: clean installs only: no Update button, keep-files hint or text, no partition-table read, no update flag in versions.json; V127.3 erases and writes the one image; no GSP32-C note (115.20), the yellow erase box mentions Backup
    python tests/test_hold_boot.py        # Flasher Version 115.17 (Gene's ESP32): auto reset first; on failure "Hold the BOOT button, click Try Again ..., let go when progress starts"; the device is remembered (USB VID:PID + MAC once read) and the next Install shows the hold-BOOT tip up front; "forget this" clears it; normal devices, other bridges and native USB never see it. SHOTS=<dir> saves the hint and the tip
    python tests/test_gspc_v1272.py       # Flasher Version 115.15: GSP32-C Beta V127.2 is its own pick, first, V127.1-V117 kept; it loads manifest-gspc-v127.2.json and firmware/gspc-v127.2; no GSP32-C note since 115.20
    python tests/test_gspc_v127.py        # Flasher Version 115.14: GSP32-C Beta V127.1 is its own pick, first, V126-V117 kept; it loads manifest-gspc-v127.1.json and firmware/gspc-v127.1; no GSP32-C note since 115.20; the page says device, not board
    python tests/test_gspc_v126.py        # Flasher Version 115.13: GSP32-C Beta V126 is its own pick, first, V125-V117 kept; it loads manifest-gspc-v126.json and firmware/gspc-v126; no GSP32-C note since 115.20
    python tests/test_gspc_v125.py        # Flasher Version 115.9: GSP32-C Beta V125 is its own pick, first, V124-V117 kept; it loads manifest-gspc-v125.json and firmware/gspc-v125 (improv: true); no GSP32-C note since 115.20
    python tests/test_gspc_improv125.py   # Flasher Version 115.9: Set Up Wi-Fi (Improv) for GSP32-C V121 and newer
    python tests/test_wifi_after_install.py # Flasher Version 115.10 (Gene's ESP32): after a V125 install the console takes typing and the port is read again; Set Up Wi-Fi stops main.py with Ctrl-C (waits for >>>, or says it could not); an empty scan offers a typed name and the gsp.wifi(...) way; a board that never answers says so; no reset into download mode: the hold-BOOT note folds in at once and with the error; a classic board's connect, reconnect and Disconnect never restart it (no probe, DTR/RTS untouched on connect, RTS first on Disconnect); an echoed gsp.wifi(...) password shows as dots; 115.11: every return to the run state (Disconnect, page leave, after a restart) is two calls, RTS off, a 30 ms gap, then DTR off, and EN is never pulled low (the mock applies one setSignals DTR first, as Chromium does, and counts EN pulses in `window.__enPulses`, line changes in `window.__lines`)
    python tests/test_gspc_v124.py        # Flasher Version 115.8: GSP32-C Beta V124 is its own pick, first, V123-V117 kept; it loads manifest-gspc-v124.json and firmware/gspc-v124 (improv: true); no GSP32-C note since 115.20
    python tests/test_gspc_v123.py        # Flasher Version 115.7: GSP32-C Beta V123 is its own pick, first, V122-V117 kept; it loads manifest-gspc-v123.json and firmware/gspc-v123 (improv: true); no GSP32-C note since 115.20
    python tests/test_gspc_v122.py        # Flasher Version 115.6: GSP32-C Beta V122 is its own pick, first, V121-V117 kept; it loads manifest-gspc-v122.json and firmware/gspc-v122 (improv: true); no GSP32-C note since 115.20
    python tests/test_gspc_v121.py        # Flasher Version 115.5: GSP32-C Beta V121 is its own pick, first, V120-V117 kept; it loads manifest-gspc-v121.json and firmware/gspc-v121 (improv: true); no GSP32-C note since 115.20
    python tests/test_gspc_v120.py        # Flasher Version 115.4: GSP32-C Beta V120 is its own pick, first, V119, V118 and V117 kept; it loads manifest-gspc-v120.json and firmware/gspc-v120; no GSP32-C note since 115.20
    python tests/test_gspc_v119.py        # Flasher Version 115.3: GSP32-C Beta V119 is its own pick, first, V118 and V117 kept; it loads manifest-gspc-v119.json and firmware/gspc-v119; no GSP32-C note since 115.20
    python tests/test_gspc_v118.py        # Flasher Version 115.2: one Release option per GSP32-C Beta in versions.json (V118 and V117 side by side, newest first), each loads its own manifest and firmware folder; the old GSP32 options are unchanged

`mock.js` is a fake board on Web Serial (Improv answers, boot lines on an RTS reset; `window.__ets` also prints the
ROM's `ets ...` line like a real ESP32), `fake-esptool.js` stands in for esptool-js. `espemu.js` (Flasher Version 107) is an ESP32 ROM and flasher stub behind a
Chromium-like port for the real vendored esptool-js, recording every port call. Needs Playwright with Chromium.
Screenshots go to a temp folder (or `SHOTS`).
