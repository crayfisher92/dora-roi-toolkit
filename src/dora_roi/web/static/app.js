/* DORA RoI Workbench – progressive enhancement. Every feature here has a no-JS fallback. */
(function () {
  "use strict";
  var live = document.getElementById("live");
  function announce(text) { if (live) { live.textContent = ""; setTimeout(function () { live.textContent = text; }, 30); } }

  /* ---------- theme switch (system / light / dark) */
  var themeBox = document.querySelector(".theme");
  if (themeBox) {
    themeBox.hidden = false;
    var current = "system";
    try { current = localStorage.getItem("roi-theme") || "system"; } catch (e) {}
    var buttons = themeBox.querySelectorAll("[data-theme-set]");
    function apply(mode) {
      if (mode === "system") { delete document.documentElement.dataset.theme; } else { document.documentElement.dataset.theme = mode; }
      buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.themeSet === mode)); });
      try { localStorage.setItem("roi-theme", mode); } catch (e) {}
    }
    buttons.forEach(function (b) { b.addEventListener("click", function () { apply(b.dataset.themeSet); }); });
    apply(current);
  }

  /* ---------- "use suggestion" buttons */
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest("[data-suggest]");
    if (!btn) return;
    var input = document.getElementById(btn.dataset.target);
    if (input) { input.value = btn.dataset.suggest; input.focus(); }
  });

  /* ---------- in-place saving of findings */
  function bind(name, value) {
    document.querySelectorAll('[data-bind="' + name + '"]').forEach(function (el) {
      if (el.tagName === "METER") { el.value = value; } else { el.textContent = value; }
    });
  }
  document.querySelectorAll("form.cell-form").forEach(function (form) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var status = form.querySelector(".status");
      var submit = form.querySelector('button[type="submit"]');
      if (submit) submit.disabled = true;
      fetch(form.action, { method: "POST", body: new FormData(form), headers: { "Accept": "application/json" } })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (data) {
          bind("score", data.score); bind("meter", data.score);
          bind("errors", data.counts.error); bind("warnings", data.counts.warning);
          document.querySelectorAll('[data-bind="readiness"]').forEach(function (el) {
            el.textContent = data.readiness_label; el.className = "ready ready-" + data.readiness;
          });
          var item = form.closest("[data-finding]");
          if (data.resolved && item) {
            item.classList.add("fixed");
            if (status) { status.innerHTML = ""; var ok = document.createElement("span"); ok.className = "ok"; ok.textContent = "✓ " + data.message; status.appendChild(ok); }
          } else if (status) {
            status.textContent = data.findings.length ? data.findings[0].message : data.message;
          }
          announce(data.message);
        })
        .catch(function () { form.submit(); })
        .finally(function () { if (submit) submit.disabled = false; });
    });
  });

  /* ---------- dependency graph highlighting (hover and keyboard focus) */
  document.querySelectorAll("svg.dep-graph").forEach(function (svg) {
    var edges = Array.prototype.slice.call(svg.querySelectorAll(".edge"));
    var nodes = Array.prototype.slice.call(svg.querySelectorAll(".node"));
    function focusOn(code) {
      var linked = {}; linked[code] = true;
      edges.forEach(function (e) {
        var hit = e.dataset.source === code || e.dataset.target === code;
        e.classList.toggle("hl", hit);
        if (hit) { linked[e.dataset.source] = true; linked[e.dataset.target] = true; }
      });
      nodes.forEach(function (n) { n.classList.toggle("hl", !!linked[n.dataset.code]); });
      svg.classList.add("focusing");
    }
    function clear() { svg.classList.remove("focusing"); }
    nodes.forEach(function (n) {
      n.addEventListener("mouseenter", function () { focusOn(n.dataset.code); });
      n.addEventListener("focus", function () { focusOn(n.dataset.code); });
      n.addEventListener("mouseleave", clear);
      n.addEventListener("blur", clear);
    });
  });
})();

/* ---------- chart tooltips (data-tip attributes on SVG marks) */
(function () {
  "use strict";
  var t = document.getElementById("viz-tip");
  if (!t || !document.querySelector("[data-tip]")) return;
  document.querySelectorAll("[data-tip] title").forEach(function (n) { n.remove(); });
  document.querySelectorAll("[data-tip][title]").forEach(function (n) { n.removeAttribute("title"); });
  document.addEventListener("mousemove", function (e) {
    var n = e.target.closest && e.target.closest("[data-tip]");
    if (!n) { t.hidden = true; return; }
    t.textContent = n.getAttribute("data-tip");
    t.hidden = false;
    var x = e.clientX + 14, y = e.clientY + 14;
    if (x + t.offsetWidth > innerWidth - 8) { x = e.clientX - t.offsetWidth - 14; }
    if (y + t.offsetHeight > innerHeight - 8) { y = e.clientY - t.offsetHeight - 14; }
    t.style.left = x + "px";
    t.style.top = y + "px";
  });
})();
