// GSP32 web installer: Get Started opens one serial port and the board card (live console plus Install GSP32,
// Set Up Wi-Fi, Open GSP32 Web UI). The install and Wi-Fi steps run inline in that card, one step at a time, with
// their output in the same console. One serial port stays open from the port pick to the end, and every open and close leaves the
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
let stable = null;
const startInstall = $("start-install");
const flashStatus = $("flash-status");
const flashBar = $("flash-bar");
const wifiStatus = $("wifi-status");
const wifiWait = $("wifi-wait");
const wifiList = $("wifi-list");
const wifiModal = $("wifi-modal");
const wifiModalStatus = $("wifi-modal-status");
const wifiModalConnect = $("wifi-modal-connect");
const wifiModalCancel = $("wifi-modal-cancel");
const wifiPassword = $("wifi-password");
const wifiError = $("wifi-error");
const wifiRescan = $("wifi-rescan");
const wifiConnect = $("wifi-connect");
const errorText = $("error-text");
const consoleCard = $("console");
const consoleBox = $("console-card");
const boardStatus = $("board-status");
const installer = $("installer");
const consoleOut = $("console-out");
const consoleIn = $("console-in");
const consoleSend = $("console-send");
const connectBtn = $("connect");
const disconnectBtn = $("disconnect");
const resetBtn = $("reset");
const ctrlCBtn = $("ctrl-c");

let versionsReady = false;
let latest = null;
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
const board = { installed: false, kind: "unknown", readyAt: 0, bootAt: 0, ip: "", name: "", repl: false, chip: "", mac: "", version: "", asked: 0, listening: false };
let otherTimer = null;
const FOLD_MS = 220;

