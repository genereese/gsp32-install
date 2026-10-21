""" Flasher Version 105.1: the trace run's Python side (tools/build_scope.py puts this folder on PYTHONPATH). Logs the files a suite
opens or imports to $GSP32_TRACE_DIR/<suite>.log,.
Whole-tree copies (shutil.copytree) are left out: a suite that copies the whole project reads nothing by that """
import os, sys

_dir = os.environ.get("GSP32_TRACE_DIR")
if (_dir) and (sys.argv) and os.path.basename(sys.argv[0]).startswith("test_"):
    _name = os.path.basename(sys.argv[0])[:-3] + ((":" + sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "")
    # a suite's own child Python (a script it starts) logs into the suite's file
    _path = os.environ.get("GSP32_TRACE_FILE") or os.path.join(_dir, _name.replace(":", "-") + ".log")
    os.environ["GSP32_TRACE_FILE"] = _path
    _out = open(_path, "a", buffering=1)
    _skip = ("tarfile", "zipfile", "tempfile", "linecache", "traceback")

    def _hook(event, args):
        if (event != "open") or not (args) or not isinstance(args[0], str):
            return
        try:
            frame = sys._getframe(1)
        except ValueError:
            frame = None
        while (frame is not None):
            module = frame.f_globals.get("__name__", "")
            if (module in _skip) or module.startswith(("playwright", "encodings")) or (frame.f_code.co_name in ("copytree", "_copytree")):
                return
            frame = frame.f_back
        try:
            _out.write(os.path.abspath(args[0]) + "\n")
        except Exception:
            pass

    sys.addaudithook(_hook)
