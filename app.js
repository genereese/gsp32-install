// GSP32 web installer: one wizard window (version and warnings, port, flashing with esptool-js, Wi-Fi over Improv,
// restart, done). One serial port stays open from the port pick to the end, and every open and close leaves the
// board's reset lines in the run state (DTR and RTS both off), so the page never resets or holds the board in reset
// by itself; it resets the board only on purpose (after flashing, after Wi-Fi setup, Reset Board).
import { ESPLoader, Transport } from "./vendor/esptool-js-0.5.7.js";

const HEADER = [0x49, 0x4d, 0x50, 0x52, 0x4f, 0x56];
const MAX_LINES = 2000;
const FLASH_BAUD = 115200;
const textEncoder = new TextEncoder();
const $ = (id) => document.getElementById(id);

const wizard = $("wizard");
const versionSelect = $("version");
const eraseOk = $("erase-ok");
const startInstall = $("start-install");
const flashStatus = $("flash-status");
const flashBar = $("flash-bar");
const flashDetail = $("flash-detail");
const wifiStatus = $("wifi-status");
const wifiWait = $("wifi-wait");
const wifiList = $("wifi-list");
const wifiForm = $("wifi-form");
const wifiPassword = $("wifi-password");
const wifiError = $("wifi-error");
const wifiRescan = $("wifi-rescan");
const wifiConnect = $("wifi-connect");
const restartStatus = $("restart-status");
const boardIp = $("board-ip");
const openWebui = $("open-webui");
const errorText = $("error-text");
const consoleCard = $("console");
const consoleOut = $("console-out");
const consoleIn = $("console-in");
const connectBtn = $("connect");
const disconnectBtn = $("disconnect");
const resetBtn = $("reset");
const ctrlCBtn = $("ctrl-c");

let versionsReady = false;
let busy = false;
let retryStep = "prep";
let wakeSentinel = null;

// Serial state: the port, our reader (null while esptool-js reads), and what came in
let port = null;
let reader = null;
let reading = false;
let readDone = Promise.resolve();
let pending = new Uint8Array(0);
let textDecoder = new TextDecoder("utf-8");
let lines = [];
let partial = "";
let onImprov = null;
let lineWatchers = [];
// What the serial lines tell about the board: GSP32 or not, when its Improv listener is ready, its address
const board = { kind: "unknown", readyAt: 0, bootAt: 0, ip: "", name: "", repl: false };
const READY_WINDOW_MS = 25000;
let otherTimer = null;

