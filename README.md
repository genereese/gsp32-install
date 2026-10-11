# GSP32 installer

A static page that installs GSP32 (a MicroPython web UI for classic ESP32 boards) from the browser with
its own install window and [esptool-js](https://github.com/espressif/esptool-js) 0.5.7 (in vendor/): Chrome or ## Getting Started

1. Open the page in Chrome or Edge on a desktop computer. Plug the board in with a USB data cable.
2. Click **Install GSP32**. In the window, pick a version, read the warning, tick **I Understand This Erases the Board**,
   and click **Choose Port and Install**. Keep the tab open until it finishes.
3. Choose **Set Up Wi-Fi** (pick a network, enter its password; sent over USB with Improv Wi-Fi serial and saved only
   when the board connects) or **USB Only**.
4. After Wi-Fi setup the board restarts; the window shows its address with **Open GSP32 Web UI** and **Connect to
   Serial Console**. Set a web UI password on the first visit.

One serial port stays open through the whole window. Opening and closing it leaves the board's reset lines in the
run state (DTR and RTS off), so the page never resets the board or holds it in reset; it resets the board only after
flashing, after Wi-Fi setup, and with **Reset Board**.

thin 10 s" prompt to set up Wi-Fi there.

## Contents

- `index.html`, `style.css`, `app.js` - the page
- `versions.json` - versions the dropdown offers; `manifest.json` - the parts to write for each version
- `vendor/esptool-js-0.5.7.js` - esptool-js bundle (Apache-2.0, `vendor/esptool-js-LICENSE`)
- `firmware/gsp32-esp32.bin` - merged 4 MB image from ESP32-httpd 62600ef (no Wi-Fi settings, no passwords, no
  personal files: the file system holds only boot.py, main.py and the shipped web pages)
