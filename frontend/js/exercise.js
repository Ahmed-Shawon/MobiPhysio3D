/* Exercise page: upload view → processing → results view */
(function () {
  const cfg = window.APP_CONFIG;
  const $ = (id) => document.getElementById(id);

  /* ---------- Which exercise? (exercise.html?id=...) ---------- */
  const id = new URLSearchParams(location.search).get("id");
  const index = cfg.EXERCISES.findIndex((e) => e.id === id);
  const exercise = cfg.EXERCISES[index];
  if (!exercise) {
    $("page").hidden = true;
    $("not-found").hidden = false;
    return;
  }

  document.title = exercise.name + " — " + cfg.SITE_NAME;
  const indexLabel = "Exercise " + (index + 1) + " of " + cfg.EXERCISES.length;
  $("exercise-index").textContent = indexLabel;
  $("exercise-name").textContent = exercise.name;
  $("crumb-name").textContent = exercise.name;
  if (exercise.area) $("exercise-chips").appendChild(el("span", "chip chip--light", exercise.area));
  if (exercise.pose) {
    $("exercise-chips").appendChild(el("span", "chip chip--light nodot", exercise.pose + " pose"));
    $("skeleton-chip").textContent = exercise.pose + " SKELETON";
  }
  $("exercise-description").textContent = exercise.description;
  const demo = mediaWithFallback(exercise.demo, "Demo GIF of the correct movement", "Demo of " + exercise.name);
  demo.classList.add("demo__media");
  $("demo-slot").replaceWith(demo);
  [...(cfg.COMMON_TIPS || []), ...(exercise.tips || [])].forEach((t) => $("tips").appendChild(el("li", null, t)));

  const input = $("video-file");
  input.accept = cfg.UPLOAD.ACCEPT;
  const sizeRule = Number.isFinite(cfg.UPLOAD.MAX_SIZE_MB) ? " · max " + cfg.UPLOAD.MAX_SIZE_MB + " MB" : "";
  const formats = String(cfg.UPLOAD.ACCEPT || "").split(",").map((f) => f.trim().replace(/^\./, "").toUpperCase()).filter(Boolean).join(", ");
  $("upload-rules").textContent = (formats || "Video file") + " · 10–60 s" + sizeRule;

  /* ---------- File selection ---------- */
  let file = null;
  let inputUrl = null;

  const formatSize = (bytes) => (bytes / (1024 * 1024)).toFixed(1) + " MB";

  /* ---------- Local video preview (also reused for "Input video" on the results page) ---------- */
  const NO_PREVIEW = "Preview not available: this browser cannot play this video format. It can still be analysed.";

  // Plays the file from the browser; if the format cannot be played (e.g. some .mkv files), shows a note instead
  function attachVideo(video, url) {
    const box = video.parentElement;
    box.querySelectorAll(".media__note").forEach((n) => n.remove());
    box.classList.remove("media--empty");
    video.hidden = false;
    video.onerror = () => {
      video.hidden = true;
      box.classList.add("media--empty");
      box.appendChild(el("p", "media__note", NO_PREVIEW));
    };
    if (url) video.src = url; else video.removeAttribute("src");
    video.load();
  }

  function setPreview(f) {
    if (inputUrl) URL.revokeObjectURL(inputUrl);
    inputUrl = f ? URL.createObjectURL(f) : null;
    $("preview").hidden = !f;
    const v = $("preview-video");
    v.pause();
    attachVideo(v, inputUrl);
  }

  function showError(message) {
    $("error").textContent = message || "";
    $("error").hidden = !message;
  }

  function setFile(f) {
    showError("");
    if (f && !f.type.startsWith("video/") && !/\.(mp4|mov|avi|mkv|webm)$/i.test(f.name)) {
      showError("This file is not a video. Choose a video file.");
      f = null;
    } else if (f && f.size > cfg.UPLOAD.MAX_SIZE_MB * 1024 * 1024) {
      showError("This video is " + formatSize(f.size) + ". The limit is " + cfg.UPLOAD.MAX_SIZE_MB + " MB.");
      f = null;
    }
    file = f || null;
    if (!file) input.value = "";
    setPreview(file);
    $("file-row").hidden = !file;
    $("file-name").textContent = file ? file.name + " · " + formatSize(file.size) : "";
    $("analyze").disabled = !file;
  }

  input.addEventListener("change", () => setFile(input.files[0]));
  $("remove-file").addEventListener("click", () => setFile(null));

  const dropzone = $("dropzone");
  ["dragenter", "dragover"].forEach((evt) => dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("dropzone--over"); }));
  ["dragleave", "drop"].forEach((evt) => dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("dropzone--over"); }));
  dropzone.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]); });

  /* ---------- Processing state ---------- */
  const stages = ["upload", "processing", "scoring"];
  function setStage(stage, percent) {
    const current = stages.indexOf(stage);
    document.querySelectorAll("#steps li").forEach((li, i) => {
      li.classList.toggle("is-done", i < current);
      li.classList.toggle("is-active", i === current);
    });
    const bar = $("progress-bar");
    if (stage === "upload") { bar.classList.remove("is-indeterminate"); bar.style.width = (percent || 0) + "%"; }
    else { bar.style.width = "100%"; bar.classList.add("is-indeterminate"); }
    $("status").textContent = stage === "upload" ? "Uploading video… " + (percent || 0) + "%"
      : stage === "scoring" ? "Calculating assessment score…" : "Extracting skeleton keypoints…";
  }

  function setBusy(busy) {
    $("progress").hidden = !busy;
    $("analyze").disabled = busy || !file;
    $("analyze").textContent = busy ? "Analyzing…" : "Analyze video";
    input.disabled = busy;
    $("remove-file").disabled = busy;
  }

  /* ---------- Analyze ---------- */
  $("analyze").addEventListener("click", async () => {
    if (!file) return;
    $("preview-video").pause();
    showError("");
    setBusy(true);
    setStage("upload", 0);
    const started = performance.now();
    try {
      const result = await API.analyze(exercise.id, file, setStage);
      showResults(result, (performance.now() - started) / 1000);
    } catch (err) {
      showError(err.message || "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  });

  /* ---------- Results ---------- */
  function showResults(result, seconds) {
    // Input video (played straight from the browser, no re-download)
    attachVideo($("input-video"), inputUrl);

    // Skeleton output: GIF/image, or video if the backend returns one
    const slot = $("skeleton-slot");
    slot.textContent = "";
    slot.classList.remove("media--empty");
    const src = result.skeletonSrc;
    if (!src) {
      slot.textContent = "No skeleton output was returned";
      slot.classList.add("media--empty");
    } else if (/\.(mp4|webm|mov)(\?|$)/i.test(src)) {
      const v = el("video");
      v.src = src; v.controls = true; v.loop = true; v.muted = true; v.autoplay = true; v.playsInline = true;
      slot.appendChild(v);
    } else {
      const img = el("img");
      img.src = src; img.alt = "Skeleton rendering of the uploaded video";
      img.onerror = () => { slot.textContent = "The skeleton output could not be loaded"; slot.classList.add("media--empty"); };
      slot.appendChild(img);
    }
    $("download-skeleton").hidden = !src;
    if (src) $("download-skeleton").href = src;

    // Score + gauge (arc draws from 0 and the number counts up when the card comes into view)
    const score = Number(result.score);
    const hasScore = result.score != null && !Number.isNaN(score);
    const max = typeof cfg.SCORE_MAX === "number" && cfg.SCORE_MAX > 0 ? cfg.SCORE_MAX : null;
    const shown = hasScore ? String(+score.toFixed(cfg.SCORE_DECIMALS)) : "—";
    $("score-max").textContent = max ? "points out of " + max : "points";
    pendingGauge = { score: hasScore ? score : null, max };
    $("score-value").textContent = hasScore ? (0).toFixed(cfg.SCORE_DECIMALS) : "—";
    $("gauge-arc").style.strokeDasharray = "0 1000";

    // Details: points first, then fixed rows, then every key the backend sends in "details"
    const rows = [["Points", shown, max ? "/ " + max : ""], ["Exercise", exercise.name]];
    if (exercise.pose) rows.push(["Pose", exercise.pose]);
    rows.push(["Video file", file.name, formatSize(file.size)], ["Processing time", seconds.toFixed(1) + " s"]);
    const hidden = (cfg.HIDDEN_DETAILS || []).map((h) => h.toLowerCase());
    Object.entries(result.details).forEach(([k, v]) => {
      if (hidden.includes(k.replace(/_/g, " ").toLowerCase())) return;
      const label = k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
      rows.push([label, typeof v === "object" ? JSON.stringify(v) : String(v)]);
    });
    const dl = $("details-list");
    dl.textContent = "";
    rows.forEach(([k, v, small], i) => {
      const row = el("div", i === 0 ? "is-points" : (String(v).length > 22 ? "is-wide" : ""));
      const dd = el("dd", null, v);
      if (small) dd.appendChild(el("small", null, small));
      row.append(el("dt", null, k), dd);
      dl.appendChild(row);
    });

    $("exercise-index").textContent = "Analysis complete in " + seconds.toFixed(1) + " s";
    $("exercise-index").classList.add("status--done");
    $("upload-view").hidden = true;
    $("results-view").hidden = false;
    $("another").hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
    watchGauge();
  }

  /* ---------- Gauge animation ---------- */
  let pendingGauge = null;
  const ARC = 377; // length of the 270° track (r = 80)
  function runGauge() {
    if (!pendingGauge) return;
    const { score, max } = pendingGauge;
    pendingGauge = null;
    if (score == null) return;
    const frac = Math.max(0, Math.min(1, score / (max || 100)));
    const arc = $("gauge-arc"), value = $("score-value");
    if (window.reducedMotion) {
      arc.style.strokeDasharray = (ARC * frac).toFixed(1) + " 1000";
      value.textContent = score.toFixed(cfg.SCORE_DECIMALS);
      return;
    }
    requestAnimationFrame(() => requestAnimationFrame(() => { arc.style.strokeDasharray = (ARC * frac).toFixed(1) + " 1000"; }));
    const t0 = performance.now(), dur = 1400;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      value.textContent = (score * e).toFixed(cfg.SCORE_DECIMALS);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  let gaugeObserver = null;
  function watchGauge() {
    if (gaugeObserver) gaugeObserver.disconnect();
    if (!("IntersectionObserver" in window)) { runGauge(); return; }
    gaugeObserver = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) { runGauge(); gaugeObserver.disconnect(); }
    }), { threshold: 0.35 });
    gaugeObserver.observe($("result-card"));
  }

  $("another").addEventListener("click", () => {
    $("input-video").pause();
    $("results-view").hidden = true;
    $("another").hidden = true;
    $("upload-view").hidden = false;
    $("exercise-index").textContent = indexLabel;
    $("exercise-index").classList.remove("status--done");
    $("download-skeleton").hidden = true;
    pendingGauge = null;
    setFile(null);
  });
})();
