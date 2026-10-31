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
# Flasher 115.25 (Gene, "remove all previous versions"): the unlisted rollbacks V84, V85 and V99 are gone from the site
#  (git history keeps them; tests/oldsite.py brings them back for test_v79). The site has GSP32-C V130 and Beta V132 only (115.26). 115.27: V133 Stable and V130 Previous. 115.28: plus Beta V134. 115.29: V135 only
mans = sorted(n for n in os.listdir(site) if n.startswith("manifest"))
check(mans == ["manifest-gspc-v136.1.json", "manifest-gspc-v136.json"], "manifests: V136 and Beta V136.1 only (115.32), no rollbacks: %r" % mans)
check(not any(os.path.exists(os.path.join(site, "firmware", d)) for d in ("v84", "v85", "v99")), "firmware/v84, v85, v99 gone")
print("FAILS", fails); sys.exit(1 if fails else 0)
