""" Flasher Version 105 (Gene): bumps the flasher version in one step: the footer (Flasher Version N), the cache tag on
style.css, app.js and tour.js (?v=N-fwM, M the firmware versions.json ships) and the tests that pin them
(test_v48, test_v64, test_v79, test_v80). Usage: python tools/bump_flasher.py [N]   (default: the next whole number) """
import glob, json, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    index = os.path.join(HERE, "index.html")
    html = open(index, encoding="utf-8").read()
    old = re.search(r"Flasher Version (\d+(?:\.\d+)?)", html).group(1)
    new = sys.argv[1] if len(sys.argv) > 1 else str(int(float(old)) + 1)
    firmware = re.search(r"Version (\d+(?:\.\d+)?)", json.load(open(os.path.join(HERE, "versions.json")))[0]["label"]).group(1)
    old_tag = re.search(r"\?v=([\w.-]+)", html).group(1)
    new_tag = "%s-fw%s" % (new, firmware)
    changed = []
    for path in [index] + sorted(glob.glob(os.path.join(HERE, "tests", "test_*.py"))):
        text = open(path, encoding="utf-8").read()
        lines = []
        for line in text.split("\n"):
            # history comments ("# Flasher Version 104 (Gene): ...") stay as they are
            if not (line.lstrip().startswith("#")):
                line = line.replace("Flasher Version " + old, "Flasher Version " + new).replace(old_tag, new_tag)
                line = line.replace('["flasher_version"] == "%s"' % old, '["flasher_version"] == "%s"' % new)
            lines.append(line)
        result = "\n".join(lines)
        if (os.path.basename(path) == "index.html"):
            assert result.count("?v=" + new_tag) == 3, "index.html: expected three ?v= tags"
        if (result != text):
            open(path, "w", encoding="utf-8").write(result)
            changed.append(os.path.relpath(path, HERE))
    print("Flasher Version %s -> %s, cache tag %s -> %s: %s" % (old, new, old_tag, new_tag, ", ".join(changed)))

if __name__ == "__main__":
    main()