function motionOk() {
  return !matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Height folds: content slides open and shut instead of jumping
function foldOpen(element) {
  // A fold shut still running is called off (the element stays open)
  if (element.shutting) {
    element.shutting.cancel();
    element.shutting = null;
    element.style.overflow = "";
    if (!element.hidden) return;
  }
  element.hidden = false;
  if (!motionOk()) return;
  const height = element.offsetHeight;
  element.style.overflow = "hidden";
  element.animate([{ height: "0px", opacity: 0 }, { height: height + "px", opacity: 1 }], { duration: FOLD_MS, easing: "ease-out" })
    .onfinish = () => { element.style.overflow = ""; };
}

function foldShut(element, done) {
  // Hotfix: a fold shut already running is left alone (a second one would leave the first to hide the element later)
  if (element.shutting) return;
  if (element.hidden) {
    if (done) done();
    return;
  }
  if (!motionOk()) {
    element.hidden = true;
    if (done) done();
    return;
  }
  element.style.overflow = "hidden";
  element.shutting = element.animate([{ height: element.offsetHeight + "px", opacity: 1 }, { height: "0px", opacity: 0 }], { duration: FOLD_MS, easing: "ease-in" });
  const animation = element.shutting;
  const finish = () => {
    if (element.shutting !== animation) return;
    element.shutting = null;
    element.style.overflow = "";
    element.hidden = true;
    if (done) done();
  };
  animation.onfinish = finish;
  // Hotfix: a background tab may hold the finish event back; the fold still ends on time
  setTimeout(finish, FOLD_MS + 150);
}

// A boot banner (the board restarted, e.g. Windows resets it when the port opens): "Board Booting Up..." until GSP32
//  says it is ready (or 20 s pass: other firmware). Not while esptool works
//  Version 42.1 (Gene): the button row stays put while booting, so a board stuck restarting can always be reinstalled
let bootingNote = null;
function startBooting() {
  if (busy || flashing) return;
  // Version 43.2 (Gene): the status is kept as nodes, not text, so "Wi-Fi Connected!" comes back with its second line
  //  and its link (as text both were lost: "Connected!Your board..." with a plain address)
  if (bootingNote === null) {
    bootingNote = boardStatus.hidden ? "" : {
      nodes: Array.from(boardStatus.childNodes, (node) => node.cloneNode(true)),
      kind: boardStatus.className.replace(/\b(board-status|waiting|filling|erasing)\b/g, "").trim(),
    };
  }
  setStatus("Board Booting Up...");
  startCheckWait();
}
function endBooting() {
  stopCheckWait();
  if (bootingNote === null) return;
  const before = bootingNote;
  bootingNote = null;
  if (before) {
    setStatus(" ", before.kind);
    boardStatus.replaceChildren(...before.nodes);
  } else {
    setStatus("");
  }
  const actions = $("board-actions");
  if (actions.hidden || actions.shutting) foldOpen(actions);
}

const WIFI_WAIT_MS = 20000;

// Version 42.1 (Gene): while the page waits to decide whether the board runs GSP32 (up to 20 s after a boot), a
//  countdown with a slim bar shows it is still working instead of looking frozen
const CHECK_WAIT_MS = 20000;
let checkWaitTimer = null;
function startCheckWait() {
  const box = $("check-wait");
  const started = Date.now();
  clearInterval(checkWaitTimer);
  function tick() {
    const left = Math.max(0, CHECK_WAIT_MS - (Date.now() - started));
    $("check-wait-text").textContent = "Checking for GSP32\u2026 " + Math.ceil(left / 1000) + " s";
    $("check-wait-bar").style.width = Math.min(100, 100 * (CHECK_WAIT_MS - left) / CHECK_WAIT_MS) + "%";
    if (left <= 0) clearInterval(checkWaitTimer);
  }
  tick();
  checkWaitTimer = setInterval(tick, 250);
  setFolded(box, true);
  statusWait("check", true);
}
function stopCheckWait() {
  clearInterval(checkWaitTimer);
  checkWaitTimer = null;
  setFolded($("check-wait"), false);
  statusWait("check", false);
}

// Version 43.2 (Gene, standing rule): whenever the page waits with nothing else moving (checking for the board,
//  restarting it, scanning, connecting to Wi-Fi up to a wrong password's timeout), the status line pulses blue like
//  the erase step, so it never looks frozen. Each wait adds its reason; an answer (ok, error) ends the pulse
const statusWaits = new Set();
function statusWait(reason, on) {
  if (on) statusWaits.add(reason);
  else statusWaits.delete(reason);
  syncStatusWait();
  if (typeof syncConsoleButtons === "function") setTimeout(syncConsoleButtons, 0);
}
function syncStatusWait() {
  const kind = /\b(ok|error)\b/.test(boardStatus.className);
  boardStatus.classList.toggle("waiting", statusWaits.size > 0 && !kind);
}

// Version 42.1 (Gene): an install cut short (page refreshed, cable pulled) leaves the board restarting over and over.
//  Three boots within 10 s, or the ROM's own complaints, mean "Incomplete Install Detected" with Recover GSP32
const BOOT_LOOP_COUNT = 3;
const BOOT_LOOP_MS = 10000;
let bootTimes = [];
function noteBoot() {
  const now = Date.now();
  bootTimes = bootTimes.filter((at) => now - at < BOOT_LOOP_MS);
  bootTimes.push(now);
  return bootTimes.length >= BOOT_LOOP_COUNT;
}
function markBroken() {
  if (board.kind === "broken" || busy || flashing) return;
  board.kind = "broken";
  clearTimeout(otherTimer);
  stopCheckWait();
  bootingNote = null;
  setStatus("Incomplete Install Detected. Click Recover GSP32 to erase the board and install again.", "error");
  syncBoardUi();
}

// Version 42.1: a note of the install under way, kept until it finishes, so a page refreshed mid-install offers
//  Recover GSP32 next time (and for the same board, by its MAC)
const FLASH_NOTE_KEY = "gsp32.flash";
function flashNoteGet() {
  try {
    return JSON.parse(localStorage.getItem(FLASH_NOTE_KEY) || "null");
  } catch (err) {
    return null;
  }
}
function flashNoteSet(note) {
  try {
    if (note) localStorage.setItem(FLASH_NOTE_KEY, JSON.stringify(note));
    else localStorage.removeItem(FLASH_NOTE_KEY);
  } catch (err) {
    // Storage blocked: recovery still works from the boot loop
  }
}
function flashNoteMatches() {
  const note = flashNoteGet();
  if (!note) return false;
  return !note.mac || !board.mac || note.mac === board.mac;
}
let wifiTimer = null;

// Version 43.1 (Gene): every Improv packet carries byte 3 (its RPC type), which is Ctrl-C to a board that is not
//  listening: it stopped main.py, and at the >>> prompt each retry echoed (its 0x04 soft-rebooted the board) in a loop,
//  Wi-Fi details included. Improv goes out only while the board said it listens ("GSP32 Improv Ready" at the boot
//  Wi-Fi offer, "GSP32 Improv Listening" from the web UI) and not since "GSP32 Improv Off", a boot or a prompt
function writeImprov(packet) {
  if (!board.listening) return Promise.reject(Object.assign(new Error("not listening"), { code: "quiet" }));
  return writeBytes(packet);
}

// Asks the board for its Improv device info (version, chip): once per boot, only while it listens, no retries
function askVersion() {
  if (board.version || board.asked > board.bootAt || !board.listening || !portOpen() || flashing) return;
  board.asked = Date.now();
  writeImprov(buildRpc(3, new Uint8Array(0))).catch(() => {});
}

function trackBoard(line) {
  if (/GSP32 Improv Ready|Server listening on port|Web UI starts without Wi-Fi|Web UI running/.test(line)) {
    board.kind = "gsp32";
    bootTimes = [];
    // A board running GSP32 finished its install: the note of an unfinished one no longer applies
    if (flashNoteGet() && !busy && !flashing) {
      flashNoteSet(null);
      // Version 61: the boot banner keeps the status shown before it and puts it back afterwards, so a stale
      //  "Incomplete Install Detected. Click Recover GSP32..." came back beside a Reinstall GSP32 button. Drop it
      //  from both places: the board runs GSP32, there is nothing to recover
      const stale = /^Incomplete Install/;
      if (bootingNote && stale.test(bootingNote.nodes.map((node) => node.textContent).join(""))) bootingNote = "";
      if (stale.test(boardStatus.textContent)) {
        if (bootingNote === null) setStatus("");
        else bootingNote = "";
      }
    }
    board.readyAt = Date.now();
    clearTimeout(otherTimer);
    endBooting();
  }
  // Version 43.1: only these lines open the door for Improv; the version is asked then, once
  if (/GSP32 Improv (Ready|Listening)/.test(line)) {
    board.kind = "gsp32";
    board.listening = true;
    board.readyAt = Date.now();
    askVersion();
  }
  if (/GSP32 Improv Off|No answer: starting without Wi-Fi|^Traceback|KeyboardInterrupt|^MicroPython v/.test(line)) board.listening = false;
  if (/invalid header|ota data partition invalid|checksum (error|failure)|image checksum|flash read err/i.test(line)) {
    markBroken();
    return;
  }
  if (board.kind === "broken" && /^rst:0x|^ets [A-Z][a-z]{2} /.test(line)) return;
  if (/^rst:0x/.test(line) && noteBoot()) {
    markBroken();
    return;
  }
  if (/^rst:0x|^ets [A-Z][a-z]{2} /.test(line)) {
    board.bootAt = Date.now();
    board.repl = false;
    board.listening = false;
    board.wifiWait = false;
    board.wifiFailed = false;
    clearTimeout(wifiTimer);
    clearTimeout(otherTimer);
    startBooting();
    // No GSP32 line within 20 s of a boot: some other firmware
    otherTimer = setTimeout(() => {
      if (board.readyAt < board.bootAt) {
        board.kind = "other";
        endBooting();
        syncBoardUi();
      }
    }, 20000);
  }
  // Version 37: a board with saved Wi-Fi says "Connecting to WiFi..." at boot; the Open button waits greyed until it
  //  connects (space kept, no jump), and after 20 s without Wi-Fi the note says so
  if (/^Connecting to WiFi/.test(line)) {
    board.wifiWait = true;
    board.wifiFailed = false;
    clearTimeout(wifiTimer);
    wifiTimer = setTimeout(() => {
      if (board.wifiWait && !board.ip) {
        board.wifiWait = false;
        board.wifiFailed = true;
        syncBoardUi();
      }
    }, WIFI_WAIT_MS);
  }
  if (/Could not (start )?connect(ing)? to WiFi/.test(line)) {
    clearTimeout(wifiTimer);
    board.wifiWait = false;
    board.wifiFailed = true;
  }
  let match = line.match(/Network config: \('(\d+\.\d+\.\d+\.\d+)'/) || line.match(/^Connected: (\d+\.\d+\.\d+\.\d+)/);
  if (match) {
    board.ip = match[1];
    board.wifiWait = false;
    board.wifiFailed = false;
    clearTimeout(wifiTimer);
  }
  match = line.match(/mDNS name: ([\w.-]+\.local)/);
  if (match) board.name = match[1];
  if (/Wi-Fi lost|Connection lost|starts without Wi-Fi/.test(line)) board.ip = "";
  syncBoardUi();
  syncActions();
}

// Show only the buttons that apply. Version 30 (Gene): a button that is added or removed slides open or shut sideways
//  (width, padding and the row's gap with it), so its neighbours move along smoothly instead of jumping
function setShown(element, on) {
  const showing = element.sliding ? element.sliding.on : !element.hidden;
  if (showing === on) return;
  if (element.sliding) {
    element.sliding.animation.cancel();
    element.sliding = null;
  }
  if (on) element.hidden = false;
  if (!motionOk()) {
    element.hidden = !on;
    return;
  }
  const style = getComputedStyle(element);
  const gap = parseFloat(getComputedStyle(element.parentNode).columnGap) || 0;
  const open = { width: element.offsetWidth + "px", paddingLeft: style.paddingLeft, paddingRight: style.paddingRight,
                 borderLeftWidth: style.borderLeftWidth, borderRightWidth: style.borderRightWidth, marginRight: "0px", opacity: 1 };
  const shut = { width: "0px", paddingLeft: "0px", paddingRight: "0px", borderLeftWidth: "0px", borderRightWidth: "0px",
                 marginRight: -gap + "px", opacity: 0 };
  element.style.overflow = "hidden";
  element.style.whiteSpace = "nowrap";
  const animation = element.animate(on ? [shut, open] : [open, shut], { duration: FOLD_MS, easing: on ? "ease-out" : "ease-in" });
  element.sliding = { on, animation };
  animation.onfinish = () => {
    element.sliding = null;
    element.style.overflow = "";
    element.style.whiteSpace = "";
    if (!on) element.hidden = true;
  };
}

// Panels inside a wizard step (Wi-Fi form, wait note, error) fold up and down instead of jumping
function setFolded(element, on) {
  // Version 43.2: the Wi-Fi step's wait (board restart, scan, connect) is a wait with nothing moving: pulse
  if (element === wifiWait) statusWait("wifi", on);
  if (on) {
    if (element.hidden || element.shutting) foldOpen(element);
  } else if (!element.hidden && !element.shutting) {
    foldShut(element);
  }
}

function syncBoardUi() {
  const setup = $("wifi-setup"), web = $("console-webui"), install = $("install-btn");
  const on = portOpen();
  const gsp32 = board.kind === "gsp32";
  // Version 42.1: a half-finished install (boot loop, or the saved note of an install that never ended) offers Recover
  const broken = board.kind === "broken" || (!gsp32 && flashNoteMatches());
  install.disabled = !on || busy;
  install.textContent = broken ? "Recover GSP32" : gsp32 ? "Reinstall GSP32" : "Install GSP32";
  // While installing, Wi-Fi and the web UI button are gone (not greyed); they come back after
  setShown(setup, gsp32 && !flashing);
  setup.disabled = !on || busy;
  const address = gsp32 && board.ip ? "http://" + board.ip + "/" : "";
  web.href = address || "#";
  // Waiting for Wi-Fi (or it never came): shown greyed, not clickable; it fades to blue once the address is known
  const waiting = gsp32 && !address && (board.wifiWait || board.wifiFailed);
  setShown(web, !!((address || waiting) && on && !flashing));
  web.classList.toggle("waiting", waiting);
  if (waiting) {
    web.setAttribute("aria-disabled", "true");
    web.tabIndex = -1;
  } else {
    web.removeAttribute("aria-disabled");
    web.removeAttribute("tabindex");
  }
  // The next step is the solid blue button, the others light blue: Install on a board without GSP32, Set Up Wi-Fi
  //  once GSP32 runs, Open GSP32 Web UI once it is on Wi-Fi
  const next = !gsp32 ? install : address ? web : setup;
  for (const button of [install, setup, web]) {
    button.classList.toggle("primary", button === next);
    button.classList.toggle("secondary", button !== next);
  }
  web.title = waiting ? (board.wifiFailed ? "Wi-Fi Didn't Connect" : "Waiting for Wi-Fi...") : address ? "Open " + address + (board.name ? " (also http://" + board.name + "/)" : "") : "";
  $("board-chip").textContent = (board.chip || "ESP32 Board").replace(/\s*\(revision[^)]*\)/i, "");
  const mac = $("board-mac");
  mac.textContent = board.mac ? "MAC " + board.mac.toUpperCase() : "";
  setShown(mac, !!board.mac);
  setup.textContent = address || waiting ? "Change Wi-Fi" : "Set Up Wi-Fi";
  const state = $("board-state");
  state.textContent = !on ? "Not Connected"
    : board.note ? board.note
    : broken ? "Incomplete Install Detected"
    : gsp32 ? (board.version ? "GSP32 Version " + board.version + " Found" : "GSP32 Found")
    : board.installed ? "Installed, Restarting..."
    : board.kind === "other" ? "No GSP32 Found" : "Checking the Board...";
  if (on && gsp32 && address && !board.note) {
    const link = document.createElement("a");
    link.href = address;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = address;
    const line = document.createElement("span");
    line.className = "web-line";
    line.append("Web UI: ", link);
    state.append(line);
  } else if (on && waiting && !board.note) {
    const line = document.createElement("span");
    line.className = "web-line wifi-note";
    line.textContent = board.wifiFailed ? "Wi-Fi Didn't Connect" : "Waiting for Wi-Fi\u2026";
    state.append(line);
  }
  state.classList.toggle("on", on && gsp32);
  // Version 39: the green box folds away while installing and comes back when it ends (done, failed or disconnected)
  setFolded(state, !flashing);
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

// Wizard steps: inline in the board card; the current step replaces the last one and the box changes height smoothly
function showStep(name) {
  const wasHidden = wizard.hidden;
  const before = wasHidden ? 0 : wizard.offsetHeight;
  for (const step of wizard.querySelectorAll(".step")) step.hidden = step.dataset.step !== name;
  setTimeout(syncConsoleButtons, 0);
  if (wasHidden) {
    foldOpen(wizard);
    return;
  }
  if (motionOk()) {
    const after = wizard.offsetHeight;
    if (after !== before) wizard.animate([{ height: before + "px" }, { height: after + "px" }], { duration: FOLD_MS, easing: "ease-out" });
  }
}

function closeWizard() {
  if (busy) return;
  onImprov = null;
  keepSession(false);
  foldShut(wizard);
  statusWait("wifi", false);
  syncConsoleButtons();
}

function setBusy(on) {
  busy = on;
  if (typeof syncConsoleButtons === "function") setTimeout(syncConsoleButtons, 0);
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
  setStatus(message, "error");
  retryStep = retry || "prep";
  errorText.textContent = message;
  showStep("error");
}

// Console text
// The console follows the newest output until the user scrolls up, and again once they scroll back to the bottom.
//  Version 30: decided by the user's scrolling, not measured at each paint (a fold or a hidden console measured as
//  "not at the bottom" and stopped the following for good)
let followConsole = true;
consoleOut.addEventListener("scroll", () => {
  if (consoleOut.clientHeight) followConsole = consoleOut.scrollHeight - consoleOut.scrollTop - consoleOut.clientHeight < 48;
});
function paintConsole() {
  consoleOut.textContent = lines.join("\n") + (partial ? (lines.length ? "\n" : "") + partial : "");
  if (followConsole) consoleOut.scrollTop = consoleOut.scrollHeight;
}

function appendConsole(text) {
  if (!text) return;
  partial += text;
  const pieces = partial.split("\n");
  partial = pieces.pop();
  if (/>>> ?$/.test(partial)) {
    board.repl = true;
    board.listening = false;
  }
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
      // Device info: firmware, version, chip family, device name
      if (parsed.command === 3 && parsed.strings.length >= 3) {
        if (!board.chip && parsed.strings[2]) board.chip = parsed.strings[2];
        const v = parsed.strings[1] || "";
        const n = v.match(/^(?:Version\s*)?(\d{2,}(?:\.\d+)?)$/i);
        if (n) board.version = n[1];
      }
    }
    // An answer means a session is running on the board (it answers, so it listens)
    board.listening = true;
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

function flasherWorking() {
  const step = (wizard.hidden || wizard.shutting) ? "" : (wizard.querySelector(".step:not([hidden])") || {}).dataset?.step || "";
  return busy || statusWaits.size > 0 || step === "flash" || step === "wifi";
}

function syncConsoleButtons() {
  const on = portOpen();
  connectBtn.disabled = on;
  disconnectBtn.disabled = !on || busy;
  resetBtn.disabled = !on || busy;
  ctrlCBtn.disabled = !on || busy;
  // Version 48 (Gene): no typing while the flasher works (install, erase, Wi-Fi setup, board checks and restarts)
  const working = flasherWorking();
  consoleIn.disabled = !on || working;
  consoleSend.disabled = !on || working;
  // Version 61 (Gene): just "Busy ..." in the box, no tip under it
  consoleIn.placeholder = on && working ? "Busy ..." : "";
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
          appendConsole("\n[The board disconnected. Plug it in and click Get Started.]\n");
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
  portBaud = FLASH_BAUD;
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
    // Only the latest build is offered (older images were removed from the repo; they stay in git history); Version 73: no
    //  prototype choice any more
    stable = list.find((item) => !item.prototype) || null;
    latest = stable;
    const number = latest ? String(latest.label || latest.version).match(/Version (\d+(?:\.\d+)?)/) : null;
    versionSelect.textContent = number ? "Version " + number[1] : latest ? String(latest.label || latest.version) : "No Version Found";
    versionsReady = !!latest;
  } catch (err) {
    versionSelect.textContent = "Could Not Load the Version";
    versionsReady = false;
  }
  syncStart();
}

function syncStart() {
  startInstall.disabled = !versionsReady || !eraseOk.checked;
}

// Version 79: one manifest, one build per chip family ("ESP32", "ESP32-S3"), as esp-web-tools picks them. The
//  manifest is read before connecting; the build's image is downloaded once the board has said which chip it is
let manifestCache = null;
async function loadManifest() {
  const manifestUrl = new URL(latest.manifest, location.href);
  const manifest = await (await fetch(manifestUrl, { cache: "no-store" })).json();
  manifestCache = { manifest, manifestUrl };
  return manifestCache;
}
// The chip family for esptool-js's chip name: "ESP32-S3" for an S3, "ESP32" for a classic ESP32, "" otherwise
function chipFamily(chip) {
  if (/ESP32-S3/.test(chip)) return "ESP32-S3";
  if (/ESP32/.test(chip) && !/ESP32-(S|C|H|P)/.test(chip)) return "ESP32";
  return "";
}
async function loadFirmware(family) {
  const { manifest, manifestUrl } = manifestCache || await loadManifest();
  const build = manifest.builds.find((item) => item.chipFamily === family);
  if (!build) throw new Error("This firmware has no build for " + family + ".");
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

// "Version 30" for the status line (the picked build), "GSP32" when it has no number
function installName() {
  const picked = versionSelect.textContent.match(/Version \d+(?:\.\d+)?/);
  return picked ? picked[0] : "GSP32";
}

// Hotfix (Gene): the row comes back whenever nothing holds it away (no install, no boot under way), whatever order
//  the board's lines, the install's end and the folds came in; checked on every board line and once a second
let actionsWanted = true;
function syncActions() {
  const actions = $("board-actions");
  if (!actionsWanted || busy || flashing || !portOpen()) return;
  if (actions.hidden || actions.shutting) foldOpen(actions);
}
setInterval(() => { if (typeof consoleCard !== "undefined" && !consoleCard.hidden) syncActions(); }, 1000);

// The install button row folds away while an install runs and comes back when it is done, failed or called off
function showActions(on) {
  const actions = $("board-actions");
  if (on) actionsWanted = true;
  if (!on) actionsWanted = false;
  if (on && (actions.hidden || actions.shutting)) foldOpen(actions);
  if (!on && !actions.hidden && !actions.shutting) foldShut(actions);
}

// The status line is the progress bar: its background fills left to right (--fill) under the text
//  Version 42: erasing gently pulses the bar blue (nothing else moves then); the next setProgress, writing, ends it
function setProgress(text, percent, status, erasing) {
  flashStatus.textContent = text;
  if (percent != null) flashBar.style.width = Math.max(0, Math.min(100, percent)) + "%";
  setStatus(status || "Installing " + installName() + " (" + Math.max(0, Math.round(percent || 0)) + "%)");
  boardStatus.classList.add("filling");
  boardStatus.classList.toggle("erasing", !!erasing);
  if (percent != null) boardStatus.style.setProperty("--fill", Math.max(0, Math.min(100, percent)) + "%");
}

// Version 75 (Gene): "About 3 Minutes Left" from the write speed. Nothing is shown until the estimate settles: at
//  least 5 s and 3% into writing, and three estimates in a row within 20% of each other. The words then only change
//  when the rounded time does, and the time never jumps back up by a little
function makeTimeLeft() {
  let first = null, smooth = null, recent = [], shown = "", shownSeconds = Infinity;
  function words(seconds) {
    if (seconds >= 90) {
      const minutes = Math.round(seconds / 60);
      return "About " + minutes + " Minutes Left";
    }
    if (seconds >= 50) return "About 1 Minute Left";
    if (seconds >= 15) return "About " + Math.round(seconds / 10) * 10 + " Seconds Left";
    return "Almost Done";
  }
  return {
    add(fraction) {
      const now = Date.now();
      if (!first) {
        first = { at: now, fraction };
        return "";
      }
      const spent = (now - first.at) / 1000, done = fraction - first.fraction;
      if (spent < 5 || done < 0.03 || fraction >= 1) return fraction >= 1 ? "" : shown;
      const estimate = spent * (1 - fraction) / done;
      smooth = smooth === null ? estimate : smooth * 0.7 + estimate * 0.3;
      recent.push(smooth);
      if (recent.length > 3) recent.shift();
      if (!shown) {
        const low = Math.min(...recent), high = Math.max(...recent);
        if (recent.length < 3 || high > low * 1.2) return "";
      }
      // Small bumps up are ignored so the countdown does not flicker back
      if (smooth > shownSeconds && smooth < shownSeconds * 1.15) return shown;
      shownSeconds = smooth;
      shown = words(smooth);
      return shown;
    },
  };
}

// The wizard's own status texts (Wi-Fi steps, errors) are shown only in the status line, never twice
function mirrorStatus() {
  new MutationObserver(function () {
    if (wifiStatus.textContent && !wifiStatus.closest(".step").hidden) setStatus(wifiStatus.textContent);
  }).observe(wifiStatus, { childList: true, characterData: true, subtree: true });
  new MutationObserver(function () {
    if (errorText.textContent) setStatus(errorText.textContent, "error");
  }).observe(errorText, { childList: true, characterData: true, subtree: true });
}
mirrorStatus();

// The board card's status line: what is going on right now (Installing (45%), Installation Successful,
//  Connecting to Wi-Fi..., Wi-Fi Connected, or the error); "" folds it away
function setStatus(text, kind, ip) {
  if (!text) {
    if (!boardStatus.hidden) foldShut(boardStatus);
    return;
  }
  boardStatus.textContent = text;
  // "Wi-Fi Connected: 192.168.2.228" with the address as a link
  if (ip) {
    const link = document.createElement("a");
    link.href = "http://" + ip + "/";
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = ip;
    boardStatus.append(": ", link);
  }
  boardStatus.className = "board-status" + (kind ? " " + kind : "");
  syncStatusWait();
  boardStatus.style.removeProperty("--fill");
  if (boardStatus.hidden) foldOpen(boardStatus);
}

// Version 64 (Gene): every install runs at 115200. Faster rates were tried in Versions 49-63; Chrome and Edge on
//  Windows restart CP2102 boards whenever the port reopens for a speed change, so none held up (see IDEAS.md)
let portBaud = FLASH_BAUD;
async function reopenPort(baud) {
  if (!port || portBaud === baud) return;
  await port.close();
  await port.open({ baudRate: baud });
  portBaud = baud;
  await setRunState().catch(() => {});
}
// Version 61: every connect step has a hard time limit, so a board that does not answer never hangs the page
const READ_MS = 3000;         // one chip or MAC read
const CONNECT_MS = 12000;     // reset into the bootloader, sync and load the stub at 115200
function withTimeout(promise, ms, what) {
  let timer;
  const limit = new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error(what + " took longer than " + Math.round(ms / 1000) + " s")), ms);
  });
  return Promise.race([promise, limit]).finally(() => clearTimeout(timer));
}
// Version 61: full cleanup between attempts. Cancel and release esptool's reader (a read left pending on a dead
//  rate keeps the stream locked), then close the port and open it fresh at 115200. Each part is time-limited too.
async function resetLink(link) {
  const transport = link && link.transport;
  if (transport && transport.reader) {
    await withTimeout(transport.reader.cancel(), 1000, "Releasing the port").catch(() => {});
    try {
      transport.reader.releaseLock();
    } catch (err) {
      // Released already
    }
    transport.reader = undefined;
  }
  if (transport) transport.buffer = new Uint8Array(0);
  if (!port) return;
  await withTimeout(port.close(), 2000, "Closing the port").catch(() => {});
  await withTimeout(port.open({ baudRate: FLASH_BAUD }), 2000, "Opening the port");
  portBaud = FLASH_BAUD;
  await setRunState().catch(() => {});
}
// A borrowed transport on the open port and a loader in the board's flasher stub at 115200
async function connectLoader(terminal) {
  await reopenPort(FLASH_BAUD);
  const transport = new Transport(port, false);
  // The port is already open at 115200: esptool-js borrows its reader
  transport.connect = async function (baud) {
    this.baudrate = baud;
    await reopenPort(baud);
    this.reader = port.readable.getReader();
  };
  transport.disconnect = async function () {
    if (this.reader) {
      await withTimeout(this.reader.cancel(), 1000, "Releasing the port").catch(() => {});
      try {
        this.reader.releaseLock();
      } catch (err) {
        // Released already
      }
    }
    this.reader = undefined;
  };
  // Version 61: esptool-js 0.5.7's flushInput awaits reader.closed, which only settles once the port closes, so
  //  on an open port it waits forever (the Version 60 hang). Ours drains, bounded (see drainInput)
  transport.flushInput = async function () {
    await drainInput(this);
  };
  const loader = new ESPLoader({ transport, baudrate: FLASH_BAUD, romBaudrate: FLASH_BAUD, terminal });
  const link = { transport, loader, chip: "" };
  try {
    link.chip = await withTimeout(loader.main("default_reset"), CONNECT_MS, "Connecting to the board");
    board.chip = (await withTimeout(loader.chip.getChipDescription(loader), READ_MS, "Reading the chip")) || link.chip;
    board.mac = (await withTimeout(loader.chip.readMac(loader), READ_MS, "Reading the MAC")) || "";
    flashNoteSet(Object.assign(flashNoteGet() || {}, { mac: board.mac }));
  } catch (err) {
    if (!link.chip) {
      await resetLink(link).catch(() => {});
      throw err;
    }
    board.chip = link.chip;
  }
  return link;
}
// Read and discard what is waiting until 100 ms pass with nothing (500 ms at most), then a fresh reader, which also
//  drops any read left waiting by an earlier timeout. Bounded throughout, so it can never hang
async function drainInput(transport, quietMs = 100, maxMs = 500) {
  let dropped = transport.buffer ? transport.buffer.length : 0;
  transport.buffer = new Uint8Array(0);
  const reader = transport.reader;
  if (!reader) return dropped;
  const started = Date.now();
  let pending = reader.read();
  while (Date.now() - started < maxMs) {
    const got = await Promise.race([pending.catch(() => ({ done: true })), delay(quietMs).then(() => null)]);
    if (got === null || got.done) break;
    dropped += got.value ? got.value.length : 0;
    pending = reader.read();
  }
  await withTimeout(reader.cancel(), 300, "Releasing the port").catch(() => {});
  try {
    reader.releaseLock();
  } catch (err) {
    // Released already
  }
  transport.reader = port && port.readable ? port.readable.getReader() : undefined;
  transport.buffer = new Uint8Array(0);
  return dropped;
}
// Step 2: port, then flash with esptool-js on the same open port
async function install() {
  showActions(false);
  showStep("flash");
  startFlashGuard();
  setBusy(true);
  syncConsoleButtons();
  if (!portOpen()) {
    stopFlashGuard();
    showError("The board is not connected. Click Get Started, then try again.", "prep");
    showActions(true);
    return;
  }
  appendConsole("\n[Installing " + versionSelect.textContent + "]\n");
  try {
    setProgress("Downloading the firmware...", 0, "Installing " + installName() + ": Downloading the Firmware...");
    await loadManifest();
    // Version 79: the image follows the chip, so it is fetched once per family after the first connect
    const imageFor = {};
    await stopReading();
    const terminal = {
      clean() {},
      writeLine(text) { appendConsole("[esptool] " + text + "\n"); },
      write(text) { appendConsole(text); },
    };
    const pickedStart = versionSelect.textContent.match(/Version (\d+(?:\.\d+)?)/);
    flashNoteSet({ mac: board.mac || "", version: pickedStart ? pickedStart[1] : "", startedAt: Date.now() });
    // Version 64: connect and write at 115200, always the full image. A write error (the occasional
    //  "Invalid head of packet (0xff)") gets one fresh connect and a second full try before it is shown
    for (let attempt = 1; ; attempt++) {
      setProgress("Connecting to the board...", 0, "Installing " + installName() + ": Connecting to the Board...");
      let link;
      try {
        link = await connectLoader(terminal);
      } catch (err) {
        // Version 61: one more try from a clean port, then a clear error with Retry
        appendConsole("[Connect did not answer (" + (err && err.message ? err.message : err) + "), trying once more]\n");
        try {
          link = await connectLoader(terminal);
        } catch (again) {
          throw new Error("The board did not answer. Unplug it, plug it back in and click Try Again. If it still does not answer, hold the BOOT button while you click Try Again.");
        }
      }
      const chip = link.chip;
      const family = chipFamily(chip);
      if (!family) {
        await link.transport.disconnect();
        throw new Error("This board is " + chip + ". GSP32 runs on ESP32 and ESP32-S3 boards.");
      }
      if (!imageFor[family]) {
        setProgress("Downloading the firmware for " + family + "...", 0, "Installing " + installName() + ": Downloading the Firmware...");
        appendConsole("[" + family + " detected: installing its build]\n");
        imageFor[family] = await loadFirmware(family);
      }
      const files = imageFor[family];
      // The whole chip is erased first: about 15 s for 4 MB, longer for an S3's 16 MB
      const eraseWords = family === "ESP32-S3" ? "about a minute" : "about 15 seconds";
      setProgress("Erasing the board (" + eraseWords + ")...", 0, "Installing " + installName() + ": Erasing the Board...", true);
      let lastPercent = -1;
      const started = Date.now();
      const timeLeft = makeTimeLeft();
      try {
        await link.loader.writeFlash({
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
              const left = timeLeft.add(written / total);
              setProgress("Writing the firmware... " + percent + "%", percent,
                "Installing " + installName() + " (" + percent + "%" + (left ? ", " + left : "") + ")");
              if (percent % 10 === 0) appendConsole("[esptool] Written " + percent + "%\n");
            }
          },
        });
      } catch (err) {
        await link.transport.disconnect();
        if (attempt >= 2) throw err;
        appendConsole("[Write failed (" + (err && err.message ? err.message : err) + "). Starting over once.]\n");
        await resetLink(link).catch(() => {});
        continue;
      }
      appendConsole("[Written in " + Math.round((Date.now() - started) / 1000) + " s, compressed]\n");
      await link.transport.disconnect();
      break;
    }
    await reopenPort(FLASH_BAUD);
    setProgress("Restarting the board...", 100, "Installing " + installName() + " (100%): Restarting the Board...");
    // Detect again from the new boot: the buttons follow what the fresh firmware prints
    board.kind = "unknown";
    board.ip = "";
    board.readyAt = 0;
    const picked = versionSelect.textContent.match(/Version (\d+(?:\.\d+)?)/);
    board.version = picked ? picked[1] : "";
    board.installed = true;
    flashNoteSet(null);
    bootTimes = [];
    appendConsole("[Installed. Restarting the board.]\n");
    await resetBoard();
    setStatus(installName() + " Installed", "ok");
    // Version 75 (Gene): what to do next, so a newcomer knows the Set Up Wi-Fi button is the way to the Web UI
    const next = document.createElement("span");
    next.className = "status-more next-step";
    next.append("Next: click ", Object.assign(document.createElement("b"), { textContent: "Set Up Wi-Fi" }),
      " above to connect the board to your Wi-Fi network. Then you can open the GSP32 Web UI from any browser on that network.");
    boardStatus.append(" ", next);
    startReading();
    setBusy(false);
    stopFlashGuard();
    closeWizard();
    showActions(true);
    syncActions();
  } catch (err) {
    await reopenPort(FLASH_BAUD).catch(() => {});
    await setRunState().catch(() => {});
    startReading();
    setBusy(false);
    stopFlashGuard();
    showError("The install did not finish: " + (err && err.message ? err.message : err), "prep");
    showActions(true);
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
// Resolves once the board says it listens for Improv (or after timeoutMs)
//  Version 43.2 (Gene): GSP32 before 43.1 never says "Listening" on a board with Wi-Fi. Once the board is up (its
//  network line or "main.py running") and OLD_FIRMWARE_MS pass without it, board.oldFirmware is set and this ends
const OLD_FIRMWARE_MS = 8000;
function waitListening(timeoutMs) {
  const since = Date.now();
  let upAt = 0;
  const watch = (line) => {
    if (!upAt && /^main\.py running|^Network config:/.test(line)) upAt = Date.now();
  };
  lineWatchers.push(watch);
  board.oldFirmware = false;
  return new Promise((resolve) => {
    const timer = setInterval(() => {
      const old = !board.listening && upAt > 0 && Date.now() - upAt > OLD_FIRMWARE_MS;
      if (board.listening || board.kind === "other" || old || Date.now() - since > timeoutMs) {
        clearInterval(timer);
        lineWatchers = lineWatchers.filter((item) => item !== watch);
        board.oldFirmware = old;
        resolve(board.listening);
      }
    }, 100);
  });
}

// Version 43.1: the board's session ends after 60 s without a packet, and the web UI then stops listening; while the
//  Wi-Fi step is open a state request every 20 s keeps it going (only while it still listens)
let keepAliveTimer = null;
function keepSession(on) {
  clearInterval(keepAliveTimer);
  keepAliveTimer = null;
  if (!on) return;
  keepAliveTimer = setInterval(() => {
    if (busy || onImprov) return;
    if (!board.listening || wizard.hidden) {
      keepSession(false);
      return;
    }
    waitBoardReady(1500).catch(() => null);
  }, 20000);
}

async function waitBoardReady(timeoutMs) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end && board.listening) {
    const answer = waitForPackets(1500, (packet, resolve) => {
      if (packet.type === 1) resolve(packet.data[0]);
    });
    await writeImprov(buildRpc(2, new Uint8Array(0)));
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
  await writeImprov(buildRpc(4, new Uint8Array(0)));
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
  wifiConnect.disabled = busy || !picked;
  wifiModalConnect.disabled = busy;
  wifiModalCancel.disabled = busy;
  wifiPassword.disabled = busy;
}

