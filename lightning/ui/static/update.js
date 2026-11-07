/* Settings "Lightning version": while a check or download runs, re-read the block (progress comes from the server). */
(function () {
  var block = document.getElementById("lightning-version");
  if (!block || !block.dataset.updatePoll) return;
  var timer = setInterval(function () {
    fetch(block.dataset.updatePoll, {credentials: "same-origin"}).then(function (r) { return r.text(); }).then(function (html) {
      var holder = document.createElement("div");
      holder.innerHTML = html;
      var fresh = holder.querySelector("#lightning-version");
      if (!fresh) return;
      block.replaceWith(fresh);
      block = fresh;
      if (!block.dataset.updatePoll) { clearInterval(timer); }
    }).catch(function () {});
  }, 1000);
})();
