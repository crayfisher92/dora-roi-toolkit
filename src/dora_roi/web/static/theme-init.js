/* Applies the saved theme before first paint (separate file so the CSP needs no inline script). */
try {
  var th = localStorage.getItem("roi-theme");
  if (th === "light" || th === "dark") { document.documentElement.dataset.theme = th; }
} catch (e) { /* storage unavailable: follow the system setting */ }
