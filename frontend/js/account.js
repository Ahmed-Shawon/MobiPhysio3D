/* My assessments: list of saved results, score-over-time chart per exercise, CSV export */
(function () {
  const cfg = window.APP_CONFIG;
  const $ = (id) => document.getElementById(id);
  const names = Object.fromEntries(cfg.EXERCISES.map((e) => [e.id, e.name]));
  const order = cfg.EXERCISES.map((e) => e.id);
  const fmtDate = (d) => d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  const fmtTime = (d) => d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  const fmtScore = (s) => Number(s).toFixed(cfg.SCORE_DECIMALS);

  let items = [];
  let selected = null;

  $("login-btn").addEventListener("click", () => AUTH.open("login"));
  $("signup-btn").addEventListener("click", () => AUTH.open("signup"));

  function showError(msg) { $("error").textContent = msg || ""; $("error").hidden = !msg; }

  async function load(user) {
    showError("");
    $("logged-out").hidden = !!user;
    $("content").hidden = !user;
    $("export-csv").hidden = !user;
    $("who").textContent = user ? user.name + " · " + user.email : "";
    if (!user) return;
    $("export-csv").href = API.url("/api/assessments.csv");
    try {
      const r = await AUTH.request("GET", "/api/assessments");
      items = r.assessments.map((a) => ({ ...a, date: new Date(a.created * 1000) }));
    } catch (e) {
      showError(e.message);
      items = [];
    }
    render();
  }

  function render() {
    const has = items.length > 0;
    $("empty").hidden = has;
    $("chart-panel").hidden = !has;
    $("list-panel").hidden = !has;
    $("stat-count").textContent = items.length;
    $("stat-exercises").textContent = new Set(items.map((a) => a.exercise_id)).size;
    $("stat-last").textContent = has ? fmtDate(items[0].date) : "—";
    if (!has) return;

    // filter pills: exercises that have results, in site order; default = most recent exercise
    const used = order.filter((id) => items.some((a) => a.exercise_id === id));
    if (!used.includes(selected)) selected = items[0].exercise_id;
    const filters = $("chart-filters");
    filters.textContent = "";
    used.forEach((id) => {
      const b = el("button", null, names[id] || id);
      b.type = "button";
      b.appendChild(el("span", null, String(items.filter((a) => a.exercise_id === id).length)));
      b.setAttribute("aria-pressed", String(id === selected));
      b.addEventListener("click", () => { selected = id; render(); });
      filters.appendChild(b);
    });
    drawChart(items.filter((a) => a.exercise_id === selected).slice().reverse());
    renderRows();
  }

  /* ---------- line chart (plain SVG) ---------- */
  function drawChart(points) {
    const box = $("chart");
    // drawn at the box's real width so the labels stay readable on phones
    const W = Math.max(320, Math.round(box.clientWidth || 760)), H = W < 500 ? 240 : 280, L = 40, R = 16, T = 20, B = 40;
    const max = typeof cfg.SCORE_MAX === "number" ? cfg.SCORE_MAX : 100;
    const n = points.length;
    const t0 = points[0].date.getTime(), t1 = points[n - 1].date.getTime();
    // spread points evenly when they are close together in time, otherwise by date
    const byTime = t1 - t0 > 0 && n > 2;
    const PAD = W < 500 ? 28 : 36; // keeps the first and last point (and their labels) off the axis
    const x = (p, i) => n === 1 ? (L + W - R) / 2
      : L + PAD + (W - L - R - 2 * PAD) * (byTime ? (p.date.getTime() - t0) / (t1 - t0) : i / (n - 1));
    const y = (s) => T + (H - T - B) * (1 - Math.max(0, Math.min(max, s)) / max);

    let svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Score over time for ' + esc(names[selected]) + '">';
    for (let v = 0; v <= max; v += max / 4) {
      svg += '<line class="chart__grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '"/>' +
        '<text class="chart__axis" x="' + (L - 10) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + v + "</text>";
    }
    const xy = points.map((p, i) => [x(p, i), y(p.score)]);
    if (n > 1) {
      const d = xy.map((c, i) => (i ? "L" : "M") + c[0].toFixed(1) + " " + c[1].toFixed(1)).join(" ");
      svg += '<path class="chart__area" d="' + d + " L" + xy[n - 1][0].toFixed(1) + " " + y(0) + " L" + xy[0][0].toFixed(1) + " " + y(0) + 'Z"/>';
      svg += '<path class="chart__line" d="' + d + '"/>';
    }
    const showValues = n <= 12;
    xy.forEach((c, i) => {
      const p = points[i];
      svg += '<g class="chart__pt"><circle cx="' + c[0] + '" cy="' + c[1] + '" r="5"/>' +
        "<title>" + esc(fmtDate(p.date) + " " + fmtTime(p.date) + ": " + fmtScore(p.score)) + "</title></g>";
      if (showValues) svg += '<text class="chart__val" x="' + c[0] + '" y="' + (c[1] - 12) + '" text-anchor="middle">' + fmtScore(p.score) + "</text>";
    });
    // date labels: first, last (and middle when there is room)
    const label = (i, anchor) => '<text class="chart__axis" x="' + xy[i][0] + '" y="' + (H - 14) + '" text-anchor="' + anchor + '">' + esc(fmtDate(points[i].date)) + "</text>";
    if (n === 1) svg += label(0, "middle");
    else {
      svg += label(0, "middle") + label(n - 1, "middle");
      if (n >= 5) svg += label(Math.floor((n - 1) / 2), "middle");
    }
    svg += "</svg>";
    box.innerHTML = svg;

    const first = points[0].score, last = points[n - 1].score;
    const diff = last - first;
    $("chart-sub").textContent = n === 1
      ? "1 result so far. Run it again to see your progress."
      : n + " results · " + (diff >= 0 ? "+" : "−") + Math.abs(diff).toFixed(cfg.SCORE_DECIMALS) + " points since the first one";
  }

  function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  /* ---------- table ---------- */
  function renderRows() {
    const tbody = $("rows");
    tbody.textContent = "";
    items.forEach((a) => {
      const tr = el("tr");
      const d = el("td");
      d.append(el("b", null, fmtDate(a.date)), el("small", null, fmtTime(a.date)));
      const ex = el("td");
      const open = el("a", "history__ex", names[a.exercise_id] || a.exercise_name);
      open.href = "exercise.html?id=" + encodeURIComponent(a.exercise_id) + "&saved=" + a.id;
      ex.appendChild(open);
      const sc = el("td", "num history__score", fmtScore(a.score));
      const model = el("td", "history__model", a.model);
      const act = el("td", "history__actions");
      const link = (text, href, download) => {
        const l = el("a", "link-btn", text); l.href = href;
        if (download) l.download = download;
        return l;
      };
      const stamp = (names[a.exercise_id] || "assessment").replace(/\s+/g, "_") + "_" + a.id;
      act.append(
        link("Open", open.href),
        link("PDF", API.url(a.report_url), ""),
        link("GIF", API.url(a.skeleton_url), "MobiPhysio_" + stamp + ".gif")
      );
      const del = el("button", "link-btn link-btn--danger", "Delete");
      del.type = "button";
      del.addEventListener("click", async () => {
        if (!confirm("Delete this " + (names[a.exercise_id] || "") + " result from " + fmtDate(a.date) + "? This cannot be undone.")) return;
        try {
          await AUTH.request("DELETE", "/api/assessments/" + a.id);
          items = items.filter((x) => x.id !== a.id);
          render();
        } catch (e) { showError(e.message); }
      });
      act.appendChild(del);
      tr.append(d, ex, sc, model, act);
      tbody.appendChild(tr);
    });
  }

  // fires once the login check finishes, and again after logging in here
  AUTH.onChange(load);
  let resizeTimer = null;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (items.length) render(); }, 150); });
})();
