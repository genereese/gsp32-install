// GSP32 web installer: Get Started opens one serial port and the board card (live console plus Install GSP32,
// Set Up Wi-Fi, Open GSP32 Web UI). The install and Wi-Fi steps run inline in that card, one step at a time, with
// their output in the same console. One serial port stays open from the port pick to the end, and every open and close leaves the
// board's reset lines in the run state (DTR and RTS both off), so the page never resets or holds the board in reset
// by itself; it resets the board only on purpose (after flashing, after Wi-Fi setup, Reset Board).
import { ESPLoader, Transport } from "./vendor/esptool-js-0.5.7.js";

const HEADER = [0x49, 0x4d, 0x50, 0x52, 0x4f, 0x56];
const MAX_LINES = 2000;
const FLASH_BAUD = 115200;
// Fix (verify): an install is reported only once the flash verifies; two mismatches end with this
const VERIFY_FAILED_TEXT = "The image on the device did not match what was sent (checked " + 3 + " times), so it is not installed. " +
  "This is usually the USB cable or port: try another data cable, plug the device straight into the computer (no hub), then click Try Again. " +
  "The flasher already writes at 115200, the slowest standard speed.";
// Fix (write retries): a write that breaks on line noise ("Invalid head of packet (0xff): Possible serial noise or
//  corruption", timeouts, a stopped transfer) or fails its MD5 check is written again from a fresh connect (reset
//  rotation, sync, stub), up to WRITE_ATTEMPTS writes in all. The raw esptool text stays in the console; the last
//  failure is said plainly
const WRITE_ATTEMPTS = 3;
const GARBLED_TEXT = "The connection to the device kept getting garbled. Try a different (short) USB cable, plugged straight into the computer.";
const NOISE_ERROR = /Invalid head of packet|serial noise|corruption|Timeout|timed out|took longer than|Packet content transfer stopped|Invalid response|invalid packet|Failed to (read|write)|Unexpected|checksum|SLIP/i;
function writeFailureText(err) {
  const raw = err && err.message ? err.message : String(err);
  if (/MD5 of file does not match/i.test(raw)) return VERIFY_FAILED_TEXT;
  if (NOISE_ERROR.test(raw)) return GARBLED_TEXT;
  return raw;
}
// MD5 of a binary string (one char per byte), as esptool-js's calculateMD5Hash wants: lowercase hex
function md5Binary(str) {
  const K = new Int32Array(64), S = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21];
  for (let i = 0; i < 64; i++) K[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 4294967296) | 0;
  const n = str.length, total = ((n + 8) >>> 6) + 1, words = new Int32Array(total * 16);
  for (let i = 0; i < n; i++) words[i >> 2] |= (str.charCodeAt(i) & 0xff) << ((i % 4) * 8);
  words[n >> 2] |= 0x80 << ((n % 4) * 8);
  words[total * 16 - 2] = (n * 8) | 0;
  words[total * 16 - 1] = Math.floor(n / 0x20000000) | 0;
  let a0 = 0x67452301, b0 = 0xefcdab89 | 0, c0 = 0x98badcfe | 0, d0 = 0x10325476;
  for (let off = 0; off < words.length; off += 16) {
    let a = a0, b = b0, c = c0, d = d0;
    for (let i = 0; i < 64; i++) {
      let f, g;
      if (i < 16) { f = (b & c) | (~b & d); g = i; }
      else if (i < 32) { f = (d & b) | (~d & c); g = (5 * i + 1) % 16; }
      else if (i < 48) { f = b ^ c ^ d; g = (3 * i + 5) % 16; }
      else { f = c ^ (b | ~d); g = (7 * i) % 16; }
      const s = S[(i >> 4) * 4 + (i % 4)];
      const x = (a + f + K[i] + words[off + g]) | 0;
      a = d; d = c; c = b;
      b = (b + ((x << s) | (x >>> (32 - s)))) | 0;
    }
    a0 = (a0 + a) | 0; b0 = (b0 + b) | 0; c0 = (c0 + c) | 0; d0 = (d0 + d) | 0;
  }
  let hex = "";
  for (const v of [a0, b0, c0, d0]) for (let i = 0; i < 4; i++) hex += ((v >>> (i * 8)) & 0xff).toString(16).padStart(2, "0");
  return hex;
}
const textEncoder = new TextEncoder();
const $ = (id) => document.getElementById(id);

const wizard = $("wizard");
const versionSelect = $("version");
const release_channel = $("release-channel");
// Version 85: the versions.json entries of each channel (an entry without "channel" is Stable)
let release_versions = { stable: null, beta: null, previous: null };
// GSP32-C Beta V118 (Gene): every GSP32-C Beta in versions.json is its own pick ("gspc-118", "gspc-117", newest first)
let gspc_channels = [];
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
// Version 82: Show Password toggles the field (each Wi-Fi window starts hidden)
const wifiShow = $("wifi-show");
function setShowPassword(on) {
  wifiShow.checked = on;
  wifiPassword.type = on ? "text" : "password";
}
wifiShow.addEventListener("change", () => {
  const at = wifiPassword.selectionStart;
  setShowPassword(wifiShow.checked);
  wifiPassword.focus();
  if (at !== null) wifiPassword.setSelectionRange(at, at);
});
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
let probing = false; // the connect probe (Reading board info) is running
// Flasher Version 115.10 (Gene's ESP32): a classic port (USB-UART bridge) is opened without touching DTR and RTS (see
//  pickPort and setRunState), and the board it was opened on was left running (no probe, so no restart)
let plainOpen = false;
// Fix (S3 native USB): the guide while shown, { kind: "boot" or "repick", resume: "probe", "install", "installed" or
//  "wifi" }; a restart expected to move a native USB board to a new port, { resume, until }
let usbGuide = null;
let usbExpect = null;
let usbAttaching = false;
let installConnecting = false;
// Fix (S3 web flash, Flasher Version 105): the end of an install (after the write) runs; the watchdog reset can take
//  the port away before it is done, and a port picked again waits for it (else its "unknown" board state came after)
let installEnding = false;
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

// A boot banner (the board restarted, e.g. Windows resets it when the port opens): "Device Booting Up..." until GSP32
//  says it is ready (or 20 s pass: other firmware). Not while esptool works
//  Version 42.1 (Gene): the button row stays put while booting, so a board stuck restarting can always be reinstalled
let bootingNote = null;
function startBooting() {
  if (busy || flashing) return;
  // Version 43.2 (Gene): the status is kept as nodes, not text, so "Wi-Fi Connected!" comes back with its second line
  //  and its link (as text both were lost: "Connected!Your device..." with a plain address)
  if (bootingNote === null) {
    bootingNote = boardStatus.hidden ? "" : {
      nodes: Array.from(boardStatus.childNodes, (node) => node.cloneNode(true)),
      kind: boardStatus.className.replace(/\b(board-status|waiting|filling|erasing)\b/g, "").trim(),
    };
  }
  setStatus("Device Booting Up...");
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
// Flasher Version 110: after a native-USB install, how long "Checking for GSP32" may run before Tap RST / pick port
let nativeHandoffTimer = null;
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
  // Flasher Version 110: Cancel only on native USB (the classic countdown is unchanged)
  const cancel = $("check-wait-cancel");
  if (cancel) cancel.hidden = !nativeUsb(port);
  setFolded(box, true);
  statusWait("check", true);
}
function stopCheckWait() {
  clearInterval(checkWaitTimer);
  checkWaitTimer = null;
  const cancel = $("check-wait-cancel");
  if (cancel) cancel.hidden = true;
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
  setStatus(INCOMPLETE_TEXT, "error");
  syncBoardUi();
}

