""" Rebuilds firmware/gsp32-esp32.bin: bootloader 0x1000, partitions 0x8000, app 0x10000 from an ESP32-httpd firmware
build (out/<commit>-heap72), and the LittleFS vfs at 0x200000 with the current web UI files (their .gz copies made
here). boot.py, main.py, examples, pages and the default settings.json are kept from the previous image. No secrets:
no config.json or webui_auth.json is ever added.
Usage: build_image.py <ESP32-httpd checkout> <firmware out dir> """
import gzip, os, sys, littlefs
repo, out = sys.argv[1], sys.argv[2]
IMG = "firmware/gsp32-esp32.bin"
old = open(IMG, "rb").read()
fs = littlefs.LittleFS(block_size=4096, block_count=512, read_size=32, prog_size=32, lookahead_size=32, disk_version=0x00020000, mount=False)
fs.context.buffer = bytearray(old[0x200000:0x400000]); fs.mount()
# Round 22 layout: the web UI's settings in gsp32-httpd/config (was ui-data)
if "ui-data" in fs.listdir("/gsp32-httpd"):
    fs.rename("/gsp32-httpd/ui-data", "/gsp32-httpd/config")
web = os.path.join(repo, "gsp32-httpd")
for name in ("app.js", "files.js", "graphs.js", "style.css", "apps/backup.js", "apps/boards.js", "apps/libraries.js",
             "apps/logger.js", "apps/pins.js", "apps/schedule.js"):
    data = open(os.path.join(web, name), "rb").read()
    for path, body in (("/gsp32-httpd/" + name, data), ("/gsp32-httpd/" + name + ".gz", gzip.compress(data, 9, mtime=0))):
        with fs.open(path, "wb") as f:
            f.write(body)
for bad in ("/config.json", "/webui_auth.json"):
    assert bad[1:] not in fs.listdir("/"), bad
image = bytearray(b"\xff" * 0x400000)
for offset, part in ((0x1000, "bootloader.bin"), (0x8000, "partition-table.bin"), (0x10000, "micropython.bin")):
    data = open(os.path.join(out, part), "rb").read()
    image[offset:offset + len(data)] = data
image[0x200000:0x400000] = bytes(fs.context.buffer)
open(IMG, "wb").write(image)
print("image", len(image), "bytes; app", os.path.getsize(os.path.join(out, "micropython.bin")))
