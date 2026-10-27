// Fake Web Serial board: logs setSignals, answers Improv (state, scan, wifi), prints boot lines on an RTS reset
(() => {
  const log = (window.__log = []);
  const enc = new TextEncoder();
  let ctrl = null, booted = false, rts = false, dtr = false, state = 2;
  const push = (bytes) => { try { if (ctrl) ctrl.enqueue(bytes); } catch (e) { /* stream closed during probe/reset */ } };
  const say = (text) => push(enc.encode(text));
  const pkt = (type, data) => {
    const b = [0x49,0x4d,0x50,0x52,0x4f,0x56,1,type,data.length,...data];
    let s = 0; for (const x of b) s = (s + x) & 255; return new Uint8Array([...b, s, 10]);
  };
  const strs = (cmd, list) => { const d = []; for (const t of list) { const e = enc.encode(t); d.push(e.length, ...e); } return pkt(4, [cmd, d.length, ...d]); };
  window.__say = (t) => say(t);
  window.__sayBytes = (arr) => push(new Uint8Array(arr));
  window.__pk = 0; window.__ctrlc = 0; window.__badPk = 0; window.__listen = false;
  // Version 43.1: the web UI's listening window ends ("GSP32 Improv Off"); a packet after that is Ctrl-C to main.py
  window.__stopListening = () => { window.__listen = false; say("GSP32 Improv Off\r\n"); };
  function boot() {
    booted = false;
    window.__mainPy = false;
    window.__listen = false;
    // A half-flashed board: the ROM finds no valid app and restarts about once a second, forever
    if (window.__bootLoop) {
      if (!window.__loopTimer) window.__loopTimer = setInterval(() => say("ets Jul 29 2019 12:21:46\r\n\r\nrst:0x10 (RTCWDT_RTC_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\ninvalid header: 0xffffffff\r\n"), 900);
      return;
    }
    // A scripted restart (window.__bootScript = [[ms, text, listen?], ...]): a real board's output, piece by piece
    if (Array.isArray(window.__bootScript)) { for (const [ms, text, listen] of window.__bootScript) setTimeout(() => { booted = true; if (listen !== undefined) window.__listen = listen;
      // Flasher Version 115.10: GSP32-C's main.py in the foreground: Improv packets go nowhere until Ctrl-C
      if (/main\.py running/.test(text)) window.__mainPy = true;
      say(text); }, ms); return; }
    if (window.__other) { setTimeout(() => say("rst:0x1 (POWERON_RESET)\r\nMicroPython v1.25.0 on 2025-04-15; Generic ESP32 module with ESP32\r\n>>> "), 300); return; }
    // GSP32-C (window.__gspc = "125"): its start-up line, then the prompt; from V121 it takes Improv packets at any time
    if (window.__gspc) { setTimeout(() => { booted = true; window.__listen = Number(window.__gspc) >= 121; say("rst:0x1 (POWERON_RESET)\r\n\r\nGSP32-C Beta V" + window.__gspc + " on ESP32 (2 cores), boot 1, reset: power on\r\n" + (window.__wifi ? "Wi-Fi: 192.168.2.77\r\n" : "") + "MicroPython v1.25.0 on 2026-10-26; GSP32-C with ESP32\r\n>>> "); }, 300); return; }
    const gap = window.__bootGap || 0;
    if (gap) setTimeout(() => say((window.__ets ? "ets Jul 29 2019 12:21:46\r\n\r\n" : "") + "rst:0x1 (POWERON_RESET)\r\n"), 300);
    setTimeout(() => { booted = true; say((gap ? "" : (window.__ets ? "ets Jul 29 2019 12:21:46\r\n\r\n" : "") + "rst:0x1 (POWERON_RESET)\r\n") + "mDNS name: gsp32.local\r\n" + (window.__noReady ? "" : "GSP32 Improv Ready\r\n") + "Press Enter within 10 s\r\nServer listening on port 80\r\nWeb UI running in the background\r\n" + (window.__oldFw ? "" : "GSP32 Improv Listening\r\n")); window.__listen = !window.__oldFw; }, 300 + gap);
    if (window.__savedWifi) setTimeout(() => say("Connecting to WiFi...\r\n"), 350 + gap);
    if (window.__savedWifi && !window.__wifiNever) setTimeout(() => say("Connection successful\r\nNetwork config: ('192.168.2.77', '255.255.255.0', '192.168.2.1', '192.168.2.1')\r\n"), 350 + gap + (window.__wifiDelay || 3000));
    setTimeout(() => { booted = true; if (window.__wifi) say("Connection successful\r\nNetwork config: ('192.168.2.77', '255.255.255.0', '192.168.2.1', '192.168.2.1')\r\n"); }, 1500);
  }
  let buf = [];
  function onWrite(bytes) {
    // Flasher Version 114.2: esptool's SYNC frame (command 0x08) counted; __onSync: what a started board does with it
    if (bytes[0] === 0xc0 && bytes[1] === 0x00 && bytes[2] === 0x08) { window.__syncs = (window.__syncs || 0) + 1; log.push("SYNC"); if (window.__onSync) window.__onSync(); return; }
    window.__typed = (window.__typed || "") + String.fromCharCode(...bytes);
    // Flasher Version 115.10: Ctrl-C alone stops main.py (unless __mainPyStuck): the traceback, then the prompt
    if (bytes.length === 1 && bytes[0] === 3) window.__ctrl1 = (window.__ctrl1 || 0) + 1;
    if (bytes.length === 1 && bytes[0] === 3 && window.__mainPy && !window.__mainPyStuck) {
      window.__mainPy = false;
      setTimeout(() => say("Traceback (most recent call last):\r\n  File \"main.py\", line 9, in <module>\r\nKeyboardInterrupt: \r\nMicroPython v1.25.0 on 2026-10-26; GSP32-C with ESP32\r\nType \"help()\" for more information.\r\n>>> "), 150);
    }
    if (!buf.length && bytes[0] === 3) window.__ctrlc++;
    buf.push(...bytes);
    while (true) {
      const i = buf.findIndex((x, k) => x === 0x49 && buf[k+1] === 0x4d);
      if (i < 0 || buf.length < i + 9) return;
      const len = buf[i+8]; if (buf.length < i + 11 + len) return;
      const data = buf.slice(i+9, i+9+len); buf = buf.slice(i+11+len);
      window.__pk++;
      if (!window.__listen) { window.__badPk++; window.__badBytes = (window.__badBytes || "") + String.fromCharCode(...data); continue; }
      if (!booted || window.__other) continue;
      if (window.__mainPy) { window.__blockedPk = (window.__blockedPk || 0) + 1; continue; }
      const cmd = data[0];
      if (cmd === 2) push(pkt(1, [state]));
      if (cmd === 3) { window.__info = (window.__info || 0) + 1; push(strs(3, window.__gspc ? ["GSP32-C", "Beta V" + window.__gspc, "ESP32", "gsp32c"] : ["GSP32", window.__ver || "1.0", "ESP32", "gsp32"])); }
      if (cmd === 4) { const scan = () => { if (!window.__noNets) { push(strs(4, ["HomeNet", "-50", "YES"])); push(strs(4, ["Cafe", "-80", "NO"])); } push(strs(4, [])); };
        if (window.__scanDelay) setTimeout(scan, window.__scanDelay); else scan(); }
      if (cmd === 1) { window.__wifiSet = String.fromCharCode(...data.slice(3, 3 + data[2])); push(pkt(1, [3])); setTimeout(() => { window.__wifi = true; push(pkt(1, [4])); push(strs(1, ["http://192.168.2.77/"])); }, 400); }
    }
  }
  // Like Web Serial: after a reader cancels, port.readable is a fresh stream
  let rs = null, isOpen = false;
  const fresh = () => new ReadableStream({ start(c) { ctrl = c; }, cancel() { ctrl = null; rs = null; } });
  const port = {
    get readable() { if (!isOpen) return null; if (!rs) rs = fresh(); return rs; },
    writable: null,
    getInfo() { return window.__usb || { usbVendorId: 0x10c4, usbProductId: 0xea60 }; },
    async open(o) { log.push("open " + o.baudRate); isOpen = true;
      // Flasher Version 115.10: like Chromium on Windows, the port comes up with DTR and RTS both on (the board runs)
      if (window.__openAsserts) { dtr = true; rts = true; log.push("opened dtr=true rts=true"); } rs = null; this.writable = new WritableStream({ write: (c) => onWrite(c) });
      // Version 62: a stray byte from the UART switch lands just after a reopen at a fast rate (Gene's first real install)
      // Version 63: a board that restarts on the reopen prints its boot output at its own rate: hundreds of bytes
      if (o.baudRate !== 115200) { window.__fastOpen = true; window.__signalsAfterFast = 0; } else window.__fastOpen = false;
      if (window.__restartOnSwitch && o.baudRate !== 115200) setTimeout(() => { if (isOpen && port.readable) { ctrl.enqueue(new Uint8Array(400).fill(0x66)); ctrl.enqueue(new Uint8Array(600).fill(0x78)); } }, 10);
      if (window.__glitch && o.baudRate !== 115200) setTimeout(() => { if (isOpen && port.readable) { ctrl.enqueue(new Uint8Array([0x80])); log.push("stray byte"); } }, 10); },
    async close() { log.push("close dtr=" + dtr + " rts=" + rts); isOpen = false; rs = null; this.writable = null; },
    async setSignals(s) {
      if (window.__fastOpen) window.__signalsAfterFast++;
      // Flasher Version 115.11: one line at a time, DTR first, as the Web Serial spec orders a setSignals call (and
      //  Chromium does it). __lines logs each line change with its time; __enPulses counts EN pulled low (RTS on,
      //  DTR off: the auto-reset transistor), which a running board takes as a restart
      const line = (name, v) => { (window.__lines = window.__lines || []).push([name + "=" + v, performance.now()]);
        const low = rts && !dtr; if (low && !window.__enLow) window.__enPulses = (window.__enPulses || 0) + 1; window.__enLow = low; };
      if ("dataTerminalReady" in s) { dtr = s.dataTerminalReady; line("dtr", dtr); }
      const was = rts; if ("requestToSend" in s) { rts = s.requestToSend; line("rts", rts); }
      log.push("signals dtr=" + dtr + " rts=" + rts);
      if (was && !rts && !dtr) { log.push("RESET"); boot(); }
    },
  };
  window.__port = port;
  // Fix (false disconnect): line noise (a FramingError, BreakError, ...) errors the open stream; the port stays open and
  //  port.readable is a fresh stream, as in Chromium
  window.__serialError = (name) => { const c = ctrl; rs = null; ctrl = null; log.push("serial error " + name);
    try { if (c) c.error(new DOMException("Serial line error", name)); } catch (e) {} };
  // Version 61: a pulled cable: the port closes under the page, open readers error, then the disconnect event
  const unplugged = [];
  window.__unplug = () => { log.push("UNPLUG"); try { ctrl && ctrl.error(new TypeError("The device has been lost.")); } catch (e) {} isOpen = false; rs = null; port.writable = null;
    unplugged.forEach((fn) => fn({ target: port })); };
  Object.defineProperty(navigator, "serial", { value: { requestPort: async () => port, addEventListener(type, fn) { if (type === "disconnect") unplugged.push(fn); } } });
})();
