// Version 46 (Gene): What You Get: thumbnails of the GSP32 web UI (shots/, made by release_shots.py from the dev board).
//  A click opens the full-size picture with a short tour. Nothing here touches the installer
// Version 106 (Gene): the tour follows the current web UI: the Experiment menu (Sandbox, Examples), Split in the editor
var TOUR = {
  home: ["Your Board at a Glance", "Open the board's address in any browser and the start page greets you with live graphs of what matters: how busy the web UI is, memory, flash and Wi-Fi signal. Getting Started links the Tutorial, your program, your files and the Experiment pages. It's your own page too, so make it a dashboard for your project.",
    ["Live graphs for Web UI Load, RAM, Flash and Wi-Fi", "Getting Started, with the Sandbox and Examples one click away", "The menu: Home, Files, Experiment and Apps, plus the AI Helper on every page"]],
  files: ["Files Without Cables", "Manage everything on the board from the browser: upload by dragging files in, move them by dragging, rename, download and delete. No USB cable, no extra tools.",
    ["Drag and drop upload and moving", "Box selection and bulk Download or Delete", "Restore Factory Version for the starter files"]],
  editor: ["Edit Code Right on the Board", "Edit main.py or any file in a real code editor, then Save & Restart to run the change at once, without a reboot. Split puts the live page next to the code and reloads it after each save. Right-click and pick Insert for ready-made code.",
    ["Split: the live page beside the code, with a draggable divider", "Save & Restart (Ctrl-S), with errors shown on their line", "Find and Replace, Go to Line, comment toggle (Ctrl-/), folding", "Insert: pins, PWM, analog inputs, components and other boards"]],
  sandbox: ["Try Things in the Sandbox", "Experiment, Sandbox is a blank page and program of its own. Switch between View, Code and HTML, then Save & Run: sandbox.py runs while main.py pauses, and Restart brings main.py back.",
    ["A blank sandbox.py and sandbox.html (/sandbox)", "Save & Run without touching main.py", "Clear Sandbox makes both blank again; Ctrl-Shift-M opens sandbox.py"]],
  examples: ["Examples to Copy From", "Experiment, Examples shows the onboard LED buttons, the log and every kind of graph, all driven by main.py. Each one is a single tag you can copy into your own pages.",
    ["Line, history, radial, bar, pie and donut graphs", "LED buttons and a live log", "One-line comments on every example"]],
  pins: ["See and Drive Every Pin", "The Pin Panel shows every GPIO as a card: its level, whether it's safe to use, and what main.py calls it. Drive a pin high or low with a click to test your wiring.",
    ["Live levels and ADC readings", "Safe, careful and taken pins color-coded", "Pins named after your main.py"]],
  console: ["A Console in Your Browser", "Watch print() output and errors from main.py as they happen, and type Python straight into the board. It's the serial console, without the serial cable.",
    ["Live output from main.py", "Run Python lines on the board", "The last error kept across reboots"]],
  libraries: ["Add Libraries in Seconds", "Apps, Libraries searches the MicroPython package index and installs packages into /lib with one click. Your browser fetches them, so the board stays fast."],
  backup: ["Back Up and Restore", "Apps, Backup downloads your whole board as one file, and puts it back on this board or a new one whenever you need to."],
  settings: ["Make It Yours", "Wi-Fi, the device name, a password and what visitors may open, the AI Helper's provider and key, the clock and time zone, optional apps, and Reset to Factory Files.",
    ["Network card: device name and .local address, Wi-Fi, password, Discoverable", "AI Helper: your key stays in your browser, never on the board", "Clock with NTP and time zone; optional apps you can switch on and off"]]
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
