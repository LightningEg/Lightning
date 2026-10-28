// One drop zone for many statements (PC P8): each file is matched to an account by its last four digits or
// the bank's name, then sent to that account's own review, so duplicates and rules work as before.
(() => {
  const host = document.querySelector("[data-import-drop]");
  if (!host) return;
  const input = host.querySelector("#import-files");
  const zone = host.querySelector(".drop-zone");
  const list = host.querySelector("[data-import-list]");
  const row = host.querySelector("[data-import-row]");
  const send = host.querySelector("[data-import-send]");
  const session = host.querySelector("[data-session]").value;
  const t = (s) => (window.lightningT ? window.lightningT(s) : s);
  const files = [];

  const guess = (name, select) => {
    const text = name.toLowerCase();
    const digits = text.match(/\d{4}/g) || [];
    const options = [...select.options].filter((o) => o.value);
    const byDigits = options.find((o) => o.dataset.last4 && digits.includes(o.dataset.last4));
    if (byDigits) return byDigits.value;
    const byName = options.find((o) => o.dataset.words.split(/\W+/).some((w) => w.length > 2 && text.includes(w)));
    return byName ? byName.value : "";
  };
  const refresh = () => { send.disabled = !files.length || files.some((f) => !f.select.value); };
  const add = (picked) => {
    for (const file of picked) {
      if (!/\.csv$/i.test(file.name)) continue;
      const item = row.content.firstElementChild.cloneNode(true);
      item.querySelector(".import-name").textContent = file.name;
      const select = item.querySelector("select");
      select.value = guess(file.name, select);
      item.querySelector(".import-state").textContent = select.value ? t("Matched") : t("Choose the account");
      select.addEventListener("change", refresh);
      list.append(item);
      files.push({ file, select, item });
    }
    refresh();
  };
  input.addEventListener("change", () => add(input.files));
  ["dragenter", "dragover"].forEach((e) => zone.addEventListener(e, (ev) => { ev.preventDefault(); zone.classList.add("is-over"); }));
  ["dragleave", "drop"].forEach((e) => zone.addEventListener(e, (ev) => { ev.preventDefault(); zone.classList.remove("is-over"); }));
  zone.addEventListener("drop", (ev) => add(ev.dataTransfer.files));

  send.addEventListener("click", async () => {
    send.disabled = true; send.setAttribute("aria-busy", "true");
    let stuck = false;
    // one file per request: the profile app takes one file part per upload, and each file is its own batch to undo
    for (const f of files) {
      const account = f.select.value;
      const body = new FormData();
      body.append("file", f.file);
      body.append("__session", session);
      const res = await fetch(`/accounts/${account}/import`, { method: "POST", body, credentials: "same-origin" });
      const ok = res.ok && /\/import\/\d+/.test(res.url);
      const state = f.item.querySelector(".import-state");
      state.innerHTML = "";
      if (ok) state.textContent = t("Ready to review");
      else { stuck = true; const a = document.createElement("a"); a.href = `/accounts/${account}/import`; a.textContent = t("Set the columns"); state.append(a); }
    }
    send.removeAttribute("aria-busy");
    if (!stuck) location.reload();
  });
})();
