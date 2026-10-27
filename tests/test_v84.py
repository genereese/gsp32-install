""" Flasher V84: LICENSE.txt is there and linked from the footer; the plain-HTTP home-network note shows; V84 is the one
rollback (all four images) """
import json, os, sys
# GSP32-C Beta V117 (Gene): manifest-gspc-beta.json (the GSP32-C line) is expected next to the GSP32 manifests
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here); fails = 0
def check(ok, msg):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + msg)
html = open(os.path.join(site, "index.html")).read(); lic = open(os.path.join(site, "LICENSE.txt")).read()
check('<a href="LICENSE.txt">License</a>' in html, "footer links LICENSE.txt")
check("redistribute" in lic and "unmodified" in lic and "closed" in lic and "WITHOUT WARRANTY" in lic, "license: redistribute unmodified, closed source, no warranty")
check("plain HTTP" in html and "home network" in html, "plain-HTTP home-network note")
rb = json.load(open(os.path.join(site, "manifest-v84.json")))
paths = [p["path"] for b in rb["builds"] for p in b["parts"]]
check(len(paths) == 4 and all(p.startswith("firmware/v84/") and os.path.exists(os.path.join(site, p)) for p in paths), "V84 rollback: 4 images %r" % paths)
check(sorted(n for n in os.listdir(site) if n.startswith("manifest")) == ["manifest-beta.json", "manifest-gspc-beta.json", "manifest-gspc-v118.json", "manifest-gspc-v119.json", "manifest-gspc-v120.json", "manifest-gspc-v121.json", "manifest-gspc-v122.json", "manifest-gspc-v123.json", "manifest-gspc-v124.json", "manifest-gspc-v125.json", "manifest-gspc-v126.json", "manifest-gspc-v127.1.json", "manifest-gspc-v127.2.json", "manifest-gspc-v127.3.json", "manifest-gspc-v128.json", "manifest-v84.json", "manifest-v85.json", "manifest-v99.json", "manifest.json"] and os.listdir(os.path.join(site, "firmware")).count("v83") == 0, "single rollback")
print("FAILS", fails); sys.exit(1 if fails else 0)