async function startWifi(fresh) {
  showStep("wifi");
  setTimeout(() => wizard.scrollIntoView({ behavior: motionOk() ? "smooth" : "auto", block: "nearest" }), motionOk() ? FOLD_MS : 0);
  setFolded(wifiError, false);
  setShown(wifiRescan, false);
  wifiPassword.value = "";
  wifiList.replaceChildren();
  setFolded(wifiWait, true);
  setBusy(true);
  syncWifiConnect();
  try {
    if (!portOpen()) await pickPort();
    wifiStatus.textContent = "Waiting for the board to start...";
    // Never Ctrl-C, never typed at the prompt: Improv goes out only while GSP32 says it listens (see writeImprov).
    //  A board on Wi-Fi listens for 30 s after a boot, so one that is not listening is restarted first
    if (!board.listening) {
      if (!fresh) {
        wifiStatus.textContent = "Restarting the board so GSP32 listens for Wi-Fi setup...";
        await resetBoard();
      }
      await waitListening(45000);
    }
    const state = board.listening ? await waitBoardReady(8000) : null;
    if (state === null && board.oldFirmware) throw new Error("This board runs an older GSP32. Install Version 43.1 or newer to change Wi-Fi here.");
    if (state === null && board.kind === "other") throw new Error("This board does not run GSP32. Install GSP32 first to set up Wi-Fi.");
    if (state === null) throw new Error("The board did not answer. Check that GSP32 is installed, then try again.");
    await scanForWifi();
    keepSession(true);
  } catch (err) {
    setFolded(wifiWait, false);
    setBusy(false);
    wifiStatus.textContent = err.message;
    setShown(wifiRescan, true);
    wifiRescan.textContent = "Try Again";
  }
  syncWifiConnect();
}

