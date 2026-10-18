// Apply the saved theme before first paint to avoid a light flash.
// Loaded synchronously from index.html as a same-origin file because the
// production CSP (backend/security_headers.py) forbids inline scripts.
(function () {
  try {
    var t = localStorage.getItem("sb_theme") || "system";
    var dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    if (dark) {
      var el = document.documentElement;
      el.classList.add("dark");
      el.style.setProperty("--bg", "#020617");
      el.style.background = "#020617";
    }
  } catch (e) {}
})();
