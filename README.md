# GSP32 installer

A static page that installs GSP32 (a MicroPython web UI for classic ESP32 boards) from the browser with
[ESP Web Tools](https://esphome.github.io/esp-web-tools/): Chrome or Edge on a desktop, and a USB data cable.

## Getting Started

1. Open the page in Chrome or Edge on a desktop computer. Plug the board in with a USB data cable.
2. Pick a version, tick **I understand this erases the board**, and click **Install GSP32**. Leave this tab open and visible.
3. The board is erased and gets the full image (bootloader, partition table, MicroPython with the web UI built in,
   and a file system with the web pages), written at offset 0.
4. Set up Wi-Fi in the install window, or click **Set up Wi-Fi** and pick a network. The password is sent over USB
   (Improv Wi-Fi serial) and is saved only when the board connects. Or choose **Skip, USB only**.
5. Open http://gsp32.local (or the address the page shows) and set a web UI password on the first visit.

The serial console on the page connects at 115200. Reset, Ctrl-C, and **Set up / change Wi-Fi** are there any time.
From a terminal: `mpremote connect /dev/ttyUSB0` (or COMx). Reset the board and press Enter at the
"Press Enter within 10 s" prompt to set up Wi-Fi there.

## Contents

- `index.html`, `style.css`, `app.js` - the page
- `versions.json` - versions the dropdown offers; `manifest.json` - the ESP Web Tools manifest (ESP32, Improv on)
- `firmware/gsp32-esp32.bin` - merged 4 MB image from ESP32-httpd 62600ef (no Wi-Fi settings, no passwords, no
  personal files: the file system holds only boot.py, main.py and the shipped web pages)
