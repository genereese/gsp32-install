// Flasher 115.23: Stable is GSP32-C V130; the classic GSP32 flow tests pick the classic Version 114.2 ("Previous") once
//  the version list is in, the way a person would in the Release dropdown
(() => {
  const pick = () => {
    const sel = document.getElementById("release-channel");
    const opt = sel && sel.querySelector('option[value="previous"]');
    if (!opt || opt.disabled) return setTimeout(pick, 20);
    if (sel.value === "stable") { sel.value = "previous"; sel.dispatchEvent(new Event("change")); }
  };
  document.addEventListener("DOMContentLoaded", pick);
})();
