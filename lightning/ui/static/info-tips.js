// One viewport-bounded tooltip for help buttons, including dynamically opened sheets.
(() => {
  const tip = document.createElement("div");
  tip.id = "lightning-info-tooltip";
  tip.className = "info-tooltip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  document.body.append(tip);
  let current = null;
  let describedBy = null;
  const close = () => {
    if (current) {
      if (describedBy === null) current.removeAttribute("aria-describedby");
      else current.setAttribute("aria-describedby", describedBy);
    }
    current = null;
    tip.hidden = true;
  };
  const show = (button) => {
    close();
    current = button;
    describedBy = button.getAttribute("aria-describedby");
    tip.textContent = button.dataset.tip;
    button.setAttribute("aria-describedby", [describedBy, tip.id].filter(Boolean).join(" "));
    tip.hidden = false;
    const box = button.getBoundingClientRect();
    const width = document.documentElement.clientWidth;
    const height = document.documentElement.clientHeight;
    const left = Math.max(12, Math.min(box.left, width - tip.offsetWidth - 12));
    const below = box.bottom + 8;
    const top = below + tip.offsetHeight <= height - 12 ? below : box.top - tip.offsetHeight - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(12, Math.min(top, height - tip.offsetHeight - 12))}px`;
  };
  const buttonAt = (event) => event.target.closest?.(".info-tip[data-tip]");
  document.addEventListener("pointerover", (event) => {
    const button = buttonAt(event);
    if (button && event.pointerType !== "touch" && !button.contains(event.relatedTarget)) show(button);
  });
  document.addEventListener("pointerout", (event) => {
    if (current && current.contains(event.target) && !current.contains(event.relatedTarget)) close();
  });
  document.addEventListener("focusin", (event) => { const button = buttonAt(event); if (button) show(button); });
  document.addEventListener("focusout", (event) => { if (current === buttonAt(event)) close(); });
  document.addEventListener("click", (event) => {
    const button = buttonAt(event);
    if (button) show(button);
    else if (!tip.contains(event.target)) close();
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
  document.addEventListener("scroll", (event) => { if (!tip.contains(event.target)) close(); }, true);
  window.addEventListener("resize", close);
})();