function trackBoard(line) {
  if (/GSP32 Improv Ready|Server listening on port|Web UI starts without Wi-Fi|Web UI running/.test(line)) {
    board.kind = "gsp32";
    board.readyAt = Date.now();
    clearTimeout(otherTimer);
  }
  if (/^rst:0x|^ets [A-Z][a-z]{2} /.test(line)) {
    board.bootAt = Date.now();
    board.repl = false;
    clearTimeout(otherTimer);
    // No GSP32 line within 20 s of a boot: some other firmware
    otherTimer = setTimeout(() => {
      if (board.readyAt < board.bootAt) {
        board.kind = "other";
        syncBoardUi();
      }
    }, 20000);
  }
  let match = line.match(/Network config: \('(\d+\.\d+\.\d+\.\d+)'/) || line.match(/^Connected: (\d+\.\d+\.\d+\.\d+)/);
  if (match) board.ip = match[1];
  match = line.match(/mDNS name: ([\w.-]+\.local)/);
  if (match) board.name = match[1];
  if (/Wi-Fi lost|Connection lost|starts without Wi-Fi/.test(line)) board.ip = "";
  syncBoardUi();
}

function syncBoardUi() {
  const setup = $("wifi-setup"), web = $("console-webui"), hint = $("board-hint");
  if (!setup || !web) return;
  const other = board.kind === "other";
  setup.disabled = other || busy;
  setup.title = other ? "Install GSP32 first to set up Wi-Fi" : "Send the Wi-Fi name and password to GSP32 over USB";
  const address = board.ip ? "http://" + board.ip + "/" : "";
  web.href = address || "#";
  web.setAttribute("aria-disabled", address ? "false" : "true");
  web.classList.toggle("primary", !!address);
  web.title = address ? "Open " + address + (board.name ? " (" + board.name + ")" : "") : "The address shows once the board reports it on Wi-Fi";
  hint.replaceChildren();
  if (other) {
    hint.append("Install GSP32 first to set up Wi-Fi. ");
    const link = document.createElement("a");
    link.href = "#";
    link.textContent = "Install GSP32";
    link.addEventListener("click", (event) => { event.preventDefault(); $("install-btn").click(); });
    hint.append(link);
  } else if (address) {
    hint.textContent = "GSP32 is on Wi-Fi at " + address + (board.name ? " (also http://" + board.name + "/)" : "") + ".";
  } else if (!portOpen()) {
    hint.textContent = "Connect to see whether the board runs GSP32 and its address.";
  } else if (board.kind === "gsp32") {
    hint.textContent = "GSP32 found. No Wi-Fi address yet: Set Up Wi-Fi, or click Reset Board to see it at boot.";
  } else {
    hint.textContent = "Waiting for the board: click Reset Board to see what it runs and its address.";
  }
}

function concatBytes(left, right) {
  if (!left.length) return right.slice();
  const out = new Uint8Array(left.length + right.length);
  out.set(left, 0);
  out.set(right, left.length);
  return out;
}

function headerAt(bytes, index) {
  if (index + 6 > bytes.length) return false;
  for (let i = 0; i < 6; i += 1) {
    if (bytes[index + i] !== HEADER[i]) return false;
  }
  return true;
}

function heldSuffix(bytes) {
  const max = Math.min(5, bytes.length);
  for (let len = max; len > 0; len -= 1) {
    let ok = true;
    for (let i = 0; i < len; i += 1) {
      if (bytes[bytes.length - len + i] !== HEADER[i]) {
        ok = false;
        break;
      }
    }
    if (ok) return len;
  }
  return 0;
}

export function buildImprovPacket(type, data) {
  const bytes = data instanceof Uint8Array ? data : Uint8Array.from(data);
  const body = new Uint8Array(9 + bytes.length);
  body.set(HEADER, 0);
  body[6] = 1;
  body[7] = type;
  body[8] = bytes.length;
  body.set(bytes, 9);
  let sum = 0;
  for (let i = 0; i < body.length; i += 1) sum = (sum + body[i]) & 0xff;
  const packet = new Uint8Array(body.length + 2);
  packet.set(body, 0);
  packet[body.length] = sum;
  packet[body.length + 1] = 10;
  return packet;
}

// RPC data is command, payload length, then the payload. Wi-Fi payload is ssidLen, ssid, pwLen, pw.
export function buildRpc(command, payload) {
  const extra = payload instanceof Uint8Array ? payload : Uint8Array.from(payload || []);
  const data = new Uint8Array(2 + extra.length);
  data[0] = command;
  data[1] = extra.length;
  data.set(extra, 2);
  return buildImprovPacket(3, data);
}

export function buildWifiRpc(ssid, password) {
  const name = textEncoder.encode(ssid);
  const secret = textEncoder.encode(password);
  const payload = new Uint8Array(1 + name.length + 1 + secret.length);
  payload[0] = name.length;
  payload.set(name, 1);
  payload[1 + name.length] = secret.length;
  payload.set(secret, 2 + name.length);
  return buildRpc(1, payload);
}

export function parseImprovResult(data) {
  const command = data.length ? data[0] : 0;
  const total = data.length > 1 ? data[1] : 0;
  const strings = [];
  let idx = 2;
  const end = Math.min(data.length, 2 + total);
  const decoder = new TextDecoder("utf-8");
  while (idx < end) {
    const size = data[idx];
    idx += 1;
    if (idx + size > data.length) break;
    strings.push(decoder.decode(data.subarray(idx, idx + size)));
    idx += size;
  }
  return { command, strings };
}

export function takeSerialBytes(input) {
  const bytes = input instanceof Uint8Array ? input : Uint8Array.from(input);
  const texts = [];
  const packets = [];
  let i = 0;
  const finish = (restFrom) => {
    let size = 0;
    for (const chunk of texts) size += chunk.length;
    const text = new Uint8Array(size);
    let offset = 0;
    for (const chunk of texts) {
      text.set(chunk, offset);
      offset += chunk.length;
    }
    return { rest: bytes.slice(restFrom), text, packets };
  };

  while (i < bytes.length) {
    let found = -1;
    for (let j = i; j + 6 <= bytes.length; j += 1) {
      if (headerAt(bytes, j)) {
        found = j;
        break;
      }
    }
    if (found < 0) {
      const hold = heldSuffix(bytes.subarray(i));
      const end = bytes.length - hold;
      if (end > i) texts.push(bytes.subarray(i, end));
      return finish(bytes.length - hold);
    }
    if (found > i) texts.push(bytes.subarray(i, found));
    if (found + 9 > bytes.length) return finish(found);
    const length = bytes[found + 8];
    const total = 9 + length + 1;
    if (found + total > bytes.length) return finish(found);
    let sum = 0;
    for (let k = 0; k < total - 1; k += 1) sum = (sum + bytes[found + k]) & 0xff;
    if (bytes[found + 6] !== 1 || sum !== bytes[found + total - 1]) {
      texts.push(bytes.subarray(found, found + 1));
      i = found + 1;
      continue;
    }
    packets.push({
      type: bytes[found + 7],
      data: bytes.slice(found + 9, found + 9 + length),
    });
    i = found + total;
    if (i < bytes.length && bytes[i] === 10) i += 1;
  }
  return finish(bytes.length);
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "http:" || url.protocol === "https:") return url.href;
  } catch (err) {
    return "";
  }
  return "";
}



