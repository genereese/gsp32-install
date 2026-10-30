// Version 46 (Gene): What You Get: thumbnails of the GSP32 web UI (shots/, made by release_shots.py from the dev board).
//  A click opens the full-size picture with a short tour. Nothing here touches the installer
// Version 106 (Gene): the tour follows the current web UI: the Experiment menu (Sandbox, Examples), Split in the editor
// Flasher Version 104 (Gene): the AI Helper first (from the web UI's own feature list: tutorial.js, AI-HELPER.md), no Settings
// Flasher 115.29 (Gene): the tour follows GSP32-C V135 (fresh shots from the dev boards: tools/flashershots135.py in gsp32-c/v135):
//  the Sandbox screen (Code | HTML, Split View, Page View), the editable menu (/pages/menu.html), the stats bar's Main/Sandbox
//  switch, Settings (Attached Display and Window Manager, Bluetooth on the S3) in place of Libraries (the Package Manager is off)
var TOUR = {
  ai: ["An AI Helper That Writes Code", "Writes and edits your code and pages, then shows each change to Apply or Discard. Fix This on an error opens it with the error and its line.",
    ["Works on the file you're viewing, including both Sandbox files", "Bring your own key: it stays in your browser, never on the device",
     "Grok, OpenAI, Claude or Gemini, plus custom models", "AI History rolls a change back"]],
  home: ["Your Device at a Glance", "Open the device's address in any browser and the start page greets you with live graphs. The stats bar on every page shows what's running, and its Main / Sandbox switch stops or runs main.py and the Sandbox with one click. The start page is a file (/pages/index.html), and so is the menu (/pages/menu.html), so both can be your own.",
    ["Live graphs, with hover readouts and zoom", "Main / Sandbox switch: green is running, a click stops it (red), a click runs it again", "An editable menu bar: Home, Files, Experiment and Apps"]],
  files: ["Files Without Cables", "Manage everything on the device from the browser: upload by dragging files in, move them by dragging, rename, download and delete. No USB cable, no extra tools.",
    ["Drag and drop upload and moving", "Box selection and bulk Download or Delete", "An image viewer, a microSD card area, and Restore Factory Version for the starter files"]],
  editor: ["Edit Code Right on the Device", "A real code editor built into the firmware, so it works with no internet. Save & Restart runs your change at once, and Split puts the live page next to the code, reloading it after each save.",
    ["Split for any file, with a draggable divider", "Save & Restart (Ctrl+S) or just Save (Ctrl+Shift+S); errors shown on their line", "Find and Replace, Go to Line, comment toggle (Ctrl+/), folding, Revert", "Insert: pins, PWM, analog inputs, components and paired devices"]],
  sandbox: ["Try Things in the Sandbox", "Experiment > Sandbox is a page and a program of their own, on one screen: Code and HTML for sandbox.py and sandbox.html, Split View for the code beside the live page, Page View for the page alone. Save & Run runs sandbox.py in place of main.py and reloads the page.",
    ["Code | HTML, Split View and Page View in one bar", "Save & Run without touching main.py; the switch takes you back to main.py", "Clear Sandbox makes both blank again; Ctrl+Shift+M opens sandbox.py"]],
  examples: ["Examples to Copy From", "Experiment > Examples shows the onboard LED buttons, sliders, a live log and every kind of graph, all driven by main.py. Each one is a single tag you can copy into your own pages, and the Pages API reference lists them all.",
    ["Line, history, radial, bar, pie and donut graphs", "LED buttons, sliders and a live log", "One-line comments on every example"]],
  pins: ["See and Drive Every Pin", "The Pin Panel shows every GPIO as a card: its level, whether it's safe to use, and what main.py calls it. Drive a pin high or low with a click to test your wiring.",
    ["Live levels and ADC readings", "Safe, careful and taken pins color-coded", "Pins named after your main.py"]],
  console: ["A Console in Your Browser", "Watch print() output and errors from main.py as they happen, and type Python straight into the device. It's the serial console, without the serial cable.",
    ["Live output from main.py", "Run Python lines, or a saved file, on the device", "The last error kept across reboots"]],
  settings: ["Settings for Your Device", "Tabs for the password and what needs a login, the device name, CPU speed and time zone, the network, the web API and your AI keys. On an ESP32-S3, Attached Display picks a screen for the Window Manager (wm), and Bluetooth lets your programs use BLE.",
    ["Attached Display and the Window Manager (ESP32-S3)", "Bluetooth Low Energy (ESP32-S3 with PSRAM)", "Paired Devices, the web API with keys, each AI provider's status"]],
  backup: ["Back Up and Restore", "Apps > Backup downloads your whole device as one file, and puts it back on this device or a new one. It's also the way to keep your files across a clean install, and the way over from the old GSP32."]
};

(function () {
  var list = document.getElementById("tour-list");
  var modal = document.getElementById("tour-modal");
  if (!list || !modal) return;
  var slides = [], current = 0;
  fetch("shots/index.json", {cache: "no-cache"}).then(function (response) { return response.json(); }).then(function (shots) {
    shots.forEach(function (shot) {
      var text = TOUR[shot.key];
      if (!text) return;
      var item = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "tour-thumb";
      button.innerHTML = '<img loading="lazy" alt=""><span></span>';
      button.firstChild.src = "shots/" + shot.key + ".jpg";
      button.lastChild.textContent = shot.title;
      button.setAttribute("aria-label", "Open " + shot.title);
      var index = slides.length;
      slides.push([shot, text]);
      button.onclick = function () { show(index); modal.showModal(); };
      item.appendChild(button);
      list.appendChild(item);
    });
  }).catch(function () { document.getElementById("tour").hidden = true; });

  // Version 48 (Gene): a slideshow: previous / next, arrow keys and a swipe
  function show(index) {
    current = (index + slides.length) % slides.length;
    var image = document.getElementById("tour-img");
    image.classList.remove("tour-in");
    void image.offsetWidth;
    image.classList.add("tour-in");
    fill(slides[current][0], slides[current][1]);
    document.getElementById("tour-count").textContent = (current + 1) + " of " + slides.length;
  }
  document.getElementById("tour-prev").onclick = function () { show(current - 1); };
  document.getElementById("tour-next").onclick = function () { show(current + 1); };
  modal.addEventListener("keydown", function (event) {
    if (event.key === "ArrowLeft") { event.preventDefault(); show(current - 1); }
    if (event.key === "ArrowRight") { event.preventDefault(); show(current + 1); }
  });
  var touchX = null;
  modal.addEventListener("touchstart", function (event) { touchX = event.touches[0].clientX; }, {passive: true});
  modal.addEventListener("touchend", function (event) {
    if (touchX === null) return;
    var dx = event.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) > 50) show(current + (dx < 0 ? 1 : -1));
  });

  function fill(shot, text) {
    document.getElementById("tour-modal-title").textContent = shot.title + ": " + text[0];
    var image = document.getElementById("tour-img");
    image.src = "shots/" + shot.key + ".jpg";
    image.alt = "The GSP32 " + shot.title;
    document.getElementById("tour-blurb").textContent = text[1];
    var points = document.getElementById("tour-points");
    points.textContent = "";
    (text[2] || []).forEach(function (point) {
      var li = document.createElement("li");
      li.textContent = point;
      points.appendChild(li);
    });
    points.hidden = !text[2];
  }
  document.getElementById("tour-close").onclick = function () { modal.close(); };
  modal.addEventListener("click", function (event) { if (event.target === modal) modal.close(); });
})();
