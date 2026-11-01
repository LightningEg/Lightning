/* Phone navigation that keeps the frame (IT-3AO2). A tap on a link, the month stepper or a period choice fetches the
   next page and swaps only what changes - the app bar, the content and the tab bar - instead of loading the whole
   document again. On a phone's CPU a full load costs 400-600 ms of parsing, styling and starting scripts; a swap
   about 100 (Audit 13). Scripts, styles, the sheet and the search bar stay; the new content gets its set-up through
   the "lightning:page" event (app.js, phone-fields.js) or the observers that already watch the page, and the page's
   own scripts run again - only those carrying the nonce of the response they came in, as on a full load.
   Anything this cannot do safely loads the normal way: another origin, a download, a new tab, a page script that
   listens on the whole document, a page whose set-up still runs only on a full load (LOADS_WHOLE), or a different
   frame (language, theme, the profile gate). No financial logic: the server still builds every page. */
(() => {
  const html = document.documentElement;
  if (!html.classList.contains("phone") || !window.fetch || !window.DOMParser || !window.history?.pushState) return;

  // Content whose script is bound once at load and not run again on a swap; such a page loads whole.
  // The PC register, statement import review, first-run setup and the profile gate: none is a phone page you tap into.
  const LOADS_WHOLE = [
    "#page-jump", "[data-fullscreen-toggle]", ".ledger", ".category-input", ".import-category", ".import-transfer-suggestion",
    "select[data-chip-add]", "input[data-strength]",
  ].join(", ");
  // Page scripts from a file that may run again on a swapped page: each binds only to its own content.
  const SAFE_SRC = /^\/static\/(reserve-autosave|ask-ai|import-drop)\.js$/;
  const OWN_NONCE = document.currentScript?.nonce || "";
  const REGIONS = ["header.phone-appbar", "main.phone-content", "nav.phone-tabbar"];
  // Downloads and files (as the busy toast's leaves() in app.js), static files and the profile gate.
  const ELSEWHERE = /^\/(static|exports|samples|profiles)(\/|$)/;

  const frameKey = (doc) => [
    doc.documentElement.lang, doc.documentElement.dir,
    ...[...doc.querySelectorAll("head link[rel=stylesheet], head script[src], body > script[src]")]
      .map((node) => node.getAttribute("href") || node.getAttribute("src")),
    ...["lightning-theme", "lightning-owned", "lightning-follow-night", "lightning-session"]
      .map((name) => doc.querySelector(`meta[name="${name}"]`)?.content || ""),
  ].join("|");
  let frame = "";  // taken on first use: while this script runs, the scripts after it are not parsed yet
  const here = () => location.pathname + location.search;
  let shown = here();  // the address whose content is on screen now
  let pending = null;  // the swap under way; a newer tap cancels it
  let early = null;    // a tab's page asked for when the finger lands, before it lifts

  const sameDocument = (url) => url.pathname + url.search === here();
  const canSwap = (url) => url.origin === location.origin && !ELSEWHERE.test(url.pathname);
  const loadWhole = (url) => { window.location.assign(url); };
  const nonceOf = (response) => /'nonce-([^']+)'/.exec(response.headers.get("content-security-policy") || "")?.[1] || "";
  // The page scripts to run again, in order, or null when the page must load whole. A script without the response's
  // nonce would not have run on a full load either, so it is dropped; a data island (JSON) stays as it is.
  const scriptsOf = (parts, nonce) => {
    const run = [];
    for (const [, next] of parts) {
      for (const node of next.querySelectorAll("script")) {
        const type = (node.getAttribute("type") || "").trim().toLowerCase();
        if (type && type !== "text/javascript") {
          if (type === "module") return null;
          continue;
        }
        if (!nonce || node.getAttribute("nonce") !== nonce) { node.remove(); continue; }
        const src = node.getAttribute("src");
        if (src ? !SAFE_SRC.test(new URL(src, location.href).pathname)
            : /\b(document|window)\.addEventListener\b/.test(node.textContent)) return null;
        run.push(node);
      }
    }
    return run;
  };
  const runAgain = (node) => {
    const fresh = document.createElement("script");
    fresh.nonce = OWN_NONCE;
    const src = node.getAttribute("src");
    if (src) { fresh.src = src; fresh.async = false; }
    else fresh.textContent = `{\n${node.textContent}\n}`;  // a block: its names do not clash with the last visit's
    node.replaceWith(fresh);
  };
  const keepScroll = () => {
    try { history.replaceState({ ...(history.state || {}), lightningScroll: window.scrollY }, ""); } catch (error) { /* full */ }
  };

  const swap = async (url, { push = true, scroll = 0 } = {}) => {
    pending?.abort();
    const ask = new AbortController();
    pending = ask;
    const busy = document.querySelector("main.phone-content");
    busy?.setAttribute("aria-busy", "true");
    const head = early && early.href === url && Date.now() - early.at < 3000 ? early.response : null;
    early = null;
    let doc;
    let address;
    let nonce = "";
    try {
      const response = await (head || fetch(url, { signal: ask.signal, credentials: "same-origin" }));
      if (!response.ok || !(response.headers.get("content-type") || "").includes("text/html")) throw new Error("not a page");
      address = new URL(response.url || url, location.href);
      nonce = nonceOf(response);
      doc = new DOMParser().parseFromString(await response.text(), "text/html");
    } catch (error) {
      if (ask.signal.aborted) return;
      busy?.removeAttribute("aria-busy");
      loadWhole(url);
      return;
    }
    if (ask.signal.aborted) return;
    pending = null;
    const parts = REGIONS.map((selector) => [document.querySelector(selector), doc.querySelector(selector)]);
    const watching = doc.querySelector("#busy-toast[data-watch]");
    frame ||= frameKey(document);
    const run = parts.every(([now, next]) => now && next) ? scriptsOf(parts, nonce) : null;
    if (frameKey(doc) !== frame || !run || watching
        || parts.some(([, next]) => next.matches(LOADS_WHOLE) || next.querySelector(LOADS_WHOLE))) {
      busy?.removeAttribute("aria-busy");
      loadWhole(address.href);
      return;
    }
    if (push) {
      keepScroll();
      history.pushState({ lightningSwap: true }, "", address.href);
    } else if (address.pathname + address.search !== here()) {
      history.replaceState(history.state, "", address.href);
    }
    shown = here();
    document.title = doc.title;  // the html element and its classes (hidden amounts, theme) stay as they are
    document.body.dataset.baseCurrency = doc.body.dataset.baseCurrency || document.body.dataset.baseCurrency || "";
    for (const [now, next] of parts) now.replaceWith(document.adoptNode(next));
    const main = document.querySelector("main.phone-content");
    run.forEach(runAgain);
    document.dispatchEvent(new CustomEvent("lightning:page", { detail: { root: main } }));
    window.scrollTo({ top: scroll, behavior: "instant" });
    if (!main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1");
    main.focus({ preventScroll: true });
  };

  // Our own content only: never a link inside a sheet, a dialog or the search bar.
  const inFrame = (node) => node.closest?.(REGIONS.join(", ")) && !node.closest("dialog");

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.("a[href]");
    if (!link || !inFrame(link) || link.target || link.hasAttribute("download") || link.matches("[data-popup-open], [data-no-swap]")) return;
    const url = new URL(link.href, location.href);
    if (!canSwap(url) || (sameDocument(url) && url.hash)) return;
    event.preventDefault();
    swap(url.href);
  });

  // A tab is asked for as the finger lands (about 100 ms before the tap ends); the tab bar never scrolls, so a touch
  // there is a tap. In place of a <link rel=prefetch>, which a no-store page cannot use.
  document.addEventListener("pointerdown", (event) => {
    const link = event.target.closest?.(".phone-tabbar a[href]:not([data-popup-open])");
    if (!link || event.button !== 0) return;
    const url = new URL(link.href, location.href);
    if (!canSwap(url)) return;
    early = { href: url.href, at: Date.now(), response: fetch(url.href, { credentials: "same-origin" }) };
    early.response.catch(() => {});
  }, { passive: true });

  // GET forms in the content (the month stepper, the period sheet, search and filters) are navigation too.
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (event.defaultPrevented || !(form instanceof HTMLFormElement) || !inFrame(form) || form.target
        || (form.getAttribute("method") || "get").toLowerCase() !== "get" || form.matches("[data-no-swap]")) return;
    const submitter = event.submitter;
    const url = new URL(submitter?.getAttribute("formaction") || form.getAttribute("action") || location.href, location.href);
    if (!canSwap(url)) return;
    const data = new FormData(form);
    if (submitter?.name) data.append(submitter.name, submitter.value);
    url.search = new URLSearchParams([...data].filter(([, value]) => typeof value === "string")).toString();
    event.preventDefault();
    swap(url.href);
  });

  // Back and forward (the phone's back gesture too) return to a swapped page by swapping again. A sheet's own
  // history entries are app.js's: when the address is still the page on screen, there is nothing to do here.
  window.addEventListener("popstate", (event) => {
    if (here() === shown || event.state?.lightningPopup) return;
    swap(location.href, { push: false, scroll: event.state?.lightningScroll || 0 });
  });
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  // Leaving the app's page for good (a full load) keeps the place to come back to.
  window.addEventListener("pagehide", keepScroll);
  const back = history.state?.lightningScroll;
  if (back) requestAnimationFrame(() => window.scrollTo({ top: back, behavior: "instant" }));
})();