function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function browserBlocked() {
  return document.documentElement.getAttribute("data-browser") === "block";
}

// Wizard steps: only the current one shows; the window keeps its place and changes height smoothly
function showStep(name) {
  const before = wizard.open ? wizard.offsetHeight : 0;
  for (const step of wizard.querySelectorAll(".step")) step.hidden = step.dataset.step !== name;
  const titles = { prep: "Install GSP32", flash: "Installing GSP32", choice: "Installed", wifi: "Set Up Wi-Fi",
                   restart: "Restarting the Board", done: "Your Board Is Ready", usb: "USB Only", error: "Something Went Wrong" };
  $("wizard-title").textContent = titles[name] || "Install GSP32";
  if (before && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const after = wizard.offsetHeight;
    wizard.animate([{ height: before + "px" }, { height: after + "px" }], { duration: 200, easing: "ease-out" });
  }
}

function setBusy(on) {
  busy = on;
  if (on) requestWakeLock();
  else releaseWakeLock();
}

async function requestWakeLock() {
  if (!busy || document.hidden || !("wakeLock" in navigator) || wakeSentinel) return;
  try {
    wakeSentinel = await navigator.wakeLock.request("screen");
    wakeSentinel.addEventListener("release", () => { wakeSentinel = null; });
  } catch (err) {
    wakeSentinel = null;
  }
}

function releaseWakeLock() {
  if (wakeSentinel) wakeSentinel.release().catch(() => {});
  wakeSentinel = null;
}

function showError(message, retry) {
  setBusy(false);
  retryStep = retry || "prep";
  errorText.textContent = message;
  showStep("error");
}

// Console text
function paintConsole() {
  const atBottom = consoleOut.scrollHeight - consoleOut.scrollTop - consoleOut.clientHeight < 48;
  consoleOut.textContent = lines.join("\n") + (partial ? (lines.length ? "\n" : "") + partial : "");
  if (atBottom) consoleOut.scrollTop = consoleOut.scrollHeight;
}

function appendConsole(text) {
  if (!text) return;
  partial += text;
  const pieces = partial.split("\n");
  partial = pieces.pop();
  if (/>>> ?$/.test(partial)) board.repl = true;
  if (partial.length > 2000) {
    pieces.push(partial);
    partial = "";
  }
  for (const line of pieces) {
    lines.push(line);
    trackBoard(line);
    for (const watch of lineWatchers.slice()) watch(line);
  }
  if (lines.length > MAX_LINES) lines = lines.slice(lines.length - MAX_LINES);
  paintConsole();
}

