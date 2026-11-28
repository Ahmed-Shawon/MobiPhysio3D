/* Accounts: navbar login / account button, the log in / sign up dialog, and AUTH helpers.
   The login lives in an HttpOnly cookie set by the backend; this file never sees it.
   Public:  AUTH.ready → Promise<user|null>,  AUTH.user,  AUTH.open("login"|"signup", opts),
            AUTH.logout(),  AUTH.onChange(fn)                                               */
(function () {
  const cfg = window.APP_CONFIG;
  const apiUrl = (path) => (cfg.API_BASE_URL || "").replace(/\/+$/, "") + path;
  const listeners = [];
  const AUTH = { user: null };
  window.AUTH = AUTH;

  async function request(method, path, body) {
    const res = await fetch(apiUrl(path), {
      method,
      credentials: "include",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined
    });
    const json = await res.json().catch(() => null);
    if (!res.ok) {
      let d = json && json.detail;
      if (Array.isArray(d)) d = d.map((x) => x.msg).join("; ");
      throw new Error(d || "The server returned an error (HTTP " + res.status + ").");
    }
    return json;
  }
  AUTH.request = request;

  function setUser(user) {
    AUTH.user = user || null;
    renderNav();
    listeners.forEach((fn) => fn(AUTH.user));
  }
  AUTH.onChange = (fn) => listeners.push(fn);

  AUTH.ready = cfg.USE_MOCK
    ? Promise.resolve(null)
    : request("GET", "/api/auth/me").then((r) => { setUser(r.user); return r.user; }).catch(() => { setUser(null); return null; });

  AUTH.logout = async function () {
    try { await request("POST", "/api/auth/logout"); } catch (_) { /* cookie is cleared anyway */ }
    setUser(null);
    if (/account\.html$/.test(location.pathname)) location.href = "index.html";
  };

  /* ---------- navbar ---------- */
  const USER_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>';

  function renderNav() {
    document.querySelectorAll(".nav").forEach((nav) => {
      const actions = nav.querySelector(".nav__actions");
      const links = nav.querySelector(".nav__links");
      nav.querySelectorAll("[data-account]").forEach((n) => n.remove());
      if (cfg.USE_MOCK) return;

      // desktop: button in the actions row (before the primary button)
      const slot = el("div", "acct");
      slot.dataset.account = "";
      if (AUTH.user) {
        const btn = el("button", "btn btn--secondary btn--sm acct__btn");
        btn.type = "button";
        btn.setAttribute("aria-haspopup", "true");
        btn.setAttribute("aria-expanded", "false");
        const initial = el("span", "acct__avatar", (AUTH.user.name || "?").trim().charAt(0).toUpperCase());
        btn.append(initial, el("span", "acct__name", AUTH.user.name.split(" ")[0]));
        const menu = el("div", "acct__menu");
        menu.hidden = true;
        const who = el("div", "acct__who");
        who.append(el("b", null, AUTH.user.name), el("span", null, AUTH.user.email));
        const mine = el("a", null, "My assessments");
        mine.href = "account.html";
        const out = el("button", null, "Log out");
        out.type = "button";
        out.addEventListener("click", AUTH.logout);
        menu.append(who, mine, out);
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          menu.hidden = !menu.hidden;
          btn.setAttribute("aria-expanded", String(!menu.hidden));
        });
        document.addEventListener("click", (e) => { if (!slot.contains(e.target)) { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); } });
        document.addEventListener("keydown", (e) => { if (e.key === "Escape") { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); } });
        slot.append(btn, menu);
      } else {
        const btn = el("button", "btn btn--secondary btn--sm");
        btn.type = "button";
        btn.innerHTML = USER_SVG + "<span>Log in</span>";
        btn.addEventListener("click", () => AUTH.open("login"));
        slot.appendChild(btn);
      }
      actions.insertBefore(slot, actions.lastElementChild);

      // phone menu: plain links
      if (AUTH.user) {
        const a = el("a", "nav__phone", "My assessments");
        a.href = "account.html"; a.dataset.account = "";
        const b = el("a", "nav__phone", "Log out (" + AUTH.user.name.split(" ")[0] + ")");
        b.href = "#"; b.dataset.account = "";
        b.addEventListener("click", (e) => { e.preventDefault(); AUTH.logout(); });
        links.append(a, b);
      } else {
        const a = el("a", "nav__phone", "Log in / Sign up");
        a.href = "#"; a.dataset.account = "";
        a.addEventListener("click", (e) => { e.preventDefault(); AUTH.open("login"); });
        links.appendChild(a);
      }
    });
  }

  /* ---------- log in / sign up dialog ---------- */
  let dialog = null, mode = "login", afterLogin = null;

  function buildDialog() {
    dialog = document.createElement("dialog");
    dialog.className = "auth";
    dialog.innerHTML =
      '<form class="auth__card" novalidate>' +
      '<button type="button" class="auth__close" aria-label="Close">&times;</button>' +
      '<p class="eyebrow" data-a="eyebrow"></p>' +
      '<h2 class="auth__title" data-a="title"></h2>' +
      '<p class="auth__lead" data-a="lead"></p>' +
      '<label class="field" data-a="name-row"><span>Name</span><input name="name" autocomplete="name" maxlength="80"></label>' +
      '<label class="field"><span>Email</span><input name="email" type="email" autocomplete="email" maxlength="254" required></label>' +
      '<label class="field"><span>Password</span><input name="password" type="password" minlength="8" maxlength="72" required>' +
      '<small data-a="pw-hint">At least 8 characters.</small></label>' +
      '<p class="error" role="alert" data-a="error" hidden></p>' +
      '<button type="submit" class="btn btn--primary btn--block" data-a="submit"></button>' +
      '<p class="auth__switch"><span data-a="switch-text"></span> <button type="button" class="link-btn" data-a="switch"></button></p>' +
      "</form>";
    document.body.appendChild(dialog);
    const q = (k) => dialog.querySelector('[data-a="' + k + '"]');
    const form = dialog.querySelector("form");

    dialog.querySelector(".auth__close").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
    q("switch").addEventListener("click", () => setMode(mode === "login" ? "signup" : "login"));

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(form).entries());
      const err = q("error");
      err.hidden = true;
      const submit = q("submit");
      submit.disabled = true;
      const label = submit.textContent;
      submit.textContent = mode === "login" ? "Logging in…" : "Creating account…";
      try {
        const body = mode === "login" ? { email: data.email, password: data.password } : data;
        const r = await request("POST", mode === "login" ? "/api/auth/login" : "/api/auth/signup", body);
        const fn = afterLogin;
        afterLogin = null;
        form.reset();
        dialog.close();
        setUser(r.user);
        if (fn) fn(r.user);
      } catch (ex) {
        err.textContent = ex.message || "Something went wrong. Try again.";
        err.hidden = false;
      } finally {
        submit.disabled = false;
        submit.textContent = label;
      }
    });
    dialog.addEventListener("close", () => { afterLogin = null; });

    dialog.setMode = function (m, lead) {
      mode = m;
      const signup = m === "signup";
      q("eyebrow").textContent = signup ? "Create account" : "Welcome back";
      q("title").textContent = signup ? "Sign up to save your results" : "Log in to MobiPhysio";
      q("lead").textContent = lead || (signup
        ? "Your assessments are saved to your account so you can track your score over time."
        : "See your saved assessments and score history.");
      q("name-row").hidden = !signup;
      q("name-row").querySelector("input").required = signup;
      q("pw-hint").hidden = !signup;
      form.password.autocomplete = signup ? "new-password" : "current-password";
      q("submit").textContent = signup ? "Create account" : "Log in";
      q("switch-text").textContent = signup ? "Already have an account?" : "New here?";
      q("switch").textContent = signup ? "Log in" : "Create an account";
      q("error").hidden = true;
    };
    function setMode(m) { dialog.setMode(m, null); }
  }

  // opts.lead: custom text under the title; opts.then(user): runs after a successful login/sign-up
  AUTH.open = function (m, opts) {
    opts = opts || {};
    if (!dialog) buildDialog();
    dialog.lead = opts.lead || null;
    dialog.setMode(m || "login", dialog.lead);
    dialog.showModal();
    afterLogin = opts.then || null;
    const first = dialog.querySelector(m === "signup" ? 'input[name="name"]' : 'input[name="email"]');
    setTimeout(() => first.focus(), 30);
  };

  renderNav();
})();
