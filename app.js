const HEADER = [0x49, 0x4d, 0x50, 0x52, 0x4f, 0x56];
const MAX_LINES = 2000;
const textEncoder = new TextEncoder();

const $ = (id) => document.getElementById(id);

const versionSelect = $("version");
const eraseOk = $("erase-ok");
const installButton = document.querySelector("esp-web-install-button");
const installBtn = $("install-btn");
const installStatus = $("install-status");
const hiddenBanner = $("hidden-banner");
const installError = $("install-error");
const afterInstall = $("after-install");
const setupWifiBtn = $("setup-wifi");
const skipUsbBtn = $("skip-usb");
const usbOnly = $("usb-only");
const connectBtn = $("connect");
const resetBtn = $("reset");
const ctrlCBtn = $("ctrl-c");
const wifiSetupBtn = $("wifi-setup");
const consoleHint = $("console-hint");
const consoleOut = $("console-out");
const consoleForm = $("console-form");
const consoleIn = $("console-in");
const wifiPanel = $("wifi");
const wifiStatus = $("wifi-status");
const wifiList = $("wifi-list");
const wifiPassword = $("wifi-password");
const wifiConnect = $("wifi-connect");
const wifiProgress = $("wifi-progress");
const wifiError = $("wifi-error");
const wifiSuccess = $("wifi-success");
const openBoard = $("open-board");
const openBoardUrl = $("open-board-url");

const PROGRESS = new Set(["initializing", "manifest", "preparing", "erasing", "writing"]);
const STATUS_TEXT = {
  initializing: "Starting the install...",
  manifest: "Reading the install file...",
  preparing: "Getting the firmware ready...",
  erasing: "Erasing the board...",
  writing: "Writing the firmware...",
};

let versionReady = false;
let phase = "idle";
let lastStateKey = "";
let wantWake = false;
let wakeSentinel = null;

let port = null;
let opening = false;
let reading = false;
let pending = new Uint8Array(0);
let textDecoder = new TextDecoder("utf-8");
let lines = [];
let partial = "";
let onImprov = null;
let wifiBusy = false;

function browserBlocked() {
  const ua = navigator.userAgent || "";
  const firefox = /firefox|fxios/i.test(ua);
  const safari = /safari/i.test(ua) && !/chrome|chromium|crios|edg\/|edge\/|edgios/i.test(ua);
  let mobile = !!(navigator.userAgentData && navigator.userAgentData.mobile);
  if (/Android|iPhone|iPad|iPod|Mobile|Tablet|Opera Mini|IEMobile/i.test(ua)) mobile = true;
  if (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) mobile = true;
  return !("serial" in navigator) || firefox || safari || mobile;
}

