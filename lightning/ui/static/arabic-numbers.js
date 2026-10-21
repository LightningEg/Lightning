/* Localize visible numeric text in the Arabic UI only. Values, URLs and identifiers stay intact. */
(() => {
  const digitMap = {"0":"٠", "1":"١", "2":"٢", "3":"٣", "4":"٤", "5":"٥", "6":"٦", "7":"٧", "8":"٨", "9":"٩"};
  const asciiLetter = /[A-Za-z]/;
  const isoDate = /^\d{4}-\d{2}(?:-\d{2})?$/;
  const protectedSelector = "script,style,textarea,input,code,pre,kbd,samp,[contenteditable='true']";

  // Every figure and date reads left to right as one unit (A06.2): the isolate keeps a minus on the left of its
  // digits, an amount's grouping in order and a yyyy-mm-dd date from flipping inside the Arabic line.
  const isolate = (value) => "\u2066" + value + "\u2069";
  // A date's hyphens sit between Arabic-Indic digits, which a plain isolate would flip into 12-10-2026: the
  // left-to-right override keeps the digits in the order they are written (the guideline's bdo dir="ltr").
  const isolateDate = (value) => "\u2066\u202D" + value + "\u202C\u2069";

  // One token of text (no spaces): the figure itself, without the bracket or the sentence punctuation around it,
  // so "(+3.8%)" and "3,410," read as numbers too and every decimal point is the Arabic "٫".
  function localizeToken(token) {
    // Keep ISO date separators, while using Arabic grouping/decimal marks for values.
    if (/^\d{4}-\d{2}(?:-\d{2})?$/.test(token)) {
      return isolateDate(token.replace(/[0-9]/g, (digit) => digitMap[digit]));
    }
    // Compact financial values use the app's k/M suffixes (for example 9.7k).
    const compact = token.match(/^([+\-−±]?\d+(?:[,.]\d+)?)([kM])$/);
    if (compact) return isolate(compact[1].replace(",", "٬").replace(".", "٫").replace(/[0-9]/g, (digit) => digitMap[digit]) + compact[2]);
    const number = token.match(/^([+\-−±]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(%?)$/);
    if (number) {
      const localized = number[1] + number[2].replaceAll(",", "٬") + (number[3] || "").replace(".", "٫") + number[4];
      return isolate(localized.replace(/[0-9]/g, (digit) => digitMap[digit]));
    }
    // Alphanumeric tokens are often tickers, version strings, filenames or transaction references.
    if (asciiLetter.test(token)) return token;
    return token.replace(/[0-9]/g, (digit) => digitMap[digit]);
  }

  // A middle dot beside a number reads as the Arabic zero "٠" (Late · 17 days reads as 170): there it is the Arabic
  // comma. The server does the same for the page it sends (lightning/ui/i18n.py arabic_dots); this covers text
  // the browser builds. A dot between two words is left alone.
  const figureEdge = "[0-9٠-٩%]";
  const bidiMarks = "[⁦-⁩‪-‮]*";
  const dotAfterFigure = new RegExp("(" + figureEdge + bidiMarks + ")\\s*·\\s*", "g");
  const dotBeforeFigure = new RegExp("\\s*·\\s*(?=" + bidiMarks + "[0-9٠-٩])", "g");
  function arabicDots(text) {
    return text.replace(dotAfterFigure, "$1، ").replace(dotBeforeFigure, "، ");
  }

  function localizeNumericText(text) {
    return arabicDots(String(text).split(/(\s+)/).map((token) => {
      if (!token) return token;
      const parts = token.match(/^([(\[«“"'،]*)([\s\S]*?)([)\]»”"'،,.;:!?؟]*)$/);
      if (!parts || !parts[2]) return token;
      return parts[1] + localizeToken(parts[2]) + parts[3];
    }).join(""));
  }

  function excludedTextNode(node) {
    let parent = node.parentElement;
    while (parent) {
      if (parent.matches(protectedSelector)) return true;
      if (parent.classList?.contains("code")) {
        const value = parent.textContent.trim();
        // ISO dates use the code style in registers; other code-styled strings are identifiers.
        if (!isoDate.test(value)) return true;
      }
      parent = parent.parentElement;
    }
    return false;
  }

  function localizeTextNode(node) {
    if (!excludedTextNode(node)) {
      const localized = localizeNumericText(node.nodeValue);
      if (localized !== node.nodeValue) node.nodeValue = localized;
    }
  }

  function localizeAttribute(element, name) {
    const value = element.getAttribute(name);
    if (value == null || (element.matches(protectedSelector) && name !== "placeholder") || element.classList?.contains("code")) return;
    const localized = localizeNumericText(value);
    if (localized !== value) element.setAttribute(name, localized);
  }

  function localizeTree(root) {
    if (root.nodeType === Node.TEXT_NODE) {
      localizeTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
    if (root.nodeType === Node.ELEMENT_NODE) {
      for (const name of ["aria-label", "title", "data-tip", "placeholder"]) localizeAttribute(root, name);
      if (root.matches(protectedSelector)) return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) localizeTextNode(node);
    if (root.querySelectorAll) {
      root.querySelectorAll("[aria-label], [title], [data-tip], [placeholder]").forEach((element) => {
        for (const name of ["aria-label", "title", "data-tip", "placeholder"]) localizeAttribute(element, name);
      });
    }
  }

  if (typeof module !== "undefined" && module.exports) module.exports = {localizeNumericText};
  if (typeof document === "undefined" || !/^ar(?:-|$)/i.test(document.documentElement.lang)) return;

  localizeTree(document.body);
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "characterData") localizeTextNode(record.target);
      for (const node of record.addedNodes || []) localizeTree(node);
      if (record.type === "attributes") localizeAttribute(record.target, record.attributeName);
    }
  });
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["aria-label", "title", "data-tip", "placeholder"]
  });
})();
