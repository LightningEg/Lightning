// Small helpers only — no financial logic lives in the browser.
const t = (text, values) => window.lightningT ? window.lightningT(text, values) : String(text);

// IV-3BF5: the browser still checks fields, but Lightning shows the message in its own rose well.
const requiredMessage = {
  amount: "Enter an amount.", category_id: "Choose a category.", date: "Pick a date.",
  name: "Enter a name.", counterparty: "Enter a name.",
};
let clientErrorId = 0;
const clearClientError = (field) => {
  const id = field.dataset.clientErrorId;
  if (!id) return;
  document.getElementById(id)?.remove();
  field.removeAttribute("aria-invalid");
  field.setAttribute("aria-describedby", (field.getAttribute("aria-describedby") || "").split(/\s+/).filter((part) => part && part !== id).join(" "));
  if (!field.getAttribute("aria-describedby")) field.removeAttribute("aria-describedby");
  field.closest(".field")?.classList.remove("has-error");
  delete field.dataset.clientErrorId;
};
const showFieldError = (field) => {
  if (!field || field.disabled) return;
  clearClientError(field);
  const host = field.closest(".field, label") || field.parentElement;
  if (!host) return;
  const message = field.validity.valueMissing
    ? t(requiredMessage[field.name] || (field.tagName === "SELECT" ? "Choose an option." : "Fill in this field."))
    : t(field.validity.customError ? field.validationMessage : "Enter a valid value.");
  const well = document.createElement("small");
  well.className = "field-error";
  well.id = `client-field-error-${++clientErrorId}`;
  well.setAttribute("role", "alert");
  well.textContent = message;
  host.append(well);
  host.classList.add("has-error");
  field.dataset.clientErrorId = well.id;
  field.setAttribute("aria-invalid", "true");
  field.setAttribute("aria-describedby", [field.getAttribute("aria-describedby"), well.id].filter(Boolean).join(" "));
};
const showFormErrors = (form) => {
  const invalid = [...form.elements].filter((field) => field.willValidate && !field.checkValidity());
  invalid.forEach(showFieldError);
  if (invalid.length) {
    const first = invalid[0];
    const visible = first.hidden ? first.closest(".counterparty-picker")?.querySelector('[role="combobox"]') : first;
    (visible || first).focus();
  }
  return invalid.length === 0;
};
window.lightningShowFormErrors = showFormErrors;
const initValidationForms = (root) => {
  const forms = [...(root.matches?.("form") ? [root] : []), ...root.querySelectorAll("form")];
  forms.forEach((form) => {
    form.noValidate = true;
    if (form.dataset.clientValidationReady) return;
    form.dataset.clientValidationReady = "1";
    form.addEventListener("input", (event) => { if (event.target.dataset?.clientErrorId) clearClientError(event.target); });
    form.addEventListener("change", (event) => { if (event.target.dataset?.clientErrorId) clearClientError(event.target); });
  });
};
initValidationForms(document);
new MutationObserver((changes) => changes.forEach((change) => change.addedNodes.forEach((node) => {
  if (node instanceof Element) initValidationForms(node);
}))).observe(document.documentElement, {childList: true, subtree: true});
document.addEventListener("submit", (event) => {
  if (!showFormErrors(event.target)) { event.preventDefault(); event.stopImmediatePropagation(); }
}, true);

// Match server-rendered numbers regardless of the device's regional settings.
window.lightningNumber = (value, {min = 0, max = 2, signed = false} = {}) => {
  const text = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: min, maximumFractionDigits: max,
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(value);
  return text.replace(/^-/, "−");
};

// Give every server-rendered or dynamically-inserted message the same
// accessible behavior. Success/status messages are transient; errors stay
// visible so users can correct the cause or dismiss them through the flow.
const flashTimers = new WeakMap();
const initFlashMessages = (root = document, refresh = false) => {
  const flashes = [
    ...(root.matches?.(".flash") ? [root] : []),
    ...root.querySelectorAll(".flash"),
  ];
  flashes.forEach((flash) => {
    const isError = flash.classList.contains("error");
    flash.setAttribute("role", isError ? "alert" : "status");
    flash.setAttribute("aria-live", isError ? "assertive" : "polite");
    flash.setAttribute("aria-atomic", "true");
    const prior = flashTimers.get(flash);
    if (prior) clearTimeout(prior);
    flashTimers.delete(flash);
    if (isError || !flash.textContent.trim() || flash.classList.contains("device-line") || flash.querySelector(".history-form")) return;
    // Only newly inserted or explicitly refreshed messages get a fresh timer.
    if (!refresh && flash.dataset.flashReady) return;
    flash.dataset.flashReady = "1";
    flashTimers.set(flash, setTimeout(() => {
      if (flash.isConnected) flash.remove();
      flashTimers.delete(flash);
    }, 5000));
  });
};
initFlashMessages();
const fullscreenButton = document.querySelector("[data-fullscreen-toggle]");
if (fullscreenButton) {
  const label = fullscreenButton.querySelector("[data-fullscreen-label]");
  const syncFullscreenButton = () => {
    const active = Boolean(document.fullscreenElement);
    const text = t(active ? "Exit full screen" : "Full screen");
    fullscreenButton.setAttribute("aria-label", text);
    fullscreenButton.title = text;
    if (label) label.textContent = text;
  };
  fullscreenButton.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      fullscreenButton.setAttribute("aria-label", t("Full screen unavailable"));
      fullscreenButton.title = t("Full screen unavailable");
    }
  });
  document.addEventListener("fullscreenchange", syncFullscreenButton);
  syncFullscreenButton();
}
// Keep the reader's place when a form post or a save returns a fresh server page (owner, 2026-10-30: no button may
// throw you out): where the page was scrolled to, and which sections were open or shut. The note is for this address,
// for fifteen seconds, and is used once. Sections are matched by their words with the numbers left out ("Tracked ·
// 5 categories" is "Tracked · # categories"), in order, so a list that grew or shrank still finds its own.
const PLACE_KEY = "lightning-page-place";
const placeLabel = (box) => (box.querySelector(":scope > summary")?.textContent || "").replace(/[\d.,+\-−]+/g, "#").replace(/\s+/g, " ").trim().slice(0, 40);
const placeBoxes = () => Array.from(document.querySelectorAll("details")).filter((box) => !box.closest(".action-menu, #app-popup-content, dialog"));
window.lightningRememberPlace = () => {
  try {
    sessionStorage.setItem(PLACE_KEY, JSON.stringify({
      path: location.pathname, at: Date.now(), top: window.scrollY,
      sections: placeBoxes().map((box) => [placeLabel(box), box.open]),
    }));
  } catch (error) { /* private mode: the page simply starts at the top */ }
};
window.lightningReload = () => { window.lightningRememberPlace(); location.reload(); };
// BV-12AF, BV-12AG · Save in place (owner, 2026-11-12: no reload on save, anywhere; stay where you are). Every page's
// content is one part, data-refresh="page" (base.html). After a save this fetches the page again and swaps only that
// part, the page title, the Undo pills, the message and the sidebar's figures, sets the part's fields up again and runs
// its own scripts on the new nodes. Scroll, open sections, the field you are in and what you typed there are kept.
// It returns false, and the caller loads the page the ordinary way, when a swap could not be faithful: the language,
// theme or Hide amounts changed, the sidebar's list changed, or the part holds a control that app.js sets up only when
// a page first opens (RELOAD_ONLY; tests/test_save_in_place_everywhere.py lists the pages this leaves).
const RELOAD_ONLY = [
  ".ledger", ".transaction-select", ".category-input", ".counterparty-input", ".import-category",
  ".import-transfer-suggestion", ".investment-entry-form", ".quantity-input", "[data-unrequires]",
  "select[data-chip-add]", "[data-command-open]", "[data-fullscreen-toggle]", "#page-jump", "input[data-strength]",
].join(", ");
const listensOnPage = (root) => [...root.querySelectorAll("script:not([src])")].some((script) =>
  /(document|window)\.addEventListener|setInterval/.test(script.textContent));
// What the server writes that a running page cannot take over in place: the language and direction, Hide amounts,
// and the theme the profile has chosen (theme-runtime.js applies it from these metas when a page opens).
const pageLook = (d) => [d.documentElement.getAttribute("lang"), d.documentElement.getAttribute("dir"),
  d.documentElement.classList.contains("privacy"),
  ...["lightning-theme", "lightning-owned", "lightning-follow-night"].map((name) => d.querySelector(`meta[name="${name}"]`)?.content ?? "")].join("|");
window.lightningRefreshInPlace = async (source = location.href) => {
  let doc = source;
  if (typeof source === "string") {
    const response = await fetch(source, { headers: { "X-Lightning-Refresh": "1" } });
    if (!response.ok || !(response.headers.get("content-type") || "").startsWith("text/html")) return false;
    if (new URL(response.url).pathname !== location.pathname) return false;  // the page itself sent you elsewhere
    doc = new DOMParser().parseFromString(await response.text(), "text/html");
  }
  const parts = [...document.querySelectorAll("[data-refresh]")];
  const freshPart = (part) => doc.querySelector(`[data-refresh="${CSS.escape(part.dataset.refresh)}"]`);
  if (!parts.length || parts.some((part) => !freshPart(part))) return false;
  if (parts.some((part) => part.querySelector(RELOAD_ONLY) || freshPart(part).querySelector(RELOAD_ONLY))) return false;
  // A page script that listens on the whole document or window, or ticks on a timer, would do it twice after a swap.
  if (parts.some((part) => listensOnPage(freshPart(part)))) return false;
  if (pageLook(document) !== pageLook(doc)) return false;
  const sideFigures = document.querySelectorAll("aside.side .num"), freshSideFigures = doc.querySelectorAll("aside.side .num");
  if (sideFigures.length !== freshSideFigures.length) return false;
  const active = document.activeElement;
  const FIELDS = "input:not([type=hidden]), select, textarea, button, a[href], summary";
  const holder = parts.find((part) => part.contains(active));
  const kept = holder && active.matches(FIELDS) ? {
    part: holder.dataset.refresh, index: [...holder.querySelectorAll(FIELDS)].indexOf(active), label: active.getAttribute("aria-label") || "",
    value: active.value, start: active.selectionStart, end: active.selectionEnd, typed: "defaultValue" in active && active.value !== active.defaultValue,
  } : null;
  const top = window.scrollY;
  const open = new Map();
  placeBoxes().forEach((box) => open.set(box.id || placeLabel(box), [...(open.get(box.id || placeLabel(box)) || []), box.open]));
  const swap = (old, fresh) => { if (old && fresh) old.replaceWith(document.importNode(fresh, true)); };
  if (doc.title) document.title = doc.title;
  swap(document.querySelector("main .page-title"), doc.querySelector("main .page-title"));
  const oldHistory = document.querySelectorAll("main .history-form"), freshHistory = doc.querySelectorAll("main .history-form");
  oldHistory.forEach((form, i) => swap(form, freshHistory[i]));
  sideFigures.forEach((figure, i) => {
    figure.textContent = freshSideFigures[i].textContent;
    figure.className = freshSideFigures[i].className;
  });
  document.querySelectorAll("main > .flash:not(.device-line)").forEach((flash) => flash.remove());
  const main = document.querySelector("main.main") || document.querySelector("main");
  const anchor = main?.querySelector(":scope > .flash.device-line") || null;
  [...doc.querySelectorAll("main > .flash:not(.device-line)")].reverse().forEach((flash) => {
    const node = document.importNode(flash, true);
    if (anchor) anchor.after(node); else main?.querySelector("[data-refresh]")?.before(node);
    initFlashMessages(node, true);
  });
  const nonce = document.querySelector("script[nonce]")?.nonce || "";
  parts.forEach((part) => {
    const node = document.importNode(freshPart(part), true);
    part.replaceWith(node);
    initAccountForm(node);
    // Scripts brought in from another document never run by themselves; each is made again with this page's nonce.
    // A page's own script runs in a block of its own, so its const and let do not meet the ones of its first run.
    node.querySelectorAll("script").forEach((old) => {
      const script = document.createElement("script");
      script.nonce = nonce;
      [...old.attributes].forEach((attr) => { if (attr.name !== "nonce" && attr.name !== "defer") script.setAttribute(attr.name, attr.value); });
      if (old.src) script.async = false;
      else script.textContent = `{\n${old.textContent}\n}`;
      old.replaceWith(script);
    });
  });
  placeBoxes().forEach((box) => {
    const queue = open.get(box.id || placeLabel(box));
    if (queue && queue.length) box.open = queue.shift();
  });
  window.scrollTo({ top, behavior: "instant" });
  if (kept) {
    const fields = [...(document.querySelector(`[data-refresh="${CSS.escape(kept.part)}"]`)?.querySelectorAll(FIELDS) || [])];
    const field = (kept.label && fields.find((f) => f.getAttribute("aria-label") === kept.label)) || fields[kept.index];
    if (field) {
      if (kept.typed) field.value = kept.value;
      field.focus({ preventScroll: true });
      try { field.setSelectionRange(kept.start, kept.end); } catch (error) { /* not a text field */ }
    }
  }
  // What a first page load sets up, set up again on the new nodes: the same event a phone page swapped in by
  // phone-nav.js sends (app.js, phone-fields.js, theme-runtime.js listen for it).
  document.querySelectorAll("[data-refresh]").forEach((root) => document.dispatchEvent(new CustomEvent("lightning:page", { detail: { root } })));
  document.dispatchEvent(new CustomEvent("lightning:refreshed"));
  return true;
};
// A file the server sends back (an export) is saved, as a plain form post would have saved it.
const saveDownload = async (response) => {
  const disposition = response.headers.get("content-disposition") || "";
  const name = (/filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1] && decodeURIComponent(/filename\*=UTF-8''([^;]+)/i.exec(disposition)[1]))
    || /filename="?([^";]+)"?/i.exec(disposition)?.[1] || "download";
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 60000);
};
// A form inside a part marked data-stay posts in the background. When the server answers with this same page, it
// refreshes in place, so a save keeps you where you were (Edit plan stays open, the row you edited stays in view).
// When it sends you to another page, you go there; when it answers with a page of its own (an error on the form, an
// import step), web.stay_shown_page keeps that page and the browser opens it as an ordinary page.
// On window, so it runs after every listener on the document: a "Delete?" question or a check that stops the post
// has had its say first (event.defaultPrevented).
window.addEventListener("submit", (event) => {
  const form = event.target;
  // Attributes, not form.action and form.method: a button named "action" (Track, Not now) hides the form's own.
  const method = (event.submitter?.getAttribute("formmethod") || form.getAttribute("method") || "get").toLowerCase();
  const part = form.closest("[data-refresh][data-stay]");
  // A page that loads whole after a save anyway (see lightningRefreshInPlace) posts the ordinary way, as it always has.
  if (event.defaultPrevented || !part || part.querySelector(RELOAD_ONLY) || listensOnPage(part) || method !== "post"
      || form.hasAttribute("data-popup-return") || form.hasAttribute("target") || event.submitter?.hasAttribute("formtarget")
      || (event.submitter?.getAttribute("formenctype") || form.getAttribute("enctype") || "") === "multipart/form-data") return;
  event.preventDefault();
  window.lightningRememberPlace();
  const action = event.submitter?.getAttribute("formaction") || form.getAttribute("action") || location.href;
  const body = new URLSearchParams(new FormData(form, event.submitter || undefined));
  const buttons = [...form.querySelectorAll("button"), ...document.querySelectorAll(`button[form="${CSS.escape(form.id || "-")}"]`)];
  buttons.forEach((button) => { button.disabled = true; });
  const release = () => buttons.forEach((button) => { if (button.isConnected) button.disabled = false; });
  fetch(new URL(action, location.href).href, { method: "POST", body, headers: { "X-Lightning-Stay": "1" } }).then(async (response) => {
    const landed = new URL(response.url);
    if (!response.redirected) {
      if (/attachment/i.test(response.headers.get("content-disposition") || "")) { await saveDownload(response); release(); return; }
      window.lightningReload();
      return;
    }
    if (landed.origin !== location.origin || landed.pathname !== location.pathname) { location.assign(landed.href); return; }
    // The server's answer (its message, an undo token, a month) on the address you are on, which keeps Edit plan open.
    const next = new URL(location.href);
    ["msg", "error", "undo"].forEach((key) => next.searchParams.delete(key));
    landed.searchParams.forEach((value, key) => next.searchParams.set(key, value));
    // Sent back to the very address you are on: its answer is already the fresh page, so it is not asked for twice.
    const source = next.search === landed.search && response.ok
      ? new DOMParser().parseFromString(await response.text(), "text/html") : next.href;
    if (!(await window.lightningRefreshInPlace(source))) location.assign(landed.href);
  }).catch(() => window.lightningReload());  // the save may have landed: show the page as it is now, never post twice
});
(() => {
  let note = null;
  try { note = JSON.parse(sessionStorage.getItem(PLACE_KEY) || "null"); sessionStorage.removeItem(PLACE_KEY); } catch (error) { note = null; }
  if (!note || note.path !== location.pathname || Date.now() - note.at > 15000) return;
  const restore = () => {
    const kept = new Map();
    (note.sections || []).forEach(([label, open]) => kept.set(label, [...(kept.get(label) || []), open]));
    placeBoxes().forEach((box) => {
      const queue = kept.get(placeLabel(box));
      if (queue && queue.length) box.open = queue.shift();
    });
    window.scrollTo({ top: Number(note.top) || 0, behavior: "instant" });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => requestAnimationFrame(restore));
  else requestAnimationFrame(restore);
})();
document.addEventListener("submit", (event) => {
  if ((event.target.method || "get").toLowerCase() === "post") window.lightningRememberPlace();
}, true);
// One menu open at a time (owner, 2026-10-30: two stacked on each other). Opening a menu shuts the others; a click
// anywhere else, or Escape, shuts them all.
(() => {
  const open = () => Array.from(document.querySelectorAll("details.action-menu[open]"));
  document.addEventListener("toggle", (event) => {
    const menu = event.target;
    if (!menu.matches?.("details.action-menu") || !menu.open) return;
    open().forEach((other) => { if (other !== menu) other.open = false; });
  }, true);
  document.addEventListener("click", (event) => {
    open().forEach((menu) => { if (!menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const menus = open();
    menus.forEach((menu) => { menu.open = false; });
    if (menus.length) menus[0].querySelector(":scope > summary")?.focus();
  });
})();
const flashObserver = new MutationObserver((changes) => {
  changes.forEach((change) => {
    if (change.type === "characterData") {
      const flash = change.target.parentElement?.closest(".flash");
      if (flash) initFlashMessages(flash, true);
      return;
    }
    const changedFlash = change.target instanceof Element
      ? change.target.closest(".flash")
      : change.target.parentElement?.closest(".flash");
    if (changedFlash) initFlashMessages(changedFlash, true);
    change.addedNodes.forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE) initFlashMessages(node, true);
    });
  });
});
const popupFlashRoot = document.getElementById("app-popup-content");
if (popupFlashRoot) {
  flashObserver.observe(popupFlashRoot, { childList: true, subtree: true, characterData: true });
}

