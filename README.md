# GSP32 Installer

Install [GSP32](https://genereese.github.io/gsp32-install/), a MicroPython web UI for ESP32, ESP32-C3 and ESP32-S3 boards, straight from your browser. No tools to install.

## Supported Boards

- ESP32 (classic) with 4 MB of flash or more
- ESP32-C3 with 4 MB of flash or more
- ESP32-S3 with 8 MB or 16 MB of flash (attached displays and the window manager are S3 only; Bluetooth needs an S3 with PSRAM)

The installer detects your board and picks the right firmware automatically.

## Getting Started

1. Open the [installer](https://genereese.github.io/gsp32-install/) in Chrome or Edge on a desktop computer, and plug the board in with a USB data cable.
2. Click **Install GSP32**, choose your board's port, and confirm that installing erases the board. Keep the tab open until it finishes.
3. Choose **Set Up Wi-Fi** to connect the board to your network, or **USB Only**.
4. Open the board's web UI from the link shown, and choose whether to set a password on your first visit.

GSP32 serves its web UI over plain HTTP and is meant for your home network, not the open internet.

## License

The firmware is free to use and redistribute unmodified. See [LICENSE.txt](LICENSE.txt). The installer uses [esptool-js](https://github.com/espressif/esptool-js) (Apache-2.0, see `vendor/esptool-js-LICENSE`).
