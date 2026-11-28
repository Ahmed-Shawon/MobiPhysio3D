/* Home page: hero video, filter pills and the exercise cards (all from config.js) */
(function () {
  const cfg = window.APP_CONFIG;

  // Hero video (autoplay, muted, loop)
  const hero = mediaWithFallback(cfg.HERO_MEDIA, "Hero video: assets/demos/hero.mp4", "MobiPhysio demo");
  hero.id = "hero-media";
  hero.classList.add("hero__media");
  document.getElementById("hero-media").replaceWith(hero);

  // Cards
  const grid = document.getElementById("exercise-grid");
  const canHover = window.matchMedia("(hover: hover)").matches;
  const cards = cfg.EXERCISES.map((ex, i) => {
    const card = el("a", "card");
    card.href = "exercise.html?id=" + encodeURIComponent(ex.id);
    card.style.setProperty("--i", i);
    card.dataset.area = ex.area || "";

    // Demo video: paused on its first frame; plays while hovered (or while in view on touch screens)
    const media = mediaWithFallback(ex.demo, "Demo video", "Demo of " + ex.name, { autoplay: false });
    media.classList.add("card__media");
    if (ex.area) media.appendChild(el("span", "chip chip--glass nodot card__tl", ex.area));
    if (ex.pose) media.appendChild(el("span", "chip chip--glass nodot card__tr", ex.pose + " pose"));
    media.appendChild(el("span", "chip chip--glass nodot card__bl card__hint", canHover ? "▶  Hover to preview" : "▶  Preview"));
    media.appendChild(el("span", "chip chip--glass card__bl card__play", "Playing preview"));
    const prog = el("span", "card__prog"); prog.appendChild(el("i"));
    media.appendChild(prog);

    const body = el("div", "card__body");
    const cta = el("span", "card__cta");
    cta.innerHTML = "Start assessment " + ARROW_SVG;
    body.append(el("h3", "card__title", ex.name), el("p", "card__text", ex.description), cta);
    card.append(media, body);
    grid.appendChild(card);

    const video = media.querySelector("video");
    if (video && !window.reducedMotion) {
      const play = () => { card.classList.add("is-playing"); video.play().catch(() => {}); };
      const stop = () => { card.classList.remove("is-playing"); video.pause(); video.currentTime = 0; };
      video.addEventListener("timeupdate", () => {
        if (video.duration) prog.firstChild.style.width = (video.currentTime / video.duration) * 100 + "%";
      });
      if (canHover) {
        card.addEventListener("mouseenter", play);
        card.addEventListener("mouseleave", stop);
        card.addEventListener("focus", play);
        card.addEventListener("blur", stop);
      } else {
        new IntersectionObserver((es) => es.forEach((e) => (e.intersectionRatio > 0.7 ? play() : stop())), { threshold: [0, 0.7] }).observe(card);
      }
    }
    return card;
  });

  // Filter pills: All + one per body area, with counts
  const filters = document.getElementById("filters");
  const areas = [];
  cfg.EXERCISES.forEach((e) => { if (e.area && !areas.includes(e.area)) areas.push(e.area); });
  if (areas.length < 2) filters.hidden = true;
  [["All", cfg.EXERCISES.length], ...areas.map((a) => [a, cfg.EXERCISES.filter((e) => e.area === a).length])].forEach(([name, n], i) => {
    const b = el("button");
    b.type = "button";
    b.setAttribute("aria-pressed", i === 0);
    b.append(name + " ", el("span", null, String(n)));
    b.addEventListener("click", () => {
      filters.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
      cards.forEach((c) => { c.hidden = !(name === "All" || c.dataset.area === name); });
    });
    filters.appendChild(b);
  });

  // Entrance: cards fade up in a 60 ms stagger when the grid scrolls into view
  if (window.reducedMotion || !("IntersectionObserver" in window)) grid.classList.add("in");
  else new IntersectionObserver((es, io) => es.forEach((e) => {
    if (e.isIntersecting) { grid.classList.add("in"); io.disconnect(); }
  }), { threshold: 0.1 }).observe(grid);
})();
