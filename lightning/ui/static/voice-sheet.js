(() => {
  let active;
  window.lightningVoiceResult = (id, text, reason) => {
    if (active?.id !== id) return;
    const {receive, unchanged} = active;
    active = null;
    receive(unchanged() ? text : null, reason);
  };
  window.addEventListener("voiceavailable", () => {
    document.querySelectorAll("[data-voice-entry]").forEach(box => box.dispatchEvent(new Event("refresh")));
  });

  window.lightningInitVoice = (form) => {
    const box = form.querySelector("[data-voice-entry]");
    if (!box) return;
    const field = name => form.elements.namedItem(name);
    const ar = document.documentElement.lang.startsWith("ar");
    const say = (en, arabic) => ar ? arabic : en;
    const status = box.querySelector("[data-voice-status]");
    const mic = box.querySelector("[data-voice-mic]");
    const micLabel = mic.textContent;
    const choices = box.querySelector("[data-voice-choices]");
    const prompt = status.textContent;
    const lang = box.querySelector("select");
    let follow = "";
    let amountQuestion = "";
    let categoryChoices = [];
    let unclearDate = false;
    const refresh = () => { box.hidden = !window.lightningVoiceAvailable || field("kind").value !== "out"; };
    box.addEventListener("refresh", refresh);
    form.addEventListener("change", refresh);
    refresh();

    function write(name, value) {
      const input = field(name);
      input.value = value;
      input.dispatchEvent(new Event(name === "category_id" ? "change" : "input", {bubbles:true}));
    }
    function ask() {
      follow = ["amount","date","category_id"].find(name => !field(name).value) || "";
      const questions = {amount:say("How much did you spend?", "دفعت كام؟"), date:say("Which day?", "كان يوم إيه؟"),
        category_id:say("Which category?", "أنهي فئة؟")};
      const amountQuestions = {
        confirm: say("What exact amount should I record?", "أسجّل كام بالضبط؟"),
        currency: say("This account uses EGP. How many Egyptian pounds did you pay?", "الحساب ده بالجنيه المصري. دفعت كام بالمصري؟"),
        total: say("What was the total you actually spent?", "إجمالي اللي صرفته فعلاً كام؟"),
        multiple: say("I heard several amounts. How much did you actually spend?", "سمعت أكتر من مبلغ. صرفت كام فعلاً؟")
      };
      if (amountQuestions[amountQuestion]) questions.amount = amountQuestions[amountQuestion];
      if (unclearDate) questions.date = say("Which date did you mean? Say the day and month, or pick a date.", "تقصد تاريخ إيه؟ قول اليوم والشهر أو اختار التاريخ.");
      choices.replaceChildren();
      if (follow === "category_id" && categoryChoices.length) {
        questions.category_id = say("Which category fits this expense?", "أنهي فئة تناسب المصروف ده؟");
        for (const item of categoryChoices) choice(item.label, () => { write("category_id", item.value); ask(); });
      }
      status.textContent = questions[follow] || say("Review, then save your expense.", "راجع المصروف وبعدين احفظه.");
      if (follow === "amount") field("amount").focus();
    }
    function choice(label, select) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "phone-chip";
      button.textContent = label;
      button.onclick = () => { choices.replaceChildren(); select(); };
      choices.append(button);
    }
    function receive(text, reason) {
      mic.textContent = micLabel;
      if (!box.isConnected || box.hidden || box.closest("dialog:not([open])")) return;
      if (text === null) {
        ask();
        return;
      }
      if (!text) {
        const errors = {
          permission: say("Allow microphone access in Android settings, or type the expense.", "اسمح باستخدام الميكروفون من إعدادات أندرويد أو اكتب المصروف."),
          language: say("Choose another speech language or install its offline language pack.", "اختار لغة تانية أو نزّل حزمة اللغة على الجهاز.")
        };
        status.textContent = errors[reason] || say("Couldn’t hear you. Try again or type.", "مسِمعتكش. جرّب تاني أو اكتب المصروف.");
        return;
      }
      const categories = [...field("category_id").options].filter(o => !o.disabled && o.dataset.movement === "OUTFLOW")
        .map(o => ({label:o.textContent.trim(),value:o.value}));
      const payees = [...form.querySelectorAll("#popup-counterparties option")].map(o => ({
        label: o.value,
        aliases: JSON.parse(o.dataset.aliases || "[]"),
        defaultCategory: o.dataset.defaultCategory,
        category: o.dataset.category,
        history: (o.dataset.history || "").split(",").filter(Boolean)
      }));
      const today = box.dataset.voiceToday;
      const context = {categories,payees,today};
      const draft = window.lightningVoiceParse(text,context);
      choices.replaceChildren();
      const phrases = text.split(/\s+(?:and\s+|و\s*)/iu);
      const change = /(?:change|back|باقي|الباقي|الباقى|رجعلي|خدت)/i.test(text);
      if (!follow && !change && draft.amountQuestion === "multiple" && draft.multipleAmounts && phrases.length > 1 && phrases.every(p => {
        const part = window.lightningVoiceParse(p, context);
        return part.amount && (part.category || part.payee);
      })) {
        status.textContent = say("Which expense first?", "نبدأ بأنهي مصروف؟");
        for (const phrase of phrases) choice(phrase, () => receive(phrase));
        return;
      }
      if (!follow || follow === "amount") {
        amountQuestion = draft.amountQuestion;
        write("amount", draft.amount);
      }
      if (!follow || follow === "date") {
        unclearDate = !draft.date || (follow === "date" && !draft.dateSpoken);
        write("date", unclearDate ? "" : draft.date);
      }
      if (!follow) write("counterparty",draft.payee);
      if (!follow || follow === "category_id") {
        write("category_id",draft.category);
        if (!follow || draft.choices.length) categoryChoices = draft.choices;
      }
      ask();
    }
    mic.addEventListener("click", () => {
      if (active?.receive === receive) {
        active = null;
        mic.href = "lightning-voice://cancel";
        mic.textContent = micLabel;
        status.textContent = prompt;
        if (follow) ask();
        return;
      }
      if (follow && field(follow).value) ask();
      const id = crypto.randomUUID();
      const initial = ["amount", "date", "counterparty", "category_id"].map(name => [name, field(name).value]);
      active = {id, receive, unchanged: () => initial.every(([name, value]) => field(name).value === value)};
      mic.textContent = say("Cancel recording", "إلغاء التسجيل");
      status.textContent = say("Listening…", "سامعك…");
      const language = lang.value === "ar-EG" ? "ar-EG" : "en-US";
      mic.href = "lightning-voice://record?id=" + id + "&lang=" + language;
    });
    form.addEventListener("change", e => {
      if (e.target.name === "kind") {
        if (active?.receive === receive) active = null;
        mic.textContent = micLabel;
        follow = "";
        status.textContent = prompt;
        choices.replaceChildren();
      } else if (follow && e.target.name === follow && e.target.value && e.isTrusted) ask();
    });
  };
})();