async function scanForWifi() {
  // Version 43.1: a board that stopped listening is restarted (startWifi) instead of reporting "No networks found"
  if (!board.listening) return startWifi(false);
  setBusy(true);
  setFolded(wifiWait, true);
  setShown(wifiRescan, false);
  wifiStatus.textContent = "Looking for Wi-Fi networks...";
  syncWifiConnect();
  let networks = [];
  try {
    networks = await scanNetworks();
  } catch (err) {
    networks = [];
  }
  setFolded(wifiWait, false);
  setBusy(false);
  renderNetworks(networks);
  setShown(wifiRescan, true);
  wifiRescan.textContent = "Scan Again";
  wifiStatus.textContent = networks.length
    ? "Pick your network, then click Connect."
    : "No networks found. Move the board closer to the router, then click Scan Again.";
  syncWifiConnect();
}

async function connectWifi() {
  const picked = wifiList.querySelector("input:checked");
  if (!picked || busy) return;
  const name = textEncoder.encode(picked.value);
  const secret = textEncoder.encode(wifiPassword.value);
  setFolded(wifiError, false);
  if (name.length > 255 || secret.length > 255) {
    setFolded(wifiError, true);
    wifiError.textContent = "That name or password is too long.";
    return;
  }
  setBusy(true);
  syncWifiConnect();
  setFolded(wifiWait, true);
  modalWait("Connecting to Wi-Fi (" + picked.value + ")...");
  wifiStatus.textContent = "Connecting to Wi-Fi (" + picked.value + ")...";
  setStatus("Connecting to Wi-Fi (" + picked.value + ")...");
  appendConsole("\n[Connecting to Wi-Fi (" + picked.value + ")...]\n");
  try {
    // SECURITY (Version 43.1): the name and password go out only right after the board's session answered
    const state = board.listening ? await waitBoardReady(3000) : null;
    if (state === null) {
      throw Object.assign(new Error("quiet"), { code: "quiet" });
    }
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
    await writeImprov(buildWifiRpc(picked.value, wifiPassword.value));
    const url = safeHttpUrl(await result);
    wifiPassword.value = "";
    modalWait("");
    if (wifiModal.open) wifiModal.close();
    finishWifi(url);
  } catch (err) {
    setFolded(wifiWait, false);
    setBusy(false);
    setFolded(wifiError, true);
    wifiError.textContent = err.code === "quiet"
      ? "The board stopped listening for Wi-Fi setup. Click Scan Again, then try again."
      : err.code === 3
      ? "Could not connect. Check the password and try again."
      : "Could not connect. Move the board closer to the router and try again.";
    wifiStatus.textContent = "Pick your network, then click Connect.";
    setStatus(wifiError.textContent, "error");
    modalWait("");
    syncWifiConnect();
    if (wifiModal.open) {
      wifiPassword.select();
      wifiPassword.focus();
    }
  }
}

