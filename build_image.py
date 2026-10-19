""" Rebuilds firmware/gsp32-esp32.bin: bootloader 0x1000, partitions 0x8000, app 0x10000 from a GSP32 (github.com/genereese/GSP32, formerly ESP32-httpd) firmware
build (out/<commit>-heap72), and the LittleFS vfs (Version 99: where the build's partition table puts it) with the current web UI files (Version 43: the
web UI's styles, scripts and examples are in the firmware and removed from the image). boot.py, your other pages and the default settings.json are kept from the previous image; main.py, index.html and menu.html come from the repo (Version 65). No secrets:
no config.json or webui_auth.json is ever added.
Usage: build_image.py <GSP32 checkout> <firmware out dir> """
import os, sys
repo, out = sys.argv[1], sys.argv[2]
# Version 99 (Gene): the file system's place comes from each image's own partition table (GSP32 firmware/fs_layout.py):
#  the previous image's files are read from where its table puts them (0x200000 before V99) and go into a new LittleFS
#  where the new build's table puts it (0x290000 to the end since V99)
sys.path.insert(0, os.path.join(repo, "firmware"))
import fs_layout
IMG = "firmware/gsp32-esp32.bin"
old = open(IMG, "rb").read()
fs = fs_layout.imageFs(old)
# Round 22 layout: the web UI's settings in gsp32-httpd/config (was ui-data)
if "ui-data" in fs.listdir("/gsp32-httpd"):
    fs.rename("/gsp32-httpd/ui-data", "/gsp32-httpd/config")
# Version 43: the web UI's styles, scripts and starter programs are built into the firmware (GSP32
#  firmware/stage_webui.py, webassets), so the file system holds none of them: old copies are taken out of the image
def removeTree(path):
    for name in fs.listdir(path):
        child = path + "/" + name
        if fs.stat(child).type == 2:
            removeTree(child)
        else:
            fs.remove(child)
    fs.remove(path)
for name in ("app.js", "files.js", "graphs.js", "style.css"):
    for path in ("/gsp32-httpd/" + name, "/gsp32-httpd/" + name + ".gz"):
        try:
            fs.remove(path)
        except Exception:
            pass
for folder in ("apps", "examples"):
    if folder in fs.listdir("/gsp32-httpd"):
        removeTree("/gsp32-httpd/" + folder)
for name in fs.listdir("/"):
    if name.startswith("webui") and name.endswith((".py", ".mpy")):
        fs.remove("/" + name)
# Version 35: the stock start page comes from the repo too (Examples link removed)
# Version 65: the stock main.py, start page and menu come from the repo (a working Pages example); the Dashboard,
#  control and live value starter pages are gone
for name in ("dashboard.html", "example.html", "live.html"):
    if name in fs.listdir("/gsp32-httpd/pages"):
        fs.remove("/gsp32-httpd/pages/" + name)
for source, target in (("gsp32-httpd/pages/index.html", "/gsp32-httpd/pages/index.html"), ("gsp32-httpd/pages/menu.html", "/gsp32-httpd/pages/menu.html"),
                       ("main.py", "/main.py"), ("LICENSE.txt", "/LICENSE.txt")):
    # Version 84: the firmware license sits in the board's top folder (GSP32 repo LICENSE.txt)
    if not os.path.exists(os.path.join(repo, source)):
        continue
    with fs.open(target, "wb") as f:
        f.write(open(os.path.join(repo, source), "rb").read())
for bad in ("/config.json", "/webui_auth.json", "/webui_ai.json"):
    assert bad[1:] not in fs.listdir("/"), bad
table = open(os.path.join(out, "partition-table.bin"), "rb").read()
new_fs, fs_offset, fs_size = fs_layout.newFs(table)
fs_layout.copyTree(fs, new_fs)
image = bytearray(b"\xff" * (fs_offset + fs_size))
for offset, part in ((0x1000, "bootloader.bin"), (0x8000, "partition-table.bin"), (0x10000, "micropython.bin")):
    data = open(os.path.join(out, part), "rb").read()
    image[offset:offset + len(data)] = data
image[fs_offset:] = bytes(new_fs.context.buffer)
open(IMG, "wb").write(image)
print("image", len(image), "bytes; app", os.path.getsize(os.path.join(out, "micropython.bin")), "; file system 0x%x+0x%x" % (fs_offset, fs_size))