function consumeSerial(chunk) {
  const taken = takeSerialBytes(concatBytes(pending, chunk));
  pending = taken.rest;
  if (taken.text.length) appendConsole(textDecoder.decode(taken.text, { stream: true }));
  for (const packet of taken.packets) {
    // Any answer is GSP32; a provisioned state's result carries the board's address
    board.kind = "gsp32";
    if (packet.type === 4) {
      const parsed = parseImprovResult(packet.data);
      const found = parsed.command === 2 && parsed.strings[0] && parsed.strings[0].match(/^http:\/\/([\d.]+)\//);
      if (found) board.ip = found[1];
    }
    syncBoardUi();
    if (!onImprov) continue;
    try {
      onImprov(packet);
    } catch (err) {
      // One bad packet must not stop the reading
    }
  }
}

// Serial port: open once, reset lines to run, our reader; esptool-js borrows the port while flashing
function portOpen() {
  return !!(port && port.readable && port.writable);
}

function syncConsoleButtons() {
  const on = portOpen();
  connectBtn.disabled = on;
  connectBtn.textContent = on ? "Connected" : "Connect";
  disconnectBtn.disabled = !on || busy;
  resetBtn.disabled = !on || busy;
  ctrlCBtn.disabled = !on || busy;
  consoleIn.disabled = !on || busy;
  syncBoardUi();
}

async function setRunState() {
  // DTR and RTS off together in one request: the board's EN and GPIO 0 lines both stay high (running)
  if (port) await port.setSignals({ dataTerminalReady: false, requestToSend: false });
}

async function resetBoard() {
  // RTS on alone pulls EN low (reset), then back to the run state
  await port.setSignals({ dataTerminalReady: false, requestToSend: true });
  await delay(120);
  await setRunState();
}

function startReading() {
  if (reading || !portOpen()) return;
  reading = true;
  readDone = (async () => {
    while (reading && port && port.readable) {
      try {
        reader = port.readable.getReader();
      } catch (err) {
        break;
      }
      let got = false;
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          got = true;
          if (value) consumeSerial(value);
        }
      } catch (err) {
        if (reading) {
          reading = false;
          appendConsole("\n[The board disconnected. Plug it in and click Connect.]\n");
          port = null;
        }
      } finally {
        try {
          reader.releaseLock();
        } catch (err) {
          // Already released when the device unplugs
        }
        reader = null;
      }
      // A stream that ends at once again and again would spin here: give the port a moment, then stop
      if (!got) await delay(50);
      if (!got && reading && port && port.readable && port.readable.locked) break;
    }
    reading = false;
    syncConsoleButtons();
  })();
}

async function stopReading() {
  reading = false;
  if (reader) await reader.cancel().catch(() => {});
  await readDone;
}

async function openPort(selected) {
  if (port === selected && portOpen()) return;
  if (port && port !== selected) await closePort();
  await selected.open({ baudRate: FLASH_BAUD });
  port = selected;
  await setRunState();
  pending = new Uint8Array(0);
  textDecoder = new TextDecoder("utf-8");
  startReading();
  syncConsoleButtons();
}

async function pickPort() {
  if (portOpen()) return port;
  let selected;
  try {
    selected = await navigator.serial.requestPort();
  } catch (err) {
    const cancel = new Error("No port was chosen.");
    cancel.code = "cancel";
    throw cancel;
  }
  try {
    await openPort(selected);
  } catch (err) {
    const fail = new Error("Could not open the port. Close other programs that use it (Arduino, Thonny, mpremote) and try again.");
    fail.code = "open";
    throw fail;
  }
  return port;
}

async function closePort() {
  if (!port) return;
  const closing = port;
  await stopReading();
  try {
    await setRunState();
  } catch (err) {
    // The device may be gone already
  }
  await closing.close().catch(() => {});
  if (port === closing) port = null;
  syncConsoleButtons();
}

async function writeBytes(bytes) {
  if (!portOpen()) throw new Error("not connected");
  const writer = port.writable.getWriter();
  try {
    await writer.write(bytes);
  } finally {
    writer.releaseLock();
  }
}