// Version 46: the password window's status line pulses while the board connects (a wait with nothing moving)
function modalWait(text) {
  wifiModalStatus.textContent = text;
  wifiModalStatus.classList.toggle("waiting", !!text);
  setFolded(wifiModalStatus, !!text);
}

function openWifiModal() {
  const picked = wifiList.querySelector("input:checked");
  if (!picked || busy) return;
  if (picked.dataset.open) {
    connectWifi();
    return;
  }
  $("wifi-modal-title").textContent = "Wi-Fi Password for " + picked.value;
  wifiPassword.value = "";
  setFolded(wifiError, false);
  modalWait("");
  wifiModal.showModal();
  wifiPassword.focus();
}

// Step 5: the board joined Wi-Fi on its own (the Improv result carries its address): no reset; the card shows it
function finishWifi(url) {
  setBusy(false);
  const ip = url ? new URL(url).hostname : "";
  if (!ip) {
    showError("The board did not report its address. The console below shows what it printed.", "prep");
    return;
  }
  board.ip = ip;
  appendConsole("\n[Wi-Fi connected. GSP32 web UI: http://" + ip + "/]\n");
  // Version 39: plain words for newcomers, with the address as a link
  setStatus("Wi-Fi Connected!", "ok");
  const ready = document.createElement("span");
  ready.className = "status-more";
  const link = document.createElement("a");
  link.href = "http://" + ip + "/";
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = "http://" + ip + "/";
  ready.append("Your board is ready. Open ", link, " in a browser on the same network to use GSP32, or click Open Web UI.");
  // Version 43.2 (Gene): a space after "Wi-Fi Connected!" (copied or read aloud, the lines no longer run together)
  boardStatus.append(" ", ready);
  onImprov = null;
  foldShut(wizard);
  syncConsoleButtons();
}

