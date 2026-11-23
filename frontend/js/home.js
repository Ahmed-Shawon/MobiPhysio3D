/* Home page: builds the 9 exercise cards from config */
(function () {
  const cfg = window.APP_CONFIG;

  const hero = document.getElementById("hero-media");
  hero.replaceWith(Object.assign(
    mediaWithFallback(cfg.HERO_MEDIA, "Hero media: input video + skeleton GIF sample", "Sample input video and skeleton output"),
    { id: "hero-media" }
  ));
  document.getElementById("hero-media").classList.add("hero__media");

  document.getElementById("exercise-count").textContent =
    cfg.EXERCISES.length + " supported exercises. Select a card to open its upload page.";

  const grid = document.getElementById("exercise-grid");
  cfg.EXERCISES.forEach((ex) => {
    const card = el("a", "card");
    card.href = "exercise.html?id=" + encodeURIComponent(ex.id);

    const media = mediaWithFallback(ex.demo, "Demo GIF", "Demo of " + ex.name);
    media.classList.add("card__media");

    const body = el("div", "card__body");
    body.append(el("h3", "card__title", ex.name), el("p", "card__text", ex.description), el("span", "card__cta", "Upload video →"));

    card.append(media, body);
    grid.appendChild(card);
  });
})();
