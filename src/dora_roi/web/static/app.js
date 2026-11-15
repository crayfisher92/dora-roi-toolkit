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

  /* ---------- keyboard access to horizontally scrolling tables (WCAG 2.1.1) */
  function labelFor(wrap) {
    var section = wrap.closest("[aria-labelledby]");
    var heading = section && document.getElementById(section.getAttribute("aria-labelledby"));
    var caption = wrap.querySelector("caption");
    return (heading || caption || {}).textContent || "Table";
  }
  function scrollRegions() {
    document.querySelectorAll(".table-wrap").forEach(function (wrap) {
      var overflowing = wrap.scrollWidth > wrap.clientWidth + 1;
      if (overflowing && !wrap.hasAttribute("tabindex")) {
        wrap.setAttribute("tabindex", "0");
        wrap.setAttribute("role", "region");
        wrap.setAttribute("aria-label", labelFor(wrap).trim());
        wrap.dataset.scrollRegion = "1";
      } else if (!overflowing && wrap.dataset.scrollRegion) {
        ["tabindex", "role", "aria-label", "data-scroll-region"].forEach(function (a) { wrap.removeAttribute(a); });
      }
    });
  }
  scrollRegions();
  var resizeTimer;
  window.addEventListener("resize", function () { clearTimeout(resizeTimer); resizeTimer = setTimeout(scrollRegions, 150); });

  /* ---------- busy state for slow form posts (imports of large registers) */
  document.querySelectorAll("form[data-busy]").forEach(function (form) {
    form.addEventListener("submit", function () {
      if (form.getAttribute("aria-busy") === "true") return;
      form.setAttribute("aria-busy", "true");
      announce(form.dataset.busy);
      var btn = form.querySelector("button[type=submit], button:not([type])");
      if (btn) {
        // disable after the submit has been dispatched so the button value is still sent
        setTimeout(function () { btn.disabled = true; btn.dataset.label = btn.textContent; btn.textContent = form.dataset.busy; }, 0);
      }
    });
  });
  window.addEventListener("pageshow", function () { // back/forward cache: reset
    document.querySelectorAll("form[aria-busy=true]").forEach(function (form) {
      form.removeAttribute("aria-busy");
      var btn = form.querySelector("button[disabled]");
      if (btn) { btn.disabled = false; if (btn.dataset.label) btn.textContent = btn.dataset.label; }
    });
  });

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

/* ---------- reporting countdowns (incidents): refreshed every 30 s and when the tab regains
   focus; deliberately not a live region (no announcements every tick) */
(function () {
  "use strict";
  var clocks = document.querySelectorAll("time.countdown[datetime]");
  if (!clocks.length) return;
  function fmt(ms, day) {
    var s = Math.floor(Math.abs(ms) / 1000), d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    if (d) return d + " " + day + " " + h + " h";
    if (h) return h + " h " + m + " min";
    return m + " min";
  }
  function tick() {
    var now = Date.now();
    clocks.forEach(function (el) {
      var due = Date.parse(el.getAttribute("datetime"));
      if (isNaN(due)) return;
      var left = due - now, over = left < 0;
      var tpl = over ? el.dataset.overdue : el.dataset.in;
      if (tpl) el.textContent = tpl.replace("{t}", fmt(left, el.dataset.day || "d"));
      el.classList.toggle("overdue", over);
    });
  }
  tick();
  setInterval(tick, 30000);
  window.addEventListener("focus", tick);
  document.addEventListener("visibilitychange", tick);
})();
