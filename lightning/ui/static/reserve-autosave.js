// Refresh server-calculated summaries after a save without replacing editable fields or scrolling.
(() => {
  let queue = Promise.resolve();
  const text = (s) => window.lightningT ? window.lightningT(s) : s;
  document.querySelectorAll("[data-autosave-form], [data-reserve-autosave]").forEach((form) => {
    const status = form.querySelector(".inline-save-status");
    const body = () => new URLSearchParams(new FormData(form)).toString();
    let saved = body();
    let busy = false;
    const save = async () => {
      const sent = body();
      if (busy || sent === saved) return;
      busy = true;
      status.textContent = text("Saving…");
      let success = false;
      queue = queue.catch(() => {}).then(async () => {
        const response = await fetch(form.action, { method: "POST", body: sent,
          headers: { "X-Requested-With": "fetch", "Content-Type": "application/x-www-form-urlencoded" } });
        const html = await response.text();
        if (!response.ok) throw new Error(html);
        const fresh = new DOMParser().parseFromString(html, "text/html");
        document.querySelectorAll("[data-reserve-refresh]").forEach((node) => {
          const updated = fresh.querySelector(`[data-reserve-refresh="${node.dataset.reserveRefresh}"]`);
          if (updated) { node.innerHTML = updated.innerHTML; node.hidden = updated.hidden; }
        });
      });
      try {
        await queue;
        saved = sent;
        success = true;
        status.textContent = text("Saved");
      } catch (error) {
        status.textContent = error.message || text("Could not save. Retry by pressing Enter or leaving the field.");
      } finally {
        busy = false;
        if (success && saved !== body()) save();
      }
    };
    form.addEventListener("submit", (event) => { event.preventDefault(); save(); });
    form.addEventListener("focusout", (event) => { if (event.target.name) save(); });
    form.addEventListener("change", (event) => { if (event.target.name) save(); });
    form.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && event.target.name && event.target.tagName !== "SELECT") {
        event.preventDefault(); save();
      }
    });
  });
})();