// Versions
async function loadVersions() {
  try {
    const response = await fetch("versions.json", { cache: "no-store" });
    const list = await response.json();
    versionSelect.replaceChildren();
    for (const item of list) {
      const option = document.createElement("option");
      option.value = item.manifest;
      option.textContent = item.label || item.version;
      versionSelect.append(option);
    }
    versionsReady = list.length > 0;
  } catch (err) {
    versionSelect.replaceChildren(new Option("Could Not Load Versions"));
    versionsReady = false;
  }
  syncStart();
}

function syncStart() {
  startInstall.disabled = !versionsReady || !eraseOk.checked;
}

async function loadFirmware() {
  const manifestUrl = new URL(versionSelect.value, location.href);
  const manifest = await (await fetch(manifestUrl, { cache: "no-store" })).json();
  const build = manifest.builds.find((item) => item.chipFamily === "ESP32") || manifest.builds[0];
  const files = [];
  for (const part of build.parts) {
    const response = await fetch(new URL(part.path, manifestUrl), { cache: "no-store" });
    if (!response.ok) throw new Error("Could not download the firmware (" + response.status + ").");
    const bytes = new Uint8Array(await response.arrayBuffer());
    // esptool-js takes each file as a binary string
    let data = "";
    for (let i = 0; i < bytes.length; i += 0x8000) data += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    files.push({ data, address: part.offset });
  }
  return files;
}

function setProgress(text, percent, detail) {
  flashStatus.textContent = text;
  if (percent != null) flashBar.style.width = Math.max(0, Math.min(100, percent)) + "%";
  if (detail != null) flashDetail.textContent = detail;
}

// Step 2: port, then flash with esptool-js on the same open port
async function install() {
  showStep("flash");
  setProgress("Choose the board's port in the browser's list...", 0, "");
  setBusy(true);
  try {
    await pickPort();
  } catch (err) {
    setBusy(false);
    if (err.code === "cancel") {
      showStep("prep");
      return;
    }
    showError(err.message, "prep");
    return;
  }
  syncConsoleButtons();
  try {
    setProgress("Downloading the firmware...", 0, "");
    const files = await loadFirmware();
    await stopReading();
    const transport = new Transport(port, false);
    // The port is already open: esptool-js only borrows its reader, never closes or reopens it
    transport.connect = async function (baud) {
      this.baudrate = baud;
      this.reader = port.readable.getReader();
    };
    transport.disconnect = async function () {
      if (this.reader) {
        await this.reader.cancel().catch(() => {});
        try {
          this.reader.releaseLock();
        } catch (err) {
          // Released already
        }
      }
      this.reader = undefined;
    };
    const terminal = {
      clean() {},
      writeLine(text) { flashDetail.textContent = text; },
      write() {},
    };
    const loader = new ESPLoader({ transport, baudrate: FLASH_BAUD, romBaudrate: FLASH_BAUD, terminal });
    setProgress("Connecting to the board...", 0);
    const chip = await loader.main("default_reset");
    if (!/ESP32/.test(chip) || /ESP32-(S|C|H|P)/.test(chip)) throw new Error("This board is " + chip + ". GSP32 needs a classic ESP32.");
    setProgress("Erasing the board (about 15 seconds)...", 0, chip);
    let lastPercent = -1;
    await loader.writeFlash({
      fileArray: files,
      flashSize: "keep",
      flashMode: "keep",
      flashFreq: "keep",
      eraseAll: true,
      compress: true,
      reportProgress: (index, written, total) => {
        const percent = Math.floor((written / total) * 100);
        if (percent !== lastPercent) {
          lastPercent = percent;
          setProgress("Writing the firmware... " + percent + "%", percent);
        }
      },
    });
    setProgress("Restarting the board...", 100, "");
    await transport.disconnect();
    await resetBoard();
    lines = [];
    partial = "";
    startReading();
    setBusy(false);
    showStep("choice");
  } catch (err) {
    await setRunState().catch(() => {});
    startReading();
    showError("The install did not finish: " + (err && err.message ? err.message : err), "prep");
  }
  syncConsoleButtons();
}

// Improv Wi-Fi
function waitForPackets(timeoutMs, onPacket) {
  return new Promise((resolve, reject) => {
    const finish = (fn) => (value) => {
      clearTimeout(timer);
      if (onImprov === handle) onImprov = null;
      fn(value);
    };
    const timer = setTimeout(finish(() => {
      const err = new Error("timeout");
      err.code = "timeout";
      reject(err);
    }), timeoutMs);
    function handle(packet) {
      onPacket(packet, finish(resolve), finish(reject));
    }
    onImprov = handle;
  });
}

