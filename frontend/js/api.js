/* All communication with the FastAPI backend happens in this file.
   Public function:  API.analyze(exerciseId, file, onStage)
                     → Promise<{ score, skeletonSrc, details, jobId, assessmentId }>
   onStage(stage, percent) is called with "upload" | "processing" | "scoring"            */
(function () {
  const cfg = window.APP_CONFIG;
  const R = cfg.RESPONSE;

  const apiUrl = (path) => cfg.API_BASE_URL.replace(/\/+$/, "") + path;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Accepts a full URL, a server path ("/outputs/x.gif"), or base64 data
  function resolveSkeleton(json) {
    const b64 = json[R.skeletonBase64];
    if (b64) return b64.startsWith("data:") ? b64 : "data:image/gif;base64," + b64;
    const v = json[R.skeleton];
    if (!v) return null;
    if (/^(https?:|data:|blob:)/i.test(v)) return v;
    return apiUrl(v.startsWith("/") ? v : "/" + v);
  }

  function normalize(json) {
    return {
      score: json[R.score],
      skeletonSrc: resolveSkeleton(json),
      details: json[R.details] && typeof json[R.details] === "object" ? json[R.details] : {},
      jobId: json.job_id || null,                 // used for the PDF report link
      assessmentId: json.assessment_id || null    // set when the result was saved to the account
    };
  }

  function errorMessage(status, body) {
    let detail = body && body[R.error];
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg || JSON.stringify(d)).join("; "); // FastAPI 422
    return detail ? String(detail) : "The server returned an error (HTTP " + status + ").";
  }

  const unreachable = () =>
    new Error("Could not reach the backend at " + (cfg.API_BASE_URL || "this address") +
      ". Check that the FastAPI server is running and that CORS allows this site.");

  // XMLHttpRequest is used for the upload because it reports upload progress
  function postVideo(exerciseId, file, onStage) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append(cfg.FIELD_NAMES.video, file, file.name);
      form.append(cfg.FIELD_NAMES.exercise, exerciseId);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", apiUrl(cfg.ENDPOINTS.analyze));
      xhr.withCredentials = true;   // sends the login cookie, so the result is saved to the account
      Object.entries(cfg.EXTRA_HEADERS || {}).forEach(([k, v]) => xhr.setRequestHeader(k, v));
      xhr.timeout = cfg.REQUEST_TIMEOUT_MS;
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onStage("upload", Math.round((e.loaded / e.total) * 100)); };
      xhr.upload.onload = () => onStage("processing");
      xhr.onerror = () => reject(unreachable());
      xhr.ontimeout = () => reject(new Error("The request timed out. Try a shorter video, or switch MODE to \"poll\" in js/config.js."));
      xhr.onload = () => {
        let body = null;
        try { body = JSON.parse(xhr.responseText); } catch (_) { /* not JSON */ }
        if (xhr.status >= 200 && xhr.status < 300 && body) resolve(body);
        else reject(new Error(errorMessage(xhr.status, body)));
      };
      xhr.send(form);
    });
  }

  async function pollUntilDone(jobId, onStage) {
    const url = apiUrl(cfg.ENDPOINTS.status.replace("{job_id}", encodeURIComponent(jobId)));
    const deadline = Date.now() + cfg.REQUEST_TIMEOUT_MS;
    while (Date.now() < deadline) {
      await sleep(cfg.POLL_INTERVAL_MS);
      let res;
      try { res = await fetch(url, { headers: cfg.EXTRA_HEADERS || {}, credentials: "include" }); } catch (_) { throw unreachable(); }
      const body = await res.json().catch(() => null);
      if (!res.ok || !body) throw new Error(errorMessage(res.status, body));
      const status = String(body[R.status] || "").toLowerCase();
      if (cfg.POLL_DONE.includes(status)) return body;
      if (cfg.POLL_FAILED.includes(status)) throw new Error(errorMessage(res.status, body) || "Processing failed.");
      onStage(status === "scoring" ? "scoring" : "processing");
    }
    throw new Error("Processing took too long and was stopped.");
  }

  async function mockAnalyze(onStage) {
    for (let p = 0; p <= 100; p += 25) { onStage("upload", p); await sleep(150); }
    onStage("processing"); await sleep(900);
    onStage("scoring"); await sleep(600);
    return cfg.MOCK_RESULT;
  }

  window.API = {
    url: apiUrl,
    async analyze(exerciseId, file, onStage) {
      onStage = onStage || function () {};
      if (cfg.USE_MOCK) return normalize(await mockAnalyze(onStage));
      let json = await postVideo(exerciseId, file, onStage);
      if (cfg.MODE === "poll") {
        const jobId = json[R.jobId];
        if (!jobId) throw new Error("MODE is \"poll\" but the server response has no \"" + R.jobId + "\".");
        json = await pollUntilDone(jobId, onStage);
      }
      return normalize(json);
    }
  };
})();
