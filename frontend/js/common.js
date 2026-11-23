/* Shared helpers used by both pages */
(function () {
  const cfg = window.APP_CONFIG;

  // Fill every element marked data-cfg="KEY" with the matching config text
  document.querySelectorAll("[data-cfg]").forEach((el) => {
    const value = cfg[el.dataset.cfg];
    if (value != null) el.textContent = value;
  });
  document.title = document.title.replace("{site}", cfg.SITE_NAME);

  // Footer contact: name, email as a mailto link, repository link
  const contact = document.getElementById("footer-contact");
  if (contact) {
    const parts = [];
    if (cfg.CONTACT_NAME) parts.push(document.createTextNode("Contact: " + cfg.CONTACT_NAME));
    if (cfg.CONTACT_EMAIL) {
      const a = document.createElement("a");
      a.href = "mailto:" + cfg.CONTACT_EMAIL;
      a.textContent = cfg.CONTACT_EMAIL;
      parts.push(a);
    }
    if (cfg.REPOSITORY_URL) {
      const a = document.createElement("a");
      a.href = cfg.REPOSITORY_URL;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = "GitHub repository";
      parts.push(a);
    }
    parts.forEach((node, i) => {
      if (i) contact.append(" · ");
      contact.append(node);
    });
  }

  // Banner so mock data is never mistaken for real model output
  if (cfg.USE_MOCK) {
    const banner = document.createElement("div");
    banner.className = "mock-banner";
    banner.textContent = "Demo mode: backend not connected, results are mock data (USE_MOCK in js/config.js).";
    document.body.prepend(banner);
  }

  // Image that turns into a labelled placeholder box if the file is missing
  window.mediaWithFallback = function (src, label, alt) {
    const box = document.createElement("div");
    box.className = "media";
    const showPlaceholder = () => {
      box.textContent = label;
      box.classList.add("media--empty");
    };
    if (!src) { showPlaceholder(); return box; }
    // .mp4 / .webm play like a GIF: autoplay, loop, muted, no controls
    if (/\.(mp4|webm)(\?.*)?$/i.test(src)) {
      const video = document.createElement("video");
      video.muted = true;
      video.autoplay = true;
      video.loop = true;
      video.playsInline = true;
      video.preload = "auto";
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

  window.el = function (tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  };
})();