// Own-data fields keep their native submitted value and gain an accessible
// type-and-pick surface. Popup markup is inserted after startup, so this must
// be safe to call repeatedly on any subtree.
// A pick list is position:fixed, so it must not sit inside a card that carries a transform, filter or contain (a theme's
// card lift, a popup's rise): there "fixed" means "relative to the card" and the list lands far from its field. It lives
// at the top of the page instead, or inside the open window when the field is in one (a modal window hides the page).
// A pick list redraws on every keystroke; page-wide scans that look for new forms and fields have nothing to find there,
// and on a long import (tens of thousands of nodes) each scan cost milliseconds per key.
const pickListOnly = (records) => records.every((record) => record.target.closest?.(".counterparty-results, .category-results, .pick-list"));
const pickerHome = (input) => input.closest("#app-popup-content") || input.closest("dialog") || document.body;
const pinFixed = (list, left, top) => { list.style.left = `${left}px`; list.style.top = `${top}px`; };
// The server uses the same Python matcher as Search and History. Only enabled options from
// this field are sent; ranking cannot add an account, change ownership or choose a value.
const pickerKind = (name = "") => /owner|whom|custody/.test(name) ? "Person" : /category/.test(name) ? "Category" : /asset|instrument/.test(name) ? "Investment" : /account/.test(name) ? "Account" : /reserve/.test(name) ? "Reserve" : "Counterparty";
const rankPicker = async (query, choices, kind) => {
  if (!query) return choices.map((choice) => choice.id);
  const body = new URLSearchParams({q: query, kind, choices: JSON.stringify(choices),
    __session: document.querySelector('meta[name="lightning-session"]')?.content || ""});
  try {
    const response = await fetch("/search/picker", {method: "POST", body});
    if (!response.ok) throw new Error("Picker search unavailable");
    return (await response.json()).ids;
  } catch (_) {
    // The original list stays usable if the local request fails.
    return choices.filter((row) => `${row.label} ${row.context || ""}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())).map((row) => row.id);
  }
};
// The Add account form: choosing an institution sets the Type (its kind is decided in Python and sent as data) and
// suggests the Name; a CD portfolio or gam'eya has no starting balance. In app.js, not inline, because a popup
// inserts the form as HTML and never runs its inline scripts.
const initAccountForm = (root = document) => {
  const type = root.querySelector("#account_type");
  if (!type || type.dataset.accountFormReady) return;
  type.dataset.accountFormReady = "1";
  const opening = root.querySelector("#opening-balance-section");
  const openingAmount = root.querySelector("#opening_balance");
  const syncBalance = () => {
    if (!opening) return;
    const isPortfolio = type.value === "DEPOSIT" || type.value === "GAMEYA";
    if (isPortfolio && !opening.hidden && openingAmount && openingAmount.value !== "0") {
      opening.dataset.previousValue = openingAmount.value;
      openingAmount.value = "0";
    } else if (!isPortfolio && opening.hidden && openingAmount && opening.dataset.previousValue) {
      openingAmount.value = opening.dataset.previousValue;
      delete opening.dataset.previousValue;
    }
    opening.hidden = isPortfolio;
    opening.style.display = isPortfolio ? "none" : "";
  };
  type.addEventListener("change", syncBalance);
  syncBalance();
  const institution = root.querySelector("#institution");
  const nameInput = root.querySelector("#name");
  const currency = root.querySelector("#currency");
  let hints = {};
  try { hints = JSON.parse(type.dataset.institutionHints || "{}"); } catch (error) { hints = {}; }
  const norm = (value) => (value || "").normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}_&]+/gu, " ").trim().replace(/\s+/g, " ");
  const hintFor = (value) => hints[value] || hints[norm(value)];
  let lastInstitution = hintFor(institution ? institution.value : "")?.name || "";
  let suggestedName = "";
  const applyInstitution = () => {
    const hint = hintFor(institution.value);
    if (!hint) { lastInstitution = ""; return; }
    if (hint.type && hint.name !== lastInstitution && type.value !== hint.type) {
      type.value = hint.type;
      type.dispatchEvent(new Event("change", {bubbles: true}));
    }
    lastInstitution = hint.name;
    if (nameInput && (!nameInput.value.trim() || nameInput.value === suggestedName)) {
      suggestedName = `${hint.short} \u00b7 ${currency ? currency.value : ""}`;
      nameInput.value = suggestedName;
    }
  };
  if (institution) {
    institution.addEventListener("change", applyInstitution);
    institution.addEventListener("input", applyInstitution);
  }
  if (currency) currency.addEventListener("change", () => {
    if (nameInput && suggestedName && nameInput.value === suggestedName) applyInstitution();
  });
};
let ownPickerId = 0;
const initOwnDataPickers = (root = document) => {
  const find = (selector) => [
    ...(root.matches?.(selector) ? [root] : []),
    ...root.querySelectorAll(selector),
  ];
  find("select[data-own-picker]").forEach((select) => {
  if (select.dataset.ownPickerReady) return;
  select.dataset.ownPickerReady = "1";
  const index = ownPickerId++;
  const originalParent = select.parentElement;
  const wasRequired = select.required;
  const wrapper = document.createElement("div");
  wrapper.className = "counterparty-picker";
  select.before(wrapper);
  wrapper.append(select);
  select.hidden = true;
  const input = document.createElement("input");
  input.type = "text";
  if (select.hasAttribute("form")) input.setAttribute("form", select.getAttribute("form"));
  input.autocomplete = "off";
  input.className = select.className;
  input.placeholder = select.selectedOptions[0]?.textContent.trim() || select.options[0]?.textContent.trim() || t("Type to find");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-haspopup", "listbox");
  const label = originalParent.querySelector(`label[for="${CSS.escape(select.id)}"]`);
  if (label) input.setAttribute("aria-labelledby", label.id || (label.id = `own-picker-label-${index}`));
  else if (select.getAttribute("aria-label")) input.setAttribute("aria-label", select.getAttribute("aria-label"));
  else input.setAttribute("aria-label", t(select.name.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase())));
  const list = document.createElement("div");
  list.className = "counterparty-results";
  list.id = `${select.id || `own-picker-${index}`}-options`;
  while (document.getElementById(list.id)) list.id = `own-picker-${ownPickerId++}-options`;
  list.setAttribute("role", "listbox");
  list.hidden = true;
  input.setAttribute("aria-controls", list.id);
  wrapper.insertBefore(input, select);
  pickerHome(input).append(list);
  let active = -1;
  let searchVersion = 0;
  const entries = () => Array.from(select.options).filter((option) => !option.disabled && !option.hidden && !(option.parentElement?.tagName === "OPTGROUP" && (option.parentElement.disabled || option.parentElement.hidden)) && option.value !== "");
  const close = () => { ++searchVersion; list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; };
  const choose = (option) => {
    if (!option || select.disabled || !entries().includes(option)) return;
    select.value = option.value;
    input.value = option.textContent.trim();
    input.setCustomValidity("");
    select.dispatchEvent(new Event("change", { bubbles: true }));
    close();
  };
  // Guideline 3.6 A10.3 / A11: an empty choice ("Choose a category", value "") is a hint, never text to
  // delete; categories show under their L1 as a header (never "L1 › L2"); focus lists every choice.
  const groupOf = (option) => option.parentElement?.tagName === "OPTGROUP" ? option.parentElement.label : "";
  const shown = () => { const option = select.selectedOptions[0]; return option && option.value !== "" ? option.textContent.trim() : ""; };
  const place = () => {
    if (list.hidden) return;
    const rect = input.getBoundingClientRect();
    const width = Math.min(Math.max(230, rect.width), innerWidth - 16);
    const below = Math.max(0, innerHeight - rect.bottom - 12);
    const above = Math.max(0, rect.top - 12);
    const upward = below < Math.min(280, list.scrollHeight) && above > below;
    const height = Math.min(280, upward ? above : below);
    list.style.width = `${width}px`;
    list.style.maxHeight = `${Math.max(48, height)}px`;
    pinFixed(list, Math.max(8, Math.min(rect.left, innerWidth - width - 8)), upward ? Math.max(8, rect.top - Math.min(list.scrollHeight, height) - 4) : rect.bottom + 4);
  };
  document.addEventListener('scroll', () => { if (!list.hidden) place(); }, true);
  window.addEventListener('resize', place);
  const render = async (all = false) => {
    const version = ++searchVersion;
    const query = all ? "" : input.value.trim();
    const enabled = entries();
    const choices = enabled.map((option) => ({id: option.value, label: option.textContent.trim(), context: groupOf(option)}));
    list.hidden = true;
    const ids = await rankPicker(query, choices, pickerKind(select.name));
    if (version !== searchVersion || document.activeElement !== input) return;
    const byId = new Map(entries().map((option) => [option.value, option]));
    const matches = ids.map((id) => byId.get(id)).filter(Boolean).slice(0, all ? 5 : 80);
    list.replaceChildren();
    let lastGroup = "";
    matches.forEach((option, i) => {
      const group = groupOf(option);
      if (group && group !== lastGroup) {
        const header = document.createElement("div");
        header.className = "picker-group"; header.setAttribute("role", "presentation"); header.textContent = group;
        list.append(header);
      }
      lastGroup = group;
      const button = document.createElement("button");
      button.type = "button"; button.className = "counterparty-option"; button.setAttribute("role", "option");
      button.id = `${list.id}-${i}`; button.dataset.value = option.value; button.textContent = option.textContent.trim();
      button.setAttribute("aria-selected", String(option.value === select.value));
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => choose(option));
      list.append(button);
    });
    // data-add-href / data-add-label: the list's own way to add what is missing (a currency), never a sentence under it.
    if (select.dataset.addHref) {
      const add = document.createElement("a"); add.className = "counterparty-option picker-add"; add.setAttribute("role", "option");
      add.href = select.dataset.addHref; add.textContent = t(select.dataset.addLabel || "+ Add");
      list.append(add);
    }
    if (!matches.length && !select.dataset.addHref) { close(); return; }
    list.hidden = false; place(); input.setAttribute("aria-expanded", "true"); active = -1;
  };
  input.value = shown();
  input.disabled = select.disabled;
  // A required own-picker is validated on its visible field: the hidden <select> cannot show a message or take focus,
  // so the browser would block Save with nothing on screen. A form script turns this on and off (setPickerRequired).
  const checkChoice = () => input.setCustomValidity(input.required && !select.value ? t("Choose an option from the list.") : "");
  select.setPickerRequired = (on) => { select.required = false; input.required = on; checkChoice(); };
  input.addEventListener("input", () => { select.value = ""; checkChoice(); render(); });
  // Focus shows every choice and selects the current text, so typing replaces it instead of filtering by it.
  input.addEventListener("focus", () => { render(true); input.select(); });
  input.addEventListener("click", () => { if (list.hidden) { render(true); input.select(); } });
  input.addEventListener("keydown", (event) => {
    const options = list.querySelectorAll('[role="option"]');
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (list.hidden) render();
      const current = list.querySelectorAll('[role="option"]');
      if (!current.length) return;
      event.preventDefault();
      active = active < 0 ? (event.key === "ArrowDown" ? 0 : current.length - 1) : (active + (event.key === "ArrowDown" ? 1 : -1) + current.length) % current.length;
      current.forEach((item, i) => item.setAttribute("aria-selected", String(i === active)));
      input.setAttribute("aria-activedescendant", current[active].id); current[active].scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" && !list.hidden) {
      const target = active >= 0 ? options[active] : options[0];
      if (target) { event.preventDefault(); choose(Array.from(select.options).find((option) => option.value === target.dataset.value)); }
    } else if (event.key === "Escape") close();
  });
  select.addEventListener("change", () => { input.value = shown(); checkChoice(); });
  const disabledObserver = new MutationObserver(() => { input.disabled = select.disabled; });
  disabledObserver.observe(select, { attributes: true, attributeFilter: ["disabled"] });
  if (wasRequired) select.setPickerRequired(true);
  select.form?.addEventListener("reset", () => requestAnimationFrame(() => { input.value = shown(); close(); }));
  document.addEventListener("click", (event) => { if (!wrapper.contains(event.target) && !list.contains(event.target)) close(); });
  });

// Free-text fields backed by app-owned datalists use the same menu behavior;
// the named input remains the submitted value and the datalist remains fallback.
find("input[data-own-suggestions][list]").forEach((input) => {
  if (input.dataset.ownSuggestionsReady) return;
  const source = document.getElementById(input.getAttribute("list"));
  if (!source) return;
  input.dataset.ownSuggestionsReady = "1";
  const wrapper = document.createElement("div");
  wrapper.className = "counterparty-picker";
  input.before(wrapper); wrapper.append(input);
  const list = document.createElement("div");
  list.className = "counterparty-results";
  list.id = `${input.id || `own-suggestions-${ownPickerId++}`}-options`;
  while (document.getElementById(list.id)) list.id = `own-suggestions-${ownPickerId++}-options`;
  list.setAttribute("role", "listbox"); list.hidden = true; pickerHome(input).append(list);
  input.removeAttribute("list"); input.autocomplete = "off";
  input.setAttribute("role", "combobox"); input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-haspopup", "listbox"); input.setAttribute("aria-controls", list.id); input.setAttribute("aria-expanded", "false");
  let active = -1;
  let searchVersion = 0;
  const close = () => { ++searchVersion; list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; };
  // An option may carry a tile (data-mono / data-logo), a group heading (data-group) and search words
  // (data-label, data-search). data-allow-add on the input offers `+ Add "typed"` for a value not listed.
  const allowAdd = input.hasAttribute("data-allow-add");
  const monogram = (text) => {
    const words = String(text || "").trim().split(/[\s\-_/]+/).filter((word) => /^[\p{L}\p{N}]/u.test(word));
    if (!words.length) return "?";
    return (words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0]).toLocaleUpperCase();
  };
  const makeTile = (mono, logo, extra = "") => {
    const tile = document.createElement("span"); tile.className = `inst-tile ${extra}`.trim(); tile.setAttribute("aria-hidden", "true");
    if (logo) { const img = document.createElement("img"); img.src = logo; img.alt = ""; tile.append(img); } else tile.textContent = mono;
    return tile;
  };
  const rowsOf = () => Array.from(source.querySelectorAll("option")).map((option) => ({
    value: option.value, label: option.dataset.label || "", group: option.dataset.group || "", mono: option.dataset.mono || "", logo: option.dataset.logo || "", pick: option.dataset.pick || "",
    hay: `${option.value} ${option.dataset.label || ""} ${option.dataset.search || ""}`.toLocaleLowerCase(),
  }));
  // data-pick-target names a hidden field that records what the text was picked as (an account, a saved
  // counterparty, a new one); typing again clears it. data-suggest lists [{v, p}] shown first as "Suggested".
  const pickField = () => (input.dataset.pickTarget ? document.getElementById(input.dataset.pickTarget) : null);
  const setPick = (value) => { const field = pickField(); if (field) field.value = value; };
  const suggested = () => {
    try { return JSON.parse(input.dataset.suggest || "[]").map((item) => ({ value: item.v, pick: item.p, group: "Suggested", label: "", mono: "", logo: "", hay: item.v.toLocaleLowerCase() })); }
    catch (error) { return []; }
  };
  let wellTile = null;
  if (input.hasAttribute("data-tile-well")) {
    wellTile = makeTile("", "", "inst-well"); wrapper.classList.add("has-tile"); wrapper.prepend(wellTile);
  }
  const syncTile = () => {
    if (!wellTile) return;
    const typed = input.value.trim();
    const found = rowsOf().find((row) => row.value.toLocaleLowerCase() === typed.toLocaleLowerCase() || (row.label && row.label.toLocaleLowerCase() === typed.toLocaleLowerCase()));
    const fresh = makeTile(found ? found.mono : (typed ? monogram(typed) : ""), found ? found.logo : "", "inst-well");
    wellTile.replaceWith(fresh); wellTile = fresh; wellTile.hidden = !typed;
  };
  const render = async () => {
    const version = ++searchVersion;
    const rect = input.getBoundingClientRect();
    const query = input.value.trim();
    const candidates = [...suggested(), ...rowsOf()].filter((row, index, all) => row.value && all.findIndex((other) => (other.pick || other.value) === (row.pick || row.value)) === index);
    list.hidden = true;
    const ids = await rankPicker(query, candidates.map((row, index) => ({id: String(index), label: row.value, context: row.hay})), pickerKind(input.name));
    if (version !== searchVersion || document.activeElement !== input) return;
    const matches = ids.map((id) => candidates[Number(id)]).filter(Boolean).slice(0, query ? 50 : (allowAdd ? 8 : 5));
    list.replaceChildren();
    let lastGroup = "";
    matches.forEach((row, i) => {
      if (row.group && row.group !== lastGroup) {
        const heading = document.createElement("div"); heading.className = "picker-group"; heading.setAttribute("role", "presentation"); heading.textContent = t(row.group); list.append(heading);
      }
      lastGroup = row.group;
      const option = document.createElement("button"); option.type = "button"; option.className = "counterparty-option";
      option.setAttribute("role", "option"); option.id = `${list.id}-${i}`;
      if (row.mono || row.logo) option.append(makeTile(row.mono, row.logo));
      option.append(row.value);
      if (row.label && row.label !== row.value) { const hint = document.createElement("span"); hint.className = "counterparty-kind"; hint.textContent = row.label; option.append(hint); }
      option.addEventListener("mousedown", (event) => event.preventDefault());
      option.addEventListener("click", () => { input.value = row.value; setPick(row.pick); input.dispatchEvent(new Event("change", { bubbles: true })); close(); });
      list.append(option);
    });
    const typed = input.value.trim();
    if (allowAdd && typed && !rowsOf().some((row) => row.value.toLocaleLowerCase() === typed.toLocaleLowerCase())) {
      const add = document.createElement("button"); add.type = "button"; add.className = "counterparty-option picker-add";
      add.setAttribute("role", "option"); add.id = `${list.id}-add`; add.textContent = t(input.dataset.addLabel || '+ Add "{name}"', { name: typed });
      add.addEventListener("mousedown", (event) => event.preventDefault());
      add.addEventListener("click", async () => {
        input.value = typed; close();
        // data-create-url: the name is saved now (the import review), and every list offers it at once. If the save fails
        // the name stays "new" and is made when the rows post, as before.
        let made = null;
        if (input.dataset.createUrl) {
          input.setAttribute("aria-busy", "true");
          try {
            const body = new FormData();
            body.set("name", typed); body.set("kind", input.dataset.createKind || "");
            body.set("__session", document.querySelector('meta[name="lightning-session"]')?.content || document.querySelector('input[name="__session"]')?.value || "");
            const response = await fetch(input.dataset.createUrl, { method: "POST", body, headers: { "Accept": "application/json", "X-Requested-With": "fetch" } });
            if (response.ok) made = await response.json();
          } catch (error) { made = null; }
          input.removeAttribute("aria-busy");
        }
        if (made && made.pick) {
          input.value = made.name; setPick(made.pick);
          document.dispatchEvent(new CustomEvent("lightning:counterparty-created", { detail: { id: made.id, name: made.name, pick: made.pick, typed, from: input } }));
        } else setPick(`new:${typed}`);
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
      list.append(add);
    } else if (!matches.length) { close(); return; }
    list.style.width = `${Math.max(230, rect.width)}px`;
    list.hidden = false; input.setAttribute("aria-expanded", "true"); active = -1;
    pinFixed(list, Math.max(8, rect.left), rect.bottom + 4);
  };
  input.addEventListener("input", () => { setPick(""); syncTile(); }); input.addEventListener("change", syncTile); syncTile();
  input.addEventListener("input", render); input.addEventListener("focus", render);
  input.addEventListener("keydown", (event) => {
    const options = list.querySelectorAll('[role="option"]');
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (list.hidden) render();
      const current = list.querySelectorAll('[role="option"]');
      if (!current.length) return;
      event.preventDefault(); active = active < 0 ? (event.key === "ArrowDown" ? 0 : current.length - 1) : (active + (event.key === "ArrowDown" ? 1 : -1) + current.length) % current.length;
      current.forEach((option, i) => option.setAttribute("aria-selected", String(i === active)));
      input.setAttribute("aria-activedescendant", current[active].id);
    } else if (event.key === "Enter" && !list.hidden) {
      const current = list.querySelectorAll('[role="option"]');
      if (current.length) { event.preventDefault(); current[active >= 0 ? active : 0].click(); }
    } else if (event.key === "Escape") close();
  });
  document.addEventListener("click", (event) => { if (!wrapper.contains(event.target) && !list.contains(event.target)) close(); });
  });
};
initOwnDataPickers();
initAccountForm();

// A small page jump replaces a sticky header while reading a long register. It stays out of the way: hidden
// until the pointer nears the bottom-right corner (bottom-left in Arabic) or the page is being scrolled, and gone
// 1.5 s after. Keyboard focus shows it. Reduced motion: no fade (the CSS), the same show and hide.
(() => {
  const jump = document.getElementById("page-jump");
  if (!jump) return;
  const atEnd = () => window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 32;
  let hideTimer = 0;
  const wake = () => {
    jump.classList.add("is-visible");
    window.clearTimeout(hideTimer);
    hideTimer = window.setTimeout(() => { if (!jump.matches(":focus-visible, :hover")) jump.classList.remove("is-visible"); }, 1500);
  };
  const update = () => {
    const canMove = document.documentElement.scrollHeight > window.innerHeight + 180;
    const nearTop = window.scrollY < 180;
    jump.hidden = !canMove || (nearTop && atEnd());
    const toTop = !nearTop;
    jump.dataset.target = toTop ? "top" : "end";
    const label = t(toTop ? "Go to top of page" : "Go to end of page");
    jump.setAttribute("aria-label", label); jump.title = label;
    jump.classList.toggle("is-top", toTop);
  };
  jump.addEventListener("click", () => window.scrollTo({ top: jump.dataset.target === "top" ? 0 : document.documentElement.scrollHeight, behavior: "smooth" }));
  window.addEventListener("scroll", () => { update(); wake(); }, { passive: true });
  window.addEventListener("resize", update);
  // The proximity handler: the pointer within 140px of the corner wakes it.
  document.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch") return;
    const rtl = document.documentElement.dir === "rtl";
    const dx = rtl ? event.clientX : window.innerWidth - event.clientX;
    if (dx < 140 && window.innerHeight - event.clientY < 140) wake();
  }, { passive: true });
  jump.addEventListener("focus", wake);
  update();
})();

// The app's own question dialog, in place of the browser's confirm and alert boxes.
// ask({title, message, ok, cancel, tone}) resolves true for the action, false for Cancel or Escape.
// cancel: false leaves one button (a notice). tone: "danger" (a red action), "warn" or "info".
window.ask = (() => {
  const icons = {
    danger: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/>',
    warn: '<path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  };
  let queue = Promise.resolve();
  const open = ({ title, message = "", ok = t("OK"), cancel = t("Cancel"), tone = "info" }) => new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = `ask-dialog tone-${tone}`;
    dialog.setAttribute("aria-labelledby", "ask-title");
    if (message) dialog.setAttribute("aria-describedby", "ask-message");
    dialog.innerHTML = `<form method="dialog" class="ask-frame">
      <span class="ask-icon" aria-hidden="true"><svg viewBox="0 0 24 24">${icons[tone] || icons.info}</svg></span>
      <div class="ask-text"><h2 id="ask-title"></h2>${message ? '<p id="ask-message"></p>' : ""}</div>
      <div class="ask-actions">${cancel === false ? "" : '<button type="button" class="btn" data-ask="no"></button>'}
        <button type="submit" class="btn ${tone === "danger" ? "is-danger" : "primary"}" data-ask="yes"></button></div></form>`;
    dialog.querySelector("h2").textContent = t(title);
    if (message) dialog.querySelector("p").textContent = t(message);
    dialog.querySelector('[data-ask="yes"]').textContent = t(ok);
    const no = dialog.querySelector('[data-ask="no"]');
    if (no) no.textContent = t(cancel);
    const back = document.activeElement;
    let answer = false;
    const finish = () => { dialog.remove(); if (back?.isConnected) back.focus?.(); resolve(answer); };
    dialog.querySelector("form").addEventListener("submit", () => { answer = true; });
    no?.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener("close", finish, { once: true });
    document.body.append(dialog);
    dialog.showModal();
    // A destructive action never takes the first focus; Enter must not delete by accident.
    (tone === "danger" && no ? no : dialog.querySelector('[data-ask="yes"]')).focus();
  });
  return (options) => (queue = queue.then(() => open(typeof options === "string" ? { title: options } : options)));
})();
// "Delete this category? If it is in use, it is archived instead." → a title and a line under it.
window.askFromOptions = (text, extra = {}) => {
  const [title, ...rest] = t(text).split(/(?<=[?؟])\s+/);
  const danger = /\b(delete|remove)\b|احذف|امسح|شيل/i.test(title);
  return { title, message: rest.join(" "), ok: danger ? "Delete" : "OK", tone: danger ? "danger" : "info", ...extra };
};
window.askFrom = (text, extra = {}) => window.ask(window.askFromOptions(text, extra));
// askChoice({title, message, choices: [{label, value, primary}]}) resolves the chosen value, or null on Escape.
window.askChoice = ({ title, message = "", choices }) => new Promise((resolve) => {
  const dialog = document.createElement("dialog");
  dialog.className = "ask-dialog tone-info";
  dialog.setAttribute("aria-labelledby", "ask-title");
  dialog.innerHTML = '<form method="dialog" class="ask-frame ask-frame-plain"><div class="ask-text"><h2 id="ask-title"></h2><p id="ask-message"></p></div><div class="ask-actions"></div></form>';
  dialog.querySelector("h2").textContent = title;
  dialog.querySelector("p").textContent = message;
  if (!message) dialog.querySelector("p").remove();
  let answer = null;
  const actions = dialog.querySelector(".ask-actions");
  choices.forEach((choice) => {
    const button = document.createElement("button");
    button.type = "button"; button.className = choice.primary ? "btn primary" : "btn"; button.textContent = choice.label;
    button.addEventListener("click", () => { answer = choice.value; dialog.close(); });
    actions.append(button);
  });
  const back = document.activeElement;
  dialog.addEventListener("close", () => { dialog.remove(); if (back?.isConnected) back.focus?.(); resolve(answer); }, { once: true });
  document.body.append(dialog);
  dialog.showModal();
  actions.querySelector(".primary")?.focus();
});
// For a submit handler: stop this submit, ask, and send the same form (and button) again on yes.
window.confirmSubmit = (() => {
  const passed = new WeakSet();
  const asking = new WeakSet();
  return (event, options) => {
    const form = event.target;
    if (passed.has(form)) return true;
    event.preventDefault(); event.stopImmediatePropagation();
    if (asking.has(form)) return false;
    asking.add(form);
    const submitter = event.submitter?.form === form ? event.submitter : undefined;
    // Local form handlers can run before the delegated delete listener.
    // The caller's delete marker is authoritative in every language.
    if (form.matches("[data-confirm-delete]") || submitter?.matches("[data-confirm-delete]")) {
      const danger = { tone: "danger", ok: t("Delete") };
      options = typeof options === "string" ? window.askFromOptions(options, danger) : { ...options, ...danger };
    }
    (typeof options === "string" ? window.askFrom(options) : window.ask(options)).then((yes) => {
      asking.delete(form);
      if (!yes) return;
      passed.add(form);
      try { form.requestSubmit(submitter); } finally { passed.delete(form); }
    });
    return false;
  };
})();

// Date quick buttons (Today / Yesterday) — always yyyy-mm-dd.
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-date]");
  if (!btn) return;
  e.preventDefault();
  const input = document.getElementById(btn.dataset.target || "date");
  const d = new Date();
  d.setDate(d.getDate() - Number(btn.dataset.date || 0));
  const pad = (n) => String(n).padStart(2, "0");
  input.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
});

// Arabic-Indic digits (٠١٢ / ۰۱۲) and the Arabic decimal/thousands marks, as a phone keyboard types them.
const asciiDigits = (value) => String(value)
  .replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660))
  .replace(/[\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) - 0x06F0))
  .replace(/\u066B/g, ".").replace(/\u066C/g, ",");
// Date fields accept ISO, day/month/year, and day/month (current year), then normalize to ISO.
const isoDate = (value) => {
  const text = asciiDigits(value).trim();
  let year, month, day;
  let match = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (match) [, year, month, day] = match;
  else {
    match = text.match(/^(\d{1,2})\/(\d{1,2})(?:\/(\d{2}|\d{4}))?$/);
    if (!match) return null;
    [, day, month, year] = match;
    if (!year) {
      // A day/month without a year means this year, unless that is more than a
      // month ahead (typing 20/12 in January means last December).
      const now = new Date();
      const candidate = new Date(now.getFullYear(), Number(month) - 1, Number(day));
      const monthAhead = new Date(now.getFullYear(), now.getMonth() + 1, now.getDate());
      year = String(now.getFullYear() - (candidate > monthAhead ? 1 : 0));
    }
    else if (year.length === 2) year = `20${year}`;
  }
  const y = Number(year), m = Number(month), d = Number(day);
  const check = new Date(Date.UTC(y, m - 1, d));
  if (check.getUTCFullYear() !== y || check.getUTCMonth() !== m - 1 || check.getUTCDate() !== d) return null;
  return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
};
// Every date field is one component: a typeable ISO text box plus the same
// calendar button. Plain [data-smart-date] boxes and leftover native date
// inputs are upgraded here, so templates only need a text input.
const DATE_ERROR = "Use yyyy-mm-dd, like 2026-01-31.";
// Our calendar for every date field (App guideline · Fields): a month at a time, weeks from Monday,
// today ringed, the chosen day in Nile. It writes yyyy-mm-dd into the text field, which stays typeable.
const CALENDAR_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>';
const CALENDAR_LOCALE = document.documentElement.lang || "en";
const MONTH_NAMES = Array.from({length: 12}, (_, month) => new Intl.DateTimeFormat(CALENDAR_LOCALE, {month: "long"}).format(new Date(2024, month, 1)));
const WEEKDAY_NAMES = Array.from({length: 7}, (_, day) => new Intl.DateTimeFormat(CALENDAR_LOCALE, {weekday: "short"}).format(new Date(2024, 0, 1 + day)));
const isoOf = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const MONTH_SHORT = Array.from({length: 12}, (_, month) => new Intl.DateTimeFormat(CALENDAR_LOCALE, {month: "short"}).format(new Date(2024, month, 1)));
let openCal = null;
const closeCalendar = () => { if (!openCal) return; openCal.panel.remove(); openCal.button?.setAttribute("aria-expanded", "false"); openCal = null; };
const openCalendar = (text, button) => {
  if (openCal && openCal.text === text) { closeCalendar(); return; }
  closeCalendar();
  const picked = isoDate(text.value) || "";
  const today = isoOf(new Date());
  const start = picked || today;
  let view = new Date(Number(start.slice(0, 4)), Number(start.slice(5, 7)) - 1, 1);
  let focus = start;
  // The head's title climbs: days -> months (12, with the year and its ‹ ›) -> years (12 at a time).
  let level = "days", monthFocus = view.getMonth(), yearFocus = view.getFullYear();
  const panel = document.createElement("div");
  panel.className = "date-popup"; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", t("Choose a date"));
  const set = (value) => {
    text.value = value; text.setCustomValidity("");
    text.dispatchEvent(new Event("input", { bubbles: true }));
    text.dispatchEvent(new Event("change", { bubbles: true }));
    closeCalendar(); text.focus();
  };
  const foot = () => `<div class="date-popup-foot"><button type="button" data-today>${t("Today")}</button>${picked ? `<button type="button" data-clear>${t("Clear")}</button>` : ""}</div>`;
  const drawMonths = () => {
    const year = view.getFullYear(), nowYear = Number(today.slice(0, 4)), nowMonth = Number(today.slice(5, 7)) - 1;
    const pickedYear = picked ? Number(picked.slice(0, 4)) : null, pickedMonth = picked ? Number(picked.slice(5, 7)) - 1 : null;
    panel.innerHTML = `<div class="date-popup-head"><button type="button" data-year-step="-1" aria-label="${t("Previous year")}">‹</button>
      <button type="button" class="date-popup-title" data-level="years" aria-label="${t("Choose a year")}">${year}</button>
      <button type="button" data-year-step="1" aria-label="${t("Next year")}">›</button></div>
      <div class="date-popup-cells" role="grid">${MONTH_SHORT.map((name, m) => {
        const cls = ["date-popup-cell", year === nowYear && m === nowMonth ? "is-today" : "", year === pickedYear && m === pickedMonth ? "is-picked" : ""].join(" ");
        return `<button type="button" class="${cls}" data-month="${m}" tabindex="${m === monthFocus ? 0 : -1}" aria-label="${MONTH_NAMES[m]} ${year}"${year === pickedYear && m === pickedMonth ? ' aria-pressed="true"' : ""}>${name}</button>`;
      }).join("")}</div>${foot()}`;
  };
  const drawYears = () => {
    const first = Math.floor(yearFocus / 12) * 12, nowYear = Number(today.slice(0, 4)), pickedYear = picked ? Number(picked.slice(0, 4)) : null;
    panel.innerHTML = `<div class="date-popup-head"><button type="button" data-page-step="-1" aria-label="${t("Earlier years")}">‹</button>
      <b>${first}–${first + 11}</b><button type="button" data-page-step="1" aria-label="${t("Later years")}">›</button></div>
      <div class="date-popup-cells" role="grid">${Array.from({length: 12}, (_, i) => first + i).map((y) => {
        const cls = ["date-popup-cell", y === nowYear ? "is-today" : "", y === pickedYear ? "is-picked" : ""].join(" ");
        return `<button type="button" class="${cls}" data-year="${y}" tabindex="${y === yearFocus ? 0 : -1}" aria-label="${y}"${y === pickedYear ? ' aria-pressed="true"' : ""}>${y}</button>`;
      }).join("")}</div>${foot()}`;
  };
  const draw = () => {
    if (level === "months") { drawMonths(); return; }
    if (level === "years") { drawYears(); return; }
    const year = view.getFullYear(), month = view.getMonth();
    const first = new Date(year, month, 1);
    const lead = (first.getDay() + 6) % 7;  // Monday first
    const cells = [];
    for (let i = 0; i < 42; i += 1) cells.push(new Date(year, month, 1 - lead + i));
    const rows = cells[35].getMonth() !== month ? 5 : 6;
    panel.innerHTML = `<div class="date-popup-head"><button type="button" data-step="-1" aria-label="${t("Previous month")}">‹</button>
      <button type="button" class="date-popup-title" data-level="months" aria-label="${t("Choose a month")}">${MONTH_NAMES[month]} ${year}</button><button type="button" data-step="1" aria-label="${t("Next month")}">›</button></div>
      <div class="date-popup-grid" role="grid">${WEEKDAY_NAMES.map((d) => `<span class="date-popup-dow">${d}</span>`).join("")}
      ${cells.slice(0, rows * 7).map((d) => {
        const iso = isoOf(d);
        const cls = ["date-popup-day", d.getMonth() !== month ? "is-other" : "", iso === today ? "is-today" : "", iso === picked ? "is-picked" : ""].join(" ");
        return `<button type="button" class="${cls}" data-day="${iso}" tabindex="${iso === focus ? 0 : -1}" aria-label="${iso}"${iso === picked ? ' aria-pressed="true"' : ""}>${d.getDate()}</button>`;
      }).join("")}</div>${foot()}`;
  };
  const refocus = () => panel.querySelector('[tabindex="0"]')?.focus();
  const go = (next) => { level = next; if (next === "days") focus = isoOf(view); if (next === "months") monthFocus = view.getMonth(); if (next === "years") yearFocus = view.getFullYear(); draw(); refocus(); };
  const move = (days) => {
    const d = new Date(Number(focus.slice(0, 4)), Number(focus.slice(5, 7)) - 1, Number(focus.slice(8, 10)) + days);
    focus = isoOf(d);
    if (d.getMonth() !== view.getMonth() || d.getFullYear() !== view.getFullYear()) view = new Date(d.getFullYear(), d.getMonth(), 1);
    draw(); panel.querySelector(`[data-day="${focus}"]`)?.focus();
  };
  panel.addEventListener("mousedown", (e) => e.preventDefault());
  panel.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    e.stopPropagation();
    if (b.dataset.level) go(b.dataset.level);
    else if (b.dataset.yearStep) { view = new Date(view.getFullYear() + Number(b.dataset.yearStep), view.getMonth(), 1); focus = isoOf(view); draw(); }
    else if (b.dataset.pageStep) { yearFocus += 12 * Number(b.dataset.pageStep); draw(); }
    else if (b.dataset.month) { view = new Date(view.getFullYear(), Number(b.dataset.month), 1); focus = isoOf(view); go("days"); }
    else if (b.dataset.year) { view = new Date(Number(b.dataset.year), view.getMonth(), 1); focus = isoOf(view); go("months"); }
    else if (b.dataset.step) { view = new Date(view.getFullYear(), view.getMonth() + Number(b.dataset.step), 1); focus = isoOf(view); draw(); }
    else if (b.dataset.day) set(b.dataset.day);
    else if ("today" in b.dataset) set(today);
    else if ("clear" in b.dataset) set("");
  });
  panel.addEventListener("keydown", (e) => {
    const keys = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    if (e.key === "Escape") {
      e.preventDefault(); e.stopPropagation();
      if (level !== "days") go("days"); else { closeCalendar(); text.focus(); }
      return;
    }
    if (level === "months" || level === "years") {
      const grid = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 };
      const page = e.key === "PageUp" ? -1 : e.key === "PageDown" ? 1 : 0;
      if (!grid[e.key] && !page) return;
      e.preventDefault();
      if (level === "months") {
        const at = monthFocus + (grid[e.key] || 12 * page);
        view = new Date(view.getFullYear() + Math.floor(at / 12), view.getMonth(), 1); monthFocus = ((at % 12) + 12) % 12;
      } else yearFocus += grid[e.key] || 12 * page;
      draw(); refocus();
      return;
    }
    if (keys[e.key]) { e.preventDefault(); move(keys[e.key]); }
    else if (e.key === "PageUp" || e.key === "PageDown") {
      e.preventDefault();
      const d = new Date(Number(focus.slice(0, 4)), Number(focus.slice(5, 7)) - 1 + (e.key === "PageUp" ? -1 : 1), 1);
      view = d; focus = isoOf(d); draw(); panel.querySelector(`[data-day="${focus}"]`)?.focus();
    }
  });
  draw();
  (text.closest("dialog[open]") || document.body).append(panel);
  const rect = (text.closest(".iso-date-control") || text).getBoundingClientRect();
  const room = window.innerHeight - rect.bottom;
  panel.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - panel.offsetWidth - 8))}px`;
  if (room < panel.offsetHeight + 12 && rect.top > room) panel.style.top = `${Math.max(8, rect.top - panel.offsetHeight - 6)}px`;
  else panel.style.top = `${rect.bottom + 6}px`;
  openCal = { panel, text, button, at: Date.now() };
  button?.setAttribute("aria-expanded", "true");
  panel.querySelector(`[data-day="${focus}"]`)?.focus();
};
document.addEventListener("mousedown", (e) => {
  if (openCal && !openCal.panel.contains(e.target) && !e.target.closest("[data-open-date-picker]")) closeCalendar();
});
// A scroll closes the calendar, except the sheet scrolling the tapped field into view as it opens, or a day taking focus.
document.addEventListener("scroll", (e) => { if (openCal && !openCal.panel.contains(e.target) && !openCal.panel.contains(document.activeElement) && Date.now() - openCal.at > 400) closeCalendar(); }, true);
window.addEventListener("resize", closeCalendar);
// Alt+Down in a date field opens the calendar, as in the browser's own.
document.addEventListener("keydown", (e) => {
  if (e.altKey && e.key === "ArrowDown" && e.target.matches?.("[data-smart-date]")) {
    e.preventDefault();
    openCalendar(e.target, e.target.closest(".iso-date-control")?.querySelector("[data-open-date-picker]"));
  }
});

// Ctrl+Z undoes and Ctrl+Shift+Z (or Ctrl+Y) redoes the last action, except while typing in a field.
document.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
  const key = e.key.toLowerCase();
  const operation = key === "z" ? (e.shiftKey ? "redo" : "undo") : key === "y" ? "redo" : "";
  if (!operation || e.target.closest?.("input, textarea, select, [contenteditable]")) return;
  const button = document.querySelector(`[data-history="${operation}"]`);
  if (!button) return;
  e.preventDefault();
  button.click();
});

