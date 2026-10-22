// ESP32 (classic, CP2102 bridge) emulator behind a Chromium-like Web Serial port, for the real esptool-js 0.5.7.
// ROM: SYNC (8 replies), READ_REG/WRITE_REG, MEM_BEGIN/DATA/END -> "OHAI" stub. Stub: SPI_ATTACH, SET_PARAMS,
// ERASE_FLASH, FLASH_DEFL_BEGIN/DATA/END, SPI_FLASH_MD5, READ_REG/WRITE_REG, CHANGE_BAUD.
// Records every port API call (window.__trace) and every byte written (window.__wire) so two app.js versions can be
// compared call for call. Options: window.__emu = {seed, chunk (max read chunk), bps (bytes per ms the line moves),
// eraseMs, blockMs}
(() => {
  const opt = Object.assign({ seed: 1, chunk: 64, bps: 11.52 * 40, eraseMs: 150, blockMs: 2, appBoot: true }, window.__emu || {});
  let seed = opt.seed >>> 0 || 1;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) >>> 0) / 4294967296);
  const trace = (window.__trace = []);
  const T = (s) => trace.push(s);
  const enc = new TextEncoder();
  // --- md5 (RFC 1321) ---
  function md5(bytes) {
    const K = [], S = [7,12,17,22,7,12,17,22,7,12,17,22,7,12,17,22,5,9,14,20,5,9,14,20,5,9,14,20,5,9,14,20,4,11,16,23,4,11,16,23,4,11,16,23,4,11,16,23,6,10,15,21,6,10,15,21,6,10,15,21,6,10,15,21];
    for (let i = 0; i < 64; i++) K[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 4294967296) >>> 0;
    const n = bytes.length, total = ((n + 8) >>> 6) + 1, w = new Uint32Array(total * 16);
    for (let i = 0; i < n; i++) w[i >> 2] |= bytes[i] << ((i % 4) * 8);
    w[n >> 2] |= 0x80 << ((n % 4) * 8);
    w[total * 16 - 2] = (n * 8) >>> 0; w[total * 16 - 1] = Math.floor(n / 536870912);
    let a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
    for (let j = 0; j < total * 16; j += 16) {
      let a = a0, b = b0, c = c0, d = d0;
      for (let i = 0; i < 64; i++) {
        let f, g;
        if (i < 16) { f = (b & c) | (~b & d); g = i; } else if (i < 32) { f = (d & b) | (~d & c); g = (5 * i + 1) % 16; }
        else if (i < 48) { f = b ^ c ^ d; g = (3 * i + 5) % 16; } else { f = c ^ (b | ~d); g = (7 * i) % 16; }
        const t = d; d = c; c = b;
        const x = (a + f + K[i] + w[j + g]) >>> 0;
        b = (b + ((x << S[i]) | (x >>> (32 - S[i])))) >>> 0; a = t;
      }
      a0 = (a0 + a) >>> 0; b0 = (b0 + b) >>> 0; c0 = (c0 + c) >>> 0; d0 = (d0 + d) >>> 0;
    }
    const out = new Uint8Array(16);
    [a0, b0, c0, d0].forEach((v, k) => { for (let i = 0; i < 4; i++) out[k * 4 + i] = (v >>> (8 * i)) & 255; });
    return out;
  }
  window.__md5 = md5;
  // --- the chip ---
  const FLASH_SIZE = 4 * 1024 * 1024;
  const flash = new Uint8Array(FLASH_SIZE).fill(0xff);
  let boot = 0, mode = "app", stub = false, en = true, io0 = true, dtr = false, rts = false;
  const regs = { 0x40001000: 0x00f01d83, 0x3ff5a004: 0xb72205e8, 0x3ff5a008: 0x0000f8b3, 0x3ff40014: 694, 0x3ff42080: 0x1640ef };
  let rx = [], inFrame = false, esc = false, frame = [];
  let defl = null;
  const stats = (window.__emuStats = { frames: 0, blocks: 0, badSeq: 0, badChecksum: 0, md5: [], erase: 0, resets: [], garbage: 0 });
  function slip(bytes) {
    const o = [0xc0];
    for (const b of bytes) { if (b === 0xc0) o.push(0xdb, 0xdc); else if (b === 0xdb) o.push(0xdb, 0xdd); else o.push(b); }
    o.push(0xc0); return o;
  }
  function reply(op, val, data) {
    const status = stub ? [0, 0] : [0, 0, 0, 0];
    const body = [...(data || []), ...status];
    const p = [1, op, body.length & 255, body.length >> 8, val & 255, (val >> 8) & 255, (val >> 16) & 255, (val >>> 24) & 255, ...body];
    send(slip(p));
  }
  // Bytes the board sends: delivered in chunks of at most opt.chunk, paced like the line
  let outQ = [], pumping = false;
  function send(bytes) { outQ.push(...bytes); if (!pumping) pump(); }
  function pump() {
    pumping = true;
    if (!outQ.length) { pumping = false; return; }
    // Chunks of random size (at most opt.chunk), as many per timer tick as the line moves in about 4 ms (a browser
    //  timer is not finer than that), so small chunks are not slower than the line
    const parts = []; let ms = 0;
    while (outQ.length && ms < 4) {
      const n = Math.max(1, Math.min(outQ.length, 1 + Math.floor(rnd() * opt.chunk)));
      parts.push(outQ.splice(0, n)); ms += n / opt.bps;
    }
    setTimeout(() => { for (const part of parts) deliver(new Uint8Array(part)); pump(); }, ms);
  }
  const u32 = (d, o) => (d[o] | (d[o + 1] << 8) | (d[o + 2] << 16) | (d[o + 3] << 24)) >>> 0;
  async function command(p) {
    stats.frames++;
    if (p.length < 8 || p[0] !== 0) return;
    const op = p[1], len = p[2] | (p[3] << 8), chk = u32(p, 4), d = p.slice(8, 8 + len);
    if (mode !== "rom") return;
    switch (op) {
      case 0x08: if (!stub) for (let i = 0; i < 8; i++) reply(op, 0x20120707, []); else reply(op, 0, []); return;
      case 0x0a: reply(op, regs[u32(d, 0)] || 0, []); return;
      case 0x09: regs[u32(d, 0)] = u32(d, 4); reply(op, 0, []); return;
      case 0x05: case 0x07: reply(op, 0, []); return;
      case 0x06: reply(op, 0, []); if (u32(d, 0) !== 0) return; setTimeout(() => { stub = true; send(slip([...enc.encode("OHAI")])); }, 5); return;
      case 0x0d: case 0x0b: case 0x0f: reply(op, 0, []); return;
      case 0xd0: stats.erase++; flash.fill(0xff); setTimeout(() => reply(op, 0, []), opt.eraseMs); return;
      case 0x10: {
        const offset = u32(d, 12);
        const ds = new DecompressionStream("deflate"); const w = ds.writable.getWriter(); const r = ds.readable.getReader();
        defl = { offset, pos: offset, seq: 0, w, done: (async () => { for (;;) { const { value, done } = await r.read(); if (done) break; flash.set(value, defl.pos); defl.pos += value.length; } })().catch((e) => { stats.inflateError = String(e); }) };
        reply(op, 0, []); return;
      }
      case 0x11: {
        stats.blocks++;
        const size = u32(d, 0), seq = u32(d, 4), data = d.slice(16, 16 + size);
        // Faults (each once per page): a flipped byte on the wire (line noise), a stray byte or a serial error before the reply
        const f = opt.faults || {};
        if (f.corrupt === stats.blocks && !f.corruptDone) { f.corruptDone = true; data[100] ^= 0x5a; T("FAULT corrupt block " + stats.blocks); }
        if (f.stray === stats.blocks && !f.strayDone) { f.strayDone = true; send([0xff]); T("FAULT stray 0xff block " + stats.blocks); }
        if (f.serialError === stats.blocks && !f.errDone) { f.errDone = true; T("FAULT serial error block " + stats.blocks); setTimeout(() => window.__serialError("BreakError"), 0); }
        if (f.dropReply === stats.blocks && !f.dropDone) { f.dropDone = true; T("FAULT reply dropped block " + stats.blocks); return; }
        let sum = 0xef; for (const b of data) sum ^= b;
        if (sum !== (chk & 255)) stats.badChecksum++;
        if (!defl || seq !== defl.seq) stats.badSeq++;
        if (defl) { defl.seq = seq + 1; defl.w.write(new Uint8Array(data)).catch(() => {}); }
        setTimeout(() => reply(op, 0, []), opt.blockMs); return;
      }
      case 0x12: reply(op, 0, []); return;
      case 0x13: {
        const addr = u32(d, 0), size = u32(d, 4);
        if (defl && !defl.closed) { defl.closed = true; defl.w.close().catch(() => {}); await defl.done; }
        const sum = md5(flash.subarray(addr, addr + size)); stats.md5.push([addr, size, Array.from(sum).map((x) => x.toString(16).padStart(2, "0")).join("")]);
        reply(op, 0, Array.from(sum)); return;
      }
      default: reply(op, 0, []);
    }
  }
  let busy = Promise.resolve();
  function receive(bytes) {
    for (const b of bytes) {
      if (!inFrame) { if (b === 0xc0) { inFrame = true; frame = []; } else stats.garbage++; continue; }
      if (esc) { esc = false; frame.push(b === 0xdc ? 0xc0 : b === 0xdd ? 0xdb : b); continue; }
      if (b === 0xdb) { esc = true; continue; }
      if (b === 0xc0) { if (frame.length) { const f = frame; busy = busy.then(() => command(f)); inFrame = false; } continue; }
      frame.push(b);
    }
  }
  // The classic auto-reset circuit: EN = !(RTS && !DTR), IO0 = !(DTR && !RTS). EN has an RC delay (about 5 ms here):
  //  the chip leaves reset only once EN stayed high that long, and reads IO0 then (download mode when it is low)
  let enTimer = null;
  function signals() {
    const enNow = !(rts && !dtr);
    io0 = !(dtr && !rts);
    if (!enNow) { clearTimeout(enTimer); enTimer = null; en = false; mode = "reset"; return; }
    if (!en && !enTimer) enTimer = setTimeout(() => {
      enTimer = null; en = true;
      const bootNow = ++boot;
      mode = io0 ? "app" : "rom"; stub = false; defl = null; inFrame = false; frame = []; outQ = [];
      stats.resets.push(mode);
      // The ROM's banner comes in one read (about 100 bytes, one USB transfer)
      if (mode === "rom") deliver(new Uint8Array([...enc.encode("rst:0x1 (POWERON_RESET),boot:0x3 (DOWNLOAD_BOOT(UART0/UART1/SDIO_REI_REO_V2))\r\nwaiting for download\r\n")]));
      else if (opt.appBoot) setTimeout(() => boot === bootNow && mode === "app" && send([...enc.encode("ets Jul 29 2019 12:21:46\r\n\r\nrst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\nmDNS name: gsp32.local\r\nGSP32 Improv Ready\r\nServer listening on port 80\r\nWeb UI running in the background\r\nGSP32 Improv Listening\r\n")]), 50);
    }, 5);
  }
  // --- a Chromium-like port ---
  let isOpen = false, rs = null, ctrl = null, ws = null, readerN = 0, writerN = 0;
  function deliver(bytes) { if (ctrl) { try { ctrl.enqueue(bytes); } catch (e) {} } }
  function fresh() {
    const id = ++readerN;
    T("readable new #" + id);
    const stream = new ReadableStream({ start(c) { ctrl = c; }, cancel() { T("readable cancel #" + id); ctrl = null; rs = null; } });
    const getReader = stream.getReader.bind(stream);
    stream.getReader = function () {
      const r = getReader(); const rid = id; T("getReader #" + rid);
      const read = r.read.bind(r), cancel = r.cancel.bind(r), release = r.releaseLock.bind(r);
      r.read = () => read();
      r.cancel = (why) => { T("reader.cancel #" + rid); return cancel(why); };
      r.releaseLock = () => { T("reader.releaseLock #" + rid); return release(); };
      return r;
    };
    return stream;
  }
  window.__wire = [];
  function freshWritable() {
    const id = ++writerN;
    const stream = new WritableStream({
      write(chunk) {
        const bytes = new Uint8Array(chunk);
        window.__wire.push(bytes.length);
        T("write " + bytes.length + " " + Array.from(md5(bytes).slice(0, 4)).map((x) => x.toString(16).padStart(2, "0")).join(""));
        const f = opt.faults || {};
        let wait = bytes.length / opt.bps;
        if (f.slowWrite && bytes.length > 4000) { f.big = (f.big || 0) + 1; if (f.big === f.slowWrite) { wait = f.slowMs || 9000; T("FAULT slow write " + wait + " ms"); } }
        return new Promise((res) => setTimeout(() => { if (mode === "rom") receive(bytes); res(); }, wait));
      },
      abort() { T("writable abort #" + id); },
    });
    const getWriter = stream.getWriter.bind(stream);
    stream.getWriter = function () {
      const w = getWriter(); T("getWriter");
      const rel = w.releaseLock.bind(w), ab = w.abort.bind(w);
      w.releaseLock = () => { T("writer.releaseLock"); return rel(); };
      w.abort = (e) => { T("writer.abort"); return ab(e); };
      return w;
    };
    return stream;
  }
  const port = {
    get readable() { if (!isOpen) return null; if (!rs) rs = fresh(); return rs; },
    get writable() { return isOpen ? ws : null; },
    getInfo() { return window.__usb || { usbVendorId: 0x10c4, usbProductId: 0xea60 }; },
    async open(o) { T("open " + o.baudRate); if (isOpen) throw new DOMException("The port is already open.", "InvalidStateError"); isOpen = true; rs = null; ws = freshWritable(); },
    async close() {
      T("close");
      if (rs && rs.locked) throw new TypeError("Cannot cancel a locked stream");
      if (ws && ws.locked) throw new TypeError("Cannot abort a locked stream");
      isOpen = false; rs = null; ctrl = null; ws = null;
    },
    async setSignals(s) {
      T("signals " + JSON.stringify(s));
      if ("dataTerminalReady" in s) dtr = s.dataTerminalReady;
      if ("requestToSend" in s) rts = s.requestToSend;
      signals();
    },
    addEventListener() {}, removeEventListener() {},
  };
  window.__port = port;
  window.__serialError = (name) => { const c = ctrl; rs = null; ctrl = null; T("serial error " + name); try { if (c) c.error(new DOMException("Serial line error", name)); } catch (e) {} };
  window.__flash = flash;
  Object.defineProperty(navigator, "serial", { value: { requestPort: async () => port, getPorts: async () => [port], addEventListener() {}, removeEventListener() {} } });
})();
