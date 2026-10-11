# GSP32 installer

A static page that installs GSP32 (a MicroPython web UI for classic ESP32 boards) from the browser with
[ESP Web Tools](https://esphome.github.io/esp-web-tools/): Chrome or Edge on a desktop, a USB data cable, one click.

## Getting Started

1. Open the page, plug the board in, click **Install GSP32** and pick its serial port.
2. The board is erased and gets the full image (bootloader, partition table, MicroPython with the web UI built in,
   and a file system with the web pages), written at offset 0.
3. When asked, enter your Wi-Fi name and password: the page sends them over USB (Improv Wi-Fi serial), the board
   tests them and saves them only when it connects.
4. Open http://gsp32.local (or the address the page shows) and set a web UI password on the first visit.

No Wi-Fi step, or it was skipped? Open a serial console at 115200 (e.g. `mpremote connect /dev/ttyUSB0` or COMx),
reset the board and press Enter at the "Press Enter within 10 s" prompt to set up Wi-Fi there.

## Contents

- `index.html` - the page; `manifest.json` - the ESP Web Tools manifest (ESP32, Improv on)
- `firmware/gsp32-esp32.bin` - merged 4 MB image from ESP32-httpd e31c853 (no Wi-Fi settings, no passwords, no
  personal files: the file system holds only boot.py, main.py and the shipped web pages)
