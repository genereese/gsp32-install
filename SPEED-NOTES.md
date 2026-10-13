# Flasher speed: what we tried (V49-V64)

Decision (Gene, 2026-10-13 2:27 PM MT): stop the speed work. The web flasher installs at 115200 only, from Flasher Version 64 (c98a0b2, rollback c4849d4 = v63). Experiments are archived on branch `v64-speed-experiments` (cd93ab7), never merged.

## What was tried
- **Speed chain (V49-V53):** connect at 115200, then per USB chip try 921600 -> 460800 -> 230400 -> 115200 (CH9102/FTDI tried 2000000 first). Each rate was checked with two MAC reads. On a failure the install stepped down a rate and started the full image over. Nothing was ever saved per board (V53). The status line showed the rate ("at 921,600 Baud") and step-down notices.
- **V61, flushInput hang:** esptool-js 0.5.7's `flushInput` awaits `reader.closed`, which only settles when the port closes, so on our borrowed open port the V60 install hung forever. Replaced it with our own flush. Also added hard time limits (3 s per rate, 12 s connect), a full reader/port cleanup between tries, and the "Calibrating Transfer Speed..." pulsing status.
- **V62, stray-byte drain:** Gene's first real Chrome install hit "Invalid head of packet (0x80)" at every rate. Theory: one stray byte after the UART switch. Added a bounded drain (100 ms quiet, 500 ms max, then a fresh reader) and a retried MAC check. It worked on the dev board under Node, but in Chrome it drained 995 / 1593 bytes. That is not a stray byte; it is the board rebooting and printing its boot log at 115200.
- **V63, line handling:** the speed-change reopen no longer touches DTR/RTS afterwards (as esptool-js's own changeBaud). If more than 64 bytes are drained, the board is treated as restarted and the install drops straight to 115200. Gene's log: "Drained 995 bytes ... the board restarted on the speed change".

## Findings
- **Chrome and Edge on Windows reset CP2102 boards on every port reopen during a baud change.** It was reproduced on both boards (Gene's and the dev board) in real Edge, with the same 995 bytes drained. Line settings tried before the reopen: both low and both high do not help. DTR-high/RTS-low was never tested (the workstation connection dropped).
- **Direct connect at 230400** (open at 230400 from the start, no switch) worked: about 100 s vs about 190 s at 115200. But it failed 1 of 2 runs.
- **Intermittent write errors:** "Invalid head of packet (0xff)", occasionally even at 115200. V64 retries the full install once after a write error (fresh connect). This is only tested against the fake board.
- **Hardware:** Espressif notes that boards without a capacitor on EN reset unreliably on Windows. A 1 uF+ cap from EN to GND would likely make the reopen survivable.
- **Desktop esptool does 921600 fine** on the same boards: a full 4 MB image in about 47 s. Its baud change does not reopen the port the way Web Serial must.

## Decision
Stay at 115200 (about 190-200 s per install). Reliability beats speed. There is no speed testing, no Calibrating text, and no rate in the status line.

## If revisited
- A newer esptool-js with its background reader / native baud change (may avoid our close/open reopen).
- WebUSB driving the CP210x directly (set the baud by vendor control transfer, no port reopen, no line glitch).
- Boards with CH9102 or FTDI chips, which may not reset on reopen. Test there first.
- Finish the untested DTR-high/RTS-low variant (on `v64-speed-experiments`, `?lines=dtr`).
- Direct 230400 connect, if it can be made reliable over many runs. Add the EN capacitor on our own boards.