function applyBrowserCheck() {
  if (browserBlocked()) document.documentElement.setAttribute("data-browser", "block");
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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

function signalWord(rssi) {
  if (rssi >= -55) return "strong";
  if (rssi >= -67) return "good";
  if (rssi >= -75) return "fair";
  return "weak";
}

function applyManifest() {
  const manifest = versionSelect.value || "manifest.json";
  installButton.setAttribute("manifest", manifest);
  installButton.manifest = manifest;
}

function syncInstallButton() {
  const installing = phase === "installing";
  installBtn.disabled = !versionReady || !eraseOk.checked || installing;
  versionSelect.disabled = !versionReady || installing;
}

async function loadVersions() {
  try {
    const response = await fetch("versions.json");
    if (!response.ok) throw new Error("bad status");
    const list = await response.json();
    if (!Array.isArray(list) || !list.length) throw new Error("empty");
    versionSelect.replaceChildren();
    for (const item of list) {
      const option = document.createElement("option");
      option.value = item.manifest;
      option.textContent = item.label || item.version || item.manifest;
      if (item.version) option.dataset.version = item.version;
      versionSelect.append(option);
    }
    versionReady = true;
    applyManifest();
  } catch (err) {
    versionReady = false;
    versionSelect.replaceChildren();
    const option = document.createElement("option");
    option.textContent = "Could not load versions";
    versionSelect.append(option);
    installStatus.hidden = false;
    installStatus.textContent = "Could not load the version list. Refresh the page and try again.";
  }
  syncInstallButton();
}

async function requestWakeLock() {
  if (!wantWake || document.hidden || !("wakeLock" in navigator)) return;
  if (wakeSentinel) return;
  try {
    const sentinel = await navigator.wakeLock.request("screen");
    wakeSentinel = sentinel;
    sentinel.addEventListener("release", () => {
      if (wakeSentinel === sentinel) wakeSentinel = null;
      if (wantWake && !document.hidden) requestWakeLock();
    });
  } catch (err) {
    wakeSentinel = null;
  }
}

async function releaseWakeLock() {
  wantWake = false;
  const sentinel = wakeSentinel;
  wakeSentinel = null;
  if (!sentinel) return;
  try {
    await sentinel.release();
  } catch (err) {
    // Already released when the tab was hidden.
  }
}

function updateHiddenBanner() {
  hiddenBanner.hidden = !(wantWake && document.hidden);
}

function onInstallState(state, detail) {
  const pct = detail && detail.details && typeof detail.details.percentage === "number"
    ? detail.details.percentage
    : "";
  const key = state + "/" + pct;
  if (key === lastStateKey) return;
  lastStateKey = key;

  if (PROGRESS.has(state)) {
    phase = "installing";
    wantWake = true;
    installError.hidden = true;
    afterInstall.hidden = true;
    usbOnly.hidden = true;
    const base = STATUS_TEXT[state] || "Installing...";
    installStatus.hidden = false;
    installStatus.textContent = state === "writing" && pct !== "" ? base + " " + pct + "%" : base;
    updateHiddenBanner();
    requestWakeLock();
    syncInstallButton();
    return;
  }

  if (state === "error") {
    phase = "error";
    installStatus.hidden = true;
    installError.hidden = false;
    releaseWakeLock();
    updateHiddenBanner();
    syncInstallButton();
    return;
  }

  if (state === "finished") {
    phase = "finished";
    installStatus.hidden = true;
    installError.hidden = true;
    afterInstall.hidden = false;
    releaseWakeLock();
    updateHiddenBanner();
    syncInstallButton();
  }
}

function watchInstallDialog() {
  const timers = new WeakMap();
  const watch = (dialog) => {
    if (timers.has(dialog)) return;
    let prev = "";
    const timer = setInterval(() => {
      if (!dialog.isConnected) {
        clearInterval(timer);
        timers.delete(dialog);
        return;
      }
      let state = null;
      try {
        state = dialog._installState;
      } catch (err) {
        return;
      }
      if (!state || !state.state) return;
      const pct = state.details && state.details.percentage;
      const key = state.state + "/" + (state.message || "") + "/" + (pct == null ? "" : pct);
      if (key === prev) return;
      prev = key;
      installButton.dispatchEvent(new CustomEvent("state-changed", { detail: state }));
    }, 200);
    timers.set(dialog, timer);
  };
  const observer = new MutationObserver(() => {
    document.querySelectorAll("ewt-install-dialog").forEach(watch);
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

function paintConsole() {
  const atBottom = consoleOut.scrollHeight - consoleOut.scrollTop - consoleOut.clientHeight < 48;
  const body = lines.join("\n") + (partial ? (lines.length ? "\n" : "") + partial : "");
  consoleOut.textContent = body;
  consoleHint.hidden = body.length > 0;
  if (atBottom) consoleOut.scrollTop = consoleOut.scrollHeight;
}

function appendConsole(text) {
  if (!text) return;
  partial += text;
  if (partial.length > 2000 && !partial.includes("\n")) {
    lines.push(partial.slice(0, 2000));
    partial = partial.slice(2000);
  }
  const pieces = partial.split("\n");
  partial = pieces.pop();
  for (const line of pieces) lines.push(line);
  if (lines.length > MAX_LINES) lines = lines.slice(lines.length - MAX_LINES);
  paintConsole();
}

function portOpen() {
  return !!(port && port.readable && port.writable);
}

function setConnected(on) {
  connectBtn.disabled = on;
  connectBtn.textContent = on ? "Connected" : "Connect";
  resetBtn.disabled = !on;
  ctrlCBtn.disabled = !on;
  consoleIn.disabled = !on;
}

function consumeSerial(chunk) {
  const merged = concatBytes(pending, chunk);
  const taken = takeSerialBytes(merged);
  pending = taken.rest;
  if (taken.text.length) {
    const text = textDecoder.decode(taken.text, { stream: true });
    if (text) appendConsole(text);
  }
  if (taken.packets.length && onImprov) {
    for (const packet of taken.packets) {
      try {
        onImprov(packet);
      } catch (err) {
        // Keep the console reading even if a Wi-Fi step mis-handles one packet.
      }
    }
  }
}

async function readLoop() {
  const current = port;
  while (reading && current && current.readable) {
    let reader;
    try {
      reader = current.readable.getReader();
    } catch (err) {
      break;
    }
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          reading = false;
          break;
        }
        if (value) consumeSerial(value);
      }
    } catch (err) {
      reading = false;
      appendConsole("\nDisconnected. Plug the board in and click Connect.\n");
    } finally {
      try {
        reader.releaseLock();
      } catch (err) {
        // The lock is already gone when the device unplugs.
      }
    }
  }
  if (port === current) {
    port = null;
    setConnected(false);
  }
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

function blockedMessage() {
  return "Use Chrome or Edge on a desktop computer.";
}

async function connectPort() {
  if (browserBlocked() || !("serial" in navigator)) {
    const err = new Error("blocked");
    err.code = "blocked";
    throw err;
  }
  if (portOpen()) return;
  if (opening) return;
  opening = true;
  connectBtn.disabled = true;
  try {
    let selected;
    try {
      selected = await navigator.serial.requestPort();
    } catch (err) {
      if (err && err.name === "NotFoundError") {
        const cancel = new Error("cancel");
        cancel.code = "cancel";
        throw cancel;
      }
      throw err;
    }
    await selected.open({ baudRate: 115200 });
    port = selected;
    pending = new Uint8Array(0);
    textDecoder = new TextDecoder("utf-8");
    reading = true;
    setConnected(true);
    readLoop();
  } catch (err) {
    if (!portOpen()) connectBtn.disabled = false;
    throw err;
  } finally {
    opening = false;
  }
}

function portProblem(err) {
  if (err && err.code === "blocked") return blockedMessage();
  if (err && err.code === "cancel") return "No port chosen. Click Connect when you want to try again.";
  return "Could not open the port. Close the install window, and close Arduino, Thonny, or mpremote if they are open. Then try another USB cable or port.";
}

function syncWifiConnect() {
  const picked = wifiList.querySelector("input:checked");
  wifiConnect.disabled = wifiBusy || !picked;
}

function renderNetworks(networks) {
  const previous = wifiList.querySelector("input:checked");
  const previousSsid = previous ? previous.value : "";
  const sorted = networks.slice().sort((a, b) => b.rssi - a.rssi);
  wifiList.replaceChildren();
  for (const net of sorted) {
    const li = document.createElement("li");
    const label = document.createElement("label");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "network";
    radio.value = net.ssid;
    if (net.ssid === previousSsid) radio.checked = true;
    const text = document.createElement("span");
    const lock = net.auth === "NO" ? "open" : "needs a password";
    const rssi = Number.isFinite(net.rssi) ? net.rssi : 0;
    text.textContent = net.ssid + " · " + rssi + " dBm, " + signalWord(rssi) + ", " + lock;
    label.append(radio, text);
    li.append(label);
    wifiList.append(li);
  }
  syncWifiConnect();
}

function waitForPackets(timeoutMs, onPacket) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      if (onImprov === handle) onImprov = null;
      const err = new Error("timeout");
      err.code = "timeout";
      reject(err);
    }, timeoutMs);
    function handle(packet) {
      onPacket(packet, (value) => {
        clearTimeout(timer);
        if (onImprov === handle) onImprov = null;
        resolve(value);
      }, (err) => {
        clearTimeout(timer);
        if (onImprov === handle) onImprov = null;
        reject(err);
      });
    }
    onImprov = handle;
  });
}