let dateFieldCount = 0;
const normalizeDateField = (input) => {
  if (!input.value.trim()) { input.setCustomValidity(""); return true; }
  const normalized = isoDate(input.value);
  if (normalized) { input.value = normalized; input.setCustomValidity(""); return true; }
  input.setCustomValidity(DATE_ERROR);
  return false;
};
const initDateFields = (root = document) => {
  root.querySelectorAll('input[type="date"]:not(.date-picker-native):not([data-native-date])').forEach((native) => {
    native.type = "text";
    native.dataset.smartDate = "";
    if (!native.placeholder) native.placeholder = t("yyyy-mm-dd");
    native.inputMode = "numeric";
    native.autocomplete = "off";
  });
  root.querySelectorAll("[data-smart-date]").forEach((input) => {
    if (document.documentElement.classList.contains("phone") && ["yyyy-mm-dd", t("yyyy-mm-dd")].includes(input.placeholder)) input.removeAttribute("placeholder");
    if (input.closest(".iso-date-control")) return;
    if (!input.id) input.id = `date-field-${++dateFieldCount}`;
    if (!input.placeholder && !document.documentElement.classList.contains("phone")) input.placeholder = t("yyyy-mm-dd");
    const wrapper = document.createElement("span");
    wrapper.className = "iso-date-control";
    input.parentNode.insertBefore(wrapper, input);
    const native = document.createElement("input");
    native.type = "date";
    native.className = "date-picker-native";
    native.tabIndex = -1;
    native.setAttribute("aria-hidden", "true");
    native.dataset.datePickerFor = input.id;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn small date-picker-button";
    button.dataset.openDatePicker = input.id;
    button.setAttribute("aria-label", t("Choose date"));
    button.title = t("Choose date");
    button.textContent = "▦";
    wrapper.append(input, native, button);
  });
  root.querySelectorAll("[data-smart-date]:not([data-date-ready])").forEach((input) => {
    input.dataset.dateReady = "1";
    input.addEventListener("input", () => input.setCustomValidity(""));
    input.addEventListener("click", () => openCalendar(input, null));
    input.addEventListener("focus", () => { if (input.dataset.openPickerOnFocus === "true") openCalendar(input, null); });
    input.addEventListener("blur", () => normalizeDateField(input));
    const form = input.form;
    if (form && !form.dataset.dateSubmitReady) {
      form.dataset.dateSubmitReady = "1";
      form.addEventListener("submit", (event) => {
        const bad = [...form.elements].find((field) => field.matches?.("[data-smart-date]") && !normalizeDateField(field));
        if (bad) { event.preventDefault(); event.stopImmediatePropagation(); showFieldError(bad); bad.focus(); }
      }, true);
    }
  });
  root.querySelectorAll("[data-open-date-picker]:not([data-picker-ready])").forEach((button) => {
    button.dataset.pickerReady = "1";
    button.innerHTML = CALENDAR_ICON;
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const control = button.closest(".iso-date-control") || root;
      const text = control.querySelector(`#${CSS.escape(button.dataset.openDatePicker)}`);
      if (text) openCalendar(text, button);
    });
  });
};
initDateFields();

// Register: click a row to edit it in place.
document.addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-href]");
  if (row && !e.target.closest("a, button, input, select")) {
    window.lightningRememberPlace();
    location.href = row.dataset.href;
  }
});

// An in-place register edit is a row, not a modal: leaving that row saves it.
// Capture pointerdown so a click on plain page space (which does not move focus)
// behaves just like leaving a normal field.
document.addEventListener("pointerdown", (event) => {
  const row = document.querySelector("tr.editing[data-txn]");
  if (!row || row.contains(event.target) || event.target.closest(".date-popup, .counterparty-results, .category-results, .transaction-select, #select-visible-header, #selection-tools, .own-record-results")) return;
  // A question open over the row ("Change 2 selected rows?") is answered, not treated as leaving the row (ticket 96).
  if (event.target.closest("dialog") || document.querySelector("dialog[open]")) return;
  const form = document.getElementById("f-edit");
  if (!form || form.dataset.submitting === "true" || !form.checkValidity()) return;
  event.preventDefault();
  form.requestSubmit();
}, true);

// Keep repeated Enter presses from posting the quick-add form twice.
document.addEventListener("submit", (event) => {
  const form = event.target;
  const confirmHost = form.matches("[data-confirm-delete]")
    ? form
    : event.submitter?.matches("[data-confirm-delete]")
      ? event.submitter
      : null;
  if (confirmHost) {
    const ids = new Set(new FormData(form).getAll("txn_ids"));
    const options = ids.size ? { title: (ids.size === 1 ? t("Delete 1 transaction?") : t("Delete {count} transactions?", {count: ids.size})),
      message: t("You can restore them from transaction history."), tone: "danger", ok: t("Delete") }
      : window.askFromOptions(confirmHost.dataset.confirmDelete || "Delete this transaction? You can restore it from its history page.",
        { tone: "danger", ok: t("Delete") });
    if (!window.confirmSubmit(event, options)) return;
  }
  if (!(form.matches("#f-new, #f-edit, .investment-entry-form"))) return;
  if (form.dataset.submitting === "true") { event.preventDefault(); return; }
  form.dataset.submitting = "true";
  const buttons = [...form.querySelectorAll("button")];
  if (form.id) buttons.push(...document.querySelectorAll(`button[form="${form.id}"]`));
  buttons.forEach((button) => { if (button !== event.submitter) button.disabled = true; });
});

