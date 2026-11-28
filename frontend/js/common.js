/* Shared helpers used by both pages: logo, footer, menu, config text, media helper */
(function () {
  const cfg = window.APP_CONFIG;

  window.el = function (tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  };

  window.ARROW_SVG = '<svg class="arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';

  // Logo: an "M" drawn as a skeleton with keypoint joints + two-tone wordmark
  const LOGO_MARK = '<i class="logo__mark" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 30 30" fill="none">' +
    '<path d="M5 23V8l10 10 10-10v15" stroke="#5EEAD4" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<circle cx="5" cy="23" r="2.4" fill="#fff"/><circle cx="5" cy="8" r="2.4" fill="#fff"/><circle cx="15" cy="18" r="2.8" fill="#A5B4FC"/>' +
    '<circle cx="25" cy="8" r="2.4" fill="#fff"/><circle cx="25" cy="23" r="2.4" fill="#fff"/></svg></i>';
  function logoHTML() {
    const name = cfg.SITE_NAME || "MobiPhysio";
    const split = name === "MobiPhysio" ? 'Mobi<span class="logo__accent">Physio</span>' : name.replace(/[&<>]/g, "");
    return LOGO_MARK + "<span>" + split + "</span>";
  }

  // Fill every element marked data-cfg="KEY" with the matching config text
  document.querySelectorAll("[data-cfg]").forEach((node) => {
    const value = cfg[node.dataset.cfg];
    if (value != null) node.textContent = value;
  });
  document.title = document.title.replace("{site}", cfg.SITE_NAME);

  // Footer: CTA card + project title + contact (name, university, email, repository)
  document.querySelectorAll("[data-footer]").forEach((foot) => {
    const onHome = !!document.getElementById("exercise-grid");
    foot.innerHTML =
      '<div class="wrap">' +
      '<div class="cta-card"><div><h2>Ready to try it?</h2><p>Choose an exercise and upload a 10–60 second video.</p></div>' +
      '<a class="btn btn--light" href="' + (onHome ? "#exercises" : "index.html#exercises") + '">Choose an exercise ' + ARROW_SVG + "</a></div>" +
      '<div class="foot__row"><div class="foot__project"><a class="logo" href="index.html">' + logoHTML() + "</a><p></p></div>" +
      '<div class="foot__contact"><span class="eyebrow eyebrow--muted">Contact</span></div></div></div>';
    foot.querySelector(".foot__project p").textContent = cfg.FOOTER_LEFT || "";
    const c = foot.querySelector(".foot__contact");
    if (cfg.CONTACT_NAME) c.appendChild(el("b", null, cfg.CONTACT_NAME));
    if (cfg.CONTACT_AFFILIATION) c.appendChild(el("span", "foot__uni", cfg.CONTACT_AFFILIATION));
    if (cfg.CONTACT_EMAIL) {
      const a = el("a", "foot__email", cfg.CONTACT_EMAIL);
      a.href = "mailto:" + cfg.CONTACT_EMAIL;
      c.appendChild(a);
    }
    if (cfg.REPOSITORY_URL) {
      const a = el("a", "foot__repo", cfg.REPOSITORY_URL.replace(/^https?:\/\//, "") + " ↗");
      a.href = cfg.REPOSITORY_URL; a.target = "_blank"; a.rel = "noopener";
      c.appendChild(a);
    }
  });

  document.querySelectorAll("[data-logo]").forEach((a) => { a.innerHTML = logoHTML(); });
  document.querySelectorAll("[data-arrow]").forEach((s) => { s.outerHTML = ARROW_SVG; });
  document.querySelectorAll("[data-repo]").forEach((a) => {
    if (cfg.REPOSITORY_URL) a.href = cfg.REPOSITORY_URL; else a.hidden = true;
  });

  // Phone menu
  document.querySelectorAll("[data-burger]").forEach((b) => {
    const nav = b.closest(".nav");
    b.addEventListener("click", () => {
      const open = nav.classList.toggle("nav--open");
      b.setAttribute("aria-expanded", open);
    });
    nav.querySelectorAll(".nav__links a").forEach((a) => a.addEventListener("click", () => {
      nav.classList.remove("nav--open"); b.setAttribute("aria-expanded", false);
    }));
  });

  // Banner so mock data is never mistaken for real model output
  if (cfg.USE_MOCK) {
    const banner = el("div", "mock-banner", "Demo mode: backend not connected, results are mock data (USE_MOCK in js/config.js).");
    document.body.prepend(banner);
  }

  window.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Image or video that turns into a labelled placeholder box if the file is missing.
  // opts.autoplay (default true): .mp4/.webm play muted in a loop like a GIF
  window.mediaWithFallback = function (src, label, alt, opts) {
    opts = opts || {};
    const box = el("div", "media");
    const showPlaceholder = () => {
      box.textContent = label;
      box.classList.add("media--empty");
    };
    if (!src) { showPlaceholder(); return box; }
    if (/\.(mp4|webm)(\?.*)?$/i.test(src)) {
      const video = document.createElement("video");
      const autoplay = opts.autoplay !== false && !window.reducedMotion;
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.autoplay = autoplay;
      video.preload = autoplay ? "auto" : "metadata";
      video.setAttribute("muted", "");
      video.setAttribute("aria-label", alt || "");
      video.onerror = showPlaceholder;
      video.src = src;
      box.appendChild(video);
      return box;
    }
    const img = document.createElement("img");
    img.src = src;
    img.alt = alt || "";
    img.loading = "lazy";
    img.onerror = showPlaceholder;
    box.appendChild(img);
    return box;
  };
})();