// While flashing: the red warning under the progress bar folds open, and away when done (Version 38)
let flashing = false;
function startFlashGuard() {
  flashing = true;
  stopCheckWait();
  syncBoardUi();
  setFolded($("flash-warn"), true);
}
function stopFlashGuard() {
  flashing = false;
  // The board's Ready line may have come while esptool still held the port: ask now if it still listens
  askVersion();
  syncBoardUi();
  setFolded($("flash-warn"), false);
}

// Start state <-> board card: the steps and Get Started fold away while the card slides in, and back on Disconnect
function showConsole() {
  foldShut(installer);
  // Version 38: the page title and its text fold away with the steps, making room for the board card and console
  if (!$("page-head").hidden && !$("page-head").shutting) foldShut($("page-head"));
  boardStatus.hidden = true;
  bootingNote = null;
  $("board-actions").hidden = false;
  if (consoleCard.hidden) foldOpen(consoleCard);
  if (consoleBox.hidden) {
    foldOpen(consoleBox);
    // Sized again once the start row has folded away above it
    setTimeout(sizeConsole, FOLD_MS + 40);
  }
  paintConsole();
}

function hideConsole() {
  stopCheckWait();
  if (!busy) closeWizard();
  foldShut(consoleBox);
  foldShut(consoleCard, () => {
    wizard.hidden = true;
    boardStatus.hidden = true;
    foldOpen(installer);
    if ($("page-head").hidden || $("page-head").shutting) foldOpen($("page-head"));
  });
}