async function scanNetworks() {
  const found = new Map();
  wifiStatus.textContent = "Looking for Wi-Fi networks...";
  renderNetworks([]);
  const pendingResult = waitForPackets(20000, (packet, resolve, reject) => {
    if (packet.type === 2 && packet.data[0] > 0) {
      const err = new Error("scan");
      err.code = packet.data[0];
      reject(err);
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
    if (!ssid) return;
    const rssi = Number(parsed.strings[1]);
    const auth = parsed.strings[2] || "YES";
    const prev = found.get(ssid);
    if (!prev || rssi > prev.rssi) found.set(ssid, { ssid, rssi, auth });
    renderNetworks([...found.values()]);
  });
  await writeBytes(buildRpc(4, new Uint8Array(0)));
  try {
    return await pendingResult;
  } catch (err) {
    if (err && err.code === "timeout") return [...found.values()];
    throw err;
  }
}

async function sendWifi(ssid, password) {
  const name = textEncoder.encode(ssid);
  const secret = textEncoder.encode(password);
  if (name.length > 255 || secret.length > 255) {
    const err = new Error("long");
    err.code = "long";
    throw err;
  }
  const pendingResult = waitForPackets(30000, (packet, resolve, reject) => {
    if (packet.type === 2 && packet.data[0] > 0) {
      const err = new Error("connect");
      err.code = packet.data[0];
      reject(err);
      return;
    }
    if (packet.type !== 4) return;
    const parsed = parseImprovResult(packet.data);
    if (parsed.command !== 1) return;
    resolve(parsed.strings[0] || "");
  });
  await writeBytes(buildWifiRpc(ssid, password));
  return pendingResult;
}

function showWifiError(message) {
  wifiProgress.hidden = true;
  wifiError.hidden = false;
  wifiError.textContent = message;
}

async function connectSelected() {
  const chosen = wifiList.querySelector("input[name=network]:checked");
  if (!chosen || wifiBusy) {
    wifiStatus.textContent = "Pick a network from the list.";
    return;
  }
  const ssid = chosen.value;
  const password = wifiPassword.value;
  wifiBusy = true;
  syncWifiConnect();
  wifiError.hidden = true;
  wifiSuccess.hidden = true;
  wifiProgress.hidden = false;
  wifiProgress.textContent = "Connecting...";
  try {
    const url = await sendWifi(ssid, password);
    wifiProgress.hidden = true;
    const safe = safeHttpUrl(url);
    if (!safe) {
      wifiStatus.textContent = "The board connected, but it did not send a link. Try http://gsp32.local";
    } else {
      openBoard.href = safe;
      openBoardUrl.textContent = safe;
      wifiSuccess.hidden = false;
      wifiStatus.textContent = "Wi-Fi is set up.";
    }
    wifiPassword.value = "";
  } catch (err) {
    if (err && err.code === 3) showWifiError("Could not connect: check the password");
    else if (err && err.code === "long") showWifiError("That name or password is too long.");
    else showWifiError("Could not connect. Move the board closer and try again.");
  } finally {
    wifiBusy = false;
    syncWifiConnect();
  }
}

async function beginWifiSetup() {
  document.getElementById("console").scrollIntoView({ block: "start" });
  if (browserBlocked()) {
    appendConsole("\n" + blockedMessage() + "\n");
    return;
  }
  if (wifiBusy) return;
  wifiBusy = true;
  wifiPanel.hidden = false;
  wifiSuccess.hidden = true;
  wifiError.hidden = true;
  wifiProgress.hidden = true;
  wifiPassword.value = "";
  renderNetworks([]);
  syncWifiConnect();
  wifiStatus.textContent = "Asking the board to listen for Wi-Fi setup...";
  try {
    await connectPort();
    // Stop a running program, then start the board's Improv listener, then give it a moment.
    await writeBytes(new Uint8Array([0x03, 0x03]));
    await writeBytes(textEncoder.encode("import webui_wifisetup; webui_wifisetup.improvSession()\r\n"));
    await delay(1500);
    let networks = [];
    try {
      networks = await scanNetworks();
    } catch (err) {
      wifiStatus.textContent = "The board could not scan for networks. Click Set up / change Wi-Fi to try again.";
      return;
    }
    if (!networks.length) {
      wifiStatus.textContent = "No networks showed up. Move the board closer to the router, then click Set up / change Wi-Fi again.";
    } else {
      wifiStatus.textContent = "Pick a network, enter its password, and click Connect.";
    }
  } catch (err) {
    if (err && err.code === "cancel") wifiStatus.textContent = "No port chosen. Click Set up / change Wi-Fi when you want to try again.";
    else if (err && err.code === "blocked") wifiStatus.textContent = blockedMessage();
    else wifiStatus.textContent = portProblem(err);
  } finally {
    wifiBusy = false;
    syncWifiConnect();
  }
}

function guardClick(fn) {
  return () => {
    fn().catch(() => {
      appendConsole("\nSomething went wrong. Unplug the board, plug it back in, and try again.\n");
    });
  };
}

applyBrowserCheck();

eraseOk.addEventListener("change", syncInstallButton);
versionSelect.addEventListener("change", () => {
  applyManifest();
  syncInstallButton();
});

installBtn.addEventListener("click", (event) => {
  if (!eraseOk.checked) {
    event.preventDefault();
    event.stopPropagation();
    return;
  }
  phase = "idle";
  lastStateKey = "";
  installStatus.hidden = true;
  installError.hidden = true;
  afterInstall.hidden = true;
  usbOnly.hidden = true;
  wantWake = true;
  updateHiddenBanner();
  requestWakeLock();
});

installButton.addEventListener("state-changed", (event) => {
  const detail = event.detail || {};
  const state = typeof detail === "string" ? detail : detail.state;
  if (!state) return;
  onInstallState(state, typeof detail === "string" ? {} : detail);
});

document.addEventListener("visibilitychange", () => {
  updateHiddenBanner();
  if (!document.hidden && wantWake) requestWakeLock();
});

window.addEventListener("focus", () => {
  setTimeout(() => {
    if (phase === "idle" && !document.querySelector("ewt-install-dialog")) {
      wantWake = false;
      releaseWakeLock();
      updateHiddenBanner();
    }
  }, 400);
});

setupWifiBtn.addEventListener("click", guardClick(beginWifiSetup));
wifiSetupBtn.addEventListener("click", guardClick(beginWifiSetup));
skipUsbBtn.addEventListener("click", () => {
  usbOnly.hidden = false;
});

connectBtn.addEventListener("click", guardClick(async () => {
  try {
    await connectPort();
  } catch (err) {
    appendConsole("\n" + portProblem(err) + "\n");
  }
}));

resetBtn.addEventListener("click", guardClick(async () => {
  if (!portOpen()) return;
  // DTR low and RTS high holds the ESP32 in reset; dropping RTS lets it run.
  await port.setSignals({ dataTerminalReady: false, requestToSend: true });
  await delay(100);
  await port.setSignals({ requestToSend: false });
}));

ctrlCBtn.addEventListener("click", guardClick(async () => {
  await writeBytes(new Uint8Array([0x03]));
}));

consoleForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!portOpen()) return;
  const text = consoleIn.value;
  consoleIn.value = "";
  writeBytes(textEncoder.encode(text + "\r\n")).catch(() => {
    appendConsole("\nCould not send. Click Connect and try again.\n");
  });
});

wifiList.addEventListener("change", syncWifiConnect);
wifiConnect.addEventListener("click", guardClick(connectSelected));
wifiPassword.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    connectSelected().catch(() => {
      showWifiError("Could not connect. Move the board closer and try again.");
    });
  }
});

watchInstallDialog();
loadVersions().then(() => {
  if (customElements.whenDefined) {
    customElements.whenDefined("esp-web-install-button").then(applyManifest);
  }
});