// The board answers Improv once its web UI runs (a few seconds after a reset; while the boot Wi-Fi prompt waits,
// that prompt answers). Ask for the state every 1.5 s until it does
// Resolves once a GSP32 ready line arrives (or after timeoutMs)
function waitReady(timeoutMs) {
  const since = Date.now();
  return new Promise((resolve) => {
    const timer = setInterval(() => {
      if (board.readyAt >= since || board.kind === "other" || Date.now() - since > timeoutMs) {
        clearInterval(timer);
        resolve(board.readyAt >= since);
      }
    }, 100);
  });
}

async function waitBoardReady(timeoutMs) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const answer = waitForPackets(1500, (packet, resolve) => {
      if (packet.type === 1) resolve(packet.data[0]);
    });
    await writeBytes(buildRpc(2, new Uint8Array(0)));
    try {
      return await answer;
    } catch (err) {
      if (err.code !== "timeout") throw err;
    }
  }
  return null;
}

async function scanNetworks() {
  const found = new Map();
  const result = waitForPackets(20000, (packet, resolve, reject) => {
    if (packet.type === 2 && packet.data[0] > 0) {
      reject(new Error("scan"));
      return;
    }
    if (packet.type !== 4) return;
    const parsed = parseImprovResult(packet.data);
    if (parsed.command !== 4) return;
    if (!parsed.strings.length) {
      resolve([...found.values()]);
      return;
    }
    const ssid = parsed.strings[0];
    const rssi = Number(parsed.strings[1]);
    if (ssid && (!found.has(ssid) || rssi > found.get(ssid).rssi)) found.set(ssid, { ssid, rssi, auth: parsed.strings[2] || "YES" });
  });
  await writeBytes(buildRpc(4, new Uint8Array(0)));
  try {
    return await result;
  } catch (err) {
    if (err.code === "timeout") return [...found.values()];
    throw err;
  }
}

function signalWord(rssi) {
  if (rssi >= -55) return "Strong";
  if (rssi >= -67) return "Good";
  if (rssi >= -75) return "Fair";
  return "Weak";
}

function renderNetworks(networks) {
  wifiList.replaceChildren();
  for (const net of networks.sort((a, b) => b.rssi - a.rssi)) {
    const item = document.createElement("li");
    const label = document.createElement("label");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "network";
    radio.value = net.ssid;
    radio.dataset.open = net.auth === "NO" ? "1" : "";
    const name = document.createElement("span");
    name.className = "net-name";
    name.textContent = net.ssid;
    const info = document.createElement("span");
    info.className = "net-info";
    info.textContent = signalWord(net.rssi) + (net.auth === "NO" ? ", Open" : "");
    label.append(radio, name, info);
    item.append(label);
    wifiList.append(item);
  }
}

function syncWifiConnect() {
  const picked = wifiList.querySelector("input:checked");
  wifiForm.hidden = !picked || !!picked.dataset.open;
  wifiConnect.disabled = busy || !picked;
}

async function startWifi(fresh) {
  showStep("wifi");
  wifiError.hidden = true;
  wifiRescan.hidden = true;
  wifiForm.hidden = true;
  wifiPassword.value = "";
  wifiList.replaceChildren();
  wifiWait.hidden = false;
  setBusy(true);
  syncWifiConnect();
  try {
    if (!portOpen()) await pickPort();
    wifiStatus.textContent = "Waiting for the board to start...";
    // Never Ctrl-C: an interrupted boot drops to the REPL, which echoes Improv packets (and their 0x04 bytes
    // soft-reboot it). Improv goes out only once GSP32 says it listens: the "GSP32 Improv Ready" line at the boot
    // Wi-Fi offer, "Server listening" (listens for 30 s after a boot, and whenever it has no Wi-Fi)
    if (Date.now() - board.readyAt > READY_WINDOW_MS) {
      if (!fresh) {
        wifiStatus.textContent = "Restarting the board so GSP32 listens for Wi-Fi setup...";
        await resetBoard();
      }
      await waitReady(45000);
    }
    let state = await waitBoardReady(8000);
    // Fallback, once: a board sitting at the REPL starts the Improv session when asked
    if (state === null && board.repl) {
      await writeBytes(textEncoder.encode("import webui_wifisetup; webui_wifisetup.improvSession()\r\n"));
      state = await waitBoardReady(6000);
    }
    if (state === null && board.kind === "other") throw new Error("This board does not run GSP32. Install GSP32 first to set up Wi-Fi.");
    if (state === null) throw new Error("The board did not answer. Check that GSP32 is installed, then try again.");
    await scanForWifi();
  } catch (err) {
    wifiWait.hidden = true;
    setBusy(false);
    if (err.code === "cancel") {
      wizard.close();
      return;
    }
    wifiStatus.textContent = err.message;
    wifiRescan.hidden = false;
    wifiRescan.textContent = "Try Again";
  }
  syncWifiConnect();
}

