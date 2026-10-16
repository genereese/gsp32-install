""" Flasher V84: LICENSE.txt is there and linked from the footer; the plain-HTTP home-network note shows; V84 is the one
rollback (all four images) """
import json, os, sys
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
check(sorted(n for n in os.listdir(site) if n.startswith("manifest")) == ["manifest-v84.json", "manifest.json"] and os.listdir(os.path.join(site, "firmware")).count("v83") == 0 and "beta" not in os.listdir(os.path.join(site, "firmware")), "single rollback")
print("FAILS", fails); sys.exit(1 if fails else 0)