// The console output fills what is left of the window under it (at least 200px), and follows window resizes and
//  the board card growing or shrinking above it (wizard steps, status line)
const CONSOLE_MIN = 200;
function sizeConsole() {
  if (consoleBox.hidden) return;
  // Measured from the top of the page (not the scrolled window), so scrolling never changes it
  const top = consoleOut.getBoundingClientRect().top + window.scrollY;
  // Everything under it down to the page's end (the card's padding and the page's bottom padding), so the page
  //  ends at the window's bottom and never scrolls (Version 30)
  const main = consoleOut.closest("main") || consoleBox;
  const below = main.getBoundingClientRect().bottom - consoleOut.getBoundingClientRect().bottom;
  consoleOut.style.height = Math.max(CONSOLE_MIN, Math.floor(window.innerHeight - top - below)) + "px";
  pinConsole();
}
// Version 75 (Gene): the console stays pinned to its newest line while it grows or shrinks (the button row folding
//  away at Install made it grow and left the erase line just out of view), unless the user scrolled up
function pinConsole() {
  if (followConsole && consoleOut.clientHeight) consoleOut.scrollTop = consoleOut.scrollHeight;
}
window.addEventListener("resize", sizeConsole);
if (window.ResizeObserver) new ResizeObserver(() => pinConsole()).observe(consoleOut);
// The board card above it grows and shrinks too (status line, folds): the console follows so the page never scrolls
if (window.ResizeObserver) {
  const watch = new ResizeObserver(() => sizeConsole());
  watch.observe(consoleCard);
  watch.observe($("console"));
}

