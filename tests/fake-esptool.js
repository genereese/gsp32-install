export class Transport { constructor(device) { this.device = device; } async flushInput() {} }
export class ESPLoader {
  constructor(o) { this.t = o.transport; this.term = o.terminal; window.__log.push("loader baud " + o.baudrate); this.chip = { getChipDescription: async () => "ESP32-D0WD-V3 (revision v3.1)", readMac: async () => { if ((window.__badBaud || []).includes(this.baudrate)) throw new Error("Timeout"); return "f8:b3:b7:22:05:e8"; } }; this.baudrate = o.baudrate; this.terminal = o.terminal; }
  async changeBaud() { window.__log.push("change baud " + this.baudrate); await this.t.disconnect(); await this.t.connect(this.baudrate); }
  async main() { await this.t.connect(115200); window.__log.push("esptool got reader " + !!this.t.reader); this.term.writeLine("Connecting..."); this.term.writeLine("Chip is ESP32-D0WD-V3");
    if (window.__failFlash) throw new Error("Failed to connect with the device"); return "ESP32-D0WD-V3 (revision v3.1)"; }
  async writeFlash(o) { window.__log.push("write at " + this.baudrate); if ((window.__failWriteAt || []).includes(this.baudrate)) { window.__failWriteAt = []; for (let p = 0; p <= 3; p++) { o.reportProgress(0, p * 10, 100); await new Promise(r => setTimeout(r, 30)); } throw new Error("Packet content transfer stopped"); }
    window.__log.push("files " + o.fileArray.length + " size " + o.fileArray[0].data.length + " eraseAll " + o.eraseAll);
    if (window.__eraseDelay) await new Promise(r => setTimeout(r, window.__eraseDelay));
    for (let p = 0; p <= 10; p++) { o.reportProgress(0, p * 10, 100); await new Promise(r => setTimeout(r, window.__flashDelay || 30)); } }
}
