// Fake Web Serial board: logs setSignals, answers Improv (state, scan, wifi), prints boot lines on an RTS reset
(() => {
  const log = (window.__log = []);
  const enc = new TextEncoder();
  let ctrl = null, booted = false, rts = false, dtr = false, state = 2;
  const push = (bytes) => ctrl && ctrl.enqueue(bytes);
  const say = (text) => push(enc.encode(text));
  const pkt = (type, data) => {
    const b = [0x49,0x4d,0x50,0x52,0x4f,0x56,1,type,data.length,...data];
    let s = 0; for (const x of b) s = (s + x) & 255; return new Uint8Array([...b, s, 10]);
  };
  const strs = (cmd, list) => { const d = []; for (const t of list) { const e = enc.encode(t); d.push(e.length, ...e); } return pkt(4, [cmd, d.length, ...d]); };
  window.__say = (t) => say(t);
  window.__pk = 0; window.__ctrlc = 0; window.__badPk = 0; window.__listen = false;
  // Version 43.1: the web UI's listening window ends ("GSP32 Improv Off"); a packet after that is Ctrl-C to main.py
  window.__stopListening = () => { window.__listen = false; say("GSP32 Improv Off\r\n"); };
  function boot() {
    booted = false;
    window.__listen = false;
    // A half-flashed board: the ROM finds no valid app and restarts about once a second, forever
    if (window.__bootLoop) {
      if (!window.__loopTimer) window.__loopTimer = setInterval(() => say("ets Jul 29 2019 12:21:46\r\n\r\nrst:0x10 (RTCWDT_RTC_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\ninvalid header: 0xffffffff\r\n"), 900);
      return;
    }
    if (window.__other) { setTimeout(() => say("rst:0x1 (POWERON_RESET)\r\nMicroPython v1.25.0 on 2025-04-15; Generic ESP32 module with ESP32\r\n>>> "), 300); return; }
    const gap = window.__bootGap || 0;
    if (gap) setTimeout(() => say((window.__ets ? "ets Jul 29 2019 12:21:46\r\n\r\n" : "") + "rst:0x1 (POWERON_RESET)\r\n"), 300);
    setTimeout(() => { booted = true; say((gap ? "" : (window.__ets ? "ets Jul 29 2019 12:21:46\r\n\r\n" : "") + "rst:0x1 (POWERON_RESET)\r\n") + "mDNS name: gsp32.local\r\n" + (window.__noReady ? "" : "GSP32 Improv Ready\r\n") + "Press Enter within 10 s\r\nServer listening on port 80\r\nWeb UI running in the background\r\n" + (window.__oldFw ? "" : "GSP32 Improv Listening\r\n")); window.__listen = !window.__oldFw; }, 300 + gap);
    if (window.__savedWifi) setTimeout(() => say("Connecting to WiFi...\r\n"), 350 + gap);
    if (window.__savedWifi && !window.__wifiNever) setTimeout(() => say("Connection successful\r\nNetwork config: ('192.168.2.77', '255.255.255.0', '192.168.2.1', '192.168.2.1')\r\n"), 350 + gap + (window.__wifiDelay || 3000));
    setTimeout(() => { booted = true; if (window.__wifi) say("Connection successful\r\nNetwork config: ('192.168.2.77', '255.255.255.0', '192.168.2.1', '192.168.2.1')\r\n"); }, 1500);
  }
  let buf = [];
  function onWrite(bytes) {
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
      const cmd = data[0];
      if (cmd === 2) push(pkt(1, [state]));
      if (cmd === 3) { window.__info = (window.__info || 0) + 1; push(strs(3, ["GSP32", window.__ver || "1.0", "ESP32", "gsp32"])); }
      if (cmd === 4) { if (!window.__noNets) { push(strs(4, ["HomeNet", "-50", "YES"])); push(strs(4, ["Cafe", "-80", "NO"])); } push(strs(4, [])); }
      if (cmd === 1) { push(pkt(1, [3])); setTimeout(() => { window.__wifi = true; push(pkt(1, [4])); push(strs(1, ["http://192.168.2.77/"])); }, 400); }
    }
  }
  // Like Web Serial: after a reader cancels, port.readable is a fresh stream
  let rs = null, isOpen = false;
  const fresh = () => new ReadableStream({ start(c) { ctrl = c; }, cancel() { rs = null; } });
  const port = {
    get readable() { if (!isOpen) return null; if (!rs) rs = fresh(); return rs; },
    writable: null,
    async open(o) { log.push("open " + o.baudRate); isOpen = true; rs = null; this.writable = new WritableStream({ write: (c) => onWrite(c) }); },
    async close() { log.push("close dtr=" + dtr + " rts=" + rts); isOpen = false; rs = null; this.writable = null; },
    async setSignals(s) {
      if ("dataTerminalReady" in s) dtr = s.dataTerminalReady;
      const was = rts; if ("requestToSend" in s) rts = s.requestToSend;
      log.push("signals dtr=" + dtr + " rts=" + rts);
      if (was && !rts && !dtr) { log.push("RESET"); boot(); }
    },
  };
  window.__port = port;
  Object.defineProperty(navigator, "serial", { value: { requestPort: async () => port, addEventListener() {} } });
})();