// Version 42.1: a note of the install under way, kept until it finishes, so a page refreshed mid-install offers
//  Recover/Install GSP32 next time (and for the same board, by its MAC)
// Fix (recover flow): the note is saved only once erasing and writing start (after a good connect), with the MAC
//  esptool read and writing: true. An install whose connect failed wrote nothing and leaves no note. Older notes
//  (saved at "Installing", before any connect) are stale: dropped on load
const FLASH_NOTE_KEY = "gsp32.flash";
const INCOMPLETE_TEXT = "Incomplete Install Detected. Click Recover/Install GSP32 to erase the device and install again.";
const RECOVER_LABEL = "Recover/Install GSP32";
function flashNoteGet() {
  try {
    const note = JSON.parse(localStorage.getItem(FLASH_NOTE_KEY) || "null");
    if (note && (!note.writing || !note.mac)) {
      localStorage.removeItem(FLASH_NOTE_KEY);
      return null;
    }
    return note;
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
// Only for a connected board whose MAC (read by the connect probe) is the one the note was written for, and not once
//  it shows other firmware running (an Arduino sketch, say: plain Install GSP32)
function flashNoteMatches() {
  if (!portOpen() || !board.mac || board.kind === "other" || gspFound()) return false;
  const note = flashNoteGet();
  return !!note && note.mac === board.mac;
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

// Flasher Version 115.9 (GSP32-C Beta V125): GSP32-C from Beta V121 takes Improv Wi-Fi packets at any time (its console
//  keeps them away from Python, even at the >>> prompt), so Set Up Wi-Fi works for it too. V117-V120 had no Improv
function gspcImprov() {
  return board.kind === "gspc" && Number(board.gspcVersion) >= 121;
}

// Asks the board for its Improv device info (version, chip): once per boot, only while it listens, no retries
function askVersion() {
  if (board.version || board.asked > board.bootAt || !board.listening || !portOpen() || flashing) return;
  board.asked = Date.now();
  writeImprov(buildRpc(3, new Uint8Array(0))).catch(() => {});
}

// The Incomplete Install text goes from the status line and from the status kept behind the boot banner
function dropIncomplete() {
  const stale = /^Incomplete Install/;
  if (bootingNote && stale.test(bootingNote.nodes.map((node) => node.textContent).join(""))) bootingNote = "";
  if (stale.test(boardStatus.textContent)) {
    if (bootingNote === null) setStatus("");
    else bootingNote = "";
  }
}
function trackBoard(line) {
  // Flasher Version 114.2: a prompt at the start of a line is the REPL too (it may come in one piece with the next text)
  if (/^>>> /.test(line)) board.repl = true;
  if (/soft reboot/.test(line)) board.repl = false;
  // GSP32-C Beta V117 (Gene): GSP32-C prints "GSP32-C Beta V117 on <chip> ..." at start-up. V117-V120 have no Improv,
  //  so Wi-Fi is set at their prompt (the note says how). Flasher Version 115.9: V121 and newer listen for Improv from
  //  this line on, so Set Up Wi-Fi is offered (and the Next step after an install)
  // Flasher 115.25 (GSP32-C V131, Gene): a Stable build prints "GSP32-C V131 on ...", a Beta "GSP32-C Beta V131 on ..."
  const gspc = line.match(/GSP32-C (Beta )?V(\d+(?:\.\d+)?) on /);
  if (gspc) {
    board.kind = "gspc";
    board.gspcVersion = gspc[2];
    board.gspcBeta = !!gspc[1];
    board.listening = gspcImprov();
    board.readyAt = Date.now();
    bootTimes = [];
    if (flashNoteGet() && !busy && !flashing) {
      flashNoteSet(null);
      dropIncomplete();
    }
    clearTimeout(otherTimer);
    clearNativeHandoff();
    endBooting();
    if (nativeUsb(port) && usbGuide && usbGuide.resume === "installed") hideUsbGuide();
    if (gspcImprov() && nextStepPending) showNextStep();
    nextStepPending = false;
    syncBoardUi();
  }
  if (/GSP32 Improv Ready|Server listening on port|Web UI starts without Wi-Fi|Web UI running/.test(line)) {
    board.kind = "gsp32";
    bootTimes = [];
    // A board running GSP32 finished its install: the note of an unfinished one no longer applies
    if (flashNoteGet() && !busy && !flashing) {
      flashNoteSet(null);
      // Version 61: the boot banner keeps the status shown before it and puts it back afterwards, so a stale
      //  "Incomplete Install Detected. Click Recover GSP32..." came back beside a Reinstall GSP32 button. Drop it
      //  from both places: the board runs GSP32, there is nothing to recover
      dropIncomplete();
    }
    board.readyAt = Date.now();
    clearTimeout(otherTimer);
    clearNativeHandoff();
    endBooting();
    if (nativeUsb(port) && usbGuide && usbGuide.resume === "installed") hideUsbGuide();
    if (nextStepPending) showNextStep();
  }
  // Version 43.1: only these lines open the door for Improv; the version is asked then, once
  // Flasher Version 114.2 (Gene's C3, 114.1 in safe mode): once the REPL has the port, a later "Listening" from the
  //  web UI is not true (the REPL eats the packets): Set Up Wi-Fi restarts the board first
  if (/GSP32 Improv (Ready|Listening)/.test(line) && !board.repl) {
    board.kind = "gsp32";
    board.listening = true;
    board.readyAt = Date.now();
    askVersion();
    // Flasher Version 110: on native USB a listening line ends Checking even when the Ready line was missed
    //  (that used to leave the countdown up, because the 20 s timer then saw the board as already ready)
    if (nativeUsb(port)) {
      clearTimeout(otherTimer);
      clearNativeHandoff();
      if (bootingNote !== null || checkWaitTimer) endBooting();
      if (usbGuide && usbGuide.resume === "installed") hideUsbGuide();
    }
    if (nextStepPending && bootingNote === null) showNextStep();
  }
  if (/GSP32 Improv Off|No answer: starting without Wi-Fi|^Traceback|KeyboardInterrupt|^MicroPython v/.test(line) && !gspcImprov()) board.listening = false;
  // Fix (verify): a corrupted app ("E (31) esp_image: invalid segment length 0x...", "Factory app partition is not
  //  bootable", "No bootable app partitions") is a broken install too
  if (/invalid header|ota data partition invalid|checksum (error|failure)|image checksum|flash read err|E \(\d+\) esp_image|invalid segment length|partition is not bootable|No bootable app partitions/i.test(line)) {
    // Only these say there is no bootable firmware (the console's restart line names it then)
    if (/invalid header|E \(\d+\) esp_image|invalid segment length|not bootable|No bootable app/i.test(line)) board.noBootable = true;
    markBroken();
    return;
  }
  if (board.kind === "broken" && /^rst:0x|^ets [A-Z][a-z]{2} /.test(line)) return;
  if (/^rst:0x/.test(line) && noteBoot()) {
    markBroken();
    return;
  }
  if (/^rst:0x|^ets [A-Z][a-z]{2} /.test(line)) {
    board.leftRunning = false;
    board.bootAt = Date.now();
    board.repl = false;
    board.listening = false;
    board.wifiWait = false;
    board.wifiFailed = false;
    clearTimeout(wifiTimer);
    clearTimeout(otherTimer);
    // Flasher Version 110: the post-install guide is already the way on; a later ROM line must not bring Checking back
    const handoff = nativeInstallHandoff();
    const guideUp = handoff && usbGuide && usbGuide.resume === "installed";
    if (!guideUp) startBooting();
    // No GSP32 line within 20 s of a boot: some other firmware.
    //  Flasher Version 110: after a native-USB install that window is the handoff (Tap RST / pick the new port), not
    //  "No GSP32 Found", and it is short so Checking cannot sit there
    if (handoff) {
      if (!guideUp) armNativeHandoff();
    } else {
      otherTimer = setTimeout(() => {
        if (board.readyAt < board.bootAt) {
          board.kind = "other";
          // Other firmware runs (an erased or half-written board would not boot it): no install to recover
          if (flashNoteGet() && !busy && !flashing) flashNoteSet(null);
          dropIncomplete();
          endBooting();
          syncBoardUi();
        }
      }, 20000);
    }
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
  // Flasher Version 115.9: GSP32-C from V121 sets up Wi-Fi here too (Improv), and gets the web UI button
  const wifiCapable = gsp32 || gspcImprov();
  // Flasher Version 115.10 (Gene's ESP32): a classic board connected without a restart says nothing yet: Set Up Wi-Fi
  //  is offered beside Install (it restarts the board, so GSP32 or GSP32-C shows itself, see startWifi)
  const quiet = board.leftRunning && board.kind === "unknown";
  // Version 42.1: a half-finished install (boot loop, or the saved note of an install that never ended) offers Recover
  const broken = board.kind === "broken" || (!gsp32 && flashNoteMatches());
  // Version 92: a C3 with Stable picked can still open the install step, to choose Beta there
  install.disabled = !on || busy || !!(board.compatIssue && !board.compatIssue.betaOnly);
  install.textContent = broken ? RECOVER_LABEL : gsp32 ? "Reinstall GSP32" : "Install GSP32";
  // While installing, Wi-Fi and the web UI button are gone (not greyed); they come back after
  setShown(setup, (wifiCapable || quiet) && !flashing);
  setup.disabled = !on || busy;
  const address = wifiCapable && board.ip ? "http://" + board.ip + "/" : "";
  web.href = address || "#";
  // Waiting for Wi-Fi (or it never came): shown greyed, not clickable; it fades to blue once the address is known
  const waiting = wifiCapable && !address && (board.wifiWait || board.wifiFailed);
  setShown(web, !!((address || waiting) && on && !flashing));
  web.classList.toggle("waiting", waiting);
  if (waiting) {
    web.setAttribute("aria-disabled", "true");
    web.tabIndex = -1;
  } else {
    web.removeAttribute("aria-disabled");
    web.removeAttribute("tabindex");
  }
  // Version 101 (Gene): Disconnect at the right of the row while the port is open; gone (slid away) while installing,
  //  greyed while the flasher is busy
  const leave = $("board-disconnect");
  setShown(leave, on && !flashing);
  leave.disabled = !on || busy;
  // The next step is the solid blue button, the others light blue: Install on a board without GSP32, Set Up Wi-Fi
  //  once GSP32 runs, Open GSP32 Web UI once it is on Wi-Fi
  const next = !wifiCapable ? install : address ? web : setup;
  for (const button of [install, setup, web]) {
    button.classList.toggle("primary", button === next);
    button.classList.toggle("secondary", button !== next);
  }
  web.title = waiting ? (board.wifiFailed ? "Wi-Fi Didn't Connect" : "Waiting for Wi-Fi...") : address ? "Open " + address + (board.name ? " (also http://" + board.name + "/)" : "") : "";
  $("board-chip").textContent = (board.chip || "ESP32 Device").replace(/\s*\(revision[^)]*\)/i, "");
  const mac = $("board-mac");
  mac.textContent = board.mac ? "MAC " + board.mac.toUpperCase() : "";
  setShown(mac, !!board.mac);
  const details = $("board-details");
  if (details) {
    const line = formatBoardDetails();
    details.textContent = line;
    setShown(details, !!line);
  }
  setup.textContent = address || waiting ? "Change Wi-Fi" : "Set Up Wi-Fi";
  const state = $("board-state");
  state.textContent = !on ? "Not Connected"
    : board.note ? board.note
    : broken ? "Incomplete Install Detected"
    : gsp32 ? (board.version ? "GSP32 Version " + board.version + " Found" : "GSP32 Found")
    : gspcImprov() ? gspcFoundName() + " Found"
    : board.kind === "gspc" ? gspcFoundName() + " Found (set Wi-Fi at its prompt: gsp.wifi('name', 'password'))"
    : board.installed ? "Installed, Restarting..."
    : board.kind === "other" ? "No GSP32 Found"
    : quiet ? "Device Connected (Left Running)" : "Checking the Device...";
  if (on && (gsp32 || gspcImprov()) && address && !board.note) {
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
  // Fix (recover flow): a main button shown greyed always says why, or what to do
  const note = $("actions-note");
  if (note) {
    let why = "";
    if (!on && usbGuide) why = "Not connected. Pick the port again (see the note below).";
    else if (!on) why = "Not connected. Click Get Started above to connect the device.";
    else if (install.disabled && board.compatIssue && !board.compatIssue.betaOnly) why = "Install is off: this device is not supported (see the note below).";
    else if (install.disabled && probing) why = "Reading the device first. This takes a few seconds.";
    // Other busy steps (installing, Wi-Fi setup, restarts) show their own progress below the buttons
    note.textContent = why;
    setShown(note, !!why && !flashing);
  }
  // Fix (S3 native USB): only setting up Wi-Fi needs GSP32 running, not download mode or the board's details: the
  //  guide offers it while the row's own Set Up Wi-Fi isn't there
  // Flasher Version 110: the post-install guide (Tap RST / pick the new port) offers it the same way
  const instead = $("usb-guide-wifi");
  if (instead) {
    const offer = !!(usbGuide && ((usbGuide.kind === "boot" && usbGuide.resume === "probe") || usbGuide.resume === "installed"));
    instead.hidden = !offer || (on && gsp32);
  }
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
    // Flasher 115.26 (GSP32-C V132 (a)): a header whose version byte isn't 1, or whose type isn't one Improv uses
    //  (1-4), is text (a REPL echoing "IMPROV" then backspaces): it is let go at once. 115.25 waited for "length"
    //  bytes first, and the echo's '[' (91) kept the board's real answers behind it until ~100 more bytes came
    if (found + 6 < bytes.length && bytes[found + 6] !== 1) {
      texts.push(bytes.subarray(found, found + 1));
      i = found + 1;
      continue;
    }
    if (found + 7 < bytes.length && (bytes[found + 7] < 1 || bytes[found + 7] > 4)) {
      texts.push(bytes.subarray(found, found + 1));
      i = found + 1;
      continue;
    }
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
  if (name === "prep") syncHoldBootTip();
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

// Flasher Version 115.10 (Gene's ESP32): a classic board whose auto-reset never reaches download mode (it keeps
//  starting its program through every reset style) installs with BOOT held: the note folds in under the error
// Flasher Version 115.10 (Gene's ESP32): the same note in the install step, at the moment the first connect failed
const BOOT_NOW_MS = 2500;
function showBootNow(on) {
  const note = $("boot-now");
  if (note) setFolded(note, on);
}
function showBootHint(on) {
  const hint = $("boot-hint");
  if (!hint) return;
  if (!on) {
    hint.hidden = true;
    return;
  }
  setFolded(hint, true);
}
// Flasher Version 115.17 (Gene's ESP32): a classic device that needed BOOT held is remembered in this browser, so the
//  next Install shows the hold-BOOT tip before it starts (the flasher still tries the automatic reset first). Web
//  Serial gives no USB serial number, so the key is the USB bridge (VID:PID) plus the MACs read from it once an
//  install got through; a device whose MAC is known and not on the list does not get the tip. "Forget" clears it
const HOLD_BOOT_KEY = "gsp32HoldBoot";
function holdBootAll() {
  try {
    const all = JSON.parse(localStorage.getItem(HOLD_BOOT_KEY) || "{}");
    return all && typeof all === "object" ? all : {};
  } catch (err) {
    return {};
  }
}
function holdBootSave(all) {
  try {
    if (Object.keys(all).length) localStorage.setItem(HOLD_BOOT_KEY, JSON.stringify(all));
    else localStorage.removeItem(HOLD_BOOT_KEY);
  } catch (err) {
    // No storage: the tip is just not remembered
  }
}
function holdBootEntry(onPort, mac) {
  if (!onPort || nativeUsb(onPort)) return null;
  const entry = holdBootAll()[resetBridgeKey(onPort)];
  if (!entry) return null;
  const macs = Array.isArray(entry.macs) ? entry.macs : [];
  if (mac && macs.length && !macs.includes(String(mac).toLowerCase())) return null;
  return entry;
}
function rememberHoldBoot(onPort, mac, quiet) {
  if (!onPort || nativeUsb(onPort)) return;
  const all = holdBootAll();
  const key = resetBridgeKey(onPort);
  const entry = all[key] && typeof all[key] === "object" ? all[key] : {};
  const macs = Array.isArray(entry.macs) ? entry.macs : [];
  if (mac && !macs.includes(String(mac).toLowerCase())) macs.push(String(mac).toLowerCase());
  all[key] = { macs, at: Date.now() };
  holdBootSave(all);
  if (!quiet) appendConsole("[This device needed BOOT held: the flasher will remind you next time]\n");
}
function forgetHoldBoot(onPort, mac) {
  const all = holdBootAll();
  const key = resetBridgeKey(onPort);
  const entry = all[key];
  if (!entry) return;
  const macs = Array.isArray(entry.macs) ? entry.macs : [];
  const one = mac && String(mac).toLowerCase();
  if (one && macs.length > 1 && macs.includes(one)) all[key] = { macs: macs.filter((m) => m !== one), at: entry.at };
  else delete all[key];
  holdBootSave(all);
}
// The tip in the Install step: shown at once (no fold) when the step opens for a remembered device
function syncHoldBootTip() {
  const tip = $("boot-remembered");
  if (!tip) return;
  const on = !!(portOpen() && holdBootEntry(port, board.mac));
  tip.hidden = !on;
  if (on) {
    const which = $("boot-remembered-which");
    if (which) which.textContent = board.mac ? " (MAC " + board.mac.toUpperCase() + ")" : "";
  }
}
function showError(message, retry) {
  showBootHint(false);
  const now = $("boot-now");
  if (now) now.hidden = true;
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
// Fix (console flood): a boot-looping board (a restart every 250 ms) froze and crashed Chromium: every line repainted
//  the whole console. Now at most one paint per frame (or 100 ms when the tab is hidden), only the last DOM_LINES
//  lines in the page (Copy Log has all MAX_LINES), and a board in a boot loop has its restart output held back
//  behind one line that counts it
const DOM_LINES = 500;
let paintQueued = false;
let mutedLines = 0;
function paintConsole() {
  if (paintQueued) return;
  paintQueued = true;
  const run = () => {
    if (!paintQueued) return;
    paintQueued = false;
    paintConsoleNow();
  };
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
  setTimeout(run, 100);
}
// Flasher Version 115.10 (Gene): the password in an echoed gsp.wifi('name', 'password') (or wifi(...)) line is shown as
//  dots, in the console and in Copy Log ('password' itself, the board's own hint, stays)
function maskWifi(text) {
  return text.replace(/(\bwifi\(\s*(['"])[^'"\n]*\2\s*,\s*)(['"])([^'"\n]*)/g,
    (all, head, q1, q2, secret) => (secret === "password" || !secret ? all : head + q2 + "\u2022\u2022\u2022\u2022\u2022\u2022"));
}
function consoleText(all) {
  const shown = all ? lines : lines.slice(-DOM_LINES);
  let text = maskWifi(shown.join("\n") + (partial ? (shown.length ? "\n" : "") + partial : ""));
  if (gate.hidden) text += (text ? "\n" : "") + "[Device output isn't readable at 115200 (other firmware?): " + gate.bytes + " bytes hidden]";
  if (mutedLines) text += (text ? "\n" : "") + "[The device keeps restarting" + (board.noBootable ? " (no bootable firmware)" : "") + ": " + mutedLines + " lines of its restart output hidden. Click " + RECOVER_LABEL + ".]";
  return text;
}
function paintConsoleNow() {
  consoleOut.textContent = consoleText(false);
  if (followConsole) consoleOut.scrollTop = consoleOut.scrollHeight;
}
// Fix (unreadable output): a board whose firmware talks at another speed (a factory sketch at 9600, 57600, 921600)
//  reads as a stream of 0xF0/0xFC/"p"/"|" at 115200. Once a quarter of the recent characters are unreadable
//  (replacement characters, control codes), its output is held back behind one updating line; it shows again once a
//  clean run with a line break comes (the ROM banner of a restart, GSP32 after an install). This is only display: it
//  never marks the board broken; such a board is "other firmware" (Install GSP32)
const UNREADABLE_SHARE = 0.25;
const UNREADABLE_MIN = 64;
const CLEAN_RUN = 64;
let gate = { good: 0, bad: 0, hidden: false, bytes: 0, cleanRun: 0, cleanBreak: false };
function readableGateReset() {
  if (gate.hidden && gate.bytes) lines.push("[" + gate.bytes + " bytes of unreadable output were hidden]");
  gate = { good: 0, bad: 0, hidden: false, bytes: 0, cleanRun: 0, cleanBreak: false };
}
function unreadableChar(code) {
  return code === 0xfffd || (code < 0x20 && code !== 9 && code !== 10 && code !== 13) || (code >= 0x7f && code < 0xa0);
}
function readableGate(text, byteCount) {
  if (!gate.hidden) {
    let bad = 0;
    for (let i = 0; i < text.length; i++) if (unreadableChar(text.charCodeAt(i))) bad++;
    gate.bad += bad;
    gate.good += text.length - bad;
    if (gate.good + gate.bad > 512) { gate.good /= 2; gate.bad /= 2; }
    const total = gate.good + gate.bad;
    if (total < UNREADABLE_MIN || gate.bad / total < UNREADABLE_SHARE) return text;
    // Hidden from here: the unfinished garbled line goes too
    gate.hidden = true;
    gate.bytes = byteCount + partial.length;
    partial = "";
    gate.cleanRun = 0;
    gate.cleanBreak = false;
    paintConsole();
    return "";
  }
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (unreadableChar(code)) {
      gate.cleanRun = 0;
      gate.cleanBreak = false;
      continue;
    }
    gate.cleanRun++;
    if (code === 10) gate.cleanBreak = true;
    if (gate.cleanRun >= CLEAN_RUN && gate.cleanBreak) {
      // Readable again: from the start of the clean run
      const start = i + 1 - gate.cleanRun;
      gate.bytes += Math.max(0, start);
      readableGateReset();
      return text.slice(Math.max(0, start));
    }
  }
  gate.bytes += byteCount;
  paintConsole();
  return "";
}

// What a restarting board prints (ROM banner, bootloader lines, the reason it can't boot)
const BOOT_NOISE = /^(rst:0x|ets [A-Z][a-z]{2} |configsip|clk_drv|mode:|load:0x|entry 0x|ho \d|[EIW] \(\d+\) |invalid header|Factory app|No bootable|abort\(\)|Rebooting|Backtrace|ELF file SHA|\s*$)/;
// Fix (fold during install): the fold stays while the install gets ready (busy), and ends when esptool takes the port
function endConsoleFolds() {
  if (mutedLines) {
    lines.push("[" + mutedLines + " lines of restart output were hidden]");
    mutedLines = 0;
  }
  readableGateReset();
  paintConsole();
}
function muteBootLoop(line) {
  if (board.kind !== "broken") {
    if (mutedLines) {
      lines.push("[" + mutedLines + " lines of restart output were hidden]");
      mutedLines = 0;
    }
    return false;
  }
  if (!BOOT_NOISE.test(line)) return false;
  mutedLines++;
  return true;
}

function appendConsole(text) {
  if (!text) return;
  partial += text;
  const pieces = partial.split("\n");
  partial = pieces.pop();
  if (/>>> ?$/.test(partial)) {
    board.repl = true;
    if (!gspcImprov()) board.listening = false;
  }
  if (partial.length > 2000) {
    pieces.push(partial);
    partial = "";
  }
  for (const line of pieces) {
    const muted = muteBootLoop(line.replace(/\r$/, ""));
    if (!muted) lines.push(line);
    trackBoard(line);
    for (const watch of lineWatchers.slice()) watch(line);
  }
  if (lines.length > MAX_LINES) lines = lines.slice(lines.length - MAX_LINES);
  paintConsole();
}

function consumeSerial(chunk) {
  const taken = takeSerialBytes(concatBytes(pending, chunk));
  pending = taken.rest;
  if (taken.text.length) {
    const shown = readableGate(textDecoder.decode(taken.text, { stream: true }), taken.text.length);
    if (shown) appendConsole(shown);
  }
  for (const packet of taken.packets) {
    // Any answer is GSP32 (or GSP32-C, which stays GSP32-C); a provisioned state's result carries the board's address
    if (board.kind !== "gspc") board.kind = "gsp32";
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
        // Flasher Version 115.9: GSP32-C answers "GSP32-C", "Beta V125". Flasher 115.25: a Stable build "V131"
        const c = parsed.strings[0] === "GSP32-C" && v.match(/^(Beta )?V(\d+(?:\.\d+)?)$/);
        if (c) {
          board.kind = "gspc";
          board.gspcVersion = c[2];
          board.gspcBeta = !!c[1];
        }
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
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's portOpen; on any other port Flasher 104's, unchanged
function portOpen() {
  return nativeUsb(port) ? portOpenNative() : portOpenClassic();
}
function portOpenNative() {
  return !!(readableOf(port) && writableOf(port));
}
function portOpenClassic() {
  return !!(port && port.readable && port.writable);
}

// Fix (S3 web flash, Flasher Version 105): Chromium's close() cancels the readable first and then throws when the
//  writable is still locked (a write that never ends: a USB device that stopped taking data, like GSP32's TinyUSB port
//  once its input buffer is full). The port then stays open without a readable while Chromium's device side still holds
//  the old read pipe, and the next port.readable asks for a new one: Chromium kills the tab (RESULT_CODE_KILLED_BAD_
//  MESSAGE, "Data pipe producer still open"). So every write has a time limit and aborts its writer when it runs out,
//  every reader and writer the page takes is known so a close can release them first, a port closes only with both
//  streams unlocked, and while it closes (or after a close that failed: a stuck port) readable and writable are never
//  touched again; the page asks for an unplug instead
const STUCK_TEXT = "\n[The USB connection got stuck. Unplug and replug the device, then click Get Started.]\n";
const STUCK_STATUS = "Unplug and Replug the Device";
const WRITE_MS = 4000;  // plus 1 ms per 5 bytes (115200 baud moves about 11)
function portUsable(onPort) {
  return !!onPort && !onPort.__gsp32Closing && !onPort.__gsp32Stuck;
}
function readableOf(onPort) {
  try {
    return portUsable(onPort) ? onPort.readable : null;
  } catch (err) {
    return null;
  }
}
function writableOf(onPort) {
  try {
    return portUsable(onPort) ? onPort.writable : null;
  } catch (err) {
    return null;
  }
}
function stuckError() {
  const err = new Error("The USB connection got stuck. Unplug and replug the device, then click Get Started.");
  err.code = "stuck";
  err.plain = true;
  return err;
}
// A reader the page takes (ours, esptool-js's, the SYNC check): known, so a close can let go of it first
function takeReader(onPort) {
  const stream = readableOf(onPort);
  if (!stream) throw new Error("The port closed");
  const taken = stream.getReader();
  (onPort.__gsp32Readers || (onPort.__gsp32Readers = new Set())).add(taken);
  return taken;
}
function dropReader(onPort, taken) {
  if (!taken) return;
  try {
    taken.releaseLock();
  } catch (err) {
    // Released already, or a read still pending (cancel first)
  }
  if (onPort && onPort.__gsp32Readers) onPort.__gsp32Readers.delete(taken);
}
// One bounded write: a write that does not finish in time is aborted (Chromium stops it on its side too), so the
//  writable is never left locked
async function writeTo(onPort, bytes) {
  const stream = writableOf(onPort);
  if (!stream) throw new Error("not connected");
  const writer = stream.getWriter();
  const writers = onPort.__gsp32Writers || (onPort.__gsp32Writers = new Set());
  writers.add(writer);
  try {
    await withTimeout(writer.write(bytes), WRITE_MS + Math.ceil(bytes.length / 5), "Writing to the device");
  } catch (err) {
    await withTimeout(writer.abort(err).catch(() => {}), 2000, "Stopping the write").catch(() => {});
    throw err;
  } finally {
    writers.delete(writer);
    try {
      writer.releaseLock();
    } catch (err) {
      // Released already
    }
  }
}
// The port can't be used again on this page: say so once (unplug and replug), forget it, Get Started comes back
function markStuck(stuck, quiet) {
  if (!stuck || stuck.__gsp32Stuck) return;
  stuck.__gsp32Stuck = true;
  stuck.__gsp32Closing = false;
  if (port === stuck) port = null;
  reading = false;
  board.listening = false;
  if (!quiet) {
    appendConsole(STUCK_TEXT);
    hideUsbGuide();
    setStatus(STUCK_STATUS, "error");
  }
  syncConsoleButtons();
  showStartAgain();
}
// Close only with nothing locked: the page's readers cancelled and released, its writers aborted; a close that fails or
//  hangs leaves the port stuck (never touched again). Resolves false then
async function safeClose(onPort, quiet) {
  if (!onPort) return true;
  if (onPort.__gsp32Stuck) return false;
  for (const taken of Array.from(onPort.__gsp32Readers || [])) {
    await withTimeout(taken.cancel().catch(() => {}), 1000, "Releasing the port").catch(() => {});
    dropReader(onPort, taken);
  }
  for (const writer of Array.from(onPort.__gsp32Writers || [])) {
    await withTimeout(writer.abort().catch(() => {}), 1000, "Stopping the write").catch(() => {});
    try {
      writer.releaseLock();
    } catch (err) {
      // Released already
    }
    onPort.__gsp32Writers.delete(writer);
  }
  let locked = false, open = false;
  try {
    const readable = onPort.readable, writable = onPort.writable;
    open = !!(readable || writable);
    locked = !!((readable && readable.locked) || (writable && writable.locked));
  } catch (err) {
    open = true;
  }
  if (!open) {
    // No streams (the device is gone): close() can't leave anything half-open, and Chromium lets go of the port
    if (onPort.__gsp32Opened) await withTimeout(Promise.resolve().then(() => onPort.close()), 1000, "Closing the port").catch(() => {});
    onPort.__gsp32Opened = false;
    return true;
  }
  if (locked) {
    markStuck(onPort, quiet);
    return false;
  }
  onPort.__gsp32Closing = true;
  try {
    await withTimeout(Promise.resolve().then(() => onPort.close()), 3000, "Closing the port");
  } catch (err) {
    markStuck(onPort, quiet);
    return false;
  }
  onPort.__gsp32Closing = false;
  onPort.__gsp32Opened = false;
  return true;
}

function flasherWorking() {
  const step = (wizard.hidden || wizard.shutting) ? "" : (wizard.querySelector(".step:not([hidden])") || {}).dataset?.step || "";
  let waiting = statusWaits.size > 0;
  // Flasher Version 110: on native USB, Checking for GSP32 does not lock the console (wifi() works on the page).
  //  A classic port still locks it, as in Flasher 104
  if (waiting && nativeUsb(port) && statusWaits.size === 1 && statusWaits.has("check")) waiting = false;
  // Flasher Version 115.10 (Gene's ESP32): the Wi-Fi step no longer locks the console while it only waits for a pick
  //  (a list, "No networks found", an error with Try Again): only while it talks to the board (busy). It locked the
  //  console as long as the step was open, so after an empty scan gsp.wifi(...) could not be typed either
  return busy || waiting || step === "flash";
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
  // Flasher Version 115.10 (Gene's ESP32): not while a classic port is being opened (pickPort): a plain connect leaves
  //  DTR and RTS as the port came up. Chromium sets the two lines one after the other, DTR first, so from both on
  //  (Windows opens a port that way) this call passed through DTR off with RTS on: EN low, a restart on every connect
  if (plainOpen && port && !nativeUsb(port)) return;
  // The board's EN and GPIO 0 lines both high (running). Flasher Version 115.11 (Gene's ESP32 on COM4): one line at a
  //  time, RTS first (see idleLines); one setSignals with both lines off is applied DTR first (the Web Serial spec's
  //  order), and from both on that passes through DTR off with RTS on: EN low, a restart
  //  Each call is awaited, so the bridge has RTS off before DTR moves. No gap here (setRunState runs inside the
  //  install, whose timing stays Flasher 104's); idleLines, for Disconnect and leaving the page, adds one
  if (!port) return;
  const p = port;
  await p.setSignals({ requestToSend: false });
  await p.setSignals({ dataTerminalReady: false });
}

// Flasher Version 115.10 (Gene's ESP32: Disconnect dropped its Wi-Fi): the run state one line at a time, RTS first. RTS
//  off first never pulls EN low (DTR on alone only holds GPIO 0 low, which a running board ignores); DTR off first
//  from both on does (a restart). Flasher Version 115.11 (on the real board, COM4: DTR then RTS restarts it, RTS then
//  DTR does not): two separate awaited calls with a short gap, so the bridge has applied RTS before DTR moves
const LINE_GAP_MS = 30;
async function idleLines() {
  if (!port) return;
  const p = port;
  await p.setSignals({ requestToSend: false });
  await delay(LINE_GAP_MS);
  await p.setSignals({ dataTerminalReady: false });
}

async function resetBoard() {
  // RTS on alone pulls EN low (reset), then back to the run state
  await port.setSignals({ dataTerminalReady: false, requestToSend: true });
  await delay(120);
  await setRunState();
}

// Fix (false disconnect): Web Serial reports line noise (a reset, an Arduino sketch's output at another speed) as a
//  read error, after which port.readable is a fresh stream. Only a missing readable (or navigator.serial's disconnect
//  event) means the board is really gone
const RECOVERABLE_SERIAL = ["BreakError", "FramingError", "ParityError", "BufferOverrunError"];
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's serialRecoverable; on any other port Flasher 104's, unchanged
function serialRecoverable(err, onPort) {
  return nativeUsb(onPort) ? serialRecoverableNative(err, onPort) : serialRecoverableClassic(err, onPort);
}
function serialRecoverableNative(err, onPort) {
  if (!readableOf(onPort)) return false;
  return true;  // with readable still there the port lives on, whatever the error (RECOVERABLE_SERIAL or other)
}
function serialRecoverableClassic(err, onPort) {
  if (!onPort || !onPort.readable) return false;
  return true;  // with readable still there the port lives on, whatever the error (RECOVERABLE_SERIAL or other)
}
function serialErrorName(err) {
  return (err && (err.name || err.message)) || "error";
}
const DISCONNECT_TEXT = "\n[The device disconnected. Plug it in and click Get Started.]\n";
// A real loss: close the port (so Chromium lets go of it), say so once, and bring Get Started back
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's portLost; on any other port Flasher 104's, unchanged
async function portLost(lost, message) {
  return nativeUsb(lost) ? portLostNative(lost, message) : portLostClassic(lost, message);
}
async function portLostNative(lost, message) {
  if (!lost || lost.__gsp32Lost) return;
  lost.__gsp32Lost = true;
  if (port === lost) port = null;
  reading = false;
  board.listening = false;
  if (message) appendConsole(message);
  // Flasher Version 110: a port that left during Checking must not leave that countdown up
  clearTimeout(otherTimer);
  clearNativeHandoff();
  if (bootingNote !== null || checkWaitTimer) endBooting();
  await stopReading().catch(() => {});
  await safeClose(lost, true).catch(() => {});
  syncConsoleButtons();
  showStartAgain();
}
async function portLostClassic(lost, message) {
  if (!lost || lost.__gsp32Lost) return;
  lost.__gsp32Lost = true;
  if (port === lost) port = null;
  reading = false;
  board.listening = false;
  if (message) appendConsole(message);
  await stopReading().catch(() => {});
  await lost.close().catch(() => {});
  syncConsoleButtons();
  showStartAgain();
}
// Get Started (the start row) comes back above the console, which keeps its log
function showStartAgain() {
  if (installer.hidden || installer.shutting) foldOpen(installer);
  connectBtn.disabled = false;
  connectBtn.hidden = false;
}
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's startReading; on any other port Flasher 104's, unchanged
function startReading() {
  return nativeUsb(port) ? startReadingNative() : startReadingClassic();
}
function startReadingNative() {
  if (reading || !portOpen()) return;
  reading = true;
  const readPort = port;
  let lost = false;
  readDone = (async () => {
    let errors = 0, empties = 0;
    while (reading && port === readPort && readableOf(readPort)) {
      try {
        reader = takeReader(readPort);
      } catch (err) {
        break;
      }
      let got = false;
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          got = true;
          errors = 0;
          if (value) consumeSerial(value);
        }
      } catch (err) {
        if (reading && serialRecoverable(err, readPort)) {
          // Line noise only: a fresh reader on the new stream, a short pause if errors keep coming
          errors += 1;
          if (errors <= 3 || errors % 50 === 0) console.warn("Serial read error, reading on:", serialErrorName(err));
          if (errors > 5) await delay(Math.min(500, errors * 10));
          got = true;
        } else if (reading) {
          lost = true;
        }
      } finally {
        dropReader(readPort, reader);
        reader = null;
      }
      // A stream that ends at once again and again would spin here: give the port a moment, then stop. Fix (S3 web
      //  flash, Flasher Version 105): the pause grows (50 ms up to 1 s) while the stream keeps ending at once
      empties = got ? 0 : empties + 1;
      if (!got) await delay(Math.min(1000, 50 * 2 ** Math.min(5, empties - 1)));
      const still = readableOf(port);
      if (!got && reading && still && still.locked) break;
    }
    if (reading && !lost && portUsable(readPort) && !readableOf(readPort)) lost = true;
    reading = false;
    if (lost) {
      readDone = Promise.resolve();
      await portLost(readPort, DISCONNECT_TEXT);
      return;
    }
    syncConsoleButtons();
  })();
}
function startReadingClassic() {
  if (reading || !portOpen()) return;
  reading = true;
  const readPort = port;
  let lost = false;
  readDone = (async () => {
    let errors = 0;
    while (reading && port === readPort && readPort.readable) {
      try {
        reader = readPort.readable.getReader();
      } catch (err) {
        break;
      }
      let got = false;
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          got = true;
          errors = 0;
          if (value) consumeSerial(value);
        }
      } catch (err) {
        if (reading && serialRecoverable(err, readPort)) {
          // Line noise only: a fresh reader on the new stream, a short pause if errors keep coming
          errors += 1;
          if (errors <= 3 || errors % 50 === 0) console.warn("Serial read error, reading on:", serialErrorName(err));
          if (errors > 5) await delay(Math.min(500, errors * 10));
          got = true;
        } else if (reading) {
          lost = true;
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
    if (reading && !lost && !readPort.readable) lost = true;
    reading = false;
    if (lost) {
      readDone = Promise.resolve();
      await portLost(readPort, DISCONNECT_TEXT);
      return;
    }
    syncConsoleButtons();
  })();
}

// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's stopReading; on any other port Flasher 104's, unchanged
async function stopReading() {
  return nativeUsb(port) ? stopReadingNative() : stopReadingClassic();
}
async function stopReadingNative() {
  reading = false;
  // Bounded: on a stuck USB device Chromium's cancel can wait for a read that never ends
  if (reader) await withTimeout(reader.cancel().catch(() => {}), 1000, "Releasing the port").catch(() => {});
  await withTimeout(readDone, 1500, "Stopping the reader").catch(() => {});
}
async function stopReadingClassic() {
  reading = false;
  if (reader) await reader.cancel().catch(() => {});
  await readDone;
}

// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's openPort; on any other port Flasher 104's, unchanged
async function openPort(selected) {
  return nativeUsb(selected) ? openPortNative(selected) : openPortClassic(selected);
}
async function openPortNative(selected) {
  if (port === selected && portOpen()) return;
  if (selected.__gsp32Stuck) throw stuckError();
  if (port && port !== selected) await closePort();
  // Still open from before (a lost state): close it first, or open() fails with "already open"
  if (!(await safeClose(selected))) throw stuckError();
  selected.__gsp32Lost = false;
  await selected.open({ baudRate: FLASH_BAUD });
  selected.__gsp32Opened = true;
  portBaud = FLASH_BAUD;
  port = selected;
  board.info = Object.assign({}, board.info || {});
  const bridge = usbBridgeInfo();
  if (bridge) { board.info.usb = bridge.name; board.info.usbLabel = bridge.label; }
  syncBoardUi();
  await setRunState();
  pending = new Uint8Array(0);
  textDecoder = new TextDecoder("utf-8");
  readableGateReset();
  startReading();
  syncConsoleButtons();
}
async function openPortClassic(selected) {
  if (port === selected && portOpen()) return;
  if (port && port !== selected) await closePort();
  // Still open from before (a lost state): close it first, or open() fails with "already open"
  if (selected.readable || selected.writable) await selected.close().catch(() => {});
  selected.__gsp32Lost = false;
  await selected.open({ baudRate: FLASH_BAUD });
  portBaud = FLASH_BAUD;
  port = selected;
  board.info = Object.assign({}, board.info || {});
  const bridge = usbBridgeInfo();
  if (bridge) { board.info.usb = bridge.name; board.info.usbLabel = bridge.label; }
  syncBoardUi();
  await setRunState();
  pending = new Uint8Array(0);
  textDecoder = new TextDecoder("utf-8");
  readableGateReset();
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
  // Flasher Version 115.10 (Gene's ESP32): a plain connect leaves DTR and RTS alone on a classic port (see setRunState)
  plainOpen = true;
  try {
    await openPicked(selected);
  } finally {
    plainOpen = false;
  }
  return port;
}
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's openPicked; on any other port Flasher 104's, unchanged
async function openPicked(selected) {
  return nativeUsb(selected) ? openPickedNative(selected) : openPickedClassic(selected);
}
async function openPickedNative(selected) {
  try {
    await openPort(selected);
  } catch (err) {
    if (err && err.code === "stuck") throw err;
    // Fix (recover flow): a port Chromium still holds from before (a stale state) often opens after a close
    try {
      if (!(await safeClose(selected))) throw stuckError();
      await delay(300);
      await openPort(selected);
      return;
    } catch (again) {
      if (again && again.code === "stuck") throw again;
      // Fall through to the clear error
    }
    const fail = new Error("Could not open the port. Close other programs that use it (Arduino, Thonny, mpremote), unplug and replug the device, then click Get Started again.");
    fail.code = "open";
    throw fail;
  }
}
async function openPickedClassic(selected) {
  try {
    await openPort(selected);
  } catch (err) {
    // Fix (recover flow): a port Chromium still holds from before (a stale state) often opens after a close
    try {
      await selected.close().catch(() => {});
      await delay(300);
      await openPort(selected);
      return;
    } catch (again) {
      // Fall through to the clear error
    }
    const fail = new Error("Could not open the port. Close other programs that use it (Arduino, Thonny, mpremote), unplug and replug the device, then click Get Started again.");
    fail.code = "open";
    throw fail;
  }
}

// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's closePort; on any other port Flasher 104's, unchanged
async function closePort() {
  return nativeUsb(port) ? closePortNative() : closePortClassic();
}
async function closePortNative() {
  if (!port) return;
  const closing = port;
  await stopReading();
  try {
    await setRunState();
  } catch (err) {
    // The device may be gone already
  }
  await safeClose(closing).catch(() => {});
  if (port === closing) port = null;
  syncConsoleButtons();
}
async function closePortClassic() {
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

// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's writeBytes; on any other port Flasher 104's, unchanged
async function writeBytes(bytes) {
  return nativeUsb(port) ? writeBytesNative(bytes) : writeBytesClassic(bytes);
}
async function writeBytesNative(bytes) {
  if (!portOpen()) throw new Error("not connected");
  await writeTo(port, bytes);
}
async function writeBytesClassic(bytes) {
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
    // Only the latest build of each channel is offered (older images were removed from the repo; they stay in git
    //  history). Version 85 (Gene): Stable (the default) or Beta, picked in the Release dropdown
    release_versions = {
      stable: list.find((item) => (!item.prototype) && ((item.channel || "stable") === "stable")) || null,
      beta: list.find((item) => (!item.prototype) && (item.channel === "beta")) || null,
      // Version 99 (Gene): the previous Stable as a fallback pick (Version 99 since Version 103 became Stable)
      previous: list.find((item) => (!item.prototype) && (item.channel === "previous")) || null,
    };
    // GSP32-C Beta V117 (Gene): the separate GSP32-C line. V118 (Gene): each listed GSP32-C Beta is a separate pick,
    //  keyed by its number, in versions.json order (newest first)
    gspc_channels = [];
    for (const item of list) {
      if (item.prototype || item.channel !== "gspc-beta") continue;
      const number = String(item.label || "").match(/GSP32-C Beta V(\d+(?:\.\d+)?)/);
      const key = "gspc-" + (number ? number[1] : item.version);
      if (release_versions[key]) continue;
      release_versions[key] = item;
      gspc_channels.push(key);
    }
    stable = release_versions.stable;
    releaseChannelUpdate();
  } catch (err) {
    versionSelect.textContent = "Could Not Load the Version";
    versionsReady = false;
  }
  syncStart();
}

// Flasher 115.25 (Gene): the name the board gave ("GSP32-C Beta V131" or, from a Stable build, "GSP32-C V132")
function gspcFoundName() {
  return "GSP32-C " + (board.gspcBeta === false ? "" : "Beta ") + "V" + board.gspcVersion;
}
// GSP32-C Beta V117 (Gene): GSP32 or GSP32-C runs on the board (the install is done, no recovery, no handoff)
function gspFound() {
  return board.kind === "gsp32" || board.kind === "gspc";
}
// GSP32-C Beta V118 (Gene): a GSP32-C pick ("gspc-118")
function isGspc(channel) {
  return String(channel || "").startsWith("gspc-");
}
// Flasher 115.23 (Gene): GSP32-C V130 is the Stable pick (a versions.json entry with no channel and line "GSP32-C")
function gspcEntry(entry) {
  return !!entry && entry.line === "GSP32-C";
}
// GSP32-C Beta V117 (Gene): "GSP32-C Beta V117" from a label like "GSP32-C Beta V117 (08999a5)"
function gspcName(entry) {
  return String(entry.label || entry.version).replace(/\s*\([0-9a-f]{7,}\)\s*$/, "");
}
// The Beta option is disabled when there is no beta; the pick sets the version (and manifest) to install
function releaseChannelUpdate() {
  const beta_option = release_channel.querySelector('option[value="beta"]');
  beta_option.disabled = !release_versions.beta;
  // Version 106 (Gene): with no Beta listed the option isn't shown at all
  beta_option.hidden = !release_versions.beta;
  if ((release_channel.value === "beta") && !(release_versions.beta)) release_channel.value = "stable";
  const previous_option = release_channel.querySelector('option[value="previous"]');
  if (previous_option) {
    const old = release_versions.previous;
    const old_number = old ? String(old.label || old.version).match(/Version (\d+(?:\.\d+)?)/) : null;
    previous_option.hidden = previous_option.disabled = !old;
    // Flasher 115.27 (Gene): the previous Stable is GSP32-C V130: "Previous (GSP32-C V130)"
    previous_option.textContent = gspcEntry(old) ? "Previous (" + gspcName(old) + ")"
      : old_number ? "Previous (Version " + old_number[1] + ")" : "Previous";
    if ((release_channel.value === "previous") && !(old)) release_channel.value = "stable";
  }
  // Version 106 (Gene): Stable is the only version listed: one choice is no choice, so the Release dropdown is hidden
  //  (the "Installs Version N" line stays); a Beta or a Previous in versions.json brings it back
  // GSP32-C Beta V117 (Gene): its own group in the dropdown, named from versions.json ("GSP32-C Beta V117").
  //  V118 (Gene): one option per listed GSP32-C Beta, newest first, each installing its own manifest
  const gspc = gspc_channels.length > 0;
  const gspc_group = $("gspc-group");
  if (gspc_group) {
    const want = gspc_channels.join(",");
    if (gspc_group.dataset.keys !== want) {
      const keep = release_channel.value;
      gspc_group.textContent = "";
      for (const key of gspc_channels) {
        const option = document.createElement("option");
        option.value = key;
        option.textContent = gspcName(release_versions[key]);
        gspc_group.appendChild(option);
      }
      gspc_group.dataset.keys = want;
      if (gspc_channels.includes(keep)) release_channel.value = keep;
    }
    gspc_group.hidden = !gspc;
  }
  if (isGspc(release_channel.value) && !release_versions[release_channel.value]) release_channel.value = "stable";
  const release_field = release_channel.closest(".release-field");
  if (release_field) release_field.hidden = !(release_versions.beta || release_versions.previous || gspc);
  const channel = release_channel.value;
  const picked = release_versions[channel];
  if (picked !== latest) manifestCache = null;
  latest = picked;
  const number = latest ? String(latest.label || latest.version).match(/Version (\d+(?:\.\d+)?)/) : null;
  versionSelect.textContent = (isGspc(channel) || gspcEntry(latest)) ? gspcName(latest)
    : number ? "Version " + number[1] : latest ? String(latest.label || latest.version) : "No Version Found";
  versionsReady = !!latest;
  syncStart();
}
release_channel.addEventListener("change", releaseChannelUpdate);
release_channel.addEventListener("change", () => recheckCompat());

function syncStart() {
  startInstall.disabled = !versionsReady || !eraseOk.checked || !!(board.compatIssue && board.compatIssue.betaOnly);
  // Fix (recover flow): greyed Erase and Install says why
  const note = $("start-note");
  if (!note) return;
  note.textContent = !startInstall.disabled ? ""
    : !versionsReady ? "Could not load the version list. Check your internet connection, then reload the page."
    : board.compatIssue && board.compatIssue.betaOnly ? "Pick Stable or Beta under Release to install on this device."
    : "Tick the box above to continue.";
  note.hidden = !note.textContent;
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
// The chip family for esptool-js's chip name: "ESP32-S3" for an S3, "ESP32" for a classic ESP32, "" otherwise.
// Version 92: "ESP32-C3" too (the Super Mini image, Beta only for now)
function chipFamily(chip) {
  if (/ESP32-S3/.test(chip)) return "ESP32-S3";
  if (/ESP32-C3/.test(chip)) return "ESP32-C3";
  if (/ESP32/.test(chip) && !/ESP32-(S|C|H|P)/.test(chip)) return "ESP32";
  return "";
}
// Flash sizes from esptool-js getFlashSize() are in KB (4 MB = 4096, 16 MB = 16384)
// Version 83: S3 boards with 8 MB flash have their own images (N8R8 octal PSRAM, N8R2 quad PSRAM)
const MIN_FLASH_KB = { "ESP32": 4096, "ESP32-S3": 8192, "ESP32-C3": 4096 };
function flashLabel(kb) {
  if (kb == null || kb <= 0) return "an unknown flash size";
  if (kb >= 1024 && kb % 1024 === 0) return (kb / 1024) + " MB flash";
  return kb + " KB flash";
}
function chipShort(chip) {
  return String(chip || "Unknown Chip").replace(/\s*\(revision[^)]*\)/i, "").trim() || "Unknown Chip";
}
// null = ok to install; otherwise { chip, flashKb, family } for the notice
function compatIssue(chip, flashKb) {
  const family = chipFamily(chip);
  if (!family) return { chip, flashKb, family: "" };
  const need = MIN_FLASH_KB[family];
  if (flashKb != null && flashKb > 0 && flashKb < need) return { chip, flashKb, family };
  if (family === "ESP32-C3") {
    // The C3 image needs chip revision v0.3 or newer; older C3s are not supported
    const rev = String(chip).match(/revision v(\d+)\.(\d+)/);
    if (rev && (Number(rev[1]) * 100 + Number(rev[2])) < 3) return { chip, flashKb, family, oldRevision: true };
    // Version 103: Stable, Beta and the previous Stable (Version 99) all have a C3 image (Version 99's no-C3 note for
    //  the previous Stable, Version 85, is gone with it)
  }
  return null;
}
// Version 92: switching Stable/Beta with a C3 connected shows or clears its Beta-only note
function recheckCompat() {
  if (!board.chip || (board.compatIssue && !board.compatIssue.betaOnly && board.compatIssue.family !== "ESP32-C3")) return;
  const issue = compatIssue(board.chip, (board.info && board.info.flashKb) || null);
  board.compatIssue = issue;
  if (issue) showCompatNotice(issue); else hideCompatNotice();
  syncBoardUi();
  syncStart();
}
function hideCompatNotice() {
  const box = $("compat-notice");
  if (box && !box.hidden) foldShut(box);
}
function showCompatNotice(issue) {
  const box = $("compat-notice");
  const title = $("compat-notice-title");
  const text = $("compat-notice-text");
  if (!box || !title || !text) return;
  const chip = chipShort(issue.chip);
  const flash = (issue.flashKb != null && issue.flashKb > 0) ? flashLabel(issue.flashKb) : "";
  if (issue.betaOnly) {
    title.textContent = "The ESP32-C3 Isn't in the Previous Release";
    text.textContent = "Choose Stable or Beta under Release to install it.";
    if (box.hidden || box.shutting) foldOpen(box);
    appendConsole("[ESP32-C3: not in the previous release]\n");
    return;
  }
  title.textContent = "This Device Is Not Supported";
  if (issue.oldRevision) {
    text.textContent = "This device is " + chip + ". GSP32 needs an ESP32-C3 of revision v0.3 or newer. Nothing was installed.";
    if (box.hidden || box.shutting) foldOpen(box);
    appendConsole("[Not supported: " + chip + "]\n");
    return;
  }
  text.textContent = flash
    ? ("This device is " + chip + " with " + flash + ". GSP32 needs a classic ESP32 with at least 4 MB flash, or an ESP32-S3 with at least 8 MB flash (PSRAM recommended). Nothing was installed.")
    : ("This device is " + chip + ". GSP32 needs a classic ESP32 with at least 4 MB flash, or an ESP32-S3 with at least 8 MB flash (PSRAM recommended). Nothing was installed.");
  if (box.hidden || box.shutting) foldOpen(box);
  appendConsole("[Not supported: " + chip + (flash ? ", " + flash : "") + "]\n");
}
// Fix (S3 native USB): a board on Espressif's own USB (VID 0x303A) that runs GSP32 talks through TinyUSB, a different
//  USB device from the ROM's USB-JTAG/serial in download mode (the T-Display-S3: COM12 running, COM10 in download
//  mode). The page often can't reset it into download mode, and when the board does restart its old port is gone. A
//  short guide then asks for BOOT and RST by hand and for the port again (the picker shows only 0x303A ports). A port
//  this page was already allowed to use that comes back (the connect event) is taken without asking. Never a browser
//  serial auto-grant policy
const NATIVE_USB_VID = 0x303a;
const USB_JTAG_SERIAL_PID = 0x1001;
const USB_GUIDE_TITLE = {
  boot: "Hold BOOT, Tap RST, Release BOOT, Then Pick the Port Again",
  repick: "Pick the Port Again",
  rst: "Tap RST to Start GSP32",
};
const USB_MOVED_TEXT = "\n[The device's USB port changed (native USB). Pick the port again (see the note above the console).]\n";
const USB_NOT_READY_TEXT = "[Not in download mode yet. Hold BOOT, tap RST, release BOOT, then pick the port again.]\n";
// Fix (S3 web flash, Flasher Version 105): a native USB port other than the ROM's USB-JTAG/serial (303a:1001) is the
//  board's own program (GSP32's TinyUSB on the T-Display-S3's COM12). No reset sequence or SYNC can reach the ROM through
//  it: they only fill GSP32's input (its Improv listener stops at the first stray byte, then writes stall) and, on some
//  systems, MicroPython's DTR/RTS reboot moves the port mid-read. The page sends neither and shows the guide at once
const USB_APP_TEXT = "[GSP32's own USB port: the page can't switch it into download mode. Hold BOOT, tap RST, release BOOT, then pick the port again.]\n";
function appUsbPort(onPort) {
  return nativeUsb(onPort) && usbPid(onPort) !== USB_JTAG_SERIAL_PID;
}
function nativeUsb(onPort) {
  try {
    return !!onPort && typeof onPort.getInfo === "function" && onPort.getInfo().usbVendorId === NATIVE_USB_VID;
  } catch (err) {
    return false;
  }
}
function usbPid(onPort) {
  try {
    return onPort.getInfo().usbProductId;
  } catch (err) {
    return 0;
  }
}
function showUsbGuide(kind, resume, text) {
  usbGuide = { kind, resume };
  const box = $("usb-guide");
  if (!box) return;
  $("usb-guide-title").textContent = USB_GUIDE_TITLE[kind];
  $("usb-guide-text").textContent = text || (kind === "boot"
    ? "This page can't switch this device's own USB into download mode. In download mode it shows up as a new port."
    : kind === "rst" ? "GSP32 is installed, but the device is still in download mode. Tap RST (not BOOT), then pick the new port."
    : resume === "installed" ? "GSP32 is installed. The device restarted on a new USB port: pick it to set up Wi-Fi."
    : "The device restarted on a new USB port: pick it to go on.");
  if (box.hidden || box.shutting) foldOpen(box);
  syncBoardUi();
}
function hideUsbGuide() {
  usbGuide = null;
  const box = $("usb-guide");
  if (box && !box.hidden) foldShut(box);
}
// What a lost native USB port means: the board moved to a new port while the page reset it (reading the board,
//  connecting to install, the restart after an install or for Wi-Fi). "" = a plain unplug
function usbLossResume(lost) {
  if (!nativeUsb(lost)) return "";
  if (usbGuide) return usbGuide.resume;
  if (probing) return "probe";
  if (installConnecting) return "install";
  if (usbExpect && Date.now() < usbExpect.until) return usbExpect.resume;
  return "";
}
function usbLost(lost, resume) {
  portLost(lost, USB_MOVED_TEXT);
  if (!usbGuide) showUsbGuide((resume === "probe" || resume === "install") ? "boot" : "repick", resume);
}
// ROM download mode answers esptool's SYNC (command 0x08) at once; a running program never does. Our reader is
//  stopped by the caller. Bounded, so it can never hang
const SYNC_FRAME = new Uint8Array([0xc0, 0x00, 0x08, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0x07, 0x12, 0x20]
  .concat(new Array(32).fill(0x55), [0xc0]));
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's answersSync; on any other port Flasher 104's, unchanged
async function answersSync(onPort, ms = 400, keepText = false, lookFirst = 0) {
  return nativeUsb(onPort) ? answersSyncNative(onPort, ms, keepText, lookFirst) : answersSyncClassic(onPort, ms);
}
// Flasher Version 114.2: what a started app prints (the ROM's flash boot line, the loader, MicroPython, GSP32); the
//  ROM's download mode prints none of these
export function appBooted(text) {
  return /boot:0x[0-9a-f]+ \(SPI_FAST_FLASH_BOOT\)|^entry 0x|GSP32 Improv|Server listening on port|Web UI running|^MicroPython v|^>>> ?$/m.test(text);
}
async function answersSyncNative(onPort, ms = 400, keepText = false, lookFirst = 0) {
  if (!readableOf(onPort) || !writableOf(onPort)) return false;
  const syncReader = takeReader(onPort);
  let got = new Uint8Array(0), saw = false;
  // Flasher Version 114.2: one read in flight at a time, kept across the look and the ask (a read given up on by a
  //  timeout still takes the next bytes, so it must not be dropped: the ROM's answer would be lost)
  let pending = null;
  const nextRead = (left) => {
    if (!pending) pending = syncReader.read();
    return Promise.race([pending.then((result) => { pending = null; return result; }), delay(left).then(() => null)]);
  };
  try {
    // Flasher Version 114.2 (Gene's C3): look before asking. A board that already started never gets the SYNC frame
    //  (it reached GSP32's console as typed bytes, and in safe mode the REPL took the port)
    if (lookFirst) {
      const until = Date.now() + lookFirst;
      while (Date.now() < until) {
        const result = await nextRead(until - Date.now());
        if (!result || result.done) break;
        got = concatBytes(got, result.value);
      }
      if (appBooted(new TextDecoder().decode(got))) return false;
    }
    await writeTo(onPort, SYNC_FRAME);
    const until = Date.now() + ms;
    while (Date.now() < until) {
      const result = await nextRead(until - Date.now());
      if (!result || result.done) break;
      got = concatBytes(got, result.value);
      for (let i = 0; i + 2 < got.length; i++) {
        if (got[i] === 0xc0 && got[i + 1] === 0x01 && got[i + 2] === 0x08) {
          saw = true;
          return true;
        }
      }
    }
  } catch (err) {
    // No answer
  } finally {
    await withTimeout(syncReader.cancel(), 300, "Releasing the port").catch(() => {});
    dropReader(onPort, syncReader);
    // Flasher Version 110: a boot log that arrived while we asked the ROM must not be thrown away, or GSP32's
    //  lines are missed and Checking never finds the board
    if (keepText && !saw && got.length) consumeSerial(got);
  }
  return false;
}
async function answersSyncClassic(onPort, ms = 400) {
  if (!onPort || !onPort.readable || !onPort.writable) return false;
  const syncReader = onPort.readable.getReader();
  let got = new Uint8Array(0);
  try {
    await writeBytes(SYNC_FRAME);
    const until = Date.now() + ms;
    while (Date.now() < until) {
      const result = await Promise.race([syncReader.read(), delay(until - Date.now()).then(() => null)]);
      if (!result || result.done) break;
      got = concatBytes(got, result.value);
      for (let i = 0; i + 2 < got.length; i++) {
        if (got[i] === 0xc0 && got[i + 1] === 0x01 && got[i + 2] === 0x08) return true;
      }
    }
  } catch (err) {
    // No answer
  } finally {
    await withTimeout(syncReader.cancel(), 300, "Releasing the port").catch(() => {});
    try {
      syncReader.releaseLock();
    } catch (err) {
      // Released already
    }
  }
  return false;
}
// The guide's button: the picker again, only Espressif USB ports in it
async function pickUsbAgain() {
  if (!usbGuide || usbAttaching) return;
  let picked;
  try {
    picked = await navigator.serial.requestPort({ filters: [{ usbVendorId: NATIVE_USB_VID }] });
  } catch (err) {
    return;  // Picker closed: the guide stays
  }
  await attachUsbPort(picked);
}
// The new port (picked, or one this page may already use that came back): open it and go on where the page was
async function attachUsbPort(picked) {
  if (!usbGuide || usbAttaching) return;
  usbAttaching = true;
  const resume = usbGuide.resume;
  try {
    // A probe or connect still ending on the old port finishes first (it is time-limited)
    for (let waited = 0; (probing || installConnecting || installEnding) && waited < CONNECT_MS + 3000; waited += 100) await delay(100);
    if (port && port !== picked) await closePort();
    try {
      await openPicked(picked);
    } catch (err) {
      appendConsole("\n[" + err.message + "]\n");
      return;
    }
    hideUsbGuide();
    if (!installer.hidden && !installer.shutting) foldShut(installer);
    usbExpect = null;
    appendConsole("\n[Port picked again]\n");
    if (resume === "probe" || resume === "install") {
      const ok = await probeBoardOnConnect({ guided: true, resume });
      if (ok && resume === "install" && board.downloadMode && !board.compatIssue) await install();
    } else if (resume === "installed") {
      afterInstallRepick(picked);
    } else if (resume === "wifi") {
      startWifi(true);
    }
  } finally {
    usbAttaching = false;
    syncBoardUi();
    syncConsoleButtons();
  }
}
// Just installed (GSP32 without Wi-Fi listens for Improv until set up): the boot lines may have come before the port
//  was picked again. With nothing heard from it for a few seconds, the board is taken as listening
const USB_QUIET_MS = 4000;
function afterInstallRepick(picked) {
  const at = Date.now(), heard = lines.length;
  clearTimeout(otherTimer);
  clearNativeHandoff();
  // Checking may have replaced the Installed line; put it back so the Next step can attach
  if (bootingNote !== null || checkWaitTimer) endBooting();
  board.kind = "gsp32";
  if (nextStepPending) showNextStep();
  syncBoardUi();
  setTimeout(() => {
    if (port !== picked || !portOpen() || board.listening || board.kind !== "gsp32" || board.bootAt > at || lines.length > heard) return;
    board.listening = true;
    askVersion();
    syncBoardUi();
  }, USB_QUIET_MS);
}
// Known USB-serial bridges only (VID:PID from SerialPort.getInfo). Unknown IDs are omitted — never guessed.
const USB_BRIDGES = {
  "10c4:ea60": "CP2102", "10c4:ea63": "CP2102", "10c4:ea70": "CP2102",
  "1a86:7523": "CH340", "1a86:55d3": "CH343", "1a86:55d4": "CH9102",
  "0403:6001": "FT232", "303a:1001": "Native USB",
};
function usbBridgeInfo() {
  try {
    if (!port || typeof port.getInfo !== "function") return null;
    const info = port.getInfo();
    const vid = info.usbVendorId, pid = info.usbProductId;
    if (vid == null || pid == null) return null;
    const key = vid.toString(16).padStart(4, "0") + ":" + pid.toString(16).padStart(4, "0");
    const name = USB_BRIDGES[key] || "";
    if (!name) return null; // unknown VID/PID: omit — never guess
    return { key, name, label: key + " " + name };
  } catch (err) {
    return null;
  }
}
function usbBridgeName() {
  const u = usbBridgeInfo();
  return u ? u.name : "";
}
// Max rated CPU MHz from the chip name only. Unknown families are omitted — never guessed.
function cpuMhzFromChip(chip) {
  const name = String(chip || "");
  if (/ESP32-S3/i.test(name)) return 240;
  if (/ESP32-S2/i.test(name)) return 240;
  if (/ESP32-C3/i.test(name)) return 160;
  if (/ESP32-C6/i.test(name)) return 160;
  if (/ESP32-H2/i.test(name)) return 96;
  // Classic ESP32 (D0WD, WROOM, etc.): not S/C/H/P variants
  if (/ESP32/i.test(name) && !/ESP32-(S|C|H|P)/i.test(name)) return 240;
  return 0;
}
function formatBoardDetails() {
  const parts = [];
  const info = board.info || {};
  if (info.cores) parts.push(info.cores);
  if (info.flashKb != null && info.flashKb > 0) {
    parts.push(info.flashKb >= 1024 && info.flashKb % 1024 === 0
      ? (info.flashKb / 1024) + " MB flash" : info.flashKb + " KB flash");
  }
  if (info.psram) parts.push(info.psram);
  const cpu = info.cpuMhz || cpuMhzFromChip(board.chip);
  if (cpu) parts.push(cpu + " MHz");
  if (info.usb) parts.push(info.usb);
  return parts.join(" · ");
}
async function readBoardExtras(link) {
  // Only what esptool-js and the serial port actually return — skip on failure
  const info = Object.assign({}, board.info || {});
  const usb = usbBridgeInfo();
  if (usb) { info.usb = usb.name; info.usbLabel = usb.label; }
  if (link && link.loader) {
    try {
      const kb = await withTimeout(link.loader.getFlashSize(), READ_MS, "Reading the flash size");
      if (kb != null && kb > 0) info.flashKb = kb;
    } catch (err) {}
    try {
      const features = await withTimeout(link.loader.chip.getChipFeatures(link.loader), READ_MS, "Reading chip features");
      if (Array.isArray(features)) {
        const joined = features.join(" ");
        if (/Dual Core/i.test(joined)) info.cores = "Dual Core";
        else if (/Single Core/i.test(joined)) info.cores = "Single Core";
        const ps = joined.match(/Embedded PSRAM (\d+)MB/i);
        if (ps) { info.psram = ps[1] + " MB PSRAM"; info.psramMb = +ps[1]; }
        else if (/Embedded PSRAM/i.test(joined)) info.psram = "Embedded PSRAM";
      }
    } catch (err) {}
    // CPU MHz is derived from the chip type (not the crystal). Crystal is not shown or sent.
  }
  const cpu = cpuMhzFromChip(board.chip || (link && link.chip) || "");
  if (cpu) info.cpuMhz = cpu;
  board.info = info;
  return info;
}


// Board-model telemetry (no MAC): once per Get Started connect, after a successful chip read. Fire-and-forget.
const TELEMETRY_URL = "https://gsp32-telemetry.genereese.workers.dev/log";
function browserKind() {
  const ua = navigator.userAgent || "";
  if (/Brave/i.test(ua) || navigator.brave) return "brave";
  if (/Edg\//i.test(ua)) return "edge";
  if (/OPR\/|Opera/i.test(ua)) return "opera";
  if (/Chrome\//i.test(ua) && !/Edg\//i.test(ua)) return "chrome";
  return "other";
}
function reportBoardTelemetry(compatible) {
  if (board.telemetrySent) return;
  const chip = chipShort(board.chip || "");
  if (!chip || chip === "Unknown Chip") return;
  board.telemetrySent = true;
  const body = { chip, compatible: !!compatible };
  const raw = String(board.chip || "");
  const rev = raw.match(/\(revision\s*([^)]+)\)/i);
  if (rev) body.revision = rev[1].trim();
  const info = board.info || {};
  if (info.cores === "Dual Core") body.cores = 2;
  else if (info.cores === "Single Core") body.cores = 1;
  if (info.flashKb != null && info.flashKb > 0) {
    body.flash_mb = info.flashKb >= 1024 && info.flashKb % 1024 === 0
      ? info.flashKb / 1024 : Math.round((info.flashKb / 1024) * 100) / 100;
  }
  if (info.psram) body.psram = true;
  if (info.usbLabel) body.usb_bridge = info.usbLabel;
  const verEl = document.querySelector(".flasher-version");
  const ver = verEl && (verEl.textContent || "").match(/Flasher Version\s+(\d+(?:\.\d+)?)/i);
  if (ver) body.flasher_version = ver[1];
  body.browser = browserKind();
  try {
    // Never await: install must not wait on telemetry. Never include MAC.
    fetch(TELEMETRY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      mode: "cors",
      keepalive: true,
    }).catch(() => {});
  } catch (err) {}
}


// Version 80: read chip/flash/features as soon as the port is picked (before Install). Leaves the board
//  running again so the console works; Install reconnects cleanly (bootloader session is not kept).
//  Fix (S3 native USB): a board in download mode stays there for Install (a reset starts its program, on another port)
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's releaseLoader; on any other port Flasher 104's, unchanged
async function releaseLoader(link, keep) {
  return nativeUsb(port) ? releaseLoaderNative(link, keep) : releaseLoaderClassic(link, keep);
}
async function releaseLoaderNative(link, keep) {
  if (link && link.transport) await link.transport.disconnect().catch(() => {});
  stopLink(link);
  await reopenPort(FLASH_BAUD).catch(() => {});
  if (keep || board.downloadMode) {
    await setRunState().catch(() => {});
    return;
  }
  await resetBoard().catch(() => setRunState().catch(() => {}));
}
async function releaseLoaderClassic(link, keep) {
  if (link && link.transport) await link.transport.disconnect().catch(() => {});
  await reopenPort(FLASH_BAUD).catch(() => {});
  if (keep || board.downloadMode) {
    await setRunState().catch(() => {});
    return;
  }
  await resetBoard().catch(() => setRunState().catch(() => {}));
}
// Resolves true once the board was read. options.guided: the port was picked from the native USB guide
async function probeBoardOnConnect(options = {}) {
  if (!portOpen()) return false;
  const probed = port;
  const resume = options.resume || "probe";
  probing = true;
  board.compatIssue = null;
  board.note = "";
  hideCompatNotice();
  setBusy(true);
  syncConsoleButtons();
  appendConsole("\n[Reading device info...]\n");
  const terminal = { clean() {}, writeLine() {}, write() {} };
  let link = null, keep = false, ok = false;
  try {
    await stopReading();
    // Fix (S3 native USB): the ROM's download mode is always the USB-JTAG/serial port (303a:1001; GSP32's own TinyUSB
    //  port never is). One there is checked for download mode first (picked from the guide, or put there by hand with
    //  BOOT and RST); a board in it is read without a reset and left there for Install
    if (nativeUsb(probed) && usbPid(probed) === USB_JTAG_SERIAL_PID) {
      board.downloadMode = await answersSync(probed);
      if (board.downloadMode) appendConsole("[Download mode: reading the device without a reset]\n");
    }
    if (options.guided && !board.downloadMode) {
      keep = true;
      appendConsole(USB_NOT_READY_TEXT);
      showUsbGuide("boot", resume);
      return false;
    }
    if (appUsbPort(probed)) {
      keep = true;
      board.downloadMode = false;
      appendConsole(USB_APP_TEXT);
      if (port === probed) showUsbGuide("boot", resume);
      return false;
    }
    try {
      link = await connectLoader(terminal);
    } catch (err) {
      const why = err && err.message ? err.message : err;
      // The port got stuck (said once already, see markStuck): nothing more to try here
      if (err && err.code === "stuck") return false;
      if (nativeUsb(probed)) {
        // The page can't reset this board into download mode: BOOT and RST by hand, and the port again
        appendConsole("[Could not switch the device into download mode (" + why + ").]\n");
        board.downloadMode = false;
        if (port === probed) showUsbGuide("boot", resume);
      } else {
        appendConsole("[Could not read the device yet (" + why + "). Install can try again.]\n");
      }
      // Fix (S3 web flash, Flasher Version 105): connectLoader already reset the link (a second close and reopen here,
      //  of a port that may be moving, is gone). Flasher Version 107: native USB only; other ports as in 104
      if (!nativeUsb(probed)) await resetLink(link).catch(() => {});
      await setRunState().catch(() => {});
      return false;
    }
    const chip = link.chip || board.chip || "";
    board.chip = chip;
    await readBoardExtras(link);
    const flashKb = (board.info && board.info.flashKb) || null;
    const issue = compatIssue(chip, flashKb);
    board.compatIssue = issue;
    reportBoardTelemetry(!issue || !!issue.betaOnly);
    syncBoardUi();
    if (issue) {
      showCompatNotice(issue);
      if (!issue.betaOnly) appendConsole("[This device is not supported for GSP32. Install is disabled.]\n");
    } else if (chip) {
      appendConsole("[Device: " + chipShort(chip) + (flashKb ? ", " + flashLabel(flashKb) : "") + "]\n");
    }
    // Fix (recover flow): Incomplete Install only for this board (its MAC is the one an unfinished install wrote to)
    if (flashNoteMatches()) setStatus(INCOMPLETE_TEXT, "error");
    if (board.downloadMode) {
      board.note = "Download Mode: Ready to Install";
      hideUsbGuide();
    }
    ok = true;
  } finally {
    await releaseLoader(link, keep).catch(() => {});
    probing = false;
    // The port did not come back after the probe (closed, reopen failed): say so and bring Get Started back
    if (port && !portOpen()) await portLost(port, "\n[The port closed while reading the device. Click Get Started to connect again.]\n");
    else startReading();
    setBusy(false);
    syncBoardUi();
    syncConsoleButtons();
  }
  return ok;
}

// Version 83: among a family's builds, the one for this board's flash size and PSRAM. Builds may carry "flashMb"
//  (16 when absent) and "psramMb" (8 = octal, 2 = quad). An S3's in-package PSRAM size (efuse) tells octal (8 MB)
//  from quad (2 MB); when it can't be read, an in-page ask (askPsram).
// Version 83: in-page ask for the PSRAM size (8 or 2); closing it (Escape) means 8, the tested N8R8 image
function askPsram() {
  const box = $("psram-modal");
  if (!box || typeof box.showModal !== "function") return Promise.resolve(8);
  return new Promise((resolve) => {
    let picked = 8;
    const pick = (mb) => () => { picked = mb; box.close(); };
    $("psram-8").onclick = pick(8);
    $("psram-2").onclick = pick(2);
    box.addEventListener("close", () => resolve(picked), { once: true });
    box.showModal();
  });
}
async function pickBuild(builds, family) {
  const list = builds.filter((item) => item.chipFamily === family);
  if (family !== "ESP32-S3") return list[0] || null;  // builds without flashMb are 16 MB (older manifests)
  const info = board.info || {};
  const flashMb = info.flashKb ? Math.floor(info.flashKb / 1024) : 16;
  const sized = list.filter((item) => (item.flashMb || 16) <= flashMb)
    .sort((a, b) => (b.flashMb || 16) - (a.flashMb || 16));
  if (!sized.length) return null;
  const best = sized.filter((item) => (item.flashMb || 16) === (sized[0].flashMb || 16));
  if (best.length === 1) return best[0];
  let want = info.psramMb;
  if (want !== 2 && want !== 8) {
    want = await askPsram();
    appendConsole("[PSRAM size not readable: " + (want === 2 ? "N8R2" : "N8R8") + " chosen]\n");
  }
  return best.find((item) => (item.psramMb || 8) === want) || best[0];
}
async function loadFirmware(family) {
  const { manifest, manifestUrl } = manifestCache || await loadManifest();
  const build = await pickBuild(manifest.builds, family);
  if (!build) throw new Error("This firmware has no build for " + family + " with this flash size.");
  if (build.label) appendConsole("[Image: " + build.label + (build.untested ? " (untested)" : "") + "]\n");
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
  if (isGspc(release_channel.value) || gspcEntry(latest)) return versionSelect.textContent;   // GSP32-C Beta V117/V118, Stable V130 (Gene)
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
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's reopenPort; on any other port Flasher 104's, unchanged
async function reopenPort(baud) {
  return nativeUsb(port) ? reopenPortNative(baud) : reopenPortClassic(baud);
}
async function reopenPortNative(baud) {
  if (!port || portBaud === baud) return;
  const onPort = port;
  if (!(await safeClose(onPort))) throw stuckError();
  await onPort.open({ baudRate: baud });
  onPort.__gsp32Opened = true;
  portBaud = baud;
  await setRunState().catch(() => {});
}
async function reopenPortClassic(baud) {
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
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's resetLink; on any other port Flasher 104's, unchanged
async function resetLink(link) {
  return nativeUsb(port) ? resetLinkNative(link) : resetLinkClassic(link);
}
async function resetLinkNative(link) {
  const transport = link && link.transport;
  stopLink(link);
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
  const onPort = port;
  if (!(await safeClose(onPort))) throw stuckError();
  await withTimeout(onPort.open({ baudRate: FLASH_BAUD }), 2000, "Opening the port");
  onPort.__gsp32Opened = true;
  portBaud = FLASH_BAUD;
  await setRunState().catch(() => {});
}
async function resetLinkClassic(link) {
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
// Fix (false disconnect): esptool-js reads through this. A recoverable read error (port.readable still there) takes a
//  fresh reader from the new stream and reads again, once per error; a real loss rejects as before
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's resilientReader; on any other port Flasher 104's, unchanged
function resilientReader(onPort) {
  return nativeUsb(onPort) ? resilientReaderNative(onPort) : resilientReaderClassic(onPort);
}
function resilientReaderNative(onPort) {
  let inner = takeReader(onPort);
  const wrapper = {
    async read() {
      try {
        return await inner.read();
      } catch (err) {
        if (!serialRecoverable(err, onPort)) throw err;
        console.warn("Serial read error during connect/flash, reading on:", serialErrorName(err));
        dropReader(onPort, inner);
        inner = takeReader(onPort);
        return await inner.read();
      }
    },
    cancel(reason) { return inner.cancel(reason); },
    releaseLock() { return dropReader(onPort, inner); },
    get closed() { return inner.closed; },
  };
  return wrapper;
}
function resilientReaderClassic(onPort) {
  let inner = onPort.readable.getReader();
  const wrapper = {
    async read() {
      try {
        return await inner.read();
      } catch (err) {
        if (!serialRecoverable(err, onPort)) throw err;
        console.warn("Serial read error during connect/flash, reading on:", serialErrorName(err));
        try { inner.releaseLock(); } catch (e) { /* released already */ }
        inner = onPort.readable.getReader();
        return await inner.read();
      }
    },
    cancel(reason) { return inner.cancel(reason); },
    releaseLock() { return inner.releaseLock(); },
    get closed() { return inner.closed; },
  };
  return wrapper;
}
// Fix (Linux reset): the reset into the bootloader. EN must rise while GPIO 0 is already low, and the classic
//  two-transistor circuit has no state with both low, so the step from "reset" (DTR off, RTS on) to "download"
//  (DTR on, RTS off) must change both lines at once. Desktop esptool on Linux does that in one TIOCMSET
//  (UnixTightReset). Chromium has no atomic call: on Linux each setSignals is one ioctl per line (DTR, then RTS),
//  and esptool-js 0.5.7's ClassicReset makes it worse (its setRTS sends a second setSignals for DTR), so a CP2102
//  board measured 0 of 12 into download mode (boot:0x13) with esptool-js's timing and 4 of 6 with one combined
//  setSignals per step (pyserial on Gene's laptop, 17 Oct 2026). So each connect attempt takes the next sequence:
//  the one that worked last on this USB bridge (else tight on Linux, classic elsewhere, USB-JTAG for a native USB
//  chip), then classic, tight and USB-JTAG in turn; the first round uses esptool's 100 ms hold and
//  DEFAULT_RESET_DELAY (50 ms), later rounds its extra delay (550 ms). Classic and USB-JTAG are esptool-js's own
//  calls, unchanged, so Windows behaves as before.
const RESET_HOLD_MS = 100;
const DEFAULT_RESET_DELAY = 50;
const EXTRA_RESET_DELAY = 550;
const RESET_KEY = "gsp32ResetSeq";
const USB_JTAG_PID = 0x1001;
// Flasher Version 115.17 (Gene's ESP32, CP2102): a gentler, longer reset for Silicon Labs CP210x bridges (VID 0x10C4).
//  EN is held low longer (a slow supply or a big EN capacitor has time to settle), the step to download mode is one
//  setSignals like tight, and GPIO 0 stays low a full second after EN rises (a slow-rising EN is sampled while it is
//  still low). It takes the USB-JTAG slot in the rotation (that sequence is for native USB chips, not a CP210x): about
//  0.75 s more than the USB-JTAG sequence it replaces, twice in a failing connect's seven attempts (about 1.5 s), inside
//  the same connect time limit (CONNECT_MS), so the connect functions themselves are unchanged
const CP210X_VID = 0x10c4;
const GENTLE_EN_LOW_MS = 300;
const GENTLE_IO0_HOLD_MS = 700;
const RESET_SEQUENCES = {
  // esptool's UnixTightReset, one setSignals per step
  async tight(p, resetDelay) {
    await p.setSignals({ dataTerminalReady: false, requestToSend: false });
    await p.setSignals({ dataTerminalReady: true, requestToSend: true });
    await p.setSignals({ dataTerminalReady: false, requestToSend: true }); // EN low (reset), GPIO 0 high
    await delay(RESET_HOLD_MS);
    await p.setSignals({ dataTerminalReady: true, requestToSend: false }); // GPIO 0 low, EN high
    await delay(resetDelay);
    await p.setSignals({ dataTerminalReady: false, requestToSend: false });
  },
  // esptool-js 0.5.7 ClassicReset, call for call (its setRTS re-sends DTR)
  async classic(p, resetDelay) {
    let dtr = false;
    const setDTR = async (v) => { dtr = v; await p.setSignals({ dataTerminalReady: v }); };
    const setRTS = async (v) => { await p.setSignals({ requestToSend: v }); await p.setSignals({ dataTerminalReady: dtr }); };
    await setDTR(false);
    await setRTS(true);
    await delay(RESET_HOLD_MS);
    await setDTR(true);
    await setRTS(false);
    await delay(resetDelay);
    await setDTR(false);
  },
  // esptool-js 0.5.7 UsbJtagSerialReset (ESP32-S3/C3 native USB), call for call
  async usbJtag(p) {
    let dtr = false;
    const setDTR = async (v) => { dtr = v; await p.setSignals({ dataTerminalReady: v }); };
    const setRTS = async (v) => { await p.setSignals({ requestToSend: v }); await p.setSignals({ dataTerminalReady: dtr }); };
    await setRTS(false);
    await setDTR(false);
    await delay(100);
    await setDTR(true);
    await setRTS(false);
    await delay(100);
    await setRTS(true);
    await setDTR(false);
    await setRTS(true);
    await delay(100);
    await setRTS(false);
    await setDTR(false);
  },
  // Flasher Version 115.17: CP210x only (see GENTLE_EN_LOW_MS)
  async gentle(p) {
    await p.setSignals({ dataTerminalReady: false, requestToSend: false });
    await delay(50);
    await p.setSignals({ dataTerminalReady: false, requestToSend: true }); // EN low (reset), GPIO 0 high
    await delay(GENTLE_EN_LOW_MS);
    await p.setSignals({ dataTerminalReady: true, requestToSend: false }); // GPIO 0 low, EN high
    await delay(GENTLE_IO0_HOLD_MS);
    await p.setSignals({ dataTerminalReady: false, requestToSend: false });
  },
};
function cp210x(onPort) {
  const info = (onPort && onPort.getInfo && onPort.getInfo()) || {};
  return info.usbVendorId === CP210X_VID;
}
function isLinuxBrowser() {
  const plat = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  if (/android/i.test(plat + " " + navigator.userAgent)) return false;
  return /linux|cros|chrome os/i.test(plat || navigator.userAgent);
}
function resetBridgeKey(onPort) {
  const info = (onPort && onPort.getInfo && onPort.getInfo()) || {};
  return (info.usbVendorId || 0).toString(16) + ":" + (info.usbProductId || 0).toString(16);
}
function rememberedReset(onPort) {
  try {
    return (JSON.parse(localStorage.getItem(RESET_KEY) || "{}") || {})[resetBridgeKey(onPort)] || "";
  } catch (err) {
    return "";
  }
}
function rememberReset(onPort, name) {
  try {
    const all = JSON.parse(localStorage.getItem(RESET_KEY) || "{}") || {};
    all[resetBridgeKey(onPort)] = name;
    localStorage.setItem(RESET_KEY, JSON.stringify(all));
  } catch (err) {
    // No storage: next time starts from the default order again
  }
}
// The order the connect attempts take: first what worked, then classic, tight, USB-JTAG
function resetOrder(onPort, linux = isLinuxBrowser(), remembered = rememberedReset(onPort)) {
  const info = (onPort && onPort.getInfo && onPort.getInfo()) || {};
  let first = "classic";
  if (info.usbProductId === USB_JTAG_PID) first = "usbJtag";
  else if (linux) first = "tight";
  // Flasher Version 115.17: a CP210x gets the gentle reset in the USB-JTAG slot
  const third = cp210x(onPort) ? "gentle" : "usbJtag";
  if (RESET_SEQUENCES[remembered]) first = remembered;
  return [first].concat(["classic", "tight", third].filter((n) => n !== first));
}
// esptool-js asks its resetConstructors for its sequences and cycles through them, one per connect attempt; every
//  one it gets is this same rotation, so attempt N runs order[N % 3] whatever esptool-js would have picked
function resetRotation(onPort) {
  const order = resetOrder(onPort);
  const rotation = {
    order,
    count: 0,
    name: "",
    tried: [],
    async reset() {
      const i = rotation.count++;
      rotation.name = order[i % order.length];
      const resetDelay = i < order.length ? DEFAULT_RESET_DELAY : EXTRA_RESET_DELAY;
      rotation.tried.push(rotation.name === "gentle" ? "gentle " + (GENTLE_EN_LOW_MS + "/" + GENTLE_IO0_HOLD_MS) : rotation.name + " " + resetDelay);
      await RESET_SEQUENCES[rotation.name](onPort, resetDelay);
    },
  };
  return rotation;
}
// Fix (S3 web flash, Flasher Version 105): esptool-js can't be stopped, so a connect that ran out of time used to go on
//  in the background (resets, SYNC writes, readers) on the port the page was closing. esptool-js now gets a stand-in
//  for the port that works only while its link is live; stopLink() ends it (no more signals, reads or writes)
const STOPPED_TEXT = "The connection to the device was stopped";
const DEAD_READER = {
  read: () => Promise.reject(new Error(STOPPED_TEXT)),
  cancel: () => Promise.resolve(),
  releaseLock() {},
  closed: Promise.resolve(),
};
function linkLive(link, onPort) {
  return !!link && !link.aborted && port === onPort && portUsable(onPort);
}
function stopLink(link) {
  if (!link || !link.native || link.aborted) return;
  link.aborted = true;
  if (link.transport) {
    link.transport.reader = DEAD_READER;
    link.transport.buffer = new Uint8Array(0);
  }
}
function loaderDevice(onPort, link) {
  const stopped = () => Promise.reject(new Error(STOPPED_TEXT));
  return {
    getInfo: () => onPort.getInfo(),
    get readable() { return linkLive(link, onPort) ? readableOf(onPort) : null; },
    get writable() { return linkLive(link, onPort) ? writableOf(onPort) : null; },
    setSignals: (signals) => (linkLive(link, onPort) ? onPort.setSignals(signals) : stopped()),
    open: stopped,
    close: stopped,
  };
}
// A borrowed transport on the open port and a loader in the board's flasher stub at 115200
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's connectLoader; on any other port Flasher 104's, unchanged
async function connectLoader(terminal) {
  return nativeUsb(port) ? connectLoaderNative(terminal) : connectLoaderClassic(terminal);
}
async function connectLoaderNative(terminal) {
  if (!portOpen()) throw new Error("The port closed");
  await reopenPort(FLASH_BAUD);
  const onPort = port;
  const link = { transport: null, loader: null, chip: "", rotation: null, aborted: false, native: true };
  const device = loaderDevice(onPort, link);
  const transport = new Transport(device, false);
  link.transport = transport;
  // The port is already open at 115200: esptool-js borrows its reader
  transport.connect = async function (baud) {
    if (!linkLive(link, onPort)) throw new Error(STOPPED_TEXT);
    this.baudrate = baud;
    await reopenPort(baud);
    this.reader = resilientReader(onPort);
  };
  // Every esptool-js write is bounded too (a write that never ends is aborted, see writeTo)
  transport.write = async function (data) {
    if (!linkLive(link, onPort)) throw new Error(STOPPED_TEXT);
    await writeTo(onPort, typeof this.slipWriter === "function" ? this.slipWriter(data) : data);
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
  const rotation = resetRotation(device);
  const loader = new ESPLoader({
    transport, baudrate: FLASH_BAUD, romBaudrate: FLASH_BAUD, terminal,
    resetConstructors: { classicReset: () => rotation, usbJTAGSerialReset: () => rotation },
  });
  link.loader = loader;
  link.rotation = rotation;
  // Fix (S3 native USB): a board already in download mode is synced without a reset (a reset would start its program)
  const mode = board.downloadMode ? "no_reset" : "default_reset";
  let lostTimer = null;
  const lost = new Promise((resolve, reject) => {
    lostTimer = setInterval(() => {
      if (port !== onPort) reject(new Error("The port closed"));
    }, 200);
  });
  try {
    link.chip = await withTimeout(Promise.race([loader.main(mode), lost]), CONNECT_MS, "Connecting to the device")
      .finally(() => clearInterval(lostTimer));
    // Fix (S3 web flash, Flasher Version 105): a board read in download mode keeps the flasher stub running (no reset
    //  in between), and esptool-js 0.5.7 then says "Stub is already running" without taking itself for the stub
    //  (IS_STUB stays false; esptool's own Python does take it). Its writeFlash then skipped the chip erase, sent the
    //  ROM's begin command to the stub and checked the MD5 without waiting for the last block: the very fast first
    //  install and its MD5 mismatches on the T-Display-S3. A stub that answered the SYNC is the stub
    if (loader.syncStubDetected && !loader.IS_STUB) {
      loader.IS_STUB = true;
      appendConsole("[The flasher stub was still running: using it]\n");
    }
    // Fix (S3 web flash, Flasher Version 105): as esptool's own Python does on the S3's USB-JTAG/serial port, the RTC
    //  and super watchdogs are turned off after the connect (they can restart the board mid-write there)
    if (usbPid(onPort) === USB_JTAG_SERIAL_PID && /ESP32-S3/.test(link.chip || "")) await disableS3Watchdogs(loader);
    if (rotation.name) {
      rememberReset(port, rotation.name);
      board.resetSeq = rotation.name;
    }
    board.chip = (await withTimeout(loader.chip.getChipDescription(loader), READ_MS, "Reading the chip")) || link.chip;
    board.mac = (await withTimeout(loader.chip.readMac(loader), READ_MS, "Reading the MAC")) || "";
    await readBoardExtras(link);
    syncBoardUi();
  } catch (err) {
    if (!link.chip) {
      // The connect ran out of time (or the port went): end esptool-js's session before the port is reset
      stopLink(link);
      if (rotation.tried.length) appendConsole("[Resets tried: " + rotation.tried.join(", ") + "]\n");
      await resetLink(link).catch((again) => { if (again && again.code === "stuck") throw again; });
      throw err;
    }
    board.chip = link.chip;
    await readBoardExtras(link).catch(() => {});
    syncBoardUi();
  }
  return link;
}
async function connectLoaderClassic(terminal) {
  await reopenPort(FLASH_BAUD);
  const transport = new Transport(port, false);
  // The port is already open at 115200: esptool-js borrows its reader
  transport.connect = async function (baud) {
    this.baudrate = baud;
    await reopenPort(baud);
    this.reader = resilientReader(port);
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
  const rotation = resetRotation(port);
  const loader = new ESPLoader({
    transport, baudrate: FLASH_BAUD, romBaudrate: FLASH_BAUD, terminal,
    resetConstructors: { classicReset: () => rotation, usbJTAGSerialReset: () => rotation },
  });
  const link = { transport, loader, chip: "", rotation };
  // Fix (S3 native USB): a board already in download mode is synced without a reset (a reset would start its program)
  const mode = board.downloadMode ? "no_reset" : "default_reset";
  const onPort = port;
  let lostTimer = null;
  const lost = new Promise((resolve, reject) => {
    lostTimer = setInterval(() => {
      if (port !== onPort) reject(new Error("The port closed"));
    }, 200);
  });
  try {
    link.chip = await withTimeout(Promise.race([loader.main(mode), lost]), CONNECT_MS, "Connecting to the device")
      .finally(() => clearInterval(lostTimer));
    if (rotation.name) {
      rememberReset(port, rotation.name);
      board.resetSeq = rotation.name;
    }
    board.chip = (await withTimeout(loader.chip.getChipDescription(loader), READ_MS, "Reading the chip")) || link.chip;
    board.mac = (await withTimeout(loader.chip.readMac(loader), READ_MS, "Reading the MAC")) || "";
    await readBoardExtras(link);
    syncBoardUi();
  } catch (err) {
    if (!link.chip) {
      if (rotation.tried.length) appendConsole("[Resets tried: " + rotation.tried.join(", ") + "]\n");
      await resetLink(link).catch(() => {});
      throw err;
    }
    board.chip = link.chip;
    await readBoardExtras(link).catch(() => {});
    syncBoardUi();
  }
  return link;
}
// Read and discard what is waiting until 100 ms pass with nothing (500 ms at most), then a fresh reader, which also
//  drops any read left waiting by an earlier timeout. Bounded throughout, so it can never hang
// Flasher Version 107: on a native-USB port (VID 0x303A) Flasher 105's drainInput; on any other port Flasher 104's, unchanged
async function drainInput(transport, quietMs = 100, maxMs = 500) {
  return nativeUsb(port) ? drainInputNative(transport, quietMs, maxMs) : drainInputClassic(transport, quietMs, maxMs);
}
async function drainInputNative(transport, quietMs = 100, maxMs = 500) {
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
  transport.reader = transport.device && transport.device.readable ? resilientReader(port) : undefined;
  transport.buffer = new Uint8Array(0);
  return dropped;
}
async function drainInputClassic(transport, quietMs = 100, maxMs = 500) {
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
  transport.reader = port && port.readable ? resilientReader(port) : undefined;
  transport.buffer = new Uint8Array(0);
  return dropped;
}
// Step 2: port, then flash with esptool-js on the same open port
async function install() {
  if (board.compatIssue) {
    showCompatNotice(board.compatIssue);
    syncBoardUi();
    return;
  }
  showActions(false);
  showStep("flash");
  startFlashGuard();
  setBusy(true);
  syncConsoleButtons();
  if (!portOpen()) {
    stopFlashGuard();
    showError("The device is not connected. Click Get Started, then try again.", "prep");
    showActions(true);
    return;
  }
  appendConsole("\n[Installing " + versionSelect.textContent + "]\n");
  nextStepPending = false;
  let watchdogDone = false, flashedPort = null;
  try {
    setProgress("Downloading the firmware...", 0, "Installing " + installName() + ": Downloading the Firmware...");
    await loadManifest();
    // Version 79: the image follows the chip, so it is fetched once per family after the first connect
    const imageFor = {};
    await stopReading();
    endConsoleFolds();
    const terminal = {
      clean() {},
      writeLine(text) { appendConsole("[esptool] " + text + "\n"); },
      write(text) { appendConsole(text); },
    };
    const pickedStart = versionSelect.textContent.match(/Version (\d+(?:\.\d+)?)/);
    // Version 64: connect and write at 115200, always the full image. A write error (the occasional
    //  "Invalid head of packet (0xff)") gets one fresh connect and a second full try before it is shown
    for (let attempt = 1; ; attempt++) {
      setProgress("Connecting to the device...", 0, "Installing " + installName() + ": Connecting to the Device...");
      let link;
      const installPort = port;
      installConnecting = true;
      try {
        if (appUsbPort(installPort) && !board.downloadMode) throw new Error("GSP32's own USB port can't be switched from the page");
        link = await connectLoader(terminal);
      } catch (err) {
        // Fix (S3 native USB): no second try for a native USB board: the page can't reset it into download mode, so
        //  the guide asks for BOOT and RST by hand and the port again, and the install goes on from there
        if (nativeUsb(installPort)) {
          installConnecting = false;
          appendConsole("[Could not switch the device into download mode (" + (err && err.message ? err.message : err) + ").]\n");
          board.downloadMode = false;
          board.note = "";
          showUsbGuide("boot", "install");
          const guided = new Error("Hold BOOT, tap RST, release BOOT, then pick the port again (see the note above).");
          guided.plain = true;
          throw guided;
        }
        if (err && err.code === "stuck") throw err;
        // Version 61: one more try from a clean port, then a clear error with Retry
        appendConsole("[Connect did not answer (" + (err && err.message ? err.message : err) + "), trying once more]\n");
        // Flasher Version 115.10 (Gene's ESP32): a weak auto-reset: the hold-BOOT note folds in now, and the second
        //  try waits a moment so BOOT can be pressed before its resets
        board.leftRunning = false;
        showBootNow(true);
        setProgress("Hold BOOT on the device now: trying once more...", 0, "Installing " + installName() + ": Hold BOOT Now...");
        appendConsole("[Hold BOOT on the device now (keep holding until Erasing the device shows)]\n");
        await delay(BOOT_NOW_MS);
        setProgress("Connecting to the device (holding BOOT)...", 0, "Installing " + installName() + ": Connecting to the Device...");
        try {
          link = await connectLoader(terminal);
          // Flasher Version 115.17: the automatic reset failed and the try with BOOT held got through: remembered
          if (!nativeUsb(installPort)) rememberHoldBoot(installPort, board.mac);
        } catch (again) {
          if (again && again.code === "stuck") throw again;
          // Flasher Version 115.17: remembered, so the next Install shows the hold-BOOT tip up front
          if (!nativeUsb(installPort)) rememberHoldBoot(installPort, board.mac);
          // Flasher Version 115.10 (Gene's ESP32): no reset style put it into download mode (a weak auto-reset keeps
          //  starting its program): the hold-BOOT note folds in under the error (see showBootHint)
          throw Object.assign(new Error("The device did not answer. Unplug it, plug it back in and click Try Again. If it still does not answer, hold the BOOT button while you click Try Again."),
            { bootHint: !nativeUsb(installPort) });
        }
      } finally {
        installConnecting = false;
      }
      board.leftRunning = false;
      // Flasher Version 115.17: a remembered device with no MAC on file yet that got through (BOOT held, as the tip
      //  asked) adds its MAC, so another device on the same kind of USB bridge whose MAC is known later does not get it
      const heldEntry = board.mac ? holdBootEntry(installPort, "") : null;
      if (heldEntry && !(heldEntry.macs || []).length) rememberHoldBoot(installPort, board.mac, true);
      const chip = link.chip || board.chip || "";
      await readBoardExtras(link);
      syncBoardUi();
      const flashKb = (board.info && board.info.flashKb) || null;
      board.chip = chip;
      const issue = compatIssue(chip, flashKb);
      // Telemetry already fired on connect probe; only send here if probe never ran
      reportBoardTelemetry(!issue || !!issue.betaOnly);
      if (issue) {
        board.compatIssue = issue;
        await link.transport.disconnect();
        stopLink(link);
        await reopenPort(FLASH_BAUD).catch(() => {});
        await setRunState().catch(() => {});
        startReading();
        setBusy(false);
        stopFlashGuard();
        closeWizard();
        setStatus(""); // fold away the Installing... progress bar
        showActions(true);
        showCompatNotice(issue);
        syncBoardUi();
        syncConsoleButtons();
        return;
      }
      const family = chipFamily(chip);
      if (!imageFor[family]) {
        setProgress("Downloading the firmware for " + family + "...", 0, "Installing " + installName() + ": Downloading the Firmware...");
        appendConsole("[" + family + " detected: installing its build]\n");
        imageFor[family] = await loadFirmware(family);
      }
      const files = imageFor[family];
      // The whole chip is erased first: about 15 s for 4 MB, longer for an S3's 16 MB
      const eraseWords = family === "ESP32-S3" ? "about a minute" : "about 15 seconds";
      setProgress("Erasing the device (" + eraseWords + ")...", 0, "Installing " + installName() + ": Erasing the Device...", true);
      showBootNow(false); // in download mode now: BOOT can be let go
      let lastPercent = -1;
      const started = Date.now();
      const timeLeft = makeTimeLeft();
      // Erasing starts now: from here an unfinished install leaves the board needing Recover/Install
      flashNoteSet({ mac: board.mac || "", version: pickedStart ? pickedStart[1] : "", startedAt: Date.now(), writing: true });
      try {
        await link.loader.writeFlash({
          fileArray: files,
          flashSize: "keep",
          flashMode: "keep",
          flashFreq: "keep",
          eraseAll: true,
          // Fix (verify): esptool-js checks each region after writing (the stub's flash MD5 against this one) and
          //  throws "MD5 of file does not match data in flash!" otherwise. Without it a corrupted write (line noise
          //  on Gene's Linux CP2102) was reported as installed and the board boot-looped
          calculateMD5Hash: (image) => md5Binary(image),
          compress: true,
          reportProgress: (index, written, total) => {
            const percent = Math.floor((written / total) * 100);
            if (percent === 100 && lastPercent !== 100) {
              lastPercent = 100;
              setProgress("Checking the written image...", 100, "Installing " + installName() + " (100%): Checking the Written Image...");
              appendConsole("[esptool] Written 100%\n[Checking the written image (MD5)...]\n");
              return;
            }
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
        const raw = err && err.message ? err.message : String(err);
        const mismatch = /MD5 of file does not match/i.test(raw);
        if (attempt >= WRITE_ATTEMPTS) {
          appendConsole("[Write " + attempt + " of " + WRITE_ATTEMPTS + " failed (" + raw + "). Giving up.]\n");
          const plain = new Error(writeFailureText(err));
          plain.plain = true;
          throw plain;
        }
        appendConsole(mismatch
          ? "[The written image did not match (MD5 check). Writing it again (" + (attempt + 1) + " of " + WRITE_ATTEMPTS + ").]\n"
          : "[Write failed (" + raw + "). Connecting again and writing it again (" + (attempt + 1) + " of " + WRITE_ATTEMPTS + ").]\n");
        await resetLink(link).catch((again) => { if (again && again.code === "stuck") throw again; });
        continue;
      }
      appendConsole("[Written in " + Math.round((Date.now() - started) / 1000) + " s, compressed; verified (MD5 matches)]\n");
      installEnding = nativeUsb(port);
      // Fix (S3 web flash, Flasher Version 105): on the S3's USB-JTAG/serial port the page's RTS restart is only a
      //  core reset, which keeps the board in download mode (BOOT is read again only by a system reset). A watchdog
      //  reset through the stub is one (as esptool's own Python does it); the board then starts GSP32
      flashedPort = installPort;
      if (family === "ESP32-S3" && nativeUsb(port) && usbPid(port) === USB_JTAG_SERIAL_PID) {
        usbExpect = { resume: "installed", until: Date.now() + 30000 };  // its port goes with the reset
        watchdogDone = await watchdogReset(link.loader);
      }
      if (watchdogDone) await withTimeout(link.transport.disconnect(), 1000, "Closing the connection").catch(() => {});
      else await link.transport.disconnect();
      stopLink(link);
      break;
    }
    await reopenPort(FLASH_BAUD);
    setProgress("Restarting the device...", 100, "Installing " + installName() + " (100%): Restarting the Device...");
    // Detect again from the new boot: the buttons follow what the fresh firmware prints
    board.kind = "unknown";
    board.noBootable = false;
    board.ip = "";
    board.readyAt = 0;
    const picked = versionSelect.textContent.match(/Version (\d+(?:\.\d+)?)/);
    board.version = picked ? picked[1] : "";
    board.installed = true;
    flashNoteSet(null);
    bootTimes = [];
    appendConsole("[Installed. Restarting the device.]\n");
    // Fix (S3 native USB): the restart starts GSP32 on its own USB port; the old one goes (see usbLossResume)
    const native = nativeUsb(port);
    if (native) usbExpect = { resume: "installed", until: Date.now() + 30000 };
    board.downloadMode = false;
    board.note = "";
    // Completed-install counter: count only (no MAC/IP), fire-and-forget, never delays anything
    try {
      fetch("https://gsp32-telemetry.genereese.workers.dev/install", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", mode: "cors", keepalive: true }).catch(() => {});
    } catch (err) {}
    if (!watchdogDone) {
      try {
        await resetBoard();
      } catch (err) {
        if (!native) throw err;
      }
    }
    setStatus(installName() + " Installed", "ok");
    // Version 75 (Gene): what to do next, so a newcomer knows the Set Up Wi-Fi button is the way to the Web UI.
    //  Fix (S3 web flash, Flasher Version 105): only once GSP32 has started (its boot lines, or its new USB port
    //  picked): a board left in download mode showed it while Set Up Wi-Fi could not work
    // Flasher Version 107: native USB only; on any other port the line comes at once, as in 104
    if (native) nextStepPending = true;
    else {
      const next = document.createElement("span");
      next.className = "status-more next-step";
      nextStepText(next);
      boardStatus.append(" ", next);
    }
    // Fix (S3 web flash, Flasher Version 105): a USB-JTAG board still answering the ROM's SYNC after the restart did
    //  not leave download mode: the guide says to tap RST (the new port then goes on as after any restart)
    if (flashedPort === port && nativeUsb(port) && usbPid(port) === USB_JTAG_SERIAL_PID && !gspFound()) {
      await delay(LEFT_DOWNLOAD_MS);
      if (port === flashedPort && portOpen() && !usbGuide && !gspFound() && await answersSync(port, 400, true, LOOK_FIRST_MS)) {
        appendConsole(STILL_DOWNLOAD_TEXT);
        clearNativeHandoff();
        showUsbGuide("rst", "installed");
      }
    }
    startReading();
    setBusy(false);
    stopFlashGuard();
    closeWizard();
    showActions(true);
    syncActions();
    // Flasher Version 110: GSP32 not seen quickly (and not already in the Tap RST guide) forces the guide
    if (nextStepPending && !gspFound() && !(usbGuide && usbGuide.resume === "installed")) armNativeHandoff();
  } catch (err) {
    await reopenPort(FLASH_BAUD).catch(() => {});
    await setRunState().catch(() => {});
    startReading();
    setBusy(false);
    stopFlashGuard();
    // Fix (write retries): the plain text alone; the raw esptool text is in the console
    if (err && err.plain) appendConsole("[The install did not finish: " + err.message + "]\n");
    showError(err && err.plain ? "The install did not finish. " + err.message : "The install did not finish: " + (err && err.message ? err.message : err), "prep");
    if (err && err.bootHint) showBootHint(true);
    showActions(true);
  } finally {
    installEnding = false;
    installConnecting = false;
    // Flasher Version 115.10 (Gene): however the install ended, the port comes back to the page: its reader runs
    //  again (esptool let go of it) and the console box takes typing (gsp.wifi(...)) once nothing else works
    handBackPort();
  }
  syncConsoleButtons();
}
// After an install (done, failed or stopped): the page reads the port again and the console box is unlocked
function handBackPort() {
  if (portOpen() && !reading && !usbGuide) startReading();
  syncConsoleButtons();
}

// Fix (S3 web flash, Flasher Version 105): the line under "... Installed" once GSP32 runs (see install). It slides and
//  fades in. Only while the status still says Installed (not over a later step's status)
let nextStepPending = false;
function nextStepText(next) {
  next.append("Next: click ", Object.assign(document.createElement("b"), { textContent: "Set Up Wi-Fi" }),
    " above to connect the device to your Wi-Fi network. Then you can open the GSP32 Web UI from any browser on that network.");
}
function showNextStep() {
  nextStepPending = false;
  if (boardStatus.querySelector(".next-step") || !/ Installed$/.test(boardStatus.textContent.trim())) return;
  const next = document.createElement("span");
  next.className = "status-more next-step";
  nextStepText(next);
  boardStatus.append(" ", next);
  try {
    next.animate([{ opacity: 0, transform: "translateY(-4px)" }, { opacity: 1, transform: "none" }], { duration: FOLD_MS, easing: "ease-out" });
  } catch (err) {
    // No animation
  }
}
// Fix (S3 web flash, Flasher Version 105): esptool's watchdog_reset for the ESP32-S3 (esptool-js 0.5.7's own S3
//  watchdog addresses are 4 bytes off, so they are not used). FORCE_DOWNLOAD_BOOT is cleared first (set when the
//  board was sent into download mode by software), then the RTC watchdog fires a system reset in a few ms, which reads
//  the BOOT pin again. Each write is time-limited; false when the stub did not take them (the page's restart then)
const S3_RTC_OPTION1 = 0x6000812c, S3_FORCE_DOWNLOAD_BOOT = 0x1;
const S3_WDTWPROTECT = 0x600080b0, S3_WDT_WKEY = 0x50d83aa1, S3_WDTCONFIG0 = 0x60008098, S3_WDTCONFIG1 = 0x6000809c;
const LEFT_DOWNLOAD_MS = 1500;
// Flasher Version 114.2: how long the post-install check reads the board's output before it asks the ROM
const LOOK_FIRST_MS = 300;
const S3_SWD_CONF = 0x600080b4, S3_SWD_WPROTECT = 0x600080b8, S3_SWD_WKEY = 0x8f1d312a, S3_SWD_AUTO_FEED = 1 << 31;
// esptool's disable_watchdogs for the S3 (USB-JTAG/serial only). Best effort: each step time-limited, a failure only
//  noted in the console
async function disableS3Watchdogs(loader) {
  const limit = (p) => withTimeout(p, 1500, "Turning off the watchdogs");
  try {
    await limit(loader.writeReg(S3_WDTWPROTECT, S3_WDT_WKEY));
    await limit(loader.writeReg(S3_WDTCONFIG0, 0));
    await limit(loader.writeReg(S3_WDTWPROTECT, 0));
    const conf = await limit(loader.readReg(S3_SWD_CONF));
    await limit(loader.writeReg(S3_SWD_WPROTECT, S3_SWD_WKEY));
    await limit(loader.writeReg(S3_SWD_CONF, (conf | S3_SWD_AUTO_FEED) >>> 0));
    await limit(loader.writeReg(S3_SWD_WPROTECT, 0));
  } catch (err) {
    appendConsole("[Could not turn off the device's watchdogs (" + (err && err.message ? err.message : err) + ")]\n");
  }
}
const STILL_DOWNLOAD_TEXT = "[The device is still in download mode. Tap RST (not BOOT) to start GSP32, then pick the new port.]\n";
const NATIVE_HANDOFF_MS = 6000;
const NATIVE_MISSED_TEXT = "[GSP32 was not seen on this port. Tap RST (not BOOT) to start it, then pick the new port.]\n";
const NATIVE_MISSED_GUIDE = "GSP32 is installed, but this page has not seen it yet. Tap RST (not BOOT), then pick the new port.";
// True only in the gap after a verified native-USB install, before GSP32 is seen. Classic installs never enter it
function nativeInstallHandoff() {
  return !!(nativeUsb(port) && board.installed && nextStepPending && !gspFound() && board.kind !== "broken");
}
function clearNativeHandoff() {
  clearTimeout(nativeHandoffTimer);
  nativeHandoffTimer = null;
}
function armNativeHandoff() {
  clearNativeHandoff();
  if (!nativeInstallHandoff()) return;
  nativeHandoffTimer = setTimeout(() => {
    nativeHandoffTimer = null;
    finishNativeHandoff();
  }, NATIVE_HANDOFF_MS);
}
// Checking is over. Still in download mode, or GSP32 never showed: Tap RST, or pick the new port, then Next / Wi-Fi
function finishNativeHandoff() {
  if (gspFound() || board.kind === "broken") return;
  if (!board.installed || !nextStepPending) return;
  if (busy || flashing) {
    armNativeHandoff();
    return;
  }
  clearTimeout(otherTimer);
  if (bootingNote !== null || checkWaitTimer) endBooting();
  if (usbGuide && usbGuide.resume === "installed") return;
  if (port && !nativeUsb(port)) return;
  const open = portOpen();
  const jtag = open && usbPid(port) === USB_JTAG_SERIAL_PID;
  if (jtag) appendConsole(STILL_DOWNLOAD_TEXT);
  else if (open) appendConsole(NATIVE_MISSED_TEXT);
  showUsbGuide(open ? "rst" : "repick", "installed", open && !jtag ? NATIVE_MISSED_GUIDE : "");
}
// Flasher Version 110: Cancel on Checking for GSP32 (native USB). Post-install, that is the Tap RST / pick-port guide
function cancelNativeCheck() {
  if (!nativeUsb(port)) return;
  if (board.installed && nextStepPending && !gspFound() && board.kind !== "broken") {
    clearNativeHandoff();
    finishNativeHandoff();
    syncConsoleButtons();
    return;
  }
  clearTimeout(otherTimer);
  clearNativeHandoff();
  if (!gspFound() && board.kind !== "broken" && board.readyAt < board.bootAt) {
    board.kind = "other";
    if (flashNoteGet() && !busy && !flashing) flashNoteSet(null);
    dropIncomplete();
  }
  endBooting();
  syncBoardUi();
  syncConsoleButtons();
}
async function watchdogReset(loader) {
  const reg = (addr, value, mask) => withTimeout(loader.writeReg(addr, value, mask), 1500, "Restarting the device");
  try {
    await reg(S3_RTC_OPTION1, 0, S3_FORCE_DOWNLOAD_BOOT).catch(() => {});
    await reg(S3_WDTWPROTECT, S3_WDT_WKEY);
    await reg(S3_WDTCONFIG1, 2000);
    await reg(S3_WDTCONFIG0, (1 << 31) | (5 << 28) | (1 << 8) | 2);
    // The reset may come before this answer
    await reg(S3_WDTWPROTECT, 0).catch(() => {});
    appendConsole("[Restarting the device (watchdog reset: leaves download mode)]\n");
    return true;
  } catch (err) {
    appendConsole("[The watchdog reset did not answer (" + (err && err.message ? err.message : err) + "). Restarting the usual way.]\n");
    return false;
  }
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
      if (board.listening || board.kind === "other" || old || (usbGuide && !portOpen()) || Date.now() - since > timeoutMs) {
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
  if (!networks.length) {
    // Flasher Version 115.10: one row with a box for the name (its radio takes the typed name as its value)
    const item = document.createElement("li");
    const label = document.createElement("label");
    label.className = "net-typed";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "network";
    radio.value = "";
    radio.checked = true;
    radio.dataset.open = "";
    const typed = document.createElement("input");
    typed.type = "text";
    typed.id = "wifi-name";
    typed.maxLength = 32;
    typed.placeholder = "Network name (SSID)";
    typed.autocomplete = "off";
    typed.spellcheck = false;
    typed.setAttribute("aria-label", "Network name");
    typed.addEventListener("input", () => {
      radio.value = typed.value.trim();
      radio.checked = true;
      syncWifiConnect();
    });
    typed.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && radio.value && !busy) {
        event.preventDefault();
        openWifiModal();
      }
    });
    label.append(radio, typed);
    item.append(label);
    wifiList.append(item);
  }
}

function syncWifiConnect() {
  const picked = wifiList.querySelector("input:checked");
  wifiConnect.disabled = busy || !picked || !picked.value;
  // Fix (recover flow): greyed Connect says why (the wait bar shows while busy)
  const note = $("wifi-note");
  if (note) {
    note.textContent = busy || !wifiList.children.length ? ""
      : !picked ? "Pick your network above." : !picked.value ? "Type your network name above." : "";
    note.hidden = !note.textContent;
  }
  wifiModalConnect.disabled = busy;
  wifiModalCancel.disabled = busy;
  wifiPassword.disabled = busy;
  wifiShow.disabled = busy;
}

async function startWifi(fresh) {
  // Fix (S3 native USB): Wi-Fi setup needs GSP32 running, not download mode: the BOOT and RST guide goes
  if (usbGuide && usbGuide.kind === "boot") hideUsbGuide();
  showStep("wifi");
  setTimeout(() => wizard.scrollIntoView({ behavior: motionOk() ? "smooth" : "auto", block: "nearest" }), motionOk() ? FOLD_MS : 0);
  setFolded(wifiError, false);
  setShown(wifiRescan, false);
  showWifiFallback(false);
  wifiPassword.value = "";
  wifiList.replaceChildren();
  setFolded(wifiWait, true);
  setBusy(true);
  wifiStatus.textContent = "Starting Wi-Fi setup...";
  syncWifiConnect();
  try {
    if (!portOpen()) await pickPort();
    wifiStatus.textContent = "Waiting for the device to start...";
    // Never Ctrl-C, never typed at the prompt: Improv goes out only while GSP32 says it listens (see writeImprov).
    //  A board on Wi-Fi listens for 30 s after a boot, so one that is not listening is restarted first
    if (!board.listening) {
      if (!fresh) {
        // Fix (S3 native USB): the page's restart may do nothing on a native USB board (then RST does it), and a
        //  restart may move it to a new port (the guide asks for it)
        const native = nativeUsb(port);
        wifiStatus.textContent = native ? "Restarting the device so GSP32 listens for Wi-Fi setup... If nothing happens, tap RST on the device."
          : "Restarting the device so GSP32 listens for Wi-Fi setup...";
        if (native) usbExpect = { resume: "wifi", until: Date.now() + 45000 };
        try {
          await resetBoard();
        } catch (err) {
          if (!native) throw err;
        }
      }
      await waitListening(45000);
      if (!portOpen() && usbGuide) throw new Error("The device restarted on a new USB port. Pick it again (see the note above).");
    }
    // Flasher 115.26 (GSP32-C V132 (a), Gene's ESP32): no Ctrl-C before Wi-Fi setup any more (115.10-115.25 sent it to
    //  stop main.py). GSP32-C's console takes Improv packets while main.py runs, so this is classic GSP32's rule again.
    //  At the >>> prompt the board's REPL echoed each packet's "IMPROV" (and rubbed it out), and that echo held the
    //  answers back here, so the first scan after a fresh install came back empty (see takeSerialBytes)
    let state = board.listening ? await waitBoardReady(8000) : null;
    // Flasher Version 114.2 (Gene's C3): GSP32 that does not answer (its REPL had the port, or the listening ended) is
    //  restarted once and asked again, instead of the user having to click Try Again
    if (state === null && (board.kind === "gsp32" || gspcImprov()) && !board.oldFirmware && portOpen()) {
      const native = nativeUsb(port);
      wifiStatus.textContent = native ? "The device did not answer. Restarting it and trying once more... If nothing happens, tap RST on the device."
        : "The device did not answer. Restarting it and trying once more...";
      board.listening = false;
      if (native) usbExpect = { resume: "wifi", until: Date.now() + 45000 };
      try {
        await resetBoard();
      } catch (err) {
        if (!native) throw err;
      }
      await waitListening(45000);
      if (!portOpen() && usbGuide) throw new Error("The device restarted on a new USB port. Pick it again (see the note above).");
      state = board.listening ? await waitBoardReady(8000) : null;
    }
    // Flasher Version 115.16 (V127.3): what to do next, not only what went wrong
    if (state === null && gspcImprov()) throw Object.assign(new Error("The device did not answer Wi-Fi setup, even after a restart. Tap RST on the device, wait a few seconds and click Try Again, or set Wi-Fi in the console as shown below."), { fallback: true });
    if (state === null && board.oldFirmware) throw new Error("This device runs an older GSP32. Install Version 43.1 or newer to change Wi-Fi here.");
    if (state === null && board.kind === "other") throw new Error("This device does not run GSP32. Install GSP32 first to set up Wi-Fi.");
    if (state === null) throw new Error("The device did not answer. Check that GSP32 is installed, then try again.");
    await scanForWifi();
    keepSession(true);
  } catch (err) {
    setFolded(wifiWait, false);
    setBusy(false);
    wifiStatus.textContent = err && err.message ? err.message : String(err);
    setShown(wifiRescan, true);
    wifiRescan.textContent = "Try Again";
    // Flasher Version 115.10: GSP32-C takes its Wi-Fi at the console too: the way is shown with the error
    if ((err && err.fallback) || board.kind === "gspc") showWifiFallback(true);
  }
  syncWifiConnect();
}

// Flasher Version 115.10 (Gene's ESP32): the console way to set Wi-Fi, under the Wi-Fi step when the list is empty or
//  the board did not answer. GSP32-C: gsp.wifi(...) at its prompt (Send Ctrl-C first stops main.py)
function showWifiFallback(on) {
  const box = $("wifi-fallback");
  if (!box) return;
  if (on) {
    const code = (text) => Object.assign(document.createElement("code"), { textContent: text });
    if (board.kind === "gspc") {
      box.replaceChildren("Or set it in the console below: click ", Object.assign(document.createElement("b"), { textContent: "Send Ctrl-C" }),
        " (stops main.py), then type ", code("import gsp; gsp.wifi('name', 'password')"), " and press Enter.");
    } else {
      box.replaceChildren("Or set it in the console below: type ", code("wifi()"), " and press Enter.");
    }
  }
  setFolded(box, on);
}

async function scanForWifi() {
  // Version 43.1: a board that stopped listening is restarted (startWifi) instead of reporting "No networks found"
  if (!board.listening) return startWifi(false);
  setBusy(true);
  setFolded(wifiWait, true);
  setShown(wifiRescan, false);
  showWifiFallback(false);
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
  // Flasher Version 115.10 (Gene's ESP32): an empty list is no dead end: the name can be typed (GSP32-C V125 and
  //  older answer the scan with an empty list until a network is set: their Wi-Fi radio is off until then)
  const empty = board.kind === "gspc"
    ? "No networks found (GSP32-C lists networks once Wi-Fi was set). Type your network name, then click Connect."
    : "No networks found. Type your network name, or move the device closer to the router and click Scan Again.";
  wifiStatus.textContent = networks.length ? "Pick your network, then click Connect." : empty;
  if (!networks.length) showWifiFallback(true);
  syncWifiConnect();
  if (!networks.length) {
    const typed = $("wifi-name");
    if (typed) typed.focus();
  }
}

async function connectWifi() {
  const picked = wifiList.querySelector("input:checked");
  if (!picked || !picked.value || busy) return;
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
      // Flasher Version 115.16 (V127.3): says why and what Scan Again does
      ? "The device stopped listening for Wi-Fi setup (it listens only for a short time after it starts). Click Scan Again: the flasher restarts it so it listens again, then pick your network and connect."
      : err.code === 3
      ? "Could not connect: the password may be wrong. Check it and try again."
      // Flasher Version 115.12: a wrong password often ends here too (no answer in time), so it is named first
      : "Could not connect. Check the password and try again. If it is right, move the device closer to the router.";
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
  if (!picked || !picked.value || busy) return;
  if (picked.dataset.open) {
    connectWifi();
    return;
  }
  $("wifi-modal-title").textContent = "Wi-Fi Password for " + picked.value;
  wifiPassword.value = "";
  setShowPassword(false);
  setFolded(wifiError, false);
  modalWait("");
  wifiModal.showModal();
  wifiPassword.focus();
}

// Step 5: the board joined Wi-Fi on its own (the Improv result carries its address): no reset; the card shows it
function finishWifi(url) {
  setBusy(false);
  // Flasher Version 115.12 (Gene's ESP32, real-board check): the wait ends with the answer. Its "wifi" reason stayed
  //  in statusWaits, so after Wi-Fi Connected! the console said "Busy ..." and took no typing or Ctrl-C
  setFolded(wifiWait, false);
  const ip = url ? new URL(url).hostname : "";
  if (!ip) {
    showError("The device did not report its address. The console below shows what it printed.", "prep");
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
  ready.append("Your device is ready. Open ", link, " in a browser on the same network to use GSP32, or click Open Web UI.");
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
  return () => fn().catch((err) => {
    appendConsole("\n[" + (err && err.message ? err.message : "Something went wrong") + "]\n");
    if (!portOpen()) { syncConsoleButtons(); showStartAgain(); }
  });
}

async function copyLog() {
  paintConsoleNow();
  const text = consoleText(true);
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
  if (busy || (board.compatIssue && !board.compatIssue.betaOnly)) return;
  eraseOk.checked = false;
  syncStart();
  showStep("prep");
});
eraseOk.addEventListener("change", syncStart);
startInstall.addEventListener("click", () => install());
$("copy-log").addEventListener("click", copyLog);
// Flasher Version 115.17: the device installs without BOOT now: stop showing the tip for it
$("boot-forget").addEventListener("click", () => {
  forgetHoldBoot(port, board.mac);
  appendConsole("[The hold-BOOT reminder for this device was cleared]\n");
  setFolded($("boot-remembered"), false);
});
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
  showStartError("");
  try {
    await pickPort();
  } catch (err) {
    // Cancelled picker: probably no board in the list, so the checklist opens
    if (err.code === "cancel") {
      showBoardHelp(true);
      return;
    }
    // Fix (recover flow): the port would not open: one clear line by Get Started, which stays usable
    showStartError(err && err.message ? err.message : "Could not open the port.");
    appendConsole("\n[" + (err && err.message ? err.message : "Could not open the port") + "]\n");
    showStartAgain();
    return;
  }
  showBoardHelp(false);
  // Fix (S3 native USB): a native USB port picked while the BOOT and RST guide shows is read as the guide's would be
  const guided = !!usbGuide && usbGuide.kind === "boot" && nativeUsb(port);
  hideUsbGuide();
  usbExpect = null;
  Object.assign(board, { leftRunning: false, noBootable: false, installed: false, kind: "unknown", ip: "", name: "", chip: "", mac: "", version: "", readyAt: 0, info: {}, telemetrySent: false, compatIssue: null, downloadMode: false, note: "" });
  // USB bridge is known from the open port (no guess); keep it after the board-state reset
  const bridge = usbBridgeInfo();
  if (bridge) { board.info.usb = bridge.name; board.info.usbLabel = bridge.label; }
  board.telemetrySent = false;
  hideCompatNotice();
  bootTimes = [];
  syncBoardUi();
  showConsole();
  // Fix (recover flow): no Incomplete Install yet; the probe shows it once it read this board's MAC
  // Version 80: probe chip/flash now so stats and an incompatible notice appear before Install
  // Flasher Version 115.10 (Gene's ESP32): not on a classic port: the probe's resets restarted a running board on every
  //  connect (and dropped its Wi-Fi). Install reads the board (chip, flash, compatibility) when it starts
  //  The one exception: an unfinished install is on record (Recover): that board is not running a healthy GSP32, and
  //  only the probe's MAC says whether it is the same board
  //  (window.__gsp32ProbeOnConnect: the page tests of the probe itself, which still runs for those cases, turn it on)
  if (!nativeUsb(port) && !flashNoteGet() && !window.__gsp32ProbeOnConnect) {
    board.leftRunning = true;
    appendConsole(PLAIN_CONNECT_TEXT);
    syncBoardUi();
    syncConsoleButtons();
    return;
  }
  await probeBoardOnConnect({ guided, resume: "probe" });
}));
const PLAIN_CONNECT_TEXT = "\n[Connected. The device keeps running (no restart); its chip and flash are read when you click Install.]\n";
function showStartError(text) {
  const line = $("start-error");
  if (!line) return;
  line.textContent = text;
  line.hidden = !text;
}
function showBoardHelp(open) {
  const help = $("board-help"), link = $("no-board");
  if (open === !help.hidden) return;
  link.setAttribute("aria-expanded", String(open));
  if (open) foldOpen(help);
  else foldShut(help);
}
$("no-board").addEventListener("click", () => showBoardHelp($("board-help").hidden));
// Version 101: the board row's Disconnect does the same as the console's: the reader stops, the board is left
//  running (EN and GPIO 0 high), the port closes, and the page goes back to Get Started
async function disconnectBoard() {
  hideUsbGuide();
  usbExpect = null;
  board.downloadMode = false;
  board.note = "";
  // Flasher Version 115.10 (Gene's ESP32): the board keeps running (and on Wi-Fi) after Disconnect: the run state is
  //  set one line at a time before the close (see idleLines); closePort's own call then changes nothing
  if (portOpen() && !nativeUsb(port)) await idleLines().catch(() => {});
  await closePort();
  hideConsole();
}
disconnectBtn.addEventListener("click", guard(disconnectBoard));
$("board-disconnect").addEventListener("click", guard(async () => {
  if (busy) return;
  await disconnectBoard();
}));
resetBtn.addEventListener("click", guard(resetBoard));
ctrlCBtn.addEventListener("click", guard(() => writeBytes(new Uint8Array([0x03]))));
$("wifi-setup").addEventListener("click", () => {
  // Flasher Version 115.10 (Gene): never a click that does nothing: busy says why in the console
  if (busy) {
    appendConsole("\n[Set Up Wi-Fi waits: the flasher is still busy. Click it again once it finishes.]\n");
    return;
  }
  startWifi(false);
});
// Fix (S3 native USB): the guide's buttons (Pick the Port Again opens the picker, so it needs this click)
$("usb-guide-pick").addEventListener("click", guard(pickUsbAgain));
$("check-wait-cancel").addEventListener("click", () => cancelNativeCheck());
$("usb-guide-wifi").addEventListener("click", () => {
  if (busy || usbAttaching) return;
  hideUsbGuide();
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
    if (event.target !== port) return;
    // Fix (S3 native USB): a native USB board that moved to a new port while the page reset it gets the guide
    const resume = usbLossResume(port);
    if (resume) usbLost(port, resume);
    else portLost(port, DISCONNECT_TEXT);
  });
  // Fix (S3 native USB): while the guide shows, an Espressif USB port this page may already use that comes back (the
  //  board restarted, or BOOT and RST put it in download mode) is taken at once, without the picker
  navigator.serial.addEventListener("connect", (event) => {
    const arrived = event.target;
    if (!usbGuide || usbAttaching || !nativeUsb(arrived) || (arrived === port && portOpen())) return;
    attachUsbPort(arrived).catch(() => {});
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
  // Flasher Version 115.11: RTS off now (the step that matters), DTR off once that is done, if the page is still there.
  //  If it is not, the port closes with only DTR on, and dropping DTR alone never pulls EN low
  if (!port) return;
  const p = port;
  p.setSignals({ requestToSend: false }).then(() => p.setSignals({ dataTerminalReady: false })).catch(() => {});
});

loadVersions();
// Hourly visit counter: one fire-and-forget POST per page load (stores only UTC hour + path). Never blocks the page.
try {
  fetch("https://gsp32-telemetry.genereese.workers.dev/visit", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: location.pathname }), mode: "cors", keepalive: true,
  }).catch(() => {});
} catch (err) {}
syncConsoleButtons();

// For the page tests (Playwright): the slide helper and the console writer
window.gsp32 = { setShown, appendConsole };
