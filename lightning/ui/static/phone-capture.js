/* Phone capture (3AN3, 3AN5, 3AN6): the Add sheet's chips, Search as you type, and the small controls the sheets share.
   Every piece is a layer: without this file the sheet's fields, the page's links and Search's form all still work.
   - Add sheet: the usual categories as chips over the Category field, the account as one changeable chip, the labels that
     follow Out, In and Transfer, and the sheet riding above the keyboard.
   - A link with data-open-sheet opens a sheet on the page (Views, from the ⋯ menu); a form with data-auto-submit sends
     as soon as its field is chosen (a category in a transaction's sheet).
   - Search: the results are redrawn as the words change; nothing is sent to a server outside this phone. */
(() => {
  const t = (text, values) => (window.lightningT ? window.lightningT(text, values) : text);

  /* A link that opens a sheet already on the page; the menu it was in closes. */
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-open-sheet]");
    if (!link) return;
    event.preventDefault();
    const sheet = document.querySelector(link.getAttribute("href"));
    const menu = link.closest("details.action-menu");
    if (menu) menu.open = false;
    if (sheet) sheet.open = true;
  });

  /* A chosen field sends its form (the "another category" picker in a row's sheet). */
  document.addEventListener("change", (event) => {
    const form = event.target.closest && event.target.closest("form[data-auto-submit]");
    if (form && event.target.matches("select") && event.target.value) form.requestSubmit();
  });

  /* The Add sheet. */
  const initEntry = (root) => {
    root.querySelectorAll(".phone-entry.is-new").forEach((sheet) => {
      if (sheet.dataset.captureReady) return;
      sheet.dataset.captureReady = "1";
      const form = sheet.querySelector("form.phone-form");
      if (!form) return;
      const select = form.querySelector('select[name="category_id"]');
      const chips = sheet.querySelector("[data-category-chips]");
      const kindNow = () => (form.querySelector('[name="kind"]:checked') || {}).value || "out";
      let openOther = false;
      const sync = () => {
        const kind = kindNow();
        form.querySelectorAll("[data-account-word]").forEach((word) => { word.hidden = (word.dataset.accountWord === "to") !== (kind === "in"); });
        if (!chips || !select) return;
        chips.querySelectorAll("[data-chip-kind]").forEach((group) => { group.hidden = group.dataset.chipKind !== kind; });
        let onChip = false;
        chips.querySelectorAll("[data-category]").forEach((chip) => {
          const on = !!select.value && chip.dataset.category === select.value;
          chip.setAttribute("aria-pressed", String(on));
          chip.classList.toggle("is-chosen", on);
          if (on && !chip.closest("[hidden]")) onChip = true;
        });
        const picker = select.closest(".counterparty-picker");
        const show = openOther || (!!select.value && !onChip);
        if (picker) picker.hidden = !show;
        const other = chips.querySelector("[data-chip-other]");
        if (other) { other.setAttribute("aria-expanded", String(show)); other.classList.toggle("is-chosen", show && !onChip); }
      };
      if (chips && select) {
        chips.hidden = false;  // the chips are a layer: the field itself is all there is without this script
        chips.addEventListener("click", (event) => {
          const chip = event.target.closest("[data-category]");
          const other = event.target.closest("[data-chip-other]");
          if (chip) {
            select.value = chip.dataset.category === select.value ? "" : chip.dataset.category;
            select.dispatchEvent(new Event("change", { bubbles: true }));
          } else if (other) {
            openOther = !openOther;
            sync();
            const input = select.closest(".counterparty-picker")?.querySelector("input");
            if (openOther && input) input.focus({ preventScroll: true });
          }
        });
        select.addEventListener("change", () => { select.setCustomValidity(""); sync(); });
      }
      form.querySelectorAll('[name="kind"]').forEach((radio) => radio.addEventListener("change", sync));
      // Save with no category: the field that says so must be on screen, or the browser blocks the form with nothing to read.
      form.addEventListener("invalid", (event) => {
        if (!event.target.closest("[data-category-field]") || !select) return;
        select.setCustomValidity(t("Choose a category."));  // our own words, not the browser's "Choose an option from the list"
        openOther = true;
        sync();
      }, true);
      sync();
      setTimeout(sync, 0);  // after the pickers have been drawn

      /* The account is one chip: choosing another opens the same sheet for it, with what was typed carried over. */
      const account = form.querySelector("[data-account-chip]");
      if (account) {
        account.addEventListener("change", () => {
          const params = new URLSearchParams();
          ["amount", "counterparty", "date", "notes", "sms_fp", "sms_ending"].forEach((name) => {
            const field = form.querySelector(`[name="${name}"]`);
            if (field && field.value) params.set(name, field.value);
          });
          params.set("kind", kindNow());
          if (select && select.value) params.set("category_id", select.value);
          params.set("return_to", (form.querySelector('[name="return_to"]') || {}).value || "/");
          if (window.lightningPopupOpen) window.lightningPopupOpen(`/accounts/${account.value}/transaction/new?${params}`);
        });
      }
    });
  };

  /* The sheet rides above the keyboard: on a phone whose keyboard shortens only the visual viewport, the sheet is lifted by
     what the keyboard covers and kept shorter than what is left. */
  const viewport = window.visualViewport;
  if (viewport) {
    const lift = () => {
      const root = document.documentElement;
      const covered = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
      root.style.setProperty("--kb", `${Math.round(covered)}px`);
      root.style.setProperty("--vv-h", `${Math.round(viewport.height)}px`);
    };
    viewport.addEventListener("resize", lift);
    viewport.addEventListener("scroll", lift);
  }

  const box = document.getElementById("app-popup-content");
  if (box) new MutationObserver(() => initEntry(box)).observe(box, { childList: true });
  document.addEventListener("DOMContentLoaded", () => initEntry(document));
  document.addEventListener("lightning:page", (event) => initEntry(event.detail.root));

  /* A message shown as a toast leaves the address: a reload does not show it again. */
  const toast = () => {
    if (!document.querySelector(".phone-flash")) return;
    try {
      const url = new URL(location.href);
      if (!url.searchParams.has("msg")) return;
      url.searchParams.delete("msg");
      history.replaceState(history.state, "", url.pathname + url.search + url.hash);
    } catch (_) { /* the address stays as it is */ }
  };
  document.addEventListener("DOMContentLoaded", toast);
  if (document.readyState !== "loading") toast();

  /* Search as you type: the field asks for the results alone, after a short pause, and the page keeps its own place. */
  const live = (root) => {
    root.querySelectorAll("form[data-live-search]").forEach((form) => {
      if (form.dataset.liveReady) return;
      form.dataset.liveReady = "1";
      const field = form.querySelector('input[name="q"]');
      const target = document.querySelector(form.dataset.liveSearch);
      if (!field || !target) return;
      if (field.hasAttribute("autofocus")) setTimeout(() => field.focus({ preventScroll: true }), 60);
      let timer = 0, serial = 0, pending = null;
      /* Anything typed, submitted or navigated away from makes the request in flight obsolete: it is stopped, and
         whatever of it still arrives is ignored (the serial). */
      const forget = () => { ++serial; if (pending) pending.abort(); pending = null; };
      const ask = async () => {
        forget();
        const mine = serial;
        const controller = pending = new AbortController();
        const query = field.value.trim().replace(/\s+/g, " ");
        try {
          const response = await fetch(`${form.getAttribute("action") || "/search"}?${new URLSearchParams({ q: query, fragment: "1" })}`,
            { credentials: "same-origin", headers: { "X-Requested-With": "fetch" }, signal: controller.signal });
          if (!response.ok) return;
          const body = await response.text();
          if (mine !== serial || !form.isConnected || !target.isConnected) return;
          target.innerHTML = body;
          if (window.lightningRefresh) window.lightningRefresh(target);
          const url = new URL(location.href);
          if (query) url.searchParams.set("q", query); else url.searchParams.delete("q");
          history.replaceState(history.state, "", url.pathname + url.search + url.hash);
        } catch (_) { /* offline or the page closed: the results stay as they were */ }
      };
      field.addEventListener("input", () => { forget(); clearTimeout(timer); timer = setTimeout(ask, 140); });
      form.addEventListener("submit", (event) => { event.preventDefault(); clearTimeout(timer); ask(); });
      window.addEventListener("pagehide", () => { clearTimeout(timer); forget(); });
    });
  };
  document.addEventListener("DOMContentLoaded", () => live(document));
  if (document.readyState !== "loading") live(document);
  document.addEventListener("lightning:page", (event) => live(event.detail.root));
})();

