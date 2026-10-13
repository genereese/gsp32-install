// Version 46 (Gene): What You Get: thumbnails of the GSP32 web UI (shots/, made by release_shots.py from the dev board).
//  A click opens the full-size picture with a short tour. Nothing here touches the installer
var TOUR = {
  home: ["Your Board at a Glance", "Open the board's address in any browser and the start page greets you with live graphs of what matters: how busy the web UI is, memory, flash and Wi-Fi signal. It's your own page too, so make it a dashboard for your project.",
    ["Live graphs for Web UI Load, RAM, Flash and Wi-Fi", "A status bar on every page with uptime and the board's IP", "Your own pages with live values from main.py"]],
  files: ["Files Without Cables", "Manage everything on the board from the browser: upload by dragging files in, move them by dragging, rename, download and delete. No USB cable, no extra tools.",
    ["Drag and drop upload and moving", "Box selection and bulk Download or Delete", "Folders tree, locks and safe system files"]],
  editor: ["Edit Code Right on the Board", "Open main.py or any file and edit it in a real code editor with line numbers, highlighting and autocomplete. Save, and your program restarts with the change.",
    ["Python highlighting and autocomplete", "Save and Run in one click", "Insert Peer Code for talking to paired boards"]],
  pins: ["See and Drive Every Pin", "The Pin Panel shows every GPIO as a card: its level, whether it's safe to use, and what main.py calls it. Drive a pin high or low with a click to test your wiring.",
    ["Live levels and ADC readings", "Safe, careful and taken pins color-coded", "Pins named after your main.py"]],
  console: ["A Console in Your Browser", "Watch print() output and errors from main.py as they happen, and type Python straight into the board. It's the serial console, without the serial cable.",
    ["Live output from main.py", "Run Python lines on the board", "The last error kept across reboots"]],
  libraries: ["Add Libraries in Seconds", "Search the MicroPython package index and install packages into /lib with one click. Your browser fetches them, so the board stays fast."],
  backup: ["Back Up and Restore", "Download your whole board as one file, and put it back on this board or a new one whenever you need to."],
  settings: ["Make It Yours", "Name the board, set a password, choose the time zone, and switch apps like Peer Manager, Scheduler and Data Logger on or off.",
    ["Password and auto logout", "Clock with NTP and time zone", "Apps you can switch on and off"]]
};

(function () {
  var list = document.getElementById("tour-list");
  var modal = document.getElementById("tour-modal");
  if (!list || !modal) return;
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
      button.onclick = function () { open(shot, text); };
      item.appendChild(button);
      list.appendChild(item);
    });
  }).catch(function () { document.getElementById("tour").hidden = true; });

  function open(shot, text) {
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
    modal.showModal();
  }
  document.getElementById("tour-close").onclick = function () { modal.close(); };
  modal.addEventListener("click", function (event) { if (event.target === modal) modal.close(); });
})();
