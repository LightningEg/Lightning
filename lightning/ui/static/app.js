// Small helpers only — no financial logic lives in the browser.
const t = (text, values) => window.lightningT ? window.lightningT(text, values) : String(text);

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
    if (isError || !flash.textContent.trim() || flash.classList.contains("device-line")) return;
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
// Keep the reader's place when a normal form post returns a fresh server page.
const savedPageScroll = sessionStorage.getItem("lightning-page-scroll");
if (savedPageScroll !== null) {
  sessionStorage.removeItem("lightning-page-scroll");
  requestAnimationFrame(() => window.scrollTo({ top: Number(savedPageScroll) || 0, behavior: "instant" }));
}
document.addEventListener("submit", (event) => {
  if ((event.target.method || "get").toLowerCase() === "post" && !event.target.closest("#app-popup-content")) {
    sessionStorage.setItem("lightning-page-scroll", String(window.scrollY));
  }
}, true);
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
  wrapper.append(list);
  let active = -1;
  const entries = () => Array.from(select.options).filter((option) => !option.disabled && option.value !== "");
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; };
  const choose = (option) => {
    if (!option) return;
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
    list.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - width - 8))}px`;
    list.style.top = `${upward ? Math.max(8, rect.top - Math.min(list.scrollHeight, height) - 4) : rect.bottom + 4}px`;
  };
  document.addEventListener('scroll', () => { if (!list.hidden) place(); }, true);
  window.addEventListener('resize', place);
  const render = (all = false) => {
    const query = all ? "" : input.value.trim().toLocaleLowerCase();
    const matches = entries().filter((option) => !query || `${groupOf(option)} ${option.textContent}`.toLocaleLowerCase().includes(query)).slice(0, all ? 5 : 80);
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
    if (!matches.length) { close(); return; }
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
  document.addEventListener("click", (event) => { if (!wrapper.contains(event.target)) close(); });
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
  list.setAttribute("role", "listbox"); list.hidden = true; wrapper.append(list);
  input.removeAttribute("list"); input.autocomplete = "off";
  input.setAttribute("role", "combobox"); input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-haspopup", "listbox"); input.setAttribute("aria-controls", list.id); input.setAttribute("aria-expanded", "false");
  let active = -1;
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; };
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
  const render = () => {
    const query = input.value.trim().toLocaleLowerCase();
    const hints = suggested().filter((row) => !query || row.hay.includes(query));
    const listed = rowsOf().filter((row) => row.value && (!query || row.hay.includes(query)) && !hints.some((hint) => hint.value === row.value));
    const matches = [...hints, ...listed].slice(0, query ? 50 : (allowAdd ? 8 : 5));
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
      option.addEventListener("click", () => { input.value = row.value; input.dispatchEvent(new Event("change", { bubbles: true })); setPick(row.pick); close(); });
      list.append(option);
    });
    const typed = input.value.trim();
    if (allowAdd && typed && !rowsOf().some((row) => row.value.toLocaleLowerCase() === typed.toLocaleLowerCase())) {
      const add = document.createElement("button"); add.type = "button"; add.className = "counterparty-option picker-add";
      add.setAttribute("role", "option"); add.id = `${list.id}-add`; add.textContent = t(input.dataset.addLabel || '+ Add "{name}"', { name: typed });
      add.addEventListener("mousedown", (event) => event.preventDefault());
      add.addEventListener("click", () => { input.value = typed; input.dispatchEvent(new Event("change", { bubbles: true })); setPick(`new:${typed}`); close(); });
      list.append(add);
    } else if (!matches.length) { close(); return; }
    const rect = input.getBoundingClientRect();
    list.style.left = `${Math.max(8, rect.left)}px`; list.style.top = `${rect.bottom + 4}px`; list.style.width = `${Math.max(230, rect.width)}px`;
    list.hidden = false; input.setAttribute("aria-expanded", "true"); active = -1;
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
  document.addEventListener("click", (event) => { if (!wrapper.contains(event.target)) close(); });
  });
};
initOwnDataPickers();

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
window.askFrom = (text, extra = {}) => {
  const [title, ...rest] = t(text).split(/(?<=\?)\s+/);
  const danger = /\b(delete|remove)\b/i.test(title);
  return window.ask({ title, message: rest.join(" "), ok: danger ? "Delete" : "OK", tone: danger ? "danger" : "info", ...extra });
};
// askChoice({title, message, choices: [{label, value, primary}]}) resolves the chosen value, or null on Escape.
window.askChoice = ({ title, message = "", choices }) => new Promise((resolve) => {
  const dialog = document.createElement("dialog");
  dialog.className = "ask-dialog tone-info";
  dialog.setAttribute("aria-labelledby", "ask-title");
  dialog.innerHTML = '<form method="dialog" class="ask-frame"><div class="ask-text"><h2 id="ask-title"></h2><p id="ask-message"></p></div><div class="ask-actions"></div></form>';
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
  openCal = { panel, text, button };
  button?.setAttribute("aria-expanded", "true");
  panel.querySelector(`[data-day="${focus}"]`)?.focus();
};
document.addEventListener("mousedown", (e) => {
  if (openCal && !openCal.panel.contains(e.target) && !e.target.closest("[data-open-date-picker]")) closeCalendar();
});
document.addEventListener("scroll", (e) => { if (openCal && !openCal.panel.contains(e.target)) closeCalendar(); }, true);
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
    if (!native.placeholder) native.placeholder = "yyyy-mm-dd";
    native.inputMode = "numeric";
    native.autocomplete = "off";
  });
  root.querySelectorAll("[data-smart-date]").forEach((input) => {
    if (input.closest(".iso-date-control")) return;
    if (!input.id) input.id = `date-field-${++dateFieldCount}`;
    if (!input.placeholder) input.placeholder = "yyyy-mm-dd";
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
        if (bad) { event.preventDefault(); event.stopImmediatePropagation(); bad.reportValidity(); bad.focus(); }
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
    sessionStorage.setItem("lightning-page-scroll", String(window.scrollY));
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
    const options = ids.size ? { title: t("Delete {count} transactions?", {count: ids.size.toLocaleString(document.documentElement.lang)}),
      message: t("You can restore them from transaction history."), tone: "danger", ok: t("Delete") }
      : confirmHost.dataset.confirmDelete || "Delete this transaction? You can restore it from its history page.";
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
const phoneMerge = document.getElementById("phone-merge-selected");
const phoneBulk = document.getElementById("phone-bulk");
if (phoneBulk) {
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
}
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
  const readSel = () => { try { const ids = JSON.parse(sessionStorage.getItem(selKey) || "[]"); return Array.isArray(ids) ? ids.filter((id) => typeof id === "string" && byId.has(id)) : []; } catch (e) { return []; } };
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
    const editSelected = document.getElementById("edit-selected");
    if (editSelected) editSelected.disabled = !boxes.some((box) => selected.has(box.value) && ["IN", "OUT"].includes(box.dataset.type));
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
      const singleRowChanged = value("amount") !== String(original.amount ?? "").trim()
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
        fetch(form.action, { method: "POST", body: new FormData(form),
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
    }
    showItems(Boolean(editing));
    menu.hidden = false;
    const x = Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8);
    const y = Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8);
    menu.style.left = `${Math.max(8, x)}px`; menu.style.top = `${Math.max(8, y)}px`;
    syncSelection();
  });
  menu?.querySelector("[data-context-edit]").addEventListener("click", () => { if (menu.dataset.href) location.href = menu.dataset.href; });
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
document.querySelectorAll(".investment-entry-form").forEach((form) => {
  const flag = form.querySelector('[name="is_others"]');
  const field = form.querySelector(".investment-owner-field");
  if (!flag || !field) return;
  const sync = () => { field.hidden = !flag.checked; };
  flag.addEventListener("change", sync);
  sync();
});
document.querySelectorAll(".investment-ownership-form").forEach((form) => {
  const flag = form.querySelector('[name="is_others"]');
  const field = form.querySelector(".investment-owner-field");
  if (!flag || !field) return;
  const sync = () => { field.hidden = !flag.checked; };
  flag.addEventListener("change", sync);
  sync();
});

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
  Promise.all(pending.map(workOutSum)).then(() => pending.find((field) => field.validationMessage)?.reportValidity());
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
    workOutSum(input).then(() => { if (input.validationMessage) input.reportValidity(); });
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
document.querySelectorAll(".trade-total").forEach((total) => {
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
      ? new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(gross / units)
      : "";
  };
  quantity.addEventListener("input", update);
  total.addEventListener("input", update);
  feeInput?.addEventListener("input", update);
  feeChoice?.addEventListener("change", () => { syncFeeField(); update(); });
  syncFeeField();
  update();
});

// Inline brokerage activity: pick an instrument, then sign units to buy or sell.
const tradeCatalogueNode = document.getElementById("trade-instrument-catalogue");
if (tradeCatalogueNode) {
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
    return new Intl.NumberFormat(undefined, { minimumFractionDigits, maximumFractionDigits }).format(value);
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
    } else if (selected) {
      positionHint.textContent = t("You hold {quantity} {unit}(s) here.", {quantity: formatted(Number(selected.holding || 0), selected.decimals), unit: selected.unit});
    }
    if (selected && selected.note) positionHint.textContent += ` ${t(selected.note)}`;
    // The live "You pay …" line (display only; the posted amounts are recomputed in Python).
    if (payLine) {
      const cur = form.dataset.currency || "";
      const money = (value) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 }).format(value);
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
        selectedLabel.value = `${item.name} · ${item.ticker}${item.exchange ? ` · ${item.exchange}` : ""}`;
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
  if (selected) { search.value = selectedLabel.value || `${selected.name} · ${selected.ticker}${selected.exchange ? ` · ${selected.exchange}` : ""}`; }
  sync();
}

// Only physical gold uses a karat selector; funds have fund units, not gold purity.
const investmentClass = document.getElementById("class_code");
const karatField = document.getElementById("karat-field");
if (investmentClass && karatField) {
  const syncKarat = () => { karatField.hidden = investmentClass.value !== "GOLD"; };
  investmentClass.addEventListener("change", syncKarat);
  syncKarat();
}

// Investment picker: filter the bundled EGX stock and Thndr fund catalogue.
const catalogueNode = document.getElementById("instrument-catalogue");
if (catalogueNode) {
  const catalogue = JSON.parse(catalogueNode.textContent || "[]");
  const search = document.getElementById("instrument-search");
  const results = document.getElementById("instrument-results");
  const selection = document.getElementById("instrument-selection");
  const form = search.closest("form");
  const name = form.querySelector('[name="name"]');
  const kind = form.querySelector('[name="class_code"]');
  const symbol = form.querySelector('[name="symbol"]');
  const venue = form.querySelector('[name="mic"]');
  const render = () => {
    const query = search.value.trim().toLocaleLowerCase(); results.replaceChildren();
    if (!query) { results.hidden = true; search.setAttribute("aria-expanded", "false"); return; }
    const matches = catalogue.filter((item) => `${item.name} ${item.ticker} ${item.kind} ${item.exchange || ""}`.toLocaleLowerCase().includes(query)).slice(0, 12);
    if (!matches.length) { const empty=document.createElement("div"); empty.className="instrument-result"; empty.textContent=t("No match. You can enter the investment details below."); results.append(empty); }
    matches.forEach((item) => {
      const button=document.createElement("button"); button.type="button"; button.className="instrument-result"; button.setAttribute("role","option");
      const label=document.createElement("span"); label.textContent=item.name; const ticker=document.createElement("small"); ticker.textContent=`${item.ticker}${item.exchange ? ` · ${item.exchange}` : ""}`; button.append(label,ticker);
      button.addEventListener("click", () => { name.value=item.name; kind.value=item.class_code; if(symbol) symbol.value=item.ticker; if(venue) venue.value=item.mic||""; search.value=`${item.name} · ${item.ticker}`; results.hidden=true; search.setAttribute("aria-expanded","false"); selection.textContent=t("Selected {name} ({ticker}). Review the details, then save.", {name: item.name, ticker: item.ticker}); }); results.append(button);
    }); results.hidden=false; search.setAttribute("aria-expanded","true");
  };
  search.addEventListener("input",render); search.addEventListener("focus",render);
  document.addEventListener("click",(event)=>{if(!event.target.closest(".instrument-picker")){results.hidden=true;search.setAttribute("aria-expanded","false");}});
}

// Category picker: one alphabetized header per activity, with broad categories nested below.
const categoryCatalogueNode = document.getElementById("category-catalogue");
if (categoryCatalogueNode) {
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
    const matchesFor = () => {
      const query = isChoice() ? "" : input.value.trim().toLocaleLowerCase().replaceAll("›", " ").replace(/\s+/g, " ");
      return categories.filter((item) => !query ||
        `${item.parent} ${item.name} ${item.label}`.toLocaleLowerCase().replaceAll("›", " ").replace(/\s+/g, " ").includes(query));
    };
    const render = () => {
      if (input.disabled || document.activeElement !== input) return;
      results.replaceChildren();
      activeIndex = -1;
      const allMatches = matchesFor();
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
            input.value = item.name;
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
}

// How alike two spellings are, 0 to 1 (1 − edit distance / longer length).
const similar = (a, b) => {
  if (a === b) return 1;
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    let prev = row[0]; row[0] = i;
    for (let j = 1; j <= b.length; j += 1) {
      const keep = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = keep;
    }
  }
  return 1 - row[b.length] / Math.max(a.length, b.length, 1);
};

if (ledger) {
  const known = JSON.parse(ledger.dataset.counterparties || "{}");
  const accounts = JSON.parse(ledger.dataset.accounts || "[]");
  const parties = Object.keys(known).sort((a, b) => a.localeCompare(b));
  document.querySelectorAll(".counterparty-input").forEach((counterparty) => {
    const form = counterparty.getAttribute("form");
    const category = document.querySelector(`.category-input[form="${form}"]`);
    const results = document.getElementById(counterparty.dataset.counterpartyResults);
    const clearDecision = (name) => document.querySelector(`input[type="hidden"][form="${form}"][name="${name}"]`)?.remove();
    const closeResults = () => { if (results) { results.hidden = true; counterparty.setAttribute("aria-expanded", "false"); } };
    const sync = () => {
      const isTransfer = accounts.some((name) => name.toLocaleLowerCase() === counterparty.value.trim().toLocaleLowerCase());
      if (category) {
        category.disabled = isTransfer;
        category.placeholder = t(isTransfer ? "Transfer — no category needed" : "Category — type to search");
        if (isTransfer) category.value = "";
        else if (!category.value) {
          const knownName = parties.find((name) => name.toLocaleLowerCase() === counterparty.value.trim().toLocaleLowerCase());
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
    const renderResults = () => {
      const query = counterparty.value.trim().toLocaleLowerCase();
      results.replaceChildren();
      const limit = query ? 8 : 5;
      const internal = accounts.filter((name) => name.toLocaleLowerCase().includes(query)).slice(0, limit);
      const saved = parties.filter((name) => name.toLocaleLowerCase().includes(query)).slice(0, Math.max(0, limit - internal.length));
      addGroup(t("Your accounts · internal transfers"), internal, t("Internal"));
      addGroup(t("People & businesses"), saved, t("External"));
      const close = query.length >= 3 ? parties.filter((name) => !saved.includes(name) && similar(query, name.toLocaleLowerCase()) >= 0.68).slice(0, 3) : [];
      addGroup(t("Did you mean"), close, t("External"));
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
          category?.focus();
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
document.querySelectorAll("form[data-autosave-existing]").forEach((form) => {
  const status = form.querySelector(".inline-save-status");
  let saved = new URLSearchParams(new FormData(form)).toString(), busy = false;
  const save = async () => {
    const data = new URLSearchParams(new FormData(form)), next = data.toString();
    if (busy || next === saved || !form.reportValidity()) return;
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

// Budget: one-click averages, per-category overrides, and typing means manual.
const budgetForm = document.querySelector("#budget-editor-form");
if (budgetForm) {
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
}

// Account form: show where the chosen type appears on the dashboard.
const typeSelect = document.getElementById("account_type");
if (typeSelect) {
  const groups = JSON.parse(typeSelect.dataset.groups || "{}");
  const target = document.getElementById("group_name");
  typeSelect.addEventListener("change", () => {
    if (target) target.textContent = groups[typeSelect.value] || "";
  });
}

// Bank import: filter the canonical Counterparty chooser as the user types.
document.querySelectorAll("[data-counterparty-filter]").forEach((search) => {
  const select = document.getElementById(search.dataset.counterpartyFilter);
  if (!select) return;
  search.addEventListener("input", () => {
    const query = search.value.trim().toLocaleLowerCase();
    Array.from(select.options).forEach((option) => {
      const fixed = option.value === "" || option.value === "new";
      option.hidden = !fixed && !option.textContent.toLocaleLowerCase().includes(query);
    });
  });
});

// Currency settings: filter the full ISO list as the user types.
document.querySelectorAll("[data-currency-search]").forEach((search) => {
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
  const unsaved = () => keepAfterError || changed();
  const askDiscard = () => window.ask({ title: "Discard your changes?", message: "What you typed in this form has not been saved.",
    ok: "Discard", cancel: "Keep editing", tone: "warn" });
  // Closing with unsaved changes asks first, then closes on yes; it returns false while it asks.
  const close = (goBack = true, force = false) => {
    if (!dialog.open) return false;
    if (!force && unsaved()) { askDiscard().then((yes) => { if (yes) close(goBack, true); }); return false; }
    dirty = false;
    keepAfterError = false;
    dialog.close();
    document.documentElement.classList.remove("sheet-open");
    document.body.classList.remove("popup-open");
    content.replaceChildren();
    if (goBack && history.state?.lightningPopup) history.back();
    else if (opener?.isConnected) opener.focus();
    window.scrollTo({ top: baseScroll, behavior: "instant" });
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
    requestAnimationFrame(() => (content.querySelector("[autofocus], input:not([type=hidden]), select, button, a[href]") ||
      dialog.querySelector("[data-popup-close]")).focus());
  };
  const initPopupFields = () => {
    initDateFields(content);
    const type = content.querySelector("#account_type"), help = content.querySelector("#account-type-help");
    if (type && help && !type.dataset.popupReady) {
      type.dataset.popupReady = "1";
      const update = () => {
        help.textContent = type.value === "DEPOSIT"
          ? "Certificate or time deposit: include the term, annual return, and maturity date in Notes."
          : type.value === "GAMEYA" ? "A gam'eya holds one savings circle's cash. After you add it, enter its terms."
          : type.value === "PHYSICAL_ASSET" ? "Add named items such as a ring after creating this account."
          : type.value === "BROKERAGE" ? "Record brokerage cash here before buying investments."
          : "";
      };
      type.addEventListener("change", update); update();
    }
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
        if (busy || next === saved || !form.reportValidity()) return;
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
      const shown = Number.isFinite(value) && value > 0 ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : "…";
      const account = root.dataset.accountName, currency = root.dataset.currency;
      if (kind === "transfer") {
        const to = destination.selectedOptions[0]?.textContent || "the selected account";
        note.textContent = t("Cash in {account} decreases by {amount} {currency}; cash in {target} increases by the same amount.", {account, amount: shown, currency, target: to});
      } else {
        const own = owner.selectedOptions[0]?.textContent || "you";
        note.textContent = t("Cash in {account} {direction} by {amount} {currency}; balance owned by {owner}.", {account, direction: t(kind === "out" ? "decreases" : "increases"), amount: shown, currency, owner: own});
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
      const wanted = match?.dataset.category || "";
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
    if (dialog.open) close(false, true);
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
    const submit = form.querySelector("button[type=submit]:not([form]),button:not([type])") || form.querySelector("button[type=submit]");
    const status = content.querySelector("[data-popup-status]");
    if (status) status.textContent = t("Saving…");
    if (submit) submit.disabled = true;
    try {
      const response = await fetch(form.action || location.href, {
        method: (form.method || "POST").toUpperCase(), body: new FormData(form),
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
        const keepInPopup = form.dataset.popupReturn === "popup";
        if (keepInPopup) {
          const doc = new DOMParser().parseFromString(text, "text/html");
          show(extract(doc), doc.title);
          activePopupUrl = response.url;
          history.pushState({ lightningPopup: true, baseUrl, baseScroll }, "", response.url);
          return;
        }
        const next = new URL(goToResponse ? response.url : baseUrl, location.href);
        close(false, true);  // saved: nothing to discard
        history.replaceState(null, "", next.pathname + next.search + next.hash);
        if (msg) sessionStorage.setItem("lightning-popup-success", msg);
        if (goToResponse) location.href = next.href;
        else {
          sessionStorage.setItem("lightning-popup-scroll", String(baseScroll));
          location.reload();
        }
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
    if (base.pathname + base.search + base.hash !== location.pathname + location.search + location.hash) location.reload();
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
document.querySelectorAll("[data-month-picker]").forEach((picker) => {
  // One month stepper: ‹ yyyy-mm ›. The box is typeable; arrows move a month.
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
        input.reportValidity();
        return;
      }
      input.setCustomValidity("");
      if (customInputs.every((field) => field.value.trim() && field.checkValidity())) {
        const start = customInputs.find((field) => field.name === "date_from");
        const end = customInputs.find((field) => field.name === "date_to");
        if (toIndex(end.value.trim()) < toIndex(start.value.trim())) {
          end.setCustomValidity("The end month must be the same as or after the start month.");
          end.reportValidity();
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
    if (event.key !== "Enter" || !event.target.matches("input")) return;
    event.preventDefault();
    if (!event.target.checkValidity() || (event.target === monthValue && !valid(monthValue.value.trim()))) {
      if (event.target === monthValue) monthValue.setCustomValidity(`Use yyyy-mm, up to ${currentMonth}.`);
      event.target.reportValidity();
      return;
    }
    form.requestSubmit(form.querySelector(".period-button.selected") || undefined);
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
      monthValue.reportValidity();
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
  document.querySelectorAll("input.month-input").forEach((input) => {
    input.readOnly = true;
    input.classList.add("month-picker-box");
    input.setAttribute("aria-haspopup", "dialog");
    input.addEventListener("click", () => (open?.input === input ? close() : show(input)));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") { event.preventDefault(); show(input); }
      if (event.key === "Escape") close();
    });
  });
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
  new MutationObserver(() => bind(document)).observe(document.body, { childList: true, subtree: true });
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
  new MutationObserver(() => enhance()).observe(document.body, { childList: true, subtree: true });
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
    const width = Math.max(rect.width, 220);
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
    Counterparty: "Counterparties", Category: "Categories", Investment: "Investments", Tag: "Tags", Search: "Transactions" };
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
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
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
  const toast = document.getElementById("busy-toast");
  if (!toast) return;
  const text = toast.querySelector(".busy-text"), link = toast.querySelector(".busy-link");
  let slow = 0, safety = 0, fade = 0;
  const show = (words, done = false) => {
    window.clearTimeout(fade);
    text.textContent = t(words);
    toast.classList.toggle("done", done);
    link.hidden = !done;
    toast.hidden = false;
  };
  const hide = () => { toast.hidden = true; };
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
  const watch = toast.dataset.watch;
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
(() => {
  document.querySelectorAll(".phone-txn[data-txn]").forEach((row) => {
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
})();

// C04.6 on a phone: the As-of chip is the phone's own date picker; choosing a day shows that day.
document.querySelectorAll("form.phone-as-of input[data-native-date]").forEach((input) => {
  input.addEventListener("change", () => { if (input.value) input.form.requestSubmit(); });
  input.addEventListener("click", () => { try { input.showPicker?.(); } catch (error) { /* the tap itself opens it */ } });
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
  const sync = () => {
    if (viewport.width !== width) { width = viewport.width; tallest = 0; }  // turning the phone starts again
    if (!typing()) tallest = Math.max(tallest, viewport.height);
    root.classList.toggle("keyboard-open", typing() && tallest - viewport.height > 120);
  };
  viewport.addEventListener("resize", sync);
  document.addEventListener("focusin", () => { tallest = Math.max(tallest, viewport.height); sync(); });
  document.addEventListener("focusout", () => setTimeout(sync, 0));
  sync();
})();