async function scanForWifi() {
  setBusy(true);
  wifiWait.hidden = false;
  wifiRescan.hidden = true;
  wifiStatus.textContent = "Looking for Wi-Fi networks...";
  syncWifiConnect();
  let networks = [];
  try {
    networks = await scanNetworks();
  } catch (err) {
    networks = [];
  }
  wifiWait.hidden = true;
  setBusy(false);
  renderNetworks(networks);
  wifiRescan.hidden = false;
  wifiRescan.textContent = "Scan Again";
  wifiStatus.textContent = networks.length
    ? "Pick your network and enter its password."
    : "No networks found. Move the board closer to the router, then click Scan Again.";
  syncWifiConnect();
}

async function connectWifi() {
  const picked = wifiList.querySelector("input:checked");
  if (!picked || busy) return;
  const name = textEncoder.encode(picked.value);
  const secret = textEncoder.encode(wifiPassword.value);
  wifiError.hidden = true;
  if (name.length > 255 || secret.length > 255) {
    wifiError.hidden = false;
    wifiError.textContent = "That name or password is too long.";
    return;
  }
  setBusy(true);
  syncWifiConnect();
  wifiWait.hidden = false;
  wifiStatus.textContent = "Connecting to " + picked.value + "...";
  const result = waitForPackets(40000, (packet, resolve, reject) => {
    if (packet.type === 2 && packet.data[0] > 0) {
      const err = new Error("connect");
      err.code = packet.data[0];
      reject(err);
      return;
    }
    if (packet.type === 4) {
      const parsed = parseImprovResult(packet.data);
      if (parsed.command === 1) resolve(parsed.strings[0] || "");
    }
  });
  try {
    await writeBytes(buildWifiRpc(picked.value, wifiPassword.value));
    const url = safeHttpUrl(await result);
    wifiPassword.value = "";
    await restartAndWait(url);
  } catch (err) {
    wifiWait.hidden = true;
    setBusy(false);
    wifiError.hidden = false;
    wifiError.textContent = err.code === 3
      ? "Could not connect. Check the password and try again."
      : "Could not connect. Move the board closer to the router and try again.";
    wifiStatus.textContent = "Pick your network and enter its password.";
    syncWifiConnect();
  }
}

