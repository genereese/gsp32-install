// Version 79: flash size, features, crystal for board details + compat check
export class Transport { constructor(device) { this.device = device; } async flushInput() { if (this.reader && !await this.reader.closed) window.__log.push("flushed"); } }
const never = () => new Promise(() => {});
function chipDesc() { return window.__chip || "ESP32-D0WD-V3 (revision v3.1)"; }
function flashKb() {
  if (window.__flashKb != null) return window.__flashKb;
  const c = chipDesc();
  if (/ESP32-S3/.test(c)) return 16384;
  if (/ESP32-C3/.test(c)) return 4096;
  return 4096; // classic ESP32 default in tests
}
function features() {
  if (Array.isArray(window.__features)) return window.__features.slice();
  const c = chipDesc();
  if (/ESP32-S3/.test(c)) return ["Wi-Fi", "BT 5", "Dual Core", "240MHz", "Embedded PSRAM", "USB OTG"];
  if (/ESP32-C3/.test(c)) return ["Wi-Fi", "BT 5", "Single Core", "160MHz"];
  return ["Wi-Fi", "BT", "Dual Core", "240MHz", "VRef calibration in efuse"];
}
function crystal() {
  if (window.__crystalMhz != null) return window.__crystalMhz;
  return 40;
}
export class ESPLoader {
  constructor(o) {
    this.t = o.transport; this.term = o.terminal; window.__log.push("loader baud " + o.baudrate);
    this.chip = {
      getChipDescription: async () => chipDesc(),
      readMac: async () => {
        if (window.__glitch && this.t.reader) {
          const r = await Promise.race([this.t.reader.read(), new Promise((res) => setTimeout(() => res(null), 30))]);
          if (r && r.value && r.value.length) {
            window.__log.push("invalid head");
            throw new Error("Invalid head of packet (0x" + r.value[0].toString(16) + "): Possible serial noise or corruption.");
          }
        }
        if ((window.__hangBaud || []).includes(this.baudrate)) { window.__log.push("hang at " + this.baudrate); await never(); }
        if ((window.__badBaud || []).includes(this.baudrate)) throw new Error("Timeout");
        return "f8:b3:b7:22:05:e8";
      },
      getChipFeatures: async () => features(),
      getCrystalFreq: async () => crystal(),
    };
    this.baudrate = o.baudrate; this.terminal = o.terminal;
  }
  async getFlashSize() { window.__log.push("flashKb " + flashKb()); return flashKb(); }
  async changeBaud() { window.__log.push("change baud " + this.baudrate); await this.t.disconnect(); await this.t.connect(this.baudrate); }
  async main() {
    await this.t.connect(115200);
    if (window.__hangConnect > 0) { window.__hangConnect--; window.__log.push("connect hang"); await never(); }
    window.__log.push("esptool got reader " + !!this.t.reader);
    this.term.writeLine("Connecting...");
    this.term.writeLine("Chip is " + chipDesc().split(" (")[0]);
    if (window.__failFlash) throw new Error("Failed to connect with the device");
    return chipDesc();
  }
  async writeFlash(o) {
    window.__log.push("write at " + this.baudrate);
    if ((window.__failWriteAt || []).includes(this.baudrate)) {
      window.__failWriteAt = [];
      for (let p = 0; p <= 3; p++) { o.reportProgress(0, p * 10, 100); await new Promise(r => setTimeout(r, 30)); }
      throw new Error("Packet content transfer stopped");
    }
    window.__log.push("files " + o.fileArray.length + " size " + o.fileArray[0].data.length + " at " + o.fileArray[0].address + " eraseAll " + o.eraseAll);
    if (window.__eraseDelay) await new Promise(r => setTimeout(r, window.__eraseDelay));
    for (let p = 0; p <= 10; p++) { o.reportProgress(0, p * 10, 100); await new Promise(r => setTimeout(r, window.__flashDelay || 30)); }
  }
}