// Select rows, use the right-click menu, and soft-delete one or many transactions.
// C08.5 selection bar. Runs again on a swapped phone page (lightning:page below).
const initPhoneBulk = () => {
  const phoneMerge = document.getElementById("phone-merge-selected");
  const phoneBulk = document.getElementById("phone-bulk");
  if (!phoneBulk || phoneBulk.dataset.bulkReady) return;
  phoneBulk.dataset.bulkReady = "1";
  const boxes = [...document.querySelectorAll('.transaction-select[form="phone-bulk"]:not(:disabled)')];
  const all = document.getElementById("phone-select-visible");
  const phoneCount = phoneBulk.querySelector(".phone-select-count");
  const updateMerge = () => {
    const ids = [...new Set(boxes.filter((box) => box.checked && !box.disabled).map((box) => box.value))];
    const count = phoneBulk.querySelector(".phone-select-count");
    if (count) count.textContent = t("{count} selected", {count: ids.length.toLocaleString(document.documentElement.lang)});
    if (phoneMerge) {
      phoneMerge.hidden = ids.length !== 2;
      if (ids.length === 2) phoneMerge.href = `/transactions/merge?keep=${encodeURIComponent(ids[0])}&drop=${encodeURIComponent(ids[1])}`;
    }
    phoneBulk.querySelectorAll("button").forEach((button) => { button.disabled = ids.length === 0; });
    if (phoneCount) phoneCount.textContent = t("{count} selected", {count: ids.length.toLocaleString(document.documentElement.lang)});
    if (all) {
      all.checked = boxes.length > 0 && boxes.every((box) => box.checked);
      all.indeterminate = ids.length > 0 && !all.checked;
    }
  };
  boxes.forEach((box) => box.addEventListener("change", () => {
    boxes.filter((item) => item.value === box.value).forEach((item) => { item.checked = box.checked; });
    updateMerge();
  }));
  all?.addEventListener("change", () => { boxes.forEach((box) => { box.checked = all.checked; }); updateMerge(); });
  phoneBulk.addEventListener("submit", (event) => {
    if (!boxes.some((box) => box.checked)) event.preventDefault();
  });
  updateMerge();
};
initPhoneBulk();
const ledger = document.querySelector(".ledger");
if (ledger) {
  const menu = document.getElementById("transaction-context-menu");
  const tools = document.getElementById("selection-tools");
  const count = document.getElementById("selection-count");
  const selectAll = document.getElementById("select-visible");
  const boxes = [...ledger.querySelectorAll(".transaction-select:not(:disabled)")];
  const byId = new Map();
  boxes.forEach((box) => { if (!byId.has(box.value)) byId.set(box.value, []); byId.get(box.value).push(box); });
  const editRow = document.querySelector("tr.editing[data-txn]");
  const selKey = (() => { const q = new URLSearchParams(location.search); ["edit", "acct", "pick", "msg"].forEach((k) => q.delete(k)); q.sort(); return `lightning-selection:${location.pathname}?${q}`; })();
  let matching = [];
  try { matching = JSON.parse(ledger.dataset.matchingIds || "[]").map(String); } catch (e) { matching = []; }
  const matchingSet = new Set(matching);
  const readSel = () => { try { const ids = JSON.parse(sessionStorage.getItem(selKey) || "[]"); return Array.isArray(ids) ? ids.filter((id) => typeof id === "string" && (byId.has(id) || matchingSet.has(id))) : []; } catch (e) { return []; } };
  const writeSel = (ids) => { try { ids.length ? sessionStorage.setItem(selKey, JSON.stringify(ids)) : sessionStorage.removeItem(selKey); } catch (e) {} };
  const selected = new Set(readSel());
  boxes.forEach((box) => { if (box.checked) selected.add(box.value); });
  const selectedIds = () => [...selected];
  const syncSelection = () => {
    const ids = selectedIds();
    boxes.forEach((box) => { box.checked = selected.has(box.value); });
    boxes.forEach((box) => box.closest("tr")?.setAttribute("aria-selected", String(box.checked)));
    writeSel(ids);
    if (tools) tools.hidden = ids.length === 0;
    const merge = document.getElementById("merge-selected");
    if (merge) merge.hidden = ids.length !== 2;
    if (count) count.textContent = t("{count} selected", {count: ids.length});
    const matchingButton = document.getElementById("select-matching");
    if (matchingButton) matchingButton.hidden = !(byId.size > 0 && [...byId.keys()].every((id) => selected.has(id))) || ids.length >= matching.length;
    const editSelected = document.getElementById("edit-selected");
    if (editSelected) editSelected.disabled = !boxes.some((box) => selected.has(box.value) && ["IN", "OUT"].includes(box.dataset.type));
    // F7 (r24): say what each tool will touch before it runs. Only income and spending rows take a category or an edit.
    const eligible = new Set(boxes.filter((box) => selected.has(box.value) && ["IN", "OUT"].includes(box.dataset.type)).map((box) => box.value)).size;
    const label = (id, text, values) => { const el = document.getElementById(id); if (el) el.textContent = t(text, values); };
    label("edit-selected", "Edit one by one");
    if (editSelected) editSelected.title = t("Opens the first of {count} editable rows; the next stays selected.", {count: eligible});
    const categoryButton = document.querySelector("#bulk-category-form button.btn");
    if (categoryButton) categoryButton.textContent = t("Set category for {count}", {count: eligible});
    // An action that would touch no selected row is not offered (IV-12W): "Set category for 0" beside "Delete 2" says nothing useful.
    const categoryForm = document.getElementById("bulk-category-form");
    if (categoryForm) categoryForm.hidden = eligible === 0;
    if (editSelected) editSelected.hidden = eligible === 0;
    label("export-selected", "Export {count}", {count: ids.length});
    label("delete-selected", "Delete {count}", {count: ids.length});
    const scope = document.getElementById("selection-scope");
    if (scope) scope.textContent = ids.length && eligible < ids.length
      ? t("A category applies to {eligible} of {count}; {skipped} (transfers, openings, investments) stay as they are.", {eligible, count: ids.length, skipped: ids.length - eligible}) : "";
    if (selectAll) {
      selectAll.checked = byId.size > 0 && selected.size === byId.size;
      selectAll.indeterminate = ids.length > 0 && !selectAll.checked;
    }
    if (menu && !menu.hidden && !menu.dataset.editing) menu.querySelector("[data-context-delete]").textContent =
      ids.length > 1 ? t("Delete {count} selected", {count: ids.length}) : t("Delete");
  };
  const deleteTransactions = (ids, backTo) => {
    if (!ids.length) return;
    window.ask({ title: t("Delete {subject}?", {subject: t(ids.length === 1 ? "this transaction" : "these transactions")}), tone: "danger", ok: t("Delete"),
      message: `${ids.length === 1 ? "It leaves" : "They leave"} the register and can be restored from transaction history.` }).then((yes) => { if (yes) send(ids, backTo); });
  };
  const send = (ids, backTo) => {
    const form = document.createElement("form");
    form.method = "post"; form.action = "/transactions/bulk-delete";
    const back = document.createElement("input"); back.type = "hidden"; back.name = "back"; back.value = backTo || location.pathname + location.search; form.append(back);
    const sessionToken = document.querySelector('meta[name="lightning-session"]')?.content;
    if (sessionToken) {
      const token = document.createElement("input");
      token.type = "hidden"; token.name = "__session"; token.value = sessionToken;
      form.append(token);
    }
    ids.forEach((id) => { const input = document.createElement("input"); input.type = "hidden"; input.name = "txn_ids"; input.value = id; form.append(input); });
    document.body.append(form); form.submit();
  };
  let anchor = null;
  ledger.addEventListener("click", (event) => {
    const box = event.target;
    if (!box.matches(".transaction-select:not(:disabled)")) return;
    if (event.shiftKey && anchor && boxes.includes(anchor)) {
      const first = boxes.indexOf(anchor), last = boxes.indexOf(box);
      boxes.slice(Math.min(first, last), Math.max(first, last) + 1).forEach((item) => {
        box.checked ? selected.add(item.value) : selected.delete(item.value);
      });
    }
    anchor = box;
  });
  ledger.addEventListener("change", (event) => {
    const box = event.target;
    if (!box.matches(".transaction-select:not(:disabled)")) return;
    box.checked ? selected.add(box.value) : selected.delete(box.value);
    syncSelection();
  });
  // Saving an edited row while others are ticked: ask whether the change is for this row or all of them.
  const editForm = document.getElementById("f-edit");
  if (editForm && editRow) {
    let decided = false;
    let asking = false;
    let bulkSaving = false;
    editForm.addEventListener("submit", (event) => {
      if (bulkSaving) { event.preventDefault(); event.stopImmediatePropagation(); return; }
      if (decided) return;
      const ticked = selectedIds();
      const ids = ticked;
      const sourceBox = editRow.querySelector(".transaction-select");
      if (!selected.has(editRow.dataset.txn) || ids.length < 2 || !["IN", "OUT"].includes(sourceBox?.dataset.type)) return;
      let original = {};
      try { original = JSON.parse(editRow.dataset.original || "{}"); } catch (e) {}
      const value = (name) => (editForm.elements[name]?.value ?? "").trim();
      const changed = ["date", "counterparty", "category", "notes", "whom"].filter((name) => value(name) !== String(original[name] ?? "").trim());
      if (value("category_choice") && value("category_choice") !== String(original.category_choice ?? "") && !changed.includes("category")) changed.push("category");
      if (!changed.length) return;
      event.preventDefault(); event.stopImmediatePropagation();
      if (asking) return;
      asking = true;
      const submitter = event.submitter;
      const num = (text) => { const n = Number(String(text ?? "").replace(/[^\d.\-]/g, "")); return Number.isFinite(n) ? n : String(text ?? "").trim(); };
      const singleRowChanged = num(value("amount")) !== num(original.amount)
        || (editForm.elements.account_id && value("account_id") !== String(original.account_id ?? ""));
      window.askChoice({
        title: t("Change {count} selected rows?", {count: ids.length}),
        message: singleRowChanged ? t("Save amount or account changes on this row first. These cannot be changed in bulk.") : "",
        choices: [{ label: t("Only this row"), value: "one", primary: Boolean(singleRowChanged) }, ...(!singleRowChanged ? [{ label: t("All {count} rows", {count: ids.length}), value: "all", primary: true }] : []), { label: t("Cancel"), value: "cancel" }],
      }).then((choice) => {
        asking = false;
        if (choice === "one") { decided = true; editForm.requestSubmit(submitter || undefined); return; }
        if (choice !== "all") return;
        const form = document.createElement("form"); form.method = "post"; form.action = "/transactions/bulk-edit";
        const add = (name, val) => { const input = document.createElement("input"); input.type = "hidden"; input.name = name; input.value = val; form.append(input); };
        const q = new URLSearchParams(location.search); ["edit", "acct"].forEach((k) => q.delete(k));
        add("back", location.pathname + (q.toString() ? `?${q}` : ""));
        const token = document.querySelector('meta[name="lightning-session"]')?.content;
        if (token) add("__session", token);
        ids.forEach((id) => add("txn_ids", id));
        changed.forEach((name) => add(name, value(name)));
        if (changed.includes("category")) add("category_choice", value("category_choice"));
        // Keep the editor and selection in place until the server confirms the whole batch.
        bulkSaving = true;
        editForm.dataset.submitting = "true";
        const notice = document.getElementById("bulk-edit-error") || document.createElement("div");
        notice.id = "bulk-edit-error"; notice.className = "flash error"; notice.setAttribute("role", "alert");
        notice.remove();
        fetch(new URL(form.getAttribute("action") || location.href, location.href).href, { method: "POST", body: new FormData(form),
          headers: { "Accept": "application/json", "X-Requested-With": "fetch" } }).then(async (response) => {
          // Session/journal middleware may redirect to its own explanation.
          if (response.redirected) { location.assign(response.url); return; }
          const result = await response.json();
          if (!response.ok || result.error) throw new Error(result.error || t("Could not save"));
          writeSel([]);
          location.assign(result.location);
        }).catch((error) => {
          notice.textContent = error.message === "Failed to fetch" || error instanceof SyntaxError
            ? t("Could not confirm this change. Check the register before trying again.") : t(error.message);
          document.querySelector(".ledger").before(notice);
          notice.scrollIntoView({block: "nearest"});
        }).finally(() => { bulkSaving = false; delete editForm.dataset.submitting; });
      });
    }, true);
  }
  selectAll?.addEventListener("change", () => { selected.clear(); if (selectAll.checked) byId.forEach((_, id) => selected.add(id)); syncSelection(); });
  document.getElementById("select-visible-header")?.addEventListener("click", (event) => {
    if (event.target.closest("input")) return;
    event.preventDefault();
    selectAll.checked = !selectAll.checked;
    selected.clear(); if (selectAll.checked) byId.forEach((_, id) => selected.add(id));
    syncSelection();
  });
  document.getElementById("delete-selected")?.addEventListener("click", () => deleteTransactions(selectedIds()));
  document.getElementById("export-matching")?.addEventListener("click", () => {
    (matching.length ? matching : [...byId.keys()]).forEach((id) => selected.add(id)); syncSelection(); document.getElementById("export-selected")?.click();
  });
  document.getElementById("select-matching")?.addEventListener("click", () => { matching.forEach((id) => selected.add(id)); syncSelection(); });
  document.getElementById("clear-selected")?.addEventListener("click", () => { selected.clear(); syncSelection(); });
  document.getElementById("edit-selected")?.addEventListener("click", () => {
    const box = boxes.find((item) => selected.has(item.value) && ["IN", "OUT"].includes(item.dataset.type));
    const row = box?.closest("tr");
    if (row?.dataset.href) location.href = row.dataset.href;
    else if (row === editRow) editForm?.elements.notes?.focus();
  });
  document.getElementById("merge-selected")?.addEventListener("click", () => {
    const ids = selectedIds();
    if (ids.length === 2) location.href = `/transactions/merge?keep=${encodeURIComponent(ids[0])}&drop=${encodeURIComponent(ids[1])}`;
  });
  // Bulk edit: the selected rows travel with the chosen category; the server keeps each row's
  // date, amount and counterparty and skips rows that cannot take the category.
  document.getElementById("bulk-category-form")?.addEventListener("submit", (event) => {
    const form = event.currentTarget;
    form.querySelectorAll('input[name="txn_ids"], input[name="back"]').forEach((input) => input.remove());
    const ids = selectedIds();
    if (!ids.length) { event.preventDefault(); return; }
    const back = document.createElement("input"); back.type = "hidden"; back.name = "back"; back.value = location.pathname + location.search; form.append(back);
    ids.forEach((id) => { const input = document.createElement("input"); input.type = "hidden"; input.name = "txn_ids"; input.value = id; form.append(input); });
  });
  // PC P7: a rule from the selection, prefilled with the first selected payee.
  // F7 (r24): replace text in the selected rows only; the server says what would change first, then the user confirms.
  const replaceForm = document.getElementById("replace-selected-form");
  replaceForm?.addEventListener("submit", async (event) => {
    if (replaceForm.dataset.confirmed) return;
    event.preventDefault();
    const ids = selectedIds();
    if (!ids.length) return;
    const body = new FormData(replaceForm);
    ids.forEach((id) => body.append("txn_ids", id));
    let plan;
    try { plan = await (await fetch("/transactions/find-replace/preview", { method: "POST", body })).json(); } catch (e) { return; }
    const find = String(body.get("find") || "");
    if (!plan.count) { await window.ask({ title: t("Nothing to replace"), message: t("None of the {count} selected rows contains “{find}”.", {count: ids.length, find}), ok: t("OK"), cancel: t("Close") }); return; }
    const examples = plan.examples.map(([from, to]) => `${from || "—"} → ${to || "—"}`).join("\n");
    const yes = await window.ask({ title: t("Replace in {count} of {selected} selected rows?", {count: plan.count, selected: ids.length}),
      message: `${examples}\n${t("Rows that do not contain the text stay as they are. You can undo this from transaction history.")}`, ok: t("Replace"), tone: "warn" });
    if (!yes) return;
    ids.forEach((id) => { const input = document.createElement("input"); input.type = "hidden"; input.name = "txn_ids"; input.value = id; replaceForm.append(input); });
    replaceForm.dataset.confirmed = "1";
    replaceForm.requestSubmit();
  });
  document.getElementById("rule-from-selected")?.addEventListener("click", () => {
    const box = selectedIds().map((id) => document.querySelector(`.transaction-select[value="${id}"]`)).find((b) => b?.dataset.payee);
    location.href = "/rules/new" + (box ? "?counterparty=" + encodeURIComponent(box.dataset.payee) : "");
  });
  document.getElementById("export-selected")?.addEventListener("click", () => {
    const ids = selectedIds();
    if (!ids.length) return;
    const form = document.createElement("form"); form.method = "post"; form.action = "/exports/transactions";
    const token = document.querySelector('meta[name="lightning-session"]')?.content;
    if (token) { const input = document.createElement("input"); input.type = "hidden"; input.name = "__session"; input.value = token; form.append(input); }
    ids.forEach((id) => { const input = document.createElement("input"); input.type = "hidden"; input.name = "txn_ids"; input.value = id; form.append(input); });
    document.body.append(form); form.submit(); setTimeout(() => form.remove(), 1000);
  });
  // One menu for every row action: the row being edited shows Save, Details, Cancel and Delete.
  const showItems = (editing) => {
    menu.querySelector("[data-context-save]").hidden = !editing;
    menu.querySelector("[data-context-cancel]").hidden = !editing;
    menu.querySelector("[data-context-edit]").hidden = editing;
    menu.querySelector("[data-context-repeat]").hidden = editing || !menu.dataset.repeat;
  };
  ledger.addEventListener("contextmenu", (event) => {
    if (!menu) return;
    const editing = event.target.closest("tr.editing[data-txn]");
    const row = editing || event.target.closest("tr[data-href]");
    if (!row) return;
    if (editing) {
      event.preventDefault();
      menu.dataset.editing = "1";
      menu.dataset.txn = editing.dataset.txn;
      menu.dataset.cancel = editing.dataset.cancelHref;
      menu.querySelector("[data-context-delete]").textContent = t("Delete");
    } else {
      const checkbox = row.querySelector(".transaction-select");
      if (!checkbox || checkbox.disabled) return;
      event.preventDefault();
      if (!checkbox.checked) { selected.clear(); selected.add(checkbox.value); }
      delete menu.dataset.editing;
      menu.dataset.href = row.dataset.href;
      menu.dataset.txn = checkbox.value;
      if (row.dataset.repeatAccount) {
        const d = row.dataset;
        const q = new URLSearchParams({ kind: d.repeatWay, amount: d.repeatAmount, counterparty: d.repeatPayee, category_id: d.repeatCategory, repeat: "1" });
        for (const [key, value] of [...q]) if (!value) q.delete(key);
        menu.dataset.repeat = `/accounts/${d.repeatAccount}/transaction/new?${q}`;
      } else delete menu.dataset.repeat;
    }
    showItems(Boolean(editing));
    menu.hidden = false;
    const x = Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8);
    const y = Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8);
    menu.style.left = `${Math.max(8, x)}px`; menu.style.top = `${Math.max(8, y)}px`;
    syncSelection();
  });
  menu?.querySelector("[data-context-edit]").addEventListener("click", () => { if (menu.dataset.href) location.href = menu.dataset.href; });
  menu?.querySelector("[data-context-repeat]").addEventListener("click", () => {  // Repeat: Add filled from this row, dated today (NF-7AM)
    menu.hidden = true;
    if (menu.dataset.repeat && window.lightningPopupOpen) window.lightningPopupOpen(menu.dataset.repeat);
    else if (menu.dataset.repeat) location.href = menu.dataset.repeat;
  });
  menu?.querySelector("[data-context-details]").addEventListener("click", () => { if (menu.dataset.txn) location.href = `/transactions/${menu.dataset.txn}`; });
  menu?.querySelector("[data-context-save]").addEventListener("click", () => { menu.hidden = true; document.getElementById("f-edit")?.requestSubmit(); });
  menu?.querySelector("[data-context-cancel]").addEventListener("click", () => { if (menu.dataset.cancel) location.href = menu.dataset.cancel; });
  menu?.querySelector("[data-context-delete]").addEventListener("click", () => {
    menu.hidden = true;
    if (menu.dataset.editing) deleteTransactions([menu.dataset.txn], menu.dataset.cancel);
    else deleteTransactions(selectedIds());
  });
  document.addEventListener("click", (event) => { if (menu && !event.target.closest("#transaction-context-menu")) menu.hidden = true; });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && menu) menu.hidden = true; });
  syncSelection();
}

// Money held for another person is shown in its own register column and needs an owner.
document.querySelectorAll(".category-input").forEach((category) => {
  const row = category.closest("tr");
  const cell = row?.querySelector(".whom-cell");
  const header = document.querySelector(".whom-head");
  const whomColumn = document.querySelector(".whom-column");
  const counterparty = row?.querySelector(".counterparty-input");
  const ledger = category.closest(".ledger");
  const internalAccounts = JSON.parse(ledger?.dataset.accounts || "[]");
  if (!cell) return;
  const syncWhom = () => {
    const isCustody = /money held for others/i.test(category.value);
    const target = counterparty?.value.trim() || "";
    const isTransfer = target.startsWith("↔") || internalAccounts.includes(target);
    const visible = isCustody || isTransfer;
    cell.classList.toggle("is-hidden", !visible);
    const anyVisible = document.querySelector(".whom-cell:not(.is-hidden)");
    if (header) header.classList.toggle("is-hidden", !anyVisible);
    if (whomColumn) whomColumn.style.width = anyVisible ? "12%" : "0";
    const input = cell.querySelector("input");
    if (input) {
      input.disabled = !visible;
      input.placeholder = t("Held for (if not you)");
    }
  };
  category.addEventListener("input", syncWhom);
  category.addEventListener("change", syncWhom);
  counterparty?.addEventListener("input", syncWhom);
  counterparty?.addEventListener("change", syncWhom);
  syncWhom();
});

// For brokerage trades, owner attribution is independent from the Counterparty field.
const initInvestmentEntry = (root = document) => root.querySelectorAll(".investment-entry-form").forEach((form) => {
  if (form.dataset.pageReady) return;
  form.dataset.pageReady = "1";
  const flag = form.querySelector('[name="is_others"]');
  const field = form.querySelector(".investment-owner-field");
  if (!flag || !field) return;
  const sync = () => { field.hidden = !flag.checked; };
  flag.addEventListener("change", sync);
  sync();
});
initInvestmentEntry();
const initInvestmentOwnership = (root = document) => root.querySelectorAll(".investment-ownership-form").forEach((form) => {
  if (form.dataset.pageReady) return;
  form.dataset.pageReady = "1";
  const flag = form.querySelector('[name="is_others"]');
  const field = form.querySelector(".investment-owner-field");
  if (!flag || !field) return;
  const sync = () => { field.hidden = !flag.checked; };
  flag.addEventListener("change", sync);
  sync();
});
initInvestmentOwnership();

// CSV rows use the same Whom rule as the register when custody is selected.
document.querySelectorAll(".import-category").forEach((category) => {
  const row = category.closest("tr");
  const cell = row?.querySelector(".import-whom-cell");
  const header = document.querySelector(".import-whom-head");
  const savedCounterparty = row?.querySelector('[name^="counterparty_choice_"]');
  const whom = cell?.querySelector("input");
  if (!cell) return;
  const sync = () => {
    const visible = /money held for others/i.test(category.selectedOptions[0]?.textContent || "");
    cell.classList.toggle("is-hidden", !visible);
    if (header) header.classList.toggle("is-hidden", !document.querySelector(".import-whom-cell:not(.is-hidden)"));
    if (whom) {
      whom.disabled = !visible;
      if (visible && !whom.value.trim() && savedCounterparty?.value.startsWith("existing:")) {
        whom.value = savedCounterparty.selectedOptions[0]?.dataset.name || "";
      }
    }
  };
  category.addEventListener("change", sync);
  savedCounterparty?.addEventListener("change", sync);
  sync();
});

// A transfer suggestion inferred from explicit note text is always opt-in.
document.querySelectorAll(".import-transfer-suggestion").forEach((button) => {
  button.addEventListener("click", () => {
    const row = button.closest("tr");
    const counterparty = row?.querySelector('[name^="counterparty_"]');
    if (!row || !counterparty) return;
    counterparty.value = button.dataset.target || "";
    const choice = row.querySelector('[name^="counterparty_choice_"]');
    if (choice) choice.value = "";
    const whom = row.querySelector('[name^="whom_"]');
    if (whom && !whom.disabled && button.dataset.owner) whom.value = button.dataset.owner;
    button.textContent = t("Transfer to {name} selected", {name: counterparty.value});
    button.disabled = true;
  });
});