function guard(fn) {
  return () => fn().catch((err) => appendConsole("\n[" + (err && err.message ? err.message : "Something went wrong") + "]\n"));
}

async function copyLog() {
  const text = consoleOut.textContent;
  const button = $("copy-log");
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  button.textContent = "Copied";
  setTimeout(() => { button.textContent = "Copy Log"; }, 1500);
}

// Events
// Version 37: the greyed Open GSP32 Web UI button (waiting for Wi-Fi) does nothing when clicked
$("console-webui").addEventListener("click", (event) => {
  if (event.currentTarget.classList.contains("waiting")) event.preventDefault();
});
$("install-btn").addEventListener("click", () => {
  if (busy) return;
  eraseOk.checked = false;
  syncStart();
  showStep("prep");
});
eraseOk.addEventListener("change", syncStart);
startInstall.addEventListener("click", () => install());
$("copy-log").addEventListener("click", copyLog);
$("error-retry").addEventListener("click", () => {
  if (retryStep === "wifi") startWifi(false);
  else showStep(retryStep);
});
wifiList.addEventListener("change", () => {
  syncWifiConnect();
});
wifiRescan.addEventListener("click", () => {
  if (wifiRescan.textContent === "Try Again") startWifi(false);
  else scanForWifi();
});
wifiConnect.addEventListener("click", () => openWifiModal());
$("wifi-modal-form").addEventListener("submit", (event) => {
  event.preventDefault();
  connectWifi();
});
wifiModalCancel.addEventListener("click", () => wifiModal.close());
wifiModal.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
for (const button of wizard.querySelectorAll("[data-action]")) {
  button.addEventListener("click", () => {
    if (button.id === "wifi-cancel" && busy) return;
    closeWizard();
  });
}

connectBtn.addEventListener("click", guard(async () => {
  // Version 75 (Gene): the version list is fetched again on every Get Started, so a page left open picks up a release
  loadVersions();
  try {
    await pickPort();
  } catch (err) {
    // Cancelled picker: probably no board in the list, so the checklist opens
    if (err.code === "cancel") {
      showBoardHelp(true);
      return;
    }
    throw err;
  }
  showBoardHelp(false);
  Object.assign(board, { installed: false, kind: "unknown", ip: "", name: "", chip: "", mac: "", version: "", readyAt: 0 });
  bootTimes = [];
  syncBoardUi();
  showConsole();
  // Version 42.1: an install that never finished (page refreshed mid-install) offers Recover GSP32 right away
  if (flashNoteGet()) setStatus("Incomplete Install Detected. Click Recover GSP32 to erase the board and install again.", "error");
}));
function showBoardHelp(open) {
  const help = $("board-help"), link = $("no-board");
  if (open === !help.hidden) return;
  link.setAttribute("aria-expanded", String(open));
  if (open) foldOpen(help);
  else foldShut(help);
}
$("no-board").addEventListener("click", () => showBoardHelp($("board-help").hidden));
disconnectBtn.addEventListener("click", guard(async () => {
  await closePort();
  hideConsole();
}));
resetBtn.addEventListener("click", guard(resetBoard));
ctrlCBtn.addEventListener("click", guard(() => writeBytes(new Uint8Array([0x03]))));
$("wifi-setup").addEventListener("click", () => {
  if (busy) return;
  startWifi(false);
});
$("console-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (consoleIn.disabled) return;
  const text = consoleIn.value;
  consoleIn.value = "";
  writeBytes(textEncoder.encode(text + "\r\n")).catch(() => appendConsole("\n[Could not send. Click Get Started and try again.]\n"));
});

if ("serial" in navigator) {
  navigator.serial.addEventListener("disconnect", (event) => {
    if (event.target === port) {
      reading = false;
      port = null;
      syncConsoleButtons();
      hideConsole();
    }
  });
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) requestWakeLock();
});
// Version 42.1 (Gene): leaving or refreshing the page while installing asks first ("Leave page?")
window.addEventListener("beforeunload", (event) => {
  if (!flashing) return;
  event.preventDefault();
  event.returnValue = "";
});
// Leaving the page: lines to run first, so closing the tab never holds the board in reset
window.addEventListener("pagehide", () => {
  if (port) port.setSignals({ dataTerminalReady: false, requestToSend: false }).catch(() => {});
});

loadVersions();
syncConsoleButtons();

// For the page tests (Playwright): the slide helper and the console writer
window.gsp32 = { setShown, appendConsole };
