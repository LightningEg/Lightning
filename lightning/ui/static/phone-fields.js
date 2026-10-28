/* Phone fields: tap a field that already has text and it opens empty, ready to type in (owner request 2026-10-14).
   Leave it empty and the old text comes back, so a stray tap never loses anything. Only a person's tap or Tab clears:
   a sheet that focuses its first field by itself leaves the values alone. Dates, pickers, passwords, selects and
   anything marked data-keep-text are left as they are. */
(() => {
  const SKIP_TYPES = new Set(["hidden", "checkbox", "radio", "date", "month", "time", "datetime-local", "password",
    "file", "range", "color", "submit", "button", "reset", "image"]);
  let lastPerson = 0;
  const person = () => { lastPerson = Date.now(); };
  document.addEventListener("pointerdown", person, true);
  document.addEventListener("touchstart", person, true);
  document.addEventListener("keydown", (event) => { if (event.key === "Tab") person(); }, true);

  const eligible = (el) => el instanceof HTMLElement && !el.readOnly && !el.disabled && !el.hasAttribute("data-keep-text")
    && ((el instanceof HTMLTextAreaElement) || (el instanceof HTMLInputElement && !SKIP_TYPES.has(el.type)));
  const putBack = (el) => {
    delete el.dataset.fieldTyped;
    if (el.dataset.fieldWas === undefined) return;
    if (el.value === "") el.value = el.dataset.fieldWas;
    delete el.dataset.fieldWas;
  };
  const open = (el) => {
    if (!eligible(el) || el.value === "" || el.dataset.fieldTyped) return;
    el.dataset.fieldWas = el.value;
    el.value = "";
  };

  document.addEventListener("focusin", (event) => { if (Date.now() - lastPerson <= 600) open(event.target); });
  // A tap on a field that is already focused (a picker closed and left it so) opens it empty too, unless text was typed in it.
  document.addEventListener("pointerdown", (event) => { if (event.target === document.activeElement) open(event.target); }, true);
  document.addEventListener("input", (event) => { if (event.isTrusted && event.target instanceof HTMLElement) event.target.dataset.fieldTyped = "1"; }, true);  // the page's own events do not count as typing
  document.addEventListener("focusout", (event) => { if (event.target instanceof HTMLElement) putBack(event.target); });
  // Enter on an empty field submits the old value, not nothing.
  document.addEventListener("submit", (event) => {
    event.target.querySelectorAll?.("[data-field-was]").forEach(putBack);
  }, true);
})();

/* Phone tables (guideline C12): CSS stacks every table row; each cell carries its column's heading as a label. */
(() => {
  document.querySelectorAll("table").forEach((table) => {
    const heads = [...table.querySelectorAll("thead th")].map((th) => th.textContent.trim());
    if (!heads.some(Boolean)) return;
    table.querySelectorAll("tbody tr").forEach((row) => {
      [...row.cells].forEach((cell, i) => { if (heads[i] && cell.textContent.trim() && !cell.dataset.label) cell.dataset.label = heads[i]; });
    });
  });
})();

/* Phone dates (guideline C12: a date is a picker, never typed): a date field is read-only so no keyboard opens; app.js opens the calendar on tap. */
(() => {
  const control = (target) => target.closest?.(".iso-date-control");
  const field = (target) => (target.matches?.("input[data-smart-date]") && control(target)) ? target : null;
  document.addEventListener("focusin", (event) => {
    const input = field(event.target);
    if (input) { input.readOnly = true; input.inputMode = "none"; }
  });
})();

/* Entry sheet (phone roadmap M2, M3): a new entry opens with the amount ready to type, and Paste bank SMS reads the
   copied bank message into Amount, Counterparty, Date and Money in or out. Nothing is saved until Save. */
(() => {
  const t = (text) => (window.lightningT ? window.lightningT(text) : text);
  const ready = (root) => {
    root.querySelectorAll("[data-sms-paste]").forEach((button) => {
      if (navigator.clipboard && navigator.clipboard.readText) button.hidden = false;
    });
    const amount = root.querySelector(".phone-entry input[autofocus]");
    if (amount && !amount.value) setTimeout(() => amount.focus({ preventScroll: true }), 60);
  };
  const box = document.getElementById("app-popup-content");
  if (box) new MutationObserver(() => ready(box)).observe(box, { childList: true });
  document.addEventListener("DOMContentLoaded", () => ready(document));

  const put = (form, name, value) => {
    const field = form.querySelector(`[name="${name}"]`);
    if (!field || value === undefined || value === null || value === "") return;
    field.value = value;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
  };
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-sms-paste]");
    if (!button) return;
    const sheet = button.closest(".phone-entry");
    const form = sheet && sheet.querySelector("form.phone-form");
    const status = sheet && sheet.querySelector("[data-sms-paste-status]");
    if (!form) return;
    const say = (text) => { if (status) status.textContent = t(text); };
    let text = "";
    try { text = (await navigator.clipboard.readText()).trim(); } catch (_) { text = ""; }
    if (!text) { say("Paste a bank message first."); return; }
    const data = new FormData();
    data.append("text", text);
    data.append("__session", form.querySelector('[name="__session"]').value);
    button.disabled = true;
    try {
      const response = await fetch(button.dataset.smsUrl, { method: "POST", body: data, headers: { "X-Requested-With": "fetch" } });
      const found = await response.json().catch(() => ({}));
      if (!response.ok) { say(found.error || "No amount found in this message."); return; }
      const kind = form.querySelector(`[name="kind"][value="${found.kind}"]`);
      if (kind) { kind.checked = true; kind.dispatchEvent(new Event("change", { bubbles: true })); }
      put(form, "amount", found.amount);
      put(form, "counterparty", found.counterparty);
      put(form, "date", found.date);
      say("Filled from the message. Check and save.");
      if (navigator.vibrate) navigator.vibrate(15);
    } finally { button.disabled = false; }
  });
})();