// Register: Escape cancels an edit.
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const cancel = document.querySelector("[data-cancel]");
  if (cancel && e.target.closest("tr.editing")) {
    location.href = cancel.href;
  }
});
// Sums in amount fields: 120+35*2 becomes 190 when you leave the field or press Enter, so the
// saved amount is always one you saw. The server works the sum out (lightning/core/money.py:
// brackets, then ^, then * /, then + -; 2(3+5) is 2*(3+5)) and explains anything it refuses; the
// browser does no arithmetic.
const isSum = (value) => {
  const text = asciiDigits(value).trim();
  return /[-+*\/×÷xX^()=²³%[\]{}−–]/.test(/^[-+−–]/.test(text) ? text.slice(1) : text);  // as _SUM_MARKS in money.py
};
const pendingSum = (field) => isSum(field.value) && field.dataset.sumUnchecked !== field.value;
const workOutSum = async (input) => {
  const typed = input.value;
  if (!pendingSum(input)) return true;
  let answer;
  try {
    answer = await (await fetch(`/amount-sum?text=${encodeURIComponent(typed)}`)).json();
  } catch {
    input.dataset.sumUnchecked = typed;  // Save then sends it as typed; the server checks it again
    return false;
  }
  if (input.value !== typed) return false;  // typed on meanwhile
  if (answer.error) {
    input.setCustomValidity(answer.error);  // blocks Save and says why
    input.setAttribute("aria-invalid", "true");
    return false;
  }
  input.value = answer.value;
  input.dispatchEvent(new Event("input", { bubbles: true }));  // regroups 1,250.5 and clears any error
  return true;
};
// Save with a sum still in a field works it out first; the next Save sends the result.
document.addEventListener("submit", (event) => {
  const pending = [...(event.target.elements || [])].filter((field) => field.matches?.(moneySelector) && !field.disabled && pendingSum(field));
  if (!pending.length) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  Promise.all(pending.map(workOutSum)).then(() => { const bad = pending.find((field) => !field.checkValidity()); if (bad) { showFieldError(bad); bad.focus(); } });
}, true);
// Format money as the user types (1,000.50) while retaining a plain numeric value on submit.
const setupMoneyInput = (input) => {
  if (input.dataset.moneyFormatReady) return;
  input.dataset.moneyFormatReady = "true";
  input.setAttribute("autocomplete", "off");
  input.addEventListener("change", () => workOutSum(input));
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || !pendingSum(input)) return;
    event.preventDefault();  // the first Enter works the sum out; the next one saves
    event.stopImmediatePropagation();
    workOutSum(input).then(() => { if (!input.checkValidity()) { showFieldError(input); input.focus(); } });
  });
  input.addEventListener("input", () => {
    input.setCustomValidity("");
    input.removeAttribute("aria-invalid");
    if (isSum(input.value)) return;  // a sum stays exactly as typed until it is worked out
    const before = asciiDigits(input.value);
    const caret = input.selectionStart ?? before.length;
    const clean = (value) => {
      const filtered = value.replace(/,/g, "").replace(/[^0-9.\-]/g, "");
      const sign = filtered.startsWith("-") ? "-" : "";
      const unsigned = filtered.replace(/-/g, "");
      const decimalAt = unsigned.indexOf(".");
      const normalized = decimalAt < 0
        ? unsigned
        : unsigned.slice(0, decimalAt) + "." + unsigned.slice(decimalAt + 1).replace(/\./g, "");
      return sign + normalized;
    };
    const raw = clean(before);
    const charactersBeforeCaret = clean(before.slice(0, caret)).length;
    const sign = raw.startsWith("-") ? "-" : "";
    const unsigned = raw.replace(/-/g, "");
    const decimalAt = unsigned.indexOf(".");
    const whole = decimalAt < 0 ? unsigned : unsigned.slice(0, decimalAt);
    const fraction = decimalAt < 0 ? null : unsigned.slice(decimalAt + 1);
    const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    input.value = sign + grouped + (fraction !== null ? "." + fraction : "");
    if (document.activeElement === input) {
      let seen = 0, next = 0;
      while (next < input.value.length && seen < charactersBeforeCaret) {
        if (input.value[next] !== ",") seen++;
        next++;
      }
      input.setSelectionRange(next, next);
    }
  });
  if (input.value) input.dispatchEvent(new Event("input"));
};
const moneySelector = 'input.money-input, input[inputmode="decimal"]:not([type="number"])';
document.querySelectorAll(moneySelector).forEach(setupMoneyInput);
const moneyPopup = document.getElementById("app-popup");
if (moneyPopup) new MutationObserver(() => moneyPopup.querySelectorAll(moneySelector).forEach(setupMoneyInput))
  .observe(moneyPopup, {childList:true, subtree:true});

// Register: Counterparty and Category work together.
//  - an owned account as counterparty -> transfer: no category is needed
//  - a known counterparty -> fill its most recent category when available
// Show the per-unit price implied by the all-in total on investment trades.
const initTradeTotals = (root = document) => root.querySelectorAll(".trade-total").forEach((total) => {
  if (total.dataset.pageReady) return;
  total.dataset.pageReady = "1";
  const form = total.closest("form");
  const quantity = form?.querySelector(".quantity-input");
  const preview = form?.querySelector(".unit-price-preview");
  if (!quantity || !preview) return;
  const feeInput = form.querySelector('[name="fees"]');
  const feeChoice = form.querySelector('[data-fees-excluded]');
  const feeField = form.querySelector('[data-fees-field]');
  const syncFeeField = () => {
    if (!feeChoice || !feeField) return;
    // Fees can always be typed: inside the amount by default, on top of it when ticked.
    feeField.hidden = false;
    if (feeInput) feeInput.disabled = false;
    const feeLabel = feeField.querySelector("label");
    if (feeLabel) feeLabel.textContent = feeChoice.checked ? "Fees (on top of the amount)" : "Fees (inside the amount)";
  };
  const update = () => {
    const units = Number(quantity.value.replace(/,/g, ""));
    const amount = Number(total.value.replace(/,/g, ""));
    const fee = Number((feeInput?.value || "0").replace(/,/g, "")) || 0;
    const included = !feeChoice?.checked;
    const gross = amount + (included ? (form.dataset.tradeKind === "buy" ? -fee : fee) : 0);
    preview.value = units > 0 && gross > 0
      ? window.lightningNumber(gross / units, {min: 2, max: 6})
      : "";
  };
  quantity.addEventListener("input", update);
  total.addEventListener("input", update);
  feeInput?.addEventListener("input", update);
  feeChoice?.addEventListener("change", () => { syncFeeField(); update(); });
  syncFeeField();
  update();
});
initTradeTotals();

// Inline brokerage activity: pick an instrument, then sign units to buy or sell.
const initTradeCatalogue = () => {
  const tradeCatalogueNode = document.getElementById("trade-instrument-catalogue");
  if (!tradeCatalogueNode || tradeCatalogueNode.dataset.pageReady) return;
  tradeCatalogueNode.dataset.pageReady = "1";
  const instruments = JSON.parse(tradeCatalogueNode.textContent || "[]");
  const form = document.querySelector(".investment-entry-form");
  const search = document.getElementById("trade-instrument-search");
  const selectedKey = form.querySelector('[name="instrument_key"]');
  const selectedLabel = form.querySelector('[name="instrument_label"]');
  const results = document.getElementById("trade-instrument-results");
  const units = document.getElementById("investment-units");
  const unitsField = document.getElementById("investment-units-field");
  const action = document.getElementById("investment-action");
  const total = document.getElementById("investment-total");
  const dividendBasis = document.getElementById("investment-dividend-basis");
  const dividendBasisField = document.getElementById("investment-dividend-basis-field");
  const unitPrice = document.getElementById("investment-unit-price");
  const fees = document.getElementById("investment-fees");
  const feesExcluded = document.getElementById("investment-fees-included");
  const feesField = document.getElementById("investment-fees-field");
  const feesToggleField = document.getElementById("investment-fees-toggle-field");
  const priceField = document.getElementById("investment-price-field");
  const basis = form.querySelector('[name="price_basis"]');
  const amountLabel = document.getElementById("investment-total-label");
  const positionHint = document.getElementById("trade-position-hint");
  const payLine = document.getElementById("investment-pay-line");
  const addButton = form.querySelector(".investment-entry-submit");
  let selected = instruments.find((item) => item.key === selectedKey.value) || null;
  let activeResult = 0;
  const number = (input) => {
    const value = input.value.replace(/,/g, "").trim();
    if (!value || value === "-" || value === "+") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const formatted = (value, decimals = 6) => {
    if (!(value > 0)) return "";
    const maximumFractionDigits = Math.max(0, Number.isFinite(decimals) ? decimals : 6);
    const minimumFractionDigits = Math.min(2, maximumFractionDigits);
    return window.lightningNumber(value, {min: minimumFractionDigits, max: maximumFractionDigits});
  };
  const sync = () => {
    const actionKind = action?.value || "buy";
    const rawQty = number(units);
    const qty = actionKind === "dividend" || actionKind === "fee" || actionKind === "interest" || rawQty === null
      ? null : (actionKind === "sell" ? -rawQty : rawQty);
    const cashTotal = number(total);
    const price = number(unitPrice);
    const fee = number(fees) || 0;
    const included = !feesExcluded?.checked;
    const isDividend = actionKind === "dividend";
    const isCash = actionKind === "fee" || actionKind === "interest";  // the broker's own cash: no instrument
    const isMove = actionKind === "move";
    const isTrade = !isDividend && !isCash && !isMove;
    form.classList.toggle("is-dividend", isDividend);
    form.querySelectorAll("[data-trade-action]").forEach((button) => {
      const active = button.dataset.tradeAction === actionKind;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const showField = (node, on) => { if (node) node.hidden = !on; };
    const enable = (node, on) => { if (node) node.disabled = !on; };
    showField(unitsField, isTrade || isMove);
    enable(units, isTrade || isMove);
    showField(dividendBasisField, isDividend);
    showField(priceField, isTrade);
    showField(feesField, isTrade);
    showField(feesToggleField, isTrade);
    enable(fees, isTrade);
    enable(feesExcluded, isTrade);
    enable(unitPrice, isTrade);
    showField(total.closest(".field"), !isMove);
    enable(total, !isMove);
    showField(form.querySelector(".instrument-picker"), !isCash);
    if (search) search.required = !isCash;
    const taxField = document.getElementById("investment-tax-field");
    showField(taxField, isDividend);
    enable(taxField?.querySelector("input"), isDividend);
    const moveField = document.getElementById("investment-move-field");
    showField(moveField, isMove);
    enable(moveField?.querySelector("select"), isMove);
    ["investment-owner-field", "investment-cash-source"].forEach((name) => {
      const field = form.querySelector("." + name);
      showField(field, isTrade || isDividend);
      field?.querySelectorAll("input, select").forEach((node) => enable(node, isTrade || isDividend));
    });
    if (isDividend) {
      const perShare = dividendBasis?.value === "per_share";
      amountLabel.textContent = t(perShare ? "Amount per unit" : "Amount");
      total.placeholder = t(perShare ? "Amount per unit" : "Amount received");
    }
    else if (isCash) {
      amountLabel.textContent = t(actionKind === "fee" ? "Fee charged" : "Interest received");
      total.placeholder = "0.00";
    }
    else {
      amountLabel.textContent = t("Amount");
      total.placeholder = t(actionKind === "sell" ? "Amount received" : "Amount paid");
    }
    if (isTrade && qty !== null && Math.abs(qty) > 0) {
      if (basis.value === "unit_price" && price !== null) {
        const gross = Math.abs(qty) * price;
        total.value = formatted(gross + (included ? (qty > 0 ? fee : -fee) : 0), 2);
      } else if (cashTotal !== null) {
        const gross = cashTotal + (included ? (qty > 0 ? -fee : fee) : 0);
        unitPrice.value = formatted(gross / Math.abs(qty));
      }
    }
    let exceeds = false;
    if (selected && (actionKind === "sell" || actionKind === "move") && qty !== null) {
      const owned = Number(selected.holding || 0);
      exceeds = Math.abs(qty) > owned;
      positionHint.textContent = exceeds
        ? t("You have {owned} {unit}(s); you cannot sell {quantity}.", {owned: formatted(owned, selected.decimals), unit: selected.unit, quantity: formatted(Math.abs(qty), selected.decimals)})
        : t("You hold {quantity} {unit}(s) here.", {quantity: formatted(owned, selected.decimals), unit: selected.unit});
    } else if (selected && selected.note) {
      positionHint.textContent = "";
    }
    if (selected && selected.note) positionHint.textContent += ` ${t(selected.note)}`;
    // The live "You pay …" line (display only; the posted amounts are recomputed in Python).
    if (payLine) {
      const cur = form.dataset.currency || "";
      const money = (value) => window.lightningNumber(value, {min: 2, max: 2});
      let text = "";
      if (isDividend) {
        if (cashTotal !== null && dividendBasis?.value !== "per_share") text = t("You receive {cash} {currency}", {cash: money(cashTotal), currency: cur});
      } else if (isTrade && qty !== null && Math.abs(qty) > 0 && cashTotal !== null) {
        const buying = qty > 0;
        const gross = cashTotal + (included ? (buying ? -fee : fee) : 0);
        const cash = buying ? gross + fee : gross - fee;
        text = t(buying ? "You pay {cash} {currency} · {gross} for {units} units at {price} + {fees} fees"
                        : "You receive {cash} {currency} · {gross} for {units} units at {price} − {fees} fees",
                 {cash: money(cash), currency: cur, gross: money(gross), units: formatted(Math.abs(qty), selected ? selected.decimals : 6) || money(Math.abs(qty)),
                  price: money(gross / Math.abs(qty)), fees: money(fee)});
      }
      payLine.textContent = text;
    }
    addButton.disabled = exceeds;
  };
  const renderResults = () => {
    const query = search.value.trim().toLocaleLowerCase();
    results.replaceChildren();
    if (!query) { results.hidden = true; search.setAttribute("aria-expanded", "false"); return; }
    const matches = instruments.filter((item) => `${item.name} ${item.ticker} ${item.exchange || ""}`
      .toLocaleLowerCase().includes(query)).slice(0, 12);
    activeResult = 0;
    if (!matches.length) {
      const empty = document.createElement("div");
      empty.className = "instrument-result";
      empty.textContent = t("No match in your list. Choose a listed stock or fund.");
      results.append(empty);
    }
    matches.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button"; button.className = "instrument-result"; button.setAttribute("role", "option");
      button.setAttribute("aria-selected", index === activeResult ? "true" : "false");
      if (index === activeResult) button.classList.add("is-active");
      const name = document.createElement("span"); name.className = "instrument-name"; name.textContent = item.name;
      const ticker = document.createElement("small"); ticker.textContent = `${item.ticker}${item.exchange ? ` · ${item.exchange}` : ""}`;
      button.title = `${item.name} · ${ticker.textContent}`;
      button.append(name, ticker);
      const choose = () => {
        selected = item; selectedKey.value = item.key;
        selectedLabel.value = item.name;
        search.value = selectedLabel.value;
        results.hidden = true; search.setAttribute("aria-expanded", "false"); sync();
      };
      button.addEventListener("click", choose);
      button.dataset.instrumentIndex = String(index);
      results.append(button);
    });
    results.hidden = false; search.setAttribute("aria-expanded", "true");
  };
  search.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (results.hidden) renderResults();
      const options = [...results.querySelectorAll('[role="option"]')];
      if (!options.length) return;
      event.preventDefault();
      activeResult = (activeResult + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
      options.forEach((option, index) => {
        option.classList.toggle("is-active", index === activeResult);
        option.setAttribute("aria-selected", index === activeResult ? "true" : "false");
      });
    } else if (event.key === "Enter") {
      // Enter in the typeahead chooses a result; it must not submit the trade
      // form with an uncommitted, display-only instrument name.
      event.preventDefault();
      const options = [...results.querySelectorAll('[role="option"]')];
      if (options.length) options[Math.min(activeResult, options.length - 1)].click();
      else renderResults();
    } else if (event.key === "Escape" && !results.hidden) {
      event.preventDefault(); results.hidden = true; search.setAttribute("aria-expanded", "false");
    }
  });
  search.addEventListener("input", () => {
    selected = null; selectedKey.value = ""; selectedLabel.value = "";
    positionHint.textContent = ""; renderResults(); sync();
  });
  search.addEventListener("focus", renderResults);
  units.addEventListener("input", sync);
  action?.addEventListener("change", sync);
  form.querySelectorAll("[data-trade-action]").forEach((button) => {
    button.addEventListener("click", () => {
      action.value = button.dataset.tradeAction;
      action.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
  total.addEventListener("input", () => { basis.value = "total"; sync(); });
  dividendBasis?.addEventListener("change", sync);
  unitPrice.addEventListener("input", () => { basis.value = "unit_price"; sync(); });
  fees?.addEventListener("input", sync);
  feesExcluded?.addEventListener("change", sync);
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".instrument-picker")) {
      results.hidden = true; search.setAttribute("aria-expanded", "false");
    }
  });
  if (selected) { search.value = selectedLabel.value || selected.name; }
  sync();
};
initTradeCatalogue();

// Only physical gold uses a karat selector; funds have fund units, not gold purity.
const initKarat = () => {
  const investmentClass = document.getElementById("class_code");
  const karatField = document.getElementById("karat-field");
  if (!investmentClass || !karatField || investmentClass.dataset.pageReady) return;
  investmentClass.dataset.pageReady = "1";
  const syncKarat = () => { karatField.hidden = investmentClass.value !== "GOLD"; };
  investmentClass.addEventListener("change", syncKarat);
  syncKarat();
};
initKarat();

// Investment picker: filter the bundled EGX stock and Thndr fund catalogue.
const initInstrumentCatalogue = () => {
  const catalogueNode = document.getElementById("instrument-catalogue");
  if (!catalogueNode || catalogueNode.dataset.pageReady) return;
  catalogueNode.dataset.pageReady = "1";
  const catalogue = JSON.parse(catalogueNode.textContent || "[]");
  const search = document.getElementById("instrument-search");
  const results = document.getElementById("instrument-results");
  const selection = document.getElementById("instrument-selection");
  const form = search.closest("form");
  const name = form.querySelector('[name="name"]');
  const kind = form.querySelector('[name="class_code"]');
  const symbol = form.querySelector('[name="symbol"]');
  const venue = form.querySelector('[name="mic"]');
  let searchVersion = 0;
  search.addEventListener("keydown", (event) => { if (event.key === "Escape") { ++searchVersion; results.hidden = true; } });
  const render = async () => {
    const version = ++searchVersion;
    const query = search.value.trim();
    results.hidden = true;
    if (!query) { search.setAttribute("aria-expanded", "false"); return; }
    const ids = await rankPicker(query, catalogue.map((item, i) => ({id: String(i), label: item.name, code: item.ticker, context: item.exchange || ""})), "Investment");
    if (version !== searchVersion || document.activeElement !== search) return;
    results.replaceChildren();
    const matches = ids.map((id) => catalogue[Number(id)]).slice(0, 12);
    if (!matches.length) { const empty=document.createElement("div"); empty.className="instrument-result"; empty.textContent=t("No match. You can enter the investment details below."); results.append(empty); }
    matches.forEach((item) => {
      const button=document.createElement("button"); button.type="button"; button.className="instrument-result"; button.setAttribute("role","option");
      const label=document.createElement("span"); label.textContent=item.name; const ticker=document.createElement("small"); ticker.textContent=`${item.ticker}${item.exchange ? ` · ${item.exchange}` : ""}`; button.append(label,ticker);
      button.addEventListener("click", () => { name.value=item.name; kind.value=item.class_code; if(symbol) symbol.value=item.ticker; if(venue) venue.value=item.mic||""; search.value=`${item.name} · ${item.ticker}`; results.hidden=true; search.setAttribute("aria-expanded","false"); selection.textContent=t("Selected {name} ({ticker}). Review the details, then save.", {name: item.name, ticker: item.ticker}); }); results.append(button);
    }); results.hidden=false; search.setAttribute("aria-expanded","true");
  };
  search.addEventListener("input",render); search.addEventListener("focus",render);
  document.addEventListener("click",(event)=>{if(!event.target.closest(".instrument-picker")){results.hidden=true;search.setAttribute("aria-expanded","false");}});
};
initInstrumentCatalogue();

