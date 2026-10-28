/* Phone gestures and polish (phone roadmap M6, M8). Everything here is an extra: each page still works by tapping.
   - Feed swipe: on a transaction row, swipe toward the end to open it (change category), toward the start to delete
     it with Undo. RTL flips the direction, so "toward the start" is always the side you read from.
   - Tabs feel instant: a tab link is prefetched on touch, so the page fade (phone.css) has nothing to wait for.
   - Save buttons go busy on submit, so nobody saves twice.
   - Pull down at the top of a page to reload it.
   - Swipe the sheet's grabber down to close the sheet.
   - A new entry that cannot be saved (no connection) waits on the phone and is sent when the app can save again.
   - A short buzz on save, swipe and delete; nothing moves when the phone asks for reduced motion. */
(() => {
  const t = (text, values) => (window.lightningT ? window.lightningT(text, values) : text);
  const rtl = document.documentElement.dir === "rtl";
  const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const buzz = (ms) => { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (_) { /* no vibrator */ } };
  const token = () => {
    const meta = document.querySelector('meta[name="lightning-session"]');
    const field = document.querySelector('input[name="__session"]');
    return (meta && meta.content) || (field && field.value) || "";
  };
  const post = (url, extra) => {
    const data = new FormData();
    data.append("__session", token());
    Object.entries(extra || {}).forEach(([k, v]) => data.append(k, v));
    return fetch(url, { method: "POST", body: data, credentials: "same-origin", headers: { "X-Requested-With": "fetch" } });
  };

  /* Toast with one action (Undo), shown for 6 seconds. */
  let toastTimer = 0;
  const toast = (text, action, onAction) => {
    let box = document.getElementById("phone-toast");
    if (!box) {
      box = document.createElement("div");
      box.id = "phone-toast";
      box.className = "phone-toast";
      box.setAttribute("role", "status");
      box.setAttribute("aria-live", "polite");
      document.body.appendChild(box);
    }
    box.textContent = "";
    const span = document.createElement("span");
    span.textContent = t(text);
    box.appendChild(span);
    if (action) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = t(action);
      button.addEventListener("click", () => { box.hidden = true; onAction(); });
      box.appendChild(button);
    }
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { box.hidden = true; }, 6000);
  };

  /* M6: swipe a transaction row. */
  const SWIPE = 72;
  let swipe = null;
  document.addEventListener("touchstart", (event) => {
    const row = event.target.closest && event.target.closest("a.phone-txn[data-txn]");
    if (!row || event.touches.length !== 1) { swipe = null; return; }
    const touch = event.touches[0];
    swipe = { row, x: touch.clientX, y: touch.clientY, dx: 0, locked: null };
  }, { passive: true });
  document.addEventListener("touchmove", (event) => {
    if (!swipe) return;
    const touch = event.touches[0];
    const dx = touch.clientX - swipe.x, dy = touch.clientY - swipe.y;
    if (swipe.locked === null && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) swipe.locked = Math.abs(dx) > Math.abs(dy);
    if (!swipe.locked) return;
    swipe.dx = dx;
    const toStart = rtl ? dx > 0 : dx < 0;
    swipe.row.classList.toggle("is-swipe-delete", toStart && Math.abs(dx) > SWIPE);
    swipe.row.classList.toggle("is-swipe-open", !toStart && Math.abs(dx) > SWIPE);
    if (!still) swipe.row.style.transform = `translateX(${Math.max(-140, Math.min(140, dx))}px)`;
  }, { passive: true });
  document.addEventListener("touchend", () => {
    if (!swipe) return;
    const { row, dx, locked } = swipe;
    swipe = null;
    row.style.transform = "";
    row.classList.remove("is-swipe-delete", "is-swipe-open");
    if (!locked || Math.abs(dx) < SWIPE) return;
    row.dataset.swiped = "1";  // the click that follows a swipe is not a tap
    setTimeout(() => { delete row.dataset.swiped; }, 400);
    const toStart = rtl ? dx > 0 : dx < 0;
    if (!toStart) { buzz(10); row.click(); return; }
    const id = row.dataset.txn;
    buzz(25);
    row.classList.add("is-gone");
    // the server answers a fetch in plain text: 200 deleted, anything else is why not (a read-only device, an opening balance)
    post(`/transactions/${id}/delete`).then(async (response) => {
      if (!response.ok) { row.classList.remove("is-gone"); toast(await response.text()); return; }
      toast("Deleted.", "Undo", () => post(`/transactions/${id}/restore`).then(async (undo) => {
        if (undo.ok) location.reload(); else toast(await undo.text());
      }));
    }).catch(() => { row.classList.remove("is-gone"); });
  });
  document.addEventListener("click", (event) => {
    const row = event.target.closest && event.target.closest("a.phone-txn[data-swiped]");
    if (row && !event.isTrusted) return;  // the swipe's own click opens it
    if (row) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);

  /* M8: prefetch a tab on touch, so the next page is already on its way. */
  const fetched = new Set();
  document.addEventListener("touchstart", (event) => {
    const link = event.target.closest && event.target.closest(".phone-tabbar a[href], .phone-more-list a[href]");
    if (!link || link.hasAttribute("data-popup-open")) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || fetched.has(url.href)) return;
    fetched.add(url.href);
    const hint = document.createElement("link");
    hint.rel = "prefetch";
    hint.href = url.href;
    document.head.appendChild(hint);
  }, { passive: true });

  /* M8: a Save button goes busy on submit; buzz once. (Entries always save: the server runs on this device.) */
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || event.defaultPrevented) return;
    const entry = form.closest(".phone-entry") && (form.getAttribute("method") || "").toLowerCase() === "post";
    const button = event.submitter || form.querySelector("button.primary, button:not([type])");
    if (button && button.matches(".phone-save, .primary")) {
      setTimeout(() => { button.disabled = true; button.classList.add("is-busy"); button.setAttribute("aria-busy", "true"); }, 0);
      setTimeout(() => { button.disabled = false; button.classList.remove("is-busy"); button.removeAttribute("aria-busy"); }, 8000);
    }
    if (entry) buzz(15);
  });

  /* M8: pull down at the very top of the page to reload it. */
  let pull = null;
  const bar = () => {
    let el = document.getElementById("phone-pull");
    if (!el) {
      el = document.createElement("div");
      el.id = "phone-pull";
      el.className = "phone-pull";
      el.setAttribute("aria-hidden", "true");
      document.body.appendChild(el);
    }
    return el;
  };
  document.addEventListener("touchstart", (event) => {
    if (window.scrollY > 0 || event.touches.length !== 1 || document.querySelector("dialog[open]")) { pull = null; return; }
    if (event.target.closest && event.target.closest("input, textarea, select, .phone-txn")) { pull = null; return; }
    pull = { y: event.touches[0].clientY, dy: 0 };
  }, { passive: true });
  document.addEventListener("touchmove", (event) => {
    if (!pull) return;
    pull.dy = event.touches[0].clientY - pull.y;
    if (pull.dy <= 0 || window.scrollY > 0) return;
    const el = bar();
    el.style.setProperty("--pull", `${Math.min(pull.dy, 120)}px`);
    el.classList.toggle("is-ready", pull.dy > 90);
    el.textContent = pull.dy > 90 ? t("Release to refresh") : "";
  }, { passive: true });
  document.addEventListener("touchend", () => {
    if (!pull) return;
    const ready = pull.dy > 90;
    pull = null;
    const el = document.getElementById("phone-pull");
    if (el) { el.style.setProperty("--pull", "0px"); el.classList.remove("is-ready"); el.textContent = ""; }
    if (ready) { buzz(10); location.reload(); }
  });

  /* M8: swipe the sheet's grabber (or its top edge) down to close it. */
  let drag = null;
  document.addEventListener("touchstart", (event) => {
    const frame = event.target.closest && event.target.closest("#app-popup .app-popup-frame");
    if (!frame) return;
    const top = frame.getBoundingClientRect().top;
    if (event.touches[0].clientY - top > 48 && !event.target.closest(".phone-grabber")) return;
    drag = { frame, y: event.touches[0].clientY, dy: 0 };
  }, { passive: true });
  document.addEventListener("touchmove", (event) => {
    if (!drag) return;
    drag.dy = Math.max(0, event.touches[0].clientY - drag.y);
    if (!still) drag.frame.style.transform = `translateY(${drag.dy}px)`;
  }, { passive: true });
  document.addEventListener("touchend", () => {
    if (!drag) return;
    const { frame, dy } = drag;
    drag = null;
    frame.style.transform = "";
    if (dy > 110) {
      const close = document.querySelector("#app-popup [data-popup-close]");
      if (close) close.click();
    }
  });
})();

// Closed folds on the Overview load when opened (backend roadmap B1): one small request instead of every chart.
document.addEventListener("toggle", (event) => {
  const fold = event.target;
  if (!(fold instanceof HTMLDetailsElement) || !fold.open) return;
  fold.querySelectorAll("[data-fold-src]").forEach((box) => {
    const src = box.getAttribute("data-fold-src");
    box.removeAttribute("data-fold-src");
    fetch(src, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then((r) => (r.ok ? r.text() : Promise.reject(r.status)))
      .then((html) => { box.innerHTML = html; })
      .catch(() => { box.setAttribute("data-fold-src", src); });
  });
}, true);

