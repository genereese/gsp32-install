""" Flasher 115.24 (Gene): V130 is the only version on the site; every older one (classic 114.2 Previous, Beta 115,
GSP32-C Betas V117-V129) was removed and stays in git history. The suites that test the page's handling of several
releases (Release dropdown, Previous, Beta, GSP32-C picks, the classic GSP32 install flow) run against an overlay: the
current site files with the 115.23 version list and its manifests and images taken back out of git (OLD below).
overlay(site) returns that folder (built once in the temp folder, shared by suites running side by side). """
import os, subprocess, tempfile, shutil, json, hashlib
OLD = "962b116"   # Flasher 115.23: V130 Stable, 114.2 Previous, Beta 115, GSP32-C Betas V129-V117
OLD_FILES = ["versions.json", "manifest.json", "manifest-beta.json", "manifest-gspc-beta.json"] + \
    ["manifest-gspc-v%s.json" % v for v in ("118", "119", "120", "121", "122", "123", "124", "125", "126", "127.1", "127.2", "127.3", "128", "129")] + \
    ["firmware/gsp32-esp32.bin", "firmware/gsp32-esp32c3.bin", "firmware/gsp32-esp32s3.bin", "firmware/gsp32-esp32s3-n8r8.bin",
     "firmware/gsp32-esp32s3-n8r2.bin", "firmware/beta", "firmware/gspc"] + \
    ["firmware/gspc-v%s" % v for v in ("118", "119", "120", "121", "122", "123", "124", "125", "126", "127.1", "127.2", "127.3", "128", "129")] + \
    ["manifest-v84.json", "manifest-v85.json", "manifest-v99.json", "firmware/v84", "firmware/v85", "firmware/v99"]  # Flasher 115.25: the rollbacks are gone from the site too

def overlay(site):
    head = subprocess.run(["git", "-C", site, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or "x"
    out = os.path.join(tempfile.gettempdir(), "flasher-oldsite-%s-%s-%05x" % (OLD, head, int(hashlib.md5(os.path.realpath(site).encode()).hexdigest()[:5], 16)))
    if os.path.exists(os.path.join(out, ".ready")):
        return out
    work = tempfile.mkdtemp(prefix=os.path.basename(out) + ".", dir=tempfile.gettempdir())
    # the old files out of git
    tar = subprocess.run(["git", "-C", site, "archive", "--format=tar", OLD] + OLD_FILES, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", work], input=tar, check=True)
    # everything else: the current site (links, nothing copied)
    for name in os.listdir(site):
        if name in (".git", "versions.json") or name.startswith("manifest") and os.path.exists(os.path.join(work, name)):
            continue
        if name == "firmware":
            for sub in os.listdir(os.path.join(site, "firmware")):
                if not os.path.exists(os.path.join(work, "firmware", sub)):
                    os.symlink(os.path.join(site, "firmware", sub), os.path.join(work, "firmware", sub))
            continue
        os.symlink(os.path.join(site, name), os.path.join(work, name))
    # the V130 entry as the current site has it (its label names the current build)
    cur = json.load(open(os.path.join(site, "versions.json")))
    old = json.load(open(os.path.join(work, "versions.json")))
    old[0] = cur[0]
    open(os.path.join(work, "versions.json"), "w").write(json.dumps(old, indent=2) + "\n")
    open(os.path.join(work, ".ready"), "w").write("ok")
    try:
        os.rename(work, out)
    except OSError:   # another suite made it first
        shutil.rmtree(work, ignore_errors=True)
    return out