// Category picker: one alphabetized header per activity, with broad categories nested below.
const initCategoryCatalogue = () => {
  const categoryCatalogueNode = document.getElementById("category-catalogue");
  if (!categoryCatalogueNode || categoryCatalogueNode.dataset.pageReady) return;
  categoryCatalogueNode.dataset.pageReady = "1";
  const categories = JSON.parse(categoryCatalogueNode.textContent || "[]");
  const closeCategoryResults = (input, results) => {
    results.hidden = true;
    input.setAttribute("aria-expanded", "false");
  };
  document.querySelectorAll(".category-input").forEach((input) => {
    const results = document.getElementById(input.dataset.categoryResults);
    const formId = input.getAttribute("form");
    let activeIndex = -1;
    // Text that is exactly a category (the row's current choice) lists everything, so the user picks
    // again instead of first deleting it; only typed text filters.
    const isChoice = () => categories.some((item) => [item.name, item.label].includes(input.value.trim()));
    let searchVersion = 0;
    input.addEventListener("keydown", (event) => { if (event.key === "Escape") ++searchVersion; });
    const render = async () => {
      if (input.disabled || document.activeElement !== input) return;
      const version = ++searchVersion;
      const query = isChoice() ? "" : input.value.trim();
      results.hidden = true;
      const ids = await rankPicker(query, categories.map((item) => ({id: String(item.id), label: item.name, context: item.parent})), "Category");
      if (version !== searchVersion || document.activeElement !== input) return;
      results.replaceChildren();
      activeIndex = -1;
      const byId = new Map(categories.map((item) => [String(item.id), item]));
      const allMatches = ids.map((id) => byId.get(id)).filter(Boolean);
      const matches = allMatches.slice(0, input.value.trim() ? 30 : 5);
      const groups = new Map();
      matches.forEach((item) => {
        if (!groups.has(item.parent)) groups.set(item.parent, []);
        groups.get(item.parent).push(item);
      });
      [...groups.keys()].sort((a, b) => a.localeCompare(b)).forEach((parent) => {
        const heading = document.createElement("div");
        heading.className = "category-group-title";
        heading.textContent = t(parent);
        results.append(heading);
        groups.get(parent).sort((a, b) => (a.order || a.name).localeCompare(b.order || b.name)).forEach((item) => {
          const option = document.createElement("button");
          option.type = "button";
          option.className = "category-option" + (item.level === 3 ? " is-detail" : "");
          option.setAttribute("role", "option");
          option.textContent = t(item.name);
          option.addEventListener("mousedown", (event) => event.preventDefault());
          option.addEventListener("click", () => {
            // Two categories with one plain name (Personal and Work "Transportation") show their group in the text too, so
            // the text alone never means the wrong one; the hidden id below is what is saved.
            input.value = categories.filter((other) => other.name === item.name).length > 1 ? item.label : item.name;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dataset.autofilled = "false";
            const choice = document.createElement("input");
            choice.type = "hidden"; choice.name = "category_choice"; choice.value = String(item.id);
            choice.setAttribute("form", formId);
            input.closest(".category-picker").append(choice);
            closeCategoryResults(input, results);
          });
          results.append(option);
        });
      });
      if (allMatches.length > matches.length) {
        const hint = document.createElement("div");
        hint.className = "category-group-title";
        hint.textContent = t("Type to find more categories");
        results.append(hint);
      }
      if (!matches.length) {
        const empty = document.createElement("div");
        empty.className = "category-group-title";
        empty.textContent = t("No matching category");
        results.append(empty);
      }
      const rect = input.getBoundingClientRect();
      results.style.left = `${Math.max(8, rect.left)}px`;
      results.style.top = `${rect.bottom + 4}px`;
      results.style.width = `${Math.max(230, rect.width)}px`;
      results.hidden = false;
      input.setAttribute("aria-expanded", "true");
    };
    input.addEventListener("input", () => {
      document.querySelector(`input[type="hidden"][form="${formId}"][name="category_choice"]`)?.remove();
      input.dataset.autofilled = "false";
      render();
    });
    input.addEventListener("focus", render);
    input.addEventListener("focus", () => {
      if (input.dataset.autofilled === "true" || isChoice()) input.select();
    });
    input.addEventListener("click", () => {
      if (input.dataset.autofilled === "true" || isChoice()) { input.select(); render(); }
    });
    input.addEventListener("keydown", (event) => {
      const options = [...results.querySelectorAll(".category-option")];
      if (event.key === "Escape") closeCategoryResults(input, results);
      else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        if (results.hidden || !options.length) return;
        event.preventDefault();
        activeIndex = (activeIndex + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
        options.forEach((option, index) => {
          option.setAttribute("aria-selected", String(index === activeIndex));
          if (index === activeIndex) option.scrollIntoView({ block: "nearest" });
        });
      } else if (event.key === "Enter" && !results.hidden && options.length) {
        event.preventDefault();
        options[activeIndex < 0 ? 0 : activeIndex].click();
        document.querySelector(`[name="notes"][form="${formId}"]`)?.focus();
      }
    });
    input.addEventListener("blur", () => setTimeout(() => closeCategoryResults(input, results), 120));
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".category-picker")) {
      document.querySelectorAll(".category-results").forEach((results) => { results.hidden = true; });
    }
  });
};
initCategoryCatalogue();

if (ledger) {
  const known = JSON.parse(ledger.dataset.counterparties || "{}");
  const accounts = JSON.parse(ledger.dataset.accounts || "[]");
  const lastAccounts = JSON.parse(ledger.dataset.lastAccounts || "{}");
  const parties = Object.keys(known).sort((a, b) => a.localeCompare(b));
  document.querySelectorAll(".counterparty-input").forEach((counterparty) => {
    const form = counterparty.getAttribute("form");
    const category = document.querySelector(`.category-input[form="${form}"]`);
    const results = document.getElementById(counterparty.dataset.counterpartyResults);
    const accountPicker = document.querySelector(`select[name="account_id"][form="${form}"]`);
    // IV-12C: the first required field still empty after a name is picked (Account before Category).
    const nextEmpty = () => [accountPicker, category, document.querySelector(`[name="amount"][form="${form}"]`)]
      .find((field) => field && !field.disabled && !field.value.trim());
    const clearDecision = (name) => document.querySelector(`input[type="hidden"][form="${form}"][name="${name}"]`)?.remove();
    let searchVersion = 0;
    const closeResults = () => { ++searchVersion; if (results) { results.hidden = true; counterparty.setAttribute("aria-expanded", "false"); } };
    const sync = () => {
      const isTransfer = accounts.some((name) => name.toLocaleLowerCase() === counterparty.value.trim().toLocaleLowerCase());
      if (category) {
        category.disabled = isTransfer;
        category.placeholder = t(isTransfer ? "Transfer — no category needed" : "Category — type to search");
        if (isTransfer) category.value = "";
        else if (!category.value) {
          const knownName = parties.find((name) => name.toLocaleLowerCase() === counterparty.value.trim().toLocaleLowerCase());
          if (knownName && accountPicker && !accountPicker.value && lastAccounts[knownName]
              && [...accountPicker.options].some((option) => option.value === String(lastAccounts[knownName]))) accountPicker.value = String(lastAccounts[knownName]);
          const savedCategory = knownName ? known[knownName] : null;
          if (savedCategory?.id && savedCategory?.name) {
            category.value = savedCategory.name;
            category.dispatchEvent(new Event("input", { bubbles: true }));
            category.dataset.autofilled = "true";
            const choice = document.createElement("input");
            choice.type = "hidden"; choice.name = "category_choice"; choice.value = String(savedCategory.id);
            choice.setAttribute("form", form);
            category.closest(".category-picker").append(choice);
          }
        }
      }
    };
    const addGroup = (title, values, tag) => {
      if (!values.length) return;
      const heading = document.createElement("div"); heading.className = "counterparty-group-title"; heading.textContent = title; results.append(heading);
      values.forEach((name) => {
        const button = document.createElement("button"); button.type = "button"; button.className = "counterparty-option"; button.setAttribute("role", "option");
        const label = document.createElement("span"); label.textContent = name;
        const type = document.createElement("span"); type.className = "counterparty-kind"; type.textContent = tag;
        button.append(label, type);
        button.addEventListener("click", () => {
          // Picking a different name than what was typed teaches Lightning the typed spelling (an alias).
          const typed = counterparty.value.trim();
          const learn = typed && !name.toLocaleLowerCase().includes(typed.toLocaleLowerCase());
          counterparty.value = name; closeResults();
          counterparty.dispatchEvent(new Event("input", { bubbles: true }));
          counterparty.dispatchEvent(new Event("change", { bubbles: true }));
          if (learn) {
            const hint = document.createElement("input");
            hint.type = "hidden"; hint.name = "counterparty_typed"; hint.value = typed; hint.setAttribute("form", form);
            counterparty.closest(".counterparty-picker")?.append(hint);
          }
        });
        results.append(button);
      });
    };
    const renderResults = async () => {
      const version = ++searchVersion;
      const query = counterparty.value.trim();
      results.hidden = true;
      const limit = query ? 8 : 5;
      const [internalIds, partyIds] = await Promise.all([
        rankPicker(query, accounts.map((name, i) => ({id: String(i), label: name})), "Account"),
        rankPicker(query, parties.map((name, i) => ({id: String(i), label: name})), "Counterparty")]);
      if (version !== searchVersion || document.activeElement !== counterparty) return;
      results.replaceChildren();
      const internal = internalIds.map((id) => accounts[Number(id)]).slice(0, limit);
      const saved = partyIds.map((id) => parties[Number(id)]).slice(0, limit);
      const close = [];
      addGroup(t("Your accounts · internal transfers"), internal, t("Internal"));
      addGroup(t("People & businesses"), saved, t("External"));
      if (!internal.length && !saved.length && !close.length) {
        const empty = document.createElement("div"); empty.className = "counterparty-group-title";
        empty.textContent = t("No saved match · press Enter to review this new name"); results.append(empty);
      }
      const rect = counterparty.getBoundingClientRect();
      results.style.left = `${Math.max(8, rect.left)}px`;
      results.style.top = `${rect.bottom + 4}px`;
      results.style.width = `${Math.max(230, rect.width)}px`;
      results.hidden = false; counterparty.setAttribute("aria-expanded", "true");
    };
    counterparty.addEventListener("change", sync);
    counterparty.addEventListener("input", () => { clearDecision("counterparty_choice"); clearDecision("counterparty_typed"); sync(); renderResults(); });
    category?.addEventListener("input", () => {
      clearDecision("category_choice");
      delete category.dataset.autofilled;
    });
    counterparty.addEventListener("focus", renderResults);
    counterparty.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeResults();
      else if (event.key === "Enter" && !results.hidden) {
        const first = results.querySelector(".counterparty-option");
        if (first) {
          event.preventDefault();
          first.click();
          (nextEmpty() || category)?.focus();
        }
      }
    });
    sync();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".counterparty-picker")) document.querySelectorAll(".counterparty-results").forEach((results) => { results.hidden = true; });
  });
}

// Existing investment transactions save a complete valid edit on field commit.
const initAutosaveExisting = (root = document) => root.querySelectorAll("form[data-autosave-existing]").forEach((form) => {
  if (form.dataset.autosaveReady) return;
  form.dataset.autosaveReady = "1";
  const status = form.querySelector(".inline-save-status");
  let saved = new URLSearchParams(new FormData(form)).toString(), busy = false;
  const save = async () => {
    const data = new URLSearchParams(new FormData(form)), next = data.toString();
    if (busy || next === saved || !showFormErrors(form)) return;
    busy = true; status.textContent = t("Saving…");
    try {
      const response = await fetch(form.action || location.href, { method: "POST", body: data,
        headers: { "X-Requested-With": "fetch" } });
      if (!response.ok) throw Error((await response.text()) || "Could not save. Correct the value and retry.");
      saved = next; status.textContent = t("Saved");
    } catch (error) { status.textContent = t(error.message || "Could not save. Correct the value and retry."); }
    finally { busy = false; }
  };
  form.querySelectorAll("input,select,textarea").forEach((field) => {
    field.addEventListener("change", () => save());
    field.addEventListener("blur", save);
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && field.tagName !== "TEXTAREA") { event.preventDefault(); save(); }
    });
  });
});
initAutosaveExisting();

// Budget: one-click averages, per-category overrides, and typing means manual.
const initBudgetEditor = () => {
  const budgetForm = document.querySelector("#budget-editor-form");
  if (!budgetForm || budgetForm.dataset.editorReady) return;
  budgetForm.dataset.editorReady = "1";
  const setMode = (row, value) => {
    const mode = row.querySelector(".budget-mode");
    const amount = row.querySelector(".budget-amount");
    if (!mode || !amount) return;
    mode.value = value;
    amount.disabled = value !== "manual";
    if (value !== "manual") amount.value = "";
    amount.placeholder = value === "3" ? "Auto · 3 mo" : value === "6" ? "Auto · 6 mo" : "Enter amount";
  };
  budgetForm.querySelectorAll("[data-budget-mode]").forEach((button) => {
    button.addEventListener("click", () => setMode(button.closest("tr"), button.dataset.budgetMode));
  });
  budgetForm.querySelectorAll(".budget-amount").forEach((amount) => {
    amount.addEventListener("input", () => setMode(amount.closest("tr"), "manual"));
    const row = amount.closest("tr");
    setMode(row, row.querySelector(".budget-mode")?.value || "manual");
  });
  budgetForm.querySelectorAll("[data-budget-all]").forEach((button) => {
    button.addEventListener("click", () => {
      budgetForm.querySelectorAll("tbody tr").forEach((row) => setMode(row, button.dataset.budgetAll));
    });
  });
};
initBudgetEditor();

// Account form: show where the chosen type appears on the dashboard.
const initAccountType = () => {
  const typeSelect = document.getElementById("account_type");
  if (!typeSelect || typeSelect.dataset.groupsReady || typeSelect.closest("#app-popup-content")) return;
  typeSelect.dataset.groupsReady = "1";
  const groups = JSON.parse(typeSelect.dataset.groups || "{}");
  const target = document.getElementById("group_name");
  typeSelect.addEventListener("change", () => {
    if (target) target.textContent = groups[typeSelect.value] || "";
  });
};
initAccountType();

// Bank import: filter the canonical Counterparty chooser as the user types.
const initCounterpartyFilters = (root = document) => root.querySelectorAll("[data-counterparty-filter]").forEach((search) => {
  const select = document.getElementById(search.dataset.counterpartyFilter);
  if (!select || search.dataset.filterReady) return;
  search.dataset.filterReady = "1";
  search.addEventListener("input", () => {
    const query = search.value.trim().toLocaleLowerCase();
    Array.from(select.options).forEach((option) => {
      const fixed = option.value === "" || option.value === "new";
      option.hidden = !fixed && !option.textContent.toLocaleLowerCase().includes(query);
    });
  });
});
initCounterpartyFilters();

// Currency settings: filter the full ISO list as the user types.
const initCurrencySearch = (root = document) => root.querySelectorAll("[data-currency-search]").forEach((search) => {
  if (search.dataset.currencyReady) return;
  search.dataset.currencyReady = "1";
  const list = search.closest(".currency-settings")?.querySelector("[data-currency-list]");
  const empty = list?.querySelector("[data-currency-empty]");
  const filter = () => {
    const query = search.value.trim().toLocaleLowerCase();
    let shown = 0;
    list?.querySelectorAll("[data-currency-row]").forEach((row) => {
      const matches = !query || (row.dataset.search || "").includes(query);
      row.hidden = !matches;
      if (matches) shown += 1;
    });
    if (empty) empty.hidden = shown !== 0;
  };
  search.addEventListener("input", filter);
  filter();
});
initCurrencySearch();