// Step 5: reset the board so it starts clean on the new network, then wait until its web server listens on Wi-Fi
// (its boot lines on the serial port: this https page cannot ask an http board on the local network directly)
function waitForBoot(timeoutMs) {
  return new Promise((resolve) => {
    let ip = "";
    let listening = false;
    const watch = (line) => {
      if (line.includes("Server listening")) listening = true;
      const match = line.match(/Network config: \('(\d+\.\d+\.\d+\.\d+)'/);
      if (match) ip = match[1];
      if (listening && ip) done();
    };
    const done = () => {
      clearTimeout(timer);
      lineWatchers = lineWatchers.filter((item) => item !== watch);
      resolve(ip);
    };
    const timer = setTimeout(done, timeoutMs);
    lineWatchers.push(watch);
  });
}

async function restartAndWait(url) {
  showStep("restart");
  restartStatus.textContent = "Restarting the board...";
  const booted = waitForBoot(45000);
  await resetBoard();
  restartStatus.textContent = "Waiting for the board to join Wi-Fi...";
  let ip = await booted;
  if (ip) {
    // The web server answers a moment after the address is set
    restartStatus.textContent = "Starting the web UI...";
    await delay(2500);
  } else if (url) {
    ip = new URL(url).hostname;
  }
  setBusy(false);
  if (!ip) {
    showError("The board did not report its address. Open the Serial Console to see what it printed.", "prep");
    return;
  }
  const address = "http://" + ip + "/";
  boardIp.href = address;
  boardIp.textContent = address;
  openWebui.href = address;
  showStep("done");
}

// Serial console on the page (shares the wizard's port)
function showConsole() {
  if (consoleCard.hidden) {
    consoleCard.hidden = false;
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      consoleCard.animate([{ opacity: 0, transform: "translateY(-6px)" }, { opacity: 1, transform: "none" }], { duration: 200, easing: "ease-out" });
    }
  }
  paintConsole();
  consoleCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

function guard(fn) {
  return () => fn().catch((err) => appendConsole("\n[" + (err && err.message ? err.message : "Something went wrong") + "]\n"));
}

function openWizard(step) {
  if (browserBlocked()) return;
  if (!wizard.open) wizard.showModal();
  showStep(step);
}

// Events
$("install-btn").addEventListener("click", () => {
  eraseOk.checked = false;
  syncStart();
  openWizard("prep");
});
$("open-console").addEventListener("click", showConsole);
eraseOk.addEventListener("change", syncStart);
startInstall.addEventListener("click", () => install());
$("choose-wifi").addEventListener("click", () => startWifi(true));
$("choose-usb").addEventListener("click", () => showStep("usb"));
$("error-retry").addEventListener("click", () => {
  if (retryStep === "wifi") startWifi(false);
  else showStep(retryStep);
});
wifiList.addEventListener("change", () => {
  syncWifiConnect();
  if (!wifiForm.hidden) wifiPassword.focus();
});
wifiRescan.addEventListener("click", () => {
  if (wifiRescan.textContent === "Try Again") startWifi(false);
  else scanForWifi();
});
wifiConnect.addEventListener("click", () => connectWifi());
wifiPassword.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    connectWifi();
  }
});
for (const button of wizard.querySelectorAll("[data-action]")) {
  button.addEventListener("click", () => {
    wizard.close();
    if (button.dataset.action === "console") showConsole();
  });
}
// No closing in the middle of a step that talks to the board
wizard.addEventListener("cancel", (event) => {
  if (busy) event.preventDefault();
});
wizard.querySelector(".close").addEventListener("click", (event) => {
  if (busy) event.preventDefault();
});
wizard.addEventListener("close", () => {
  onImprov = null;
  syncConsoleButtons();
});

connectBtn.addEventListener("click", guard(async () => {
  showConsole();
  await pickPort();
}));
disconnectBtn.addEventListener("click", guard(closePort));
resetBtn.addEventListener("click", guard(resetBoard));
ctrlCBtn.addEventListener("click", guard(() => writeBytes(new Uint8Array([0x03]))));
$("wifi-setup").addEventListener("click", () => {
  openWizard("wifi");
  startWifi(false);
});
$("console-webui").addEventListener("click", (event) => {
  if ($("console-webui").getAttribute("aria-disabled") === "true") event.preventDefault();
});
$("console-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = consoleIn.value;
  consoleIn.value = "";
  writeBytes(textEncoder.encode(text + "\r\n")).catch(() => appendConsole("\n[Could not send. Click Connect and try again.]\n"));
});

if ("serial" in navigator) {
  navigator.serial.addEventListener("disconnect", (event) => {
    if (event.target === port) {
      reading = false;
      port = null;
      syncConsoleButtons();
    }
  });
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) requestWakeLock();
});
window.addEventListener("beforeunload", (event) => {
  if (busy) {
    event.preventDefault();
    event.returnValue = "";
  }
});
// Leaving the page: lines to run first, so closing the tab never holds the board in reset
window.addEventListener("pagehide", () => {
  if (port) port.setSignals({ dataTerminalReady: false, requestToSend: false }).catch(() => {});
});

loadVersions();
syncConsoleButtons();