// One contextual dialog for server-rendered forms and transaction details.
(() => {
  const dialog = document.getElementById("app-popup");
  const content = document.getElementById("app-popup-content");
  if (!dialog || !content) return;
  let opener = null;
  let baseUrl = location.href;
  let baseScroll = 0;
  let dirty = false;
  let activePopupUrl = null;

  // Changed means the form data differs from what the popup opened with (or a save just failed).
  // Formatting a field when the popup opens is not a change.
  let snapshot = "";
  const formState = () => [...content.querySelectorAll("form")]
    .map((form) => new URLSearchParams(new FormData(form)).toString()).join("&");
  const changed = () => dirty && formState() !== snapshot;
  let keepAfterError = false;
  let pageStale = false;  // a sheet that saved and showed another sheet (To sort): the page behind it has changed
  const unsaved = () => keepAfterError || changed();
  const askDiscard = () => window.ask({ title: "Discard your changes?", message: "What you typed in this form has not been saved.",
    ok: "Discard", cancel: "Keep editing", tone: "warn" });
  // Closing with unsaved changes asks first, then closes on yes; it returns false while it asks.
  const close = (goBack = true, force = false, reopening = false) => {
    if (!dialog.open) return false;
    if (!force && unsaved()) { askDiscard().then((yes) => { if (yes) close(goBack, true); }); return false; }
    dirty = false;
    keepAfterError = false;
    dialog.close();
    document.documentElement.classList.remove("sheet-open");
    document.body.classList.remove("popup-open");
    // A theme may give the popup an exit (theme-materials.css): it is then still on screen for a moment after close(),
    // so its content stays until it has gone; emptied at once it would leave as a blank shell. Reopened meanwhile: kept.
    const empty = () => { if (!dialog.open) content.replaceChildren(); };
    if (reopening || getComputedStyle(dialog).display === "none") content.replaceChildren();
    else setTimeout(empty, 260);
    if (goBack && history.state?.lightningPopup) history.back();
    else if (opener?.isConnected) opener.focus();
    window.scrollTo({ top: baseScroll, behavior: "instant" });
    if (pageStale && !reopening) {
      pageStale = false;
      // BV-12AF: a page with a part marked data-refresh takes the popup's change in place; any other page reloads.
      const reload = () => { sessionStorage.setItem("lightning-popup-scroll", String(baseScroll)); window.lightningReload(); };
      if (document.querySelector("[data-refresh]")) window.lightningRefreshInPlace().then((done) => { if (!done) reload(); }, reload);
      else reload();
    }
    return true;
  };
  // A sheet or popup shows the form's own content. The page's chrome around it (the undo and redo pills, the
  // phone's action row, the section tabs, the device line) belongs to the page, not to the form.
  const PAGE_CHROME = ".phone-page-actions, .section-bar, .history-form, .flash.device-line";
  const extract = (doc) => {
    const main = doc.querySelector("main.main") || doc.querySelector("main");
    main?.querySelectorAll(PAGE_CHROME).forEach((chrome) => chrome.remove());
    return main?.innerHTML || doc.body.innerHTML;
  };
  const show = (html, title = t("Dialog")) => {
    content.innerHTML = html;
    initFlashMessages(content, true);
    initOwnDataPickers(content);
    const h = content.querySelector("h1, h2, [data-popup-title]");
    if (h) { h.id = "app-popup-title"; dialog.setAttribute("aria-labelledby", h.id); }
    else { dialog.removeAttribute("aria-labelledby"); dialog.setAttribute("aria-label", t(title)); }
    dirty = false;
    keepAfterError = false;
    document.body.classList.add("popup-open");
    if (!dialog.open) dialog.showModal();
    document.documentElement.classList.add("sheet-open");  // the phone's tab bar steps aside (guideline C02.4)
    initPopupFields();
    initTransactionForm();
    snapshot = formState();
    // Money fields are formatted by a MutationObserver after this runs; take the snapshot after it.
    setTimeout(() => { snapshot = formState(); dirty = false; }, 0);
    requestAnimationFrame(() => (content.querySelector("[autofocus]") || content.querySelector("input:not([type=hidden]), select, button, a[href]") ||
      dialog.querySelector("[data-popup-close]")).focus());
  };
  const initPopupFields = () => {
    initDateFields(content);
    initAccountForm(content);
    content.querySelectorAll("[data-karat-reference]").forEach((select) => {
      if (select.dataset.popupKaratReady) return;
      select.dataset.popupKaratReady = "1";
      const karat = content.querySelector("#karat");
      const filter = () => {
        const selected = select.value;
        let kept = false;
        [...select.options].forEach((option) => {
          const match = !option.value || option.dataset.karat === karat?.value;
          option.hidden = !match; option.disabled = !match;
          if (option.value === selected && match) kept = true;
        });
        if (!kept) select.value = "";
      };
      karat?.addEventListener("change", filter); filter();
    });
    content.querySelectorAll("[data-popup-autosave]").forEach((form) => {
      if (form.dataset.popupAutosaveReady) return;
      form.dataset.popupAutosaveReady = "1";
      const status = form.querySelector("[data-autosave-status],.inline-save-status");
      let saved = new URLSearchParams(new FormData(form)).toString();
      let busy = false;
      const save = async () => {
        const data = new URLSearchParams(new FormData(form));
        const next = data.toString();
        if (busy || next === saved || !showFormErrors(form)) return;
        busy = true;
        if (status) status.textContent = t("Saving…");
        let succeeded = false;
        try {
          const response = await fetch(form.action || location.href, { method: "POST", body: data,
            headers: { "X-Requested-With": "fetch" } });
          if (!response.ok) throw Error((await response.text()) || "Could not save. Correct the value and retry.");
          saved = next;
          succeeded = true;
          if (status) status.textContent = t("Saved");
          if (new URLSearchParams(new FormData(form)).toString() === saved) dirty = false;
        } catch (error) {
          if (status) status.textContent = t(error.message || "Could not save. Correct the value and retry.");
        } finally {
          busy = false;
          if (succeeded && new URLSearchParams(new FormData(form)).toString() !== saved) queueMicrotask(save);
        }
      };
      form.querySelectorAll("input,select,textarea").forEach((field) => {
        field.addEventListener("change", () => queueMicrotask(save));
        field.addEventListener("blur", save);
        field.addEventListener("keydown", (event) => {
          if (event.key === "Enter" && field.tagName !== "TEXTAREA") { event.preventDefault(); save(); }
        });
      });
    });
  };
  const initTransactionForm = () => {
    const root = content.querySelector("[data-transaction-form]");
    const form = root?.querySelector("form");
    if (!form || form.dataset.popupInitialized) return;
    form.dataset.popupInitialized = "1";
    const kinds = [...form.querySelectorAll('[name="kind"]')];
    const amount = form.querySelector('[name="amount"]');
    const owner = form.querySelector('[name="owner_id"]');
    const note = form.querySelector('[data-transaction-effect]');
    const category = form.querySelector('[name="category_id"]');
    const destination = form.querySelector('[name="to_account_id"]');
    const update = () => {
      const kind = kinds.find((input) => input.checked)?.value || "out";
      form.querySelectorAll(".transfer-only").forEach((field) => field.hidden = kind !== "transfer");
      form.querySelectorAll(".money-only").forEach((field) => field.hidden = kind === "transfer");
      if (category) {
        let cleared = false;
        [...category.options].forEach((option) => {
          option.hidden = kind === "out" && option.value !== "" && option.dataset.movement !== "OUTFLOW";  // in: income, or a refund
          if (option.hidden && option.selected) { category.value = ""; cleared = true; }
        });
        category.disabled = kind === "transfer";
        // The own-picker shows the message on its visible field; a plain select carries `required` itself.
        if (category.setPickerRequired) category.setPickerRequired(kind !== "transfer");
        else category.required = kind !== "transfer";
        if (cleared) category.dispatchEvent(new Event("change", { bubbles: true }));  // the picker's text follows
      }
      if (destination) {
        if (destination.setPickerRequired) destination.setPickerRequired(kind === "transfer");
        else destination.required = kind === "transfer";
      }
      const value = Number((amount.value || "").replaceAll(",", ""));
      const shown = Number.isFinite(value) && value > 0 ? window.lightningNumber(value) : "…";
      const account = root.dataset.accountName, currency = root.dataset.currency;
      if (kind === "transfer") {
        const to = destination.selectedOptions[0]?.textContent || "the selected account";
        if (note) note.textContent = t("Cash in {account} decreases by {amount} {currency}; cash in {target} increases by the same amount.", {account, amount: shown, currency, target: to});
      } else {
        const own = owner.selectedOptions[0]?.textContent || "you";
        if (note) note.textContent = t("Cash in {account} {direction} by {amount} {currency}; balance owned by {owner}.", {account, direction: t(kind === "out" ? "decreases" : "increases"), amount: shown, currency, owner: own});
      }
    };
    form.addEventListener("input", update); form.addEventListener("change", update); update();
    // A counterparty with a learned category (its own, a rule's, or the one it is usually filed under; each
    // datalist option carries it as data-category) fills an empty Category. A choice you made stays.
    const counterparty = form.querySelector('[name="counterparty"]');
    const known = form.querySelector("datalist");
    let filled = "";
    counterparty?.addEventListener("change", () => {
      if (!category || category.disabled || !known || (category.value && category.value !== filled)) return;
      const typed = counterparty.value.trim().toLocaleLowerCase();
      const match = [...known.options].find((option) => option.value.toLocaleLowerCase() === typed);
      const usualAccount = match?.dataset.account || "";
      const accountChip = form.querySelector("[data-account-chip]");
      const wanted = match?.dataset.category || "";
      if (usualAccount && accountChip && accountChip.value !== usualAccount && [...accountChip.options].some((o) => o.value === usualAccount)) {
        // The payee's usual account (3 of its last 5): the sheet reopens for it, with what was typed carried over.
        const want = wanted && [...category.options].some((item) => item.value === wanted && !item.hidden) ? wanted : "";
        if (want) category.value = want;
        accountChip.value = usualAccount;
        accountChip.dispatchEvent(new Event("change", { bubbles: true }));
        return;
      }
      const option = wanted && [...category.options].find((item) => item.value === wanted && !item.hidden);
      if (!option) return;
      filled = wanted;
      category.value = wanted;
      category.dispatchEvent(new Event("change", { bubbles: true }));
    });
  };
  const openUrl = async (url, trigger, push = true) => {
    const replacing = dialog.open;
    const priorOpener = opener;
    if (dialog.open && unsaved() && !(await askDiscard())) return;
    if (dialog.open) close(false, true, true);
    opener = replacing ? priorOpener : (trigger || document.activeElement);
    if (!replacing) {
      baseUrl = location.href;
      baseScroll = window.scrollY;
    }
    const destination = new URL(url, location.href);
    if (!destination.searchParams.has("return_to")) destination.searchParams.set("return_to", baseUrl);
    const response = await fetch(destination.href, { headers: { "X-Lightning-Popup": "1" } });
    const doc = new DOMParser().parseFromString(await response.text(), "text/html");
    show(extract(doc), doc.title);
    content.querySelectorAll("form:not([action])").forEach((form) => { form.action = destination.href; });
    if (push) {
      activePopupUrl = destination.href;
      const state = { lightningPopup: true, baseUrl, baseScroll };
      if (replacing) history.replaceState(state, "", destination.href);
      else history.pushState(state, "", destination.href);
    }
  };

  // The Add sheet changes its account by opening the same sheet for the other one, with what was typed carried over.
  window.lightningPopupOpen = (url) => { dirty = false; keepAfterError = false; return openUrl(url, opener || document.activeElement); };

  document.addEventListener("click", (event) => {
    const closeButton = event.target.closest("[data-popup-close]");
    if (closeButton) { event.preventDefault(); close(); return; }
    // Full page: the same address outside the popup; its Back button returns here (return_to).
    const expand = event.target.closest("[data-popup-expand]");
    if (expand) {
      event.preventDefault();
      if (!activePopupUrl) return;
      (unsaved() ? askDiscard() : Promise.resolve(true)).then((yes) => {
        if (!yes) return;
        const target = new URL(activePopupUrl, location.href);
        target.searchParams.delete("popup");
        dirty = false; keepAfterError = false;
        location.href = target.href;
      });
      return;
    }
    const link = event.target.closest("a[data-popup-open]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    openUrl(link.href, link).catch(() => { location.href = link.href; });
  });
  dialog.addEventListener("close", () => document.documentElement.classList.remove("sheet-open"));
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) close();
  });
  content.addEventListener("input", (event) => {
    if (event.target.closest("form")) dirty = true;
  });
  content.addEventListener("change", (event) => {
    if (event.target.closest("form")) dirty = true;
  });
  content.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const focusable = [...content.querySelectorAll("a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])")];
    if (!focusable.length) return;
    if (event.shiftKey && document.activeElement === focusable[0]) { event.preventDefault(); focusable.at(-1).focus(); }
    else if (!event.shiftKey && document.activeElement === focusable.at(-1)) { event.preventDefault(); focusable[0].focus(); }
  });
  content.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.target === "_blank" || form.method.toLowerCase() === "get") return;
    event.preventDefault();
    const submit = event.submitter || form.querySelector("button[type=submit]:not([form]),button:not([type])") || form.querySelector("button[type=submit]");
    const again = !!(event.submitter && event.submitter.name === "again");  // Save and add another: the sheet comes back (NF-7AM)
    const status = content.querySelector("[data-popup-status]");
    if (status) status.textContent = t("Saving…");
    if (submit) submit.disabled = true;
    try {
      const response = await fetch(form.action || location.href, {
        method: (form.method || "POST").toUpperCase(), body: again ? new FormData(form, event.submitter) : new FormData(form),
        headers: { "X-Lightning-Popup": "1" }, redirect: "follow"
      });
      const text = await response.text();
      if (response.status >= 400) {
        const doc = new DOMParser().parseFromString(text, "text/html");
        show(extract(doc), doc.title);
        keepAfterError = true;  // the form holds what the user typed; closing would lose it
        const firstError = content.querySelector(".flash.error,.error,[aria-invalid=true]");
        firstError?.focus?.();
      } else {
        const msg = new URL(response.url).searchParams.get("msg");
        const goToResponse = form.dataset.popupReturn === "response";
        const keepInPopup = form.dataset.popupReturn === "popup" || again;
        if (keepInPopup) {
          const doc = new DOMParser().parseFromString(text, "text/html");
          show(extract(doc), doc.title);
          pageStale = true;
          activePopupUrl = response.url;
          history.pushState({ lightningPopup: true, baseUrl, baseScroll }, "", response.url);
          return;
        }
        const next = new URL(goToResponse ? response.url : baseUrl, location.href);
        // A phone entry or category chip (data-phone-toast): the page behind reloads with the message in its address, so the
        // server draws "Saved" with Undo as the toast above the tab bar, and you stay where you were.
        const toast = form.hasAttribute("data-phone-toast") && msg && !goToResponse;
        if (toast) next.searchParams.set("msg", msg);
        pageStale = false;  // this save reloads the page itself
        close(false, true);  // saved: nothing to discard
        history.replaceState(null, "", next.pathname + next.search + next.hash);
        const inPlace = !goToResponse && !toast && document.querySelector("[data-refresh]");
        if (msg && !toast && !inPlace) sessionStorage.setItem("lightning-popup-success", msg);
        const reload = () => {
          if (msg && !toast) sessionStorage.setItem("lightning-popup-success", msg);
          sessionStorage.setItem("lightning-popup-scroll", String(baseScroll));
          window.lightningReload();
        };
        if (goToResponse) location.href = next.href;
        else if (inPlace) {
          // BV-12AF: the page behind takes the change in place, with the server's message and its Undo.
          const here = new URL(location.href);
          if (msg) here.searchParams.set("msg", msg);
          window.lightningRefreshInPlace(here.href).then((done) => { if (!done) reload(); }, reload);
        } else reload();
      }
    } catch (error) {
      if (status) status.textContent = t("Could not save. Check your connection and try again.");
      if (submit) submit.disabled = false;
    }
  });
  window.addEventListener("popstate", () => {
    if (!dialog.open) return;
    if (unsaved()) {
      // Stay on the popup's address while asking; on yes, close and step back for real.
      history.pushState({ lightningPopup: true, baseUrl, baseScroll }, "", activePopupUrl || location.href);
      askDiscard().then((yes) => { if (yes) close(true, true); });
      return;
    }
    close(false, true);
    const base = new URL(baseUrl, location.href);
    if (base.pathname + base.search + base.hash !== location.pathname + location.search + location.hash) window.lightningReload();
  });
  // Opening a register row for editing reloads the page with ?edit=; keep the place instead of jumping to the top.
  document.addEventListener("click", (event) => {
    const link = event.target.closest?.("a[href*='edit=']");
    if (!link || event.defaultPrevented || event.button || event.ctrlKey || event.metaKey || event.shiftKey) return;
    try { if (new URL(link.href, location.href).searchParams.has("edit")) sessionStorage.setItem("lightning-popup-scroll", String(window.scrollY)); } catch (error) { /* keep the default */ }
  });
  const savedScroll = sessionStorage.getItem("lightning-popup-scroll");
  if (savedScroll !== null) {
    sessionStorage.removeItem("lightning-popup-scroll");
    requestAnimationFrame(() => window.scrollTo({ top: Number(savedScroll) || 0, behavior: "instant" }));
  }
  const success = sessionStorage.getItem("lightning-popup-success");
  if (success) {
    sessionStorage.removeItem("lightning-popup-success");
    // Confirm what the popup just did, even on pages that had no message of their own.
    let flash = document.querySelector(".flash:not(.error):not(.device-line)");
    if (!flash) {
      flash = document.createElement("div");
      flash.className = "flash";
      flash.setAttribute("role", "status");
      const topbar = document.querySelector("main .topbar");
      if (topbar) topbar.after(flash); else document.querySelector("main")?.prepend(flash);
    }
    flash.hidden = false;
    // Phone notices carry Undo beside their message; retain that action.
    const message = flash.matches(".phone-flash") ? flash.querySelector(":scope > span") : flash;
    (message || flash).textContent = success;
    initFlashMessages(flash, true);
  }
  if (new URLSearchParams(location.search).get("popup") === "1" && location.pathname.startsWith("/transactions/")) {
    baseUrl = location.pathname + location.search.replace(/(?:\?|&)popup=1/, "");
    baseScroll = 0;
    show(document.querySelector("main.main")?.innerHTML || "", document.title);
  }
})();

// Shared period controls use separate month/year fields and a bounded scroll list.
// One month stepper: ‹ yyyy-mm ›. The box is typeable; arrows move a month. Runs again on a swapped phone page.
const initMonthPickers = (root = document) => root.querySelectorAll("[data-month-picker]").forEach((picker) => {
  if (picker.dataset.monthPickerReady) return;
  picker.dataset.monthPickerReady = "1";
  const monthValue = picker.querySelector("[data-month-select]");
  const form = picker.matches("form") ? picker : picker.closest("form");
  const currentMonth = picker.dataset.currentMonth;
  const monthlyButton = form?.querySelector('[name="period"][value="month"]');
  const toIndex = (value) => {
    const [year, month] = value.split("-").map(Number);
    return year * 12 + month - 1;
  };
  const fromIndex = (index) => `${Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, "0")}`;
  const currentIndex = /^\d{4}-\d{2}$/.test(currentMonth || "") ? toIndex(currentMonth) : Infinity;
  const valid = (value) => /^\d{4}-(0[1-9]|1[0-2])$/.test(value) && toIndex(value) <= currentIndex;
  if (form?.hasAttribute("data-period-auto-apply")) {
    const customInputs = [...form.querySelectorAll('[name="date_from"], [name="date_to"]')]
      .filter((input) => input.type !== "hidden");
    customInputs.forEach((input) => input.addEventListener("input", () => input.setCustomValidity("")));
    customInputs.forEach((input) => input.addEventListener("change", () => {
      const value = input.value.trim();
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value) || toIndex(value) > currentIndex) {
        input.setCustomValidity(`Use yyyy-mm, up to ${currentMonth}.`);
        showFieldError(input);
        return;
      }
      input.setCustomValidity("");
      if (customInputs.every((field) => field.value.trim() && field.checkValidity())) {
        const start = customInputs.find((field) => field.name === "date_from");
        const end = customInputs.find((field) => field.name === "date_to");
        if (toIndex(end.value.trim()) < toIndex(start.value.trim())) {
          end.setCustomValidity("The end month must be the same as or after the start month.");
          showFieldError(end);
          return;
        }
        form.requestSubmit(form.querySelector('[name="period"][value="custom"]'));
      }
    }));
  }
  if (monthlyButton && monthValue) monthlyButton.addEventListener("click", () => { monthValue.value = currentMonth; });
  // Enter in a month box keeps the selected period; the browser would
  // otherwise submit with the first button (All time).
  form?.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.key !== "Enter" || !event.target.matches("input")) return;
    event.preventDefault();
    if (!event.target.checkValidity() || (event.target === monthValue && !valid(monthValue.value.trim()))) {
      if (event.target === monthValue) monthValue.setCustomValidity(`Use yyyy-mm, up to ${currentMonth}.`);
      showFieldError(event.target);
      return;
    }
    const selected = form.querySelector("button.period-button.selected")
      || (picker.classList.contains("site-period-control") ? monthlyButton : null);
    form.requestSubmit(selected || undefined);
  });
  if (!monthValue || !form || !/^\d{4}-\d{2}$/.test(currentMonth || "")) return;
  const updateButtons = () => {
    const index = valid(monthValue.value) ? toIndex(monthValue.value) : currentIndex;
    picker.querySelector('[data-month-shift="1"]').disabled = index >= currentIndex;
  };
  monthValue.addEventListener("input", () => monthValue.setCustomValidity(""));
  monthValue.addEventListener("change", () => {
    const value = monthValue.value.trim();
    if (!valid(value)) {
      monthValue.setCustomValidity(`Use yyyy-mm, up to ${currentMonth}.`);
      showFieldError(monthValue);
      return;
    }
    monthValue.value = value;
    form.requestSubmit(monthlyButton || undefined);
  });
  picker.querySelectorAll("[data-month-shift]").forEach((button) => {
    button.addEventListener("click", () => {
      const base = valid(monthValue.value) ? toIndex(monthValue.value) : currentIndex;
      const next = Math.min(base + Number(button.dataset.monthShift), currentIndex);
      monthValue.value = fromIndex(next);
      form.requestSubmit(monthlyButton || undefined);
    });
  });
  updateButtons();
});
initMonthPickers();

// Month picker: every month box (class "month-input") opens a small popup instead of being typed.
// The year and the month are picked separately, so going back years is one tap per year.
(() => {
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const now = new Date();
  const thisMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  let open = null;
  const close = () => { if (open) { open.pop.remove(); open.input.setAttribute("aria-expanded", "false"); open = null; } };
  const maxFor = (input) => input.dataset.maxMonth || input.closest("[data-current-month]")?.dataset.currentMonth || "";
  function show(input) {
    close();
    const max = maxFor(input);
    const valid = /^\d{4}-\d{2}$/.test(input.value) ? input.value : (max || thisMonth);
    let year = Number(valid.slice(0, 4));
    const pop = document.createElement("div");
    pop.className = "month-popup";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", t("Choose a month"));
    const render = () => {
      const maxYear = max ? Number(max.slice(0, 4)) : 9999;
      pop.innerHTML = `<div class="month-popup-year"><button type="button" data-year="-1" aria-label="${t("Previous year")}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg></button><b>${year}</b><button type="button" data-year="1" aria-label="${t("Next year")}" ${year >= maxYear ? "disabled" : ""}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg></button></div>`
        + `<div class="month-popup-grid">${MONTHS.map((name, i) => {
          const value = `${year}-${String(i + 1).padStart(2, "0")}`;
          const disabled = max && value > max;
          return `<button type="button" data-value="${value}" class="${value === input.value ? "selected" : ""}" ${disabled ? "disabled" : ""}>${t(name)}</button>`;
        }).join("")}</div>`
        + (input.required || input.closest("[data-month-picker]") ? "" : `<button type="button" class="month-popup-clear" data-value="">${t("Any month")}</button>`);
    };
    render();
    pop.addEventListener("click", (event) => {
      event.stopPropagation();  // a redrawn year row detaches the clicked button; it is still inside
      const button = event.target.closest("button");
      if (!button || button.disabled) return;
      event.preventDefault();
      if (button.dataset.year) { year += Number(button.dataset.year); render(); return; }
      input.value = button.dataset.value;
      input.setCustomValidity("");
      close();
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    document.body.appendChild(pop);
    const box = input.getBoundingClientRect();
    const left = Math.min(box.left + window.scrollX, window.scrollX + document.documentElement.clientWidth - pop.offsetWidth - 12);
    pop.style.left = `${Math.max(12, left)}px`;
    pop.style.top = `${box.bottom + window.scrollY + 6}px`;
    input.setAttribute("aria-expanded", "true");
    open = { input, pop };
    pop.querySelector("button.selected, .month-popup-grid button:not([disabled])")?.focus();
  }
  const bind = (root) => root.querySelectorAll("input.month-input:not(.month-picker-box)").forEach((input) => {
    input.readOnly = true;
    input.classList.add("month-picker-box");
    input.setAttribute("aria-haspopup", "dialog");
    input.addEventListener("click", () => (open?.input === input ? close() : show(input)));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") { event.preventDefault(); show(input); }
      if (event.key === "Escape") close();
    });
  });
  bind(document);
  document.addEventListener("lightning:page", (event) => { close(); bind(event.detail.root); });
  document.addEventListener("click", (event) => {
    if (open && !open.pop.contains(event.target) && event.target !== open.input) close();
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
  window.addEventListener("resize", close);
})();

// Target allocation: each Required % saves on Enter or when you leave it, then the table is redrawn
// in place, so the page never reloads or jumps.
(() => {
  const bind = (root) => {
    root.querySelectorAll("[data-target-save]").forEach((form) => {
      if (form.dataset.bound) return;
      form.dataset.bound = "1";
      const input = form.elements.target_weight;
      let before = input.value;
      const save = async () => {
        const value = input.value.trim().replace("%", "");
        if (value === before.trim().replace("%", "") || (form.elements.bucket.value || "") === "") return;  // empty clears the target
        const box = form.closest(".targets"), state = box?.querySelector(".save-state");
        const data = new URLSearchParams(new FormData(form)); data.set("target_weight", value);
        if (state) state.textContent = t("Saving…");
        const response = await fetch(form.action, { method: "POST", body: data, headers: { "X-Requested-With": "fetch" } });
        if (!response.ok) { if (state) state.textContent = await response.text(); return; }
        before = input.value;
        const focusBucket = form.elements.bucket.value;
        const fresh = await (await fetch(box.dataset.targetsSrc)).text();
        const holder = document.createElement("div"); holder.innerHTML = fresh;
        const next = holder.querySelector(".targets");
        box.replaceWith(next); bind(next);
        next.querySelector(".save-state").textContent = t("Saved");
        const rows = [...next.querySelectorAll('[data-target-save] input[name="bucket"]')];
        const at = rows.findIndex((b) => b.value === focusBucket);
        rows[at + 1]?.closest("form").elements.target_weight.focus();
      };
      input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); save(); } });
      input.addEventListener("blur", () => { if (!form.classList.contains("target-add")) save(); });
      form.elements.bucket.addEventListener?.("change", () => input.focus());
      form.addEventListener("submit", (event) => { event.preventDefault(); save(); });
    });
  };
  bind(document);
  new MutationObserver((records) => { if (!pickListOnly(records)) bind(document); }).observe(document.body, { childList: true, subtree: true });
})();

// No browser history under fields: suggestions come only from the app's own lists (counterparties,
// categories, accounts). Applies to every form, including ones loaded into a popup later.
(() => {
  const quiet = (root) => {
    root.querySelectorAll?.("form:not([autocomplete])").forEach((form) => form.setAttribute("autocomplete", "off"));
    root.querySelectorAll?.('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button]):not([type=password]), textarea')
      .forEach((field) => { if (field.getAttribute("autocomplete") !== "off") field.setAttribute("autocomplete", "off"); });
  };
  quiet(document);
  new MutationObserver((changes) => changes.forEach((change) => change.addedNodes.forEach((node) => node.nodeType === 1 && quiet(node))))
    .observe(document.body, { childList: true, subtree: true });
})();
// Explicit delegated replacements for inline event handlers; compatible with
// script-src-attr 'none' and with controls inserted into finance popups.
document.addEventListener("submit", (event) => {
  const message = event.target.dataset.confirm;
  if (message) window.confirmSubmit(event, message);
}, true);
document.addEventListener("input", (event) => {
  if (event.target.matches("[data-filter-holdings]")) window.filterHoldings?.();
});
document.addEventListener("change", (event) => {
  if (event.target.matches("[data-filter-holdings]")) window.filterHoldings?.();
  if (event.target.matches("[data-submit-on-change]")) event.target.form.requestSubmit();
});
document.addEventListener("click", (event) => {
  const remove = event.target.closest("[data-remove-row]");
  if (remove) { event.preventDefault(); remove.closest("tr").remove(); }
  const horizon = event.target.closest("[data-horizon-filter]");
  if (horizon) {
    document.getElementById("horizon-filter").value = horizon.dataset.horizonFilter;
    window.filterHoldings?.();
    document.getElementById("holdings-table").scrollIntoView({behavior: "smooth"});
  }
});

/* Percent fields: our own up and down chevrons, one whole percent a step. A pause after the last
   click saves the field the way Enter does. */
(() => {
  const chevron = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;
  const enhance = (root = document) => root.querySelectorAll(".row-field-unit, .sc-unit").forEach((box) => {
    const unit = box.querySelector("i"), input = box.querySelector("input");
    if (!input || !unit || unit.textContent.trim() !== "%" || box.dataset.stepper) return;
    box.dataset.stepper = "1";
    box.classList.add("has-stepper");
    const wrap = document.createElement("span");
    wrap.className = "pct-stepper";
    wrap.innerHTML = `<button type="button" tabindex="-1" aria-label="${t("Up 1%")}" data-step="1">${chevron("m6 15 6-6 6 6")}</button>` +
                     `<button type="button" tabindex="-1" aria-label="${t("Down 1%")}" data-step="-1">${chevron("m6 9 6 6 6-6")}</button>`;
    box.append(wrap);
    let timer;
    wrap.addEventListener("mousedown", (event) => event.preventDefault());
    wrap.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-step]");
      if (!button) return;
      const current = parseFloat(input.value || input.placeholder || "0") || 0;
      const max = input.max !== "" && input.max !== undefined ? parseFloat(input.max) : 100;
      const next = Math.min(isNaN(max) ? 100 : max, Math.max(0, Math.round(current) + Number(button.dataset.step)));
      input.value = String(next);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      clearTimeout(timer);
      timer = setTimeout(() => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })), 700);
    });
  });
  enhance();
  new MutationObserver((records) => { if (!pickListOnly(records)) enhance(); }).observe(document.body, { childList: true, subtree: true });
})();

/* Our dropdown list. The select box itself stays (its style, form value and change events); clicking
   it, or Space / Enter / Down on it, opens our panel instead of the browser's flat list: group
   headers, details indented, the current choice marked, and a search box on long lists. Phones keep
   their own picker. */
(() => {
  if (window.matchMedia("(pointer: coarse)").matches) return;
  let open = null;
  const close = () => { if (!open) return; open.panel.remove(); open.select.setAttribute("aria-expanded", "false"); open = null; };
  const choose = (select, value) => {
    if (select.value !== value) {
      select.value = value;
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    close(); select.focus();
  };
  const build = (select) => {
    const panel = document.createElement("div");
    panel.className = "pick-panel"; panel.setAttribute("role", "listbox");
    const options = [...select.options];
    const long = options.length > 10;
    let search;
    if (long) {
      search = document.createElement("input");
      search.type = "search"; search.className = "pick-search"; search.placeholder = t("Type to find"); search.autocomplete = "off";
      panel.append(search);
    }
    const list = document.createElement("div"); list.className = "pick-list"; panel.append(list);
    const add = (opt) => {
      const text = opt.textContent.replace(/^[ \s]+/, "");
      const row = document.createElement("div");
      if (opt.disabled) { row.className = "pick-head"; row.textContent = text; list.append(row); return; }
      row.className = "pick-option" + (/^ /.test(opt.textContent) ? " is-detail" : "") + (opt.classList.contains("option-head") ? " is-head" : "");
      row.setAttribute("role", "option"); row.dataset.value = opt.value; row.textContent = text || " ";
      if (opt.value === select.value) row.setAttribute("aria-selected", "true");
      row.addEventListener("mousedown", (e) => e.preventDefault());
      row.addEventListener("click", () => choose(select, opt.value));
      list.append(row);
    };
    [...select.children].forEach((child) => {
      if (child.tagName === "OPTGROUP") {
        const head = document.createElement("div"); head.className = "pick-group"; head.textContent = child.label; list.append(head);
        [...child.children].forEach(add);
      } else add(child);
    });
    const rows = () => [...list.querySelectorAll(".pick-option:not([hidden])")];
    let active = Math.max(0, rows().findIndex((r) => r.getAttribute("aria-selected") === "true"));
    const mark = () => { rows().forEach((r, i) => r.classList.toggle("is-active", i === active)); rows()[active]?.scrollIntoView({ block: "nearest" }); };
    const filter = () => {
      const q = search.value.trim().toLocaleLowerCase();
      list.querySelectorAll(".pick-option").forEach((r) => { r.hidden = q && !r.textContent.toLocaleLowerCase().includes(q); });
      list.querySelectorAll(".pick-group").forEach((g) => {
        let n = g.nextElementSibling, any = false;
        while (n && !n.classList.contains("pick-group")) { if (n.classList.contains("pick-option") && !n.hidden) any = true; n = n.nextElementSibling; }
        g.hidden = !any;
      });
      active = 0; mark();
    };
    search?.addEventListener("input", filter);
    panel.addEventListener("keydown", (e) => {
      const r = rows();
      if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(r.length - 1, active + 1); mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(0, active - 1); mark(); }
      else if (e.key === "Enter") { e.preventDefault(); if (r[active]) choose(select, r[active].dataset.value); }
      else if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); close(); select.focus(); }
    });
    panel.tabIndex = -1;
    return { panel, search, mark };
  };
  const show = (select) => {
    if (select.disabled) return;
    close();
    const { panel, search, mark } = build(select);
    // Inside a popup the panel must live in the dialog: a modal dialog sits above everything else on
    // the page, so a panel on the body would open behind it, out of reach.
    (select.closest("dialog[open]") || document.body).append(panel);
    const rect = select.getBoundingClientRect();
    const width = Math.min(Math.max(rect.width, 220), Math.max(0, window.innerWidth - 16));
    panel.style.minWidth = `${width}px`;
    const room = window.innerHeight - rect.bottom;
    panel.style.left = `${Math.min(rect.left, window.innerWidth - width - 8)}px`;
    if (room < 280 && rect.top > room) { panel.style.bottom = `${window.innerHeight - rect.top + 4}px`; panel.style.maxHeight = `${Math.min(360, rect.top - 16)}px`; }
    else { panel.style.top = `${rect.bottom + 4}px`; panel.style.maxHeight = `${Math.min(360, room - 16)}px`; }
    open = { select, panel };
    select.setAttribute("aria-expanded", "true");
    mark();
    (search || panel).focus();
  };
  const eligible = (el) => el instanceof HTMLSelectElement && !el.hidden && !el.matches("[data-own-picker]") && !el.multiple && el.size <= 1 && !el.hasAttribute("data-native") && el.closest(".main, .popup-sheet, dialog");
  document.addEventListener("mousedown", (e) => {
    const select = e.target.closest("select");
    if (select && eligible(select)) { e.preventDefault(); select.focus(); open && open.select === select ? close() : show(select); return; }
    if (open && !open.panel.contains(e.target)) close();
  });
  document.addEventListener("keydown", (e) => {
    const select = e.target;
    if (!eligible(select) || open) return;
    if (e.key === " " || e.key === "Enter" || e.key === "ArrowDown" || (e.altKey && e.key === "ArrowDown")) { e.preventDefault(); show(select); }
  });
  window.addEventListener("resize", close);
  document.addEventListener("scroll", (e) => { if (open && !open.panel.contains(e.target)) close(); }, true);
})();

// Privacy mode (the eye in the sidebar, or "Hide amounts" in the command bar): every money amount on
// the page is blurred, for a café or an office; percentages, dates and names stay readable. A page
// that starts hidden is blurred whole by CSS until its amounts are marked, so none flashes.
window.lightningPrivacy = (() => {
  const root = document.documentElement;
  const AMOUNT = /(?<![\d.,])[+−-]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2})(?![\d%])(?!\s%)/g;
  const LONE = /^\s*[+−-]?\d+(?:\.\d+)?\s*$/;
  const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT", "SELECT", "OPTION", "NOSCRIPT", "TITLE"]);
  const currency = () => document.querySelector("[data-base-currency]")?.dataset.baseCurrency || "EGP";
  const mark = (scope) => {
    if (!scope) return;
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, { acceptNode: (node) => {
      const parent = node.parentElement;
      return parent && !SKIP.has(parent.tagName) && /\d/.test(node.data) && !parent.closest(".amt, .command-bar")
        ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    } });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const parent = node.parentElement, text = node.data;
      // "450" with its currency beside it (<b>450<small>EGP</small></b>) is an amount too.
      const lone = LONE.test(text) && (node.nextSibling?.textContent || "").trim() === currency();
      const found = lone ? [[0, text.length]] : [...text.matchAll(AMOUNT)].map((m) => [m.index, m.index + m[0].length]);
      if (!found.length) continue;
      if (parent instanceof SVGElement) { parent.classList.add("amt"); continue; }  // chart labels blur whole
      const pieces = document.createDocumentFragment();
      let at = 0;
      for (const [start, end] of found) {
        if (start > at) pieces.append(text.slice(at, start));
        const span = document.createElement("span");
        span.className = "amt";
        span.textContent = text.slice(start, end);
        pieces.append(span);
        at = end;
      }
      if (at < text.length) pieces.append(text.slice(at));
      node.replaceWith(pieces);
    }
  };
  const label = (on) => document.querySelectorAll("[data-privacy-toggle]").forEach((control) => {
    const words = on ? "Show amounts" : "Hide amounts";
    control.setAttribute("aria-pressed", on ? "true" : "false");
    if (control.tagName === "BUTTON") { control.setAttribute("aria-label", words); control.title = words; }
    else if (control.querySelector("b")) control.querySelector("b").textContent = words;
  });
  const set = (on) => {
    if (on) mark(document.body);
    root.classList.toggle("privacy", on);
    root.classList.toggle("privacy-ready", on);
    label(on);
    document.cookie = `lightning_privacy=${on ? 1 : 0}; path=/; SameSite=Strict`;
    // Remember it in the profile too; a read-only (reader) session refuses, and the cookie keeps it for now.
    const token = document.querySelector('meta[name="lightning-session"]')?.content
      || document.querySelector('input[name="__session"]')?.value || "";
    fetch("/settings/privacy", { method: "POST", body: new URLSearchParams({ on: on ? "1" : "0", __session: token }) })
      .catch(() => {});
  };
  if (root.classList.contains("privacy")) { mark(document.body); root.classList.add("privacy-ready"); }
  new MutationObserver((records) => {
    if (!root.classList.contains("privacy")) return;
    for (const record of records) {
      if (record.type === "characterData") mark(record.target.parentElement);
      for (const node of record.addedNodes) mark(node.nodeType === 1 ? node : node.parentElement);
    }
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
  document.addEventListener("click", (event) => {
    const control = event.target.closest("[data-privacy-toggle]");
    if (!control) return;
    event.preventDefault();
    set(!root.classList.contains("privacy"));
  });
  return { toggle: () => set(!root.classList.contains("privacy")), mark };
})();

// Command bar: Ctrl-K (Cmd-K on a Mac), or Search in the sidebar. One field over the app's one search
// (/search, ranked in Python), grouped by type as on the Search page. Arrows move, Enter opens the
// highlighted result, Escape or a click outside closes it.
(() => {
  const bar = document.getElementById("command-bar");
  if (!bar) return;
  const field = bar.querySelector(".command-input"), list = bar.querySelector(".command-results");
  const groups = { Transaction: "Transaction", Page: "Pages", Action: "Actions", Account: "Accounts",
    Person: "People", Reserve: "Reserves", Counterparty: "Counterparties", Category: "Categories", Investment: "Investments", Tag: "Tags", Search: "Transactions" };
  let results = [], active = 0, asked = "", waiting = null, timer = null;
  const paint = () => {
    list.replaceChildren();
    let kind = "";
    results.forEach((row, index) => {
      if (row.kind !== kind) {
        kind = row.kind;
        const head = document.createElement("div");
        head.className = "pick-group";
        head.textContent = t(groups[kind] || kind);
        list.append(head);
      }
      const option = document.createElement("a");
      option.className = `pick-option command-option${index === active ? " is-active" : ""}`;
      option.href = row.href;
      option.id = `command-option-${index}`;
      option.setAttribute("role", "option");
      const name = document.createElement("span");
      name.textContent = row.label;
      option.append(name);
      if (row.context) {
        const context = document.createElement("small");
        context.className = "command-context";
        context.textContent = row.context;
        option.append(context);
      }
      option.addEventListener("mousemove", () => { if (active !== index) { active = index; paint(); } });
      option.addEventListener("click", (event) => { event.preventDefault(); go(row); });
      list.append(option);
    });
    field.setAttribute("aria-activedescendant", results.length ? `command-option-${active}` : "");
  };
  const ask = () => {
    const query = field.value;
    asked = query;
    waiting = fetch(`/search?format=json&q=${encodeURIComponent(query)}`)
      .then((response) => response.json())
      .then((data) => { if (asked === query) { results = data.results || []; active = 0; paint(); } })
      .catch(() => {});
    return waiting;
  };
  const go = (row) => {
    if (!row) return;
    bar.close();
    if (row.action === "privacy") window.lightningPrivacy?.toggle();
    else if (row.popup) {  // a typed entry (3G7) opens its sheet over the page, as Add does
      const link = document.createElement("a");
      link.href = row.href; link.setAttribute("data-popup-open", ""); link.hidden = true;
      document.body.append(link); link.click(); link.remove();
    }
    else location.href = row.href;
  };
  const open = () => {
    if (bar.open) return;
    field.value = "";
    results = [];
    paint();
    bar.showModal();
    field.focus();
    ask();
  };
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (bar.open) bar.close(); else open();
    }
  });
  document.querySelectorAll("[data-command-open]").forEach((link) =>
    link.addEventListener("click", (event) => { event.preventDefault(); open(); }));
  field.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(ask, 120); });
  field.addEventListener("keydown", async (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      bar.close();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!results.length) return;
      active = (active + (event.key === "ArrowDown" ? 1 : -1) + results.length) % results.length;
      paint();
      list.querySelector(".is-active")?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (asked !== field.value) { clearTimeout(timer); ask(); }  // typed faster than the search answered
      await waiting;
      go(results[active]);
    }
  });
  bar.addEventListener("click", (event) => { if (event.target === bar) bar.close(); });
})();

// Show that the app is working, never stuck (brand guideline A10.6). A pressed button becomes unavailable and,
// if the next page takes more than a moment, shows a small turning square (and its data-busy words). A slow
// page, and work running in the background (month-end prices after opening a profile), show the same square
// in a note at the bottom right. Downloads never leave the page, so they are left alone.
(() => {
  // The profile pages have no toast; their buttons still go unavailable, so Enter and a click unlock once (2AC).
  const toast = document.getElementById("busy-toast");
  const text = toast?.querySelector(".busy-text"), link = toast?.querySelector(".busy-link");
  let slow = 0, safety = 0, fade = 0;
  const show = (words, done = false) => {
    window.clearTimeout(fade);
    if (!toast) return;
    text.textContent = t(words);
    toast.classList.toggle("done", done);
    link.hidden = !done;
    toast.hidden = false;
  };
  const hide = () => { if (toast) toast.hidden = true; };
  const reset = () => {
    window.clearTimeout(slow);
    window.clearTimeout(safety);
    hide();
    document.querySelectorAll("button[data-busy-on]").forEach((button) => {
      button.disabled = false;
      button.removeAttribute("data-busy-on");
      button.removeAttribute("aria-busy");
      if (button.dataset.busyWas !== undefined) button.textContent = button.dataset.busyWas;
      button.querySelector(".busy-square")?.remove();
    });
  };
  const leaves = (url) => url.origin === location.origin && !/^\/(exports|samples)\//.test(url.pathname);
  document.addEventListener("submit", (event) => {
    const form = event.target, button = event.submitter;
    const target = new URL(button?.formAction || form.action || location.href, location.href);
    if ((button?.formTarget || form.target) === "_blank" || form.matches("[data-no-busy]") || !leaves(target)) return;
    window.setTimeout(() => {  // after the form's own handlers and its data are taken: disabling now loses nothing
      if (event.defaultPrevented || !button) return;
      button.dataset.busyOn = "1";
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
      if (button.dataset.busy) { button.dataset.busyWas = button.textContent; button.textContent = t(button.dataset.busy); }
      slow = window.setTimeout(() => show(button.dataset.busy || "Loading…"), 300);
      safety = window.setTimeout(reset, 20000);  // a page that never comes: give the button back
    }, 0);
  });
  document.addEventListener("click", (event) => {
    const anchor = event.target.closest?.("a[href]");
    if (!anchor || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey
        || anchor.target || anchor.hasAttribute("download") || anchor.matches("[data-popup-open]")) return;
    const url = new URL(anchor.href, location.href);
    if (!leaves(url) || (url.pathname === location.pathname && url.search === location.search)) return;
    window.setTimeout(() => {
      if (event.defaultPrevented) return;
      slow = window.setTimeout(() => show("Opening…"), 300);
      safety = window.setTimeout(reset, 20000);
    }, 0);
  });
  window.addEventListener("pageshow", (event) => { if (event.persisted) reset(); });
  const watch = toast?.dataset.watch;
  if (watch) {
    show(toast.dataset.watchLabel || "Working…");
    const ask = async () => {
      try {
        const state = await (await fetch(watch, { headers: { "X-Requested-With": "fetch" } })).json();
        if (state.running) { window.setTimeout(ask, 2000); return; }
        if (state.note) { show(state.note, true); fade = window.setTimeout(hide, 8000); } else hide();
      } catch (error) { hide(); }
    };
    window.setTimeout(ask, 2000);
  }
})();

// C08.5 on a phone: press and hold a transaction to start selecting, with that row chosen.
const initHoldToSelect = (root = document) => root.querySelectorAll(".phone-txn[data-txn]").forEach((row) => {
  if (row.dataset.holdReady) return;
  row.dataset.holdReady = "1";
  let timer = 0, held = false, x = 0, y = 0;
  const stop = () => window.clearTimeout(timer);
  row.addEventListener("pointerdown", (event) => {
    held = false; x = event.clientX; y = event.clientY;
    timer = window.setTimeout(() => {
      held = true;
      const url = new URL(window.location.href);
      url.searchParams.set("select", "1");
      url.searchParams.set("pick", row.dataset.txn);
      window.location.href = url.toString();
    }, 550);
  });
  row.addEventListener("pointermove", (event) => { if (Math.abs(event.clientX - x) + Math.abs(event.clientY - y) > 10) stop(); });
  ["pointerup", "pointerleave", "pointercancel"].forEach((name) => row.addEventListener(name, stop));
  row.addEventListener("contextmenu", (event) => event.preventDefault());
  row.addEventListener("click", (event) => { if (held) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);
});
initHoldToSelect();

// C04.6 on a phone: the As-of chip is the phone's own date picker; choosing a day shows that day.
const initAsOf = (root = document) => root.querySelectorAll("form.phone-as-of input[data-native-date]").forEach((input) => {
  if (input.dataset.asOfReady) return;
  input.dataset.asOfReady = "1";
  input.addEventListener("change", () => { if (input.value) input.form.requestSubmit(); });
  input.addEventListener("click", () => { try { input.showPicker?.(); } catch (error) { /* the tap itself opens it */ } });
});
initAsOf();

// A phone page swapped in without a reload (phone-nav.js, IT-3AO2) gets the set-up a loaded page gets. Everything else
// here listens on the document or watches it, so it already covers the new content.
document.addEventListener("lightning:page", (event) => {
  const root = event.detail.root;
  initFlashMessages(root, true);
  initOwnDataPickers(root);
  initDateFields(root);
  root.querySelectorAll(moneySelector).forEach(setupMoneyInput);
  initMonthPickers(root);
  initHoldToSelect(root);
  initAsOf(root);
  initPhoneBulk();
  initAutosaveExisting(root);
  initBudgetEditor();
  initAccountType();
  initCounterpartyFilters(root);
  initCurrencySearch(root);
  initInvestmentEntry(root);
  initInvestmentOwnership(root);
  initTradeTotals(root);
  initTradeCatalogue();
  initKarat();
  initInstrumentCatalogue();
  initCategoryCatalogue();
});

// Setup, "Other currencies you hold": a type-and-pick that adds removable chips; each chip submits its code.
(() => {
  document.querySelectorAll("select[data-chip-add]").forEach((select) => {
    const box = document.querySelector(select.dataset.chipAdd);
    if (!box) return;
    const name = select.dataset.chipName || "extra";
    box.addEventListener("click", (event) => {
      const button = event.target.closest("[data-chip-remove]");
      if (button) button.closest(".chip")?.remove();
    });
    select.addEventListener("change", () => {
      const code = select.value;
      window.setTimeout(() => {
        select.value = "";
        const typed = select.parentElement.querySelector('input[type="text"]');
        if (typed) typed.value = "";
      }, 0);
      if (!code || Array.from(box.querySelectorAll("input")).some((input) => input.value === code)) return;
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.append(`${code} `);
      const remove = document.createElement("button");
      remove.type = "button"; remove.className = "chip-x"; remove.dataset.chipRemove = "";
      remove.setAttribute("aria-label", t("Remove")); remove.textContent = "×";
      const hidden = document.createElement("input");
      hidden.type = "hidden"; hidden.name = name; hidden.value = code;
      chip.append(remove, hidden);
      box.append(chip);
    });
  });
})();
// Saved filters use the same delegated listener in full pages and popup content.
document.addEventListener('change', (event) => {
  const field = event.target.closest('[data-submit-on-change]');
  if (field?.form) field.form.requestSubmit();
});

// The phone's tab bar steps aside while the keyboard is up (guideline C02.4; phone.css hides it under
// html.keyboard-open). The keyboard is up when a field takes text and the visible viewport is clearly shorter
// than the tallest one seen at this width, which holds whether the shell resizes the page or only the viewport.
(() => {
  const root = document.documentElement, viewport = window.visualViewport;
  if (!root.classList.contains("phone") || !viewport) return;
  let tallest = 0, width = 0;
  const typing = () => {
    const field = document.activeElement;
    if (!field || field === document.body) return false;
    if (field.tagName === "TEXTAREA" || field.isContentEditable) return true;
    return field.tagName === "INPUT" && !/^(checkbox|radio|button|submit|reset|range|file|color|image|hidden)$/i.test(field.type);
  };
  const turned = () => { if (viewport.width !== width) { width = viewport.width; tallest = 0; } };  // turning the phone starts again
  const sync = () => {
    turned();
    if (!typing()) tallest = Math.max(tallest, viewport.height);
    root.classList.toggle("keyboard-open", typing() && tallest - viewport.height > 120);
  };
  viewport.addEventListener("resize", sync);
  document.addEventListener("focusin", () => { turned(); tallest = Math.max(tallest, viewport.height); sync(); });
  document.addEventListener("focusout", () => setTimeout(sync, 0));
  // After the first paint: measuring the viewport while the page is still loading forces an early layout (IT-3AO3).
  requestAnimationFrame(() => setTimeout(sync, 0));
})();

// F8 (r24): a transactions list opened from an analysis page remembers it, so the way back keeps its period and scope.
(() => {
  const link = document.getElementById("investigation-back");
  if (!link) return;
  const key = "lightning-investigation-back";
  const analysis = /^\/(birdview|spending|reports|financial-health)(\/|$)/;
  try {
    if (document.referrer) {
      const from = new URL(document.referrer);
      if (from.origin === location.origin && analysis.test(from.pathname)) sessionStorage.setItem(key, from.pathname + from.search);
    }
    const back = sessionStorage.getItem(key);
    if (back && analysis.test(back.split("?")[0])) {
      link.href = back; link.hidden = false;
      link.textContent = t("Back to {page}", {page: t(back.startsWith("/birdview/expenses") || back.startsWith("/spending") ? "Spending" : "the analysis")});
    }
  } catch (e) {}
})();

// NF-12I: "I already own it" on the certificate form: no account pays, so "Buy from" stops being required.
document.querySelectorAll("[data-unrequires]").forEach((box) => {
  const select = box.form && box.form.querySelector(`select[name="${box.dataset.unrequires}"]`);
  if (!select) return;
  const apply = () => (select.setPickerRequired ? select.setPickerRequired(!box.checked) : (select.required = !box.checked));
  box.addEventListener("change", apply);
  if (box.checked) apply();
});

// A screen that waits for another device (the phone's two pairing digits, NF-4M) shows its news without a tap: it
// reloads every few seconds while it is visible, and never while the person is typing in it.
document.querySelectorAll("[data-refresh-seconds]").forEach((node) => {
  const seconds = Math.max(2, Number(node.dataset.refreshSeconds) || 3);
  window.setInterval(() => {
    const typing = document.activeElement && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (document.visibilityState === "visible" && !typing) window.location.reload();
  }, seconds * 1000);
});
