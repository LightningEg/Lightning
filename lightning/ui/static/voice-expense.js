/* Local expense dictation. Match complete words and keep conflicting fields unresolved. */
(() => {
  const normalize = text => text.toLowerCase().normalize("NFKC")
    .replace(/[\u064b-\u065f\u0670ـ]/g, "").replace(/[أإآ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه")
    .replace(/[٠-٩]/g, ch => String(ch.charCodeAt(0) - 1632)).replace(/[۰-۹]/g, ch => String(ch.charCodeAt(0) - 1776))
    .replace(/٫/g, ".").replace(/٬/g, ",").replace(/[^\p{L}\d.,/-]+/gu, " ").trim();

  const numbers = new Map();
  const add = (words, n) => numbers.set(normalize(words), n);
  const en = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(" ");
  const ar = "صفر واحد اتنين تلاته اربعه خمسه سته سبعه تمانيه تسعه عشره حداشر اتناشر تلتاشر اربعتاشر خمستاشر ستاشر سبعتاشر تمنتاشر تسعتاشر".split(" ");
  en.forEach((word, n) => add(word, n));
  ar.forEach((word, n) => add(word, n));
  const tens = "twenty thirty forty fifty sixty seventy eighty ninety".split(" ");
  const arabicTens = "عشرين تلاتين اربعين خمسين ستين سبعين تمانين تسعين".split(" ");
  tens.forEach((word, i) => {
    const base = (i + 2) * 10;
    add(word, base);
    add(arabicTens[i], base);
    for (let n = 1; n < 10; n++) {
      add(word + " " + en[n], base + n);
      add(ar[n] + " و" + arabicTens[i], base + n);
    }
  });
  for (const [word, n] of [["ميه",100],["مئه",100],["مائه",100],["ميتين",200],["مئتين",200],
    ["تلتميه",300],["تلاتميه",300],["ربعمية",400],["خمسمية",500],["ستمية",600],
    ["سبعمية",700],["تمنمية",800],["تسعمية",900],["الف",1000],["الفين",2000]]) add(word,n);
  for (let n = 1; n < 10; n++) add(en[n] + " hundred", n * 100);
  add("a hundred", 100);
  for (let n = 1; n < 10; n++) add(en[n] + " thousand", n * 1000);

  // Only join a smaller group after a spoken scale: "one thousand two hundred and ten".
  // Keep separate prices, including "a hundred pounds and fifty pounds", as separate candidates.
  function group(parts, start, conjunction) {
    let i = start;
    if (conjunction && ["and", "و"].includes(parts[i])) i++;
    let word = parts[i] || "";
    if (conjunction && word.startsWith("و") && !numbers.has(word)) word = word.slice(1);
    const pair = word + " " + parts[i + 1];
    if (numbers.has(pair)) return {value: numbers.get(pair), end: i + 2};
    if (numbers.has(word)) return {value: numbers.get(word), end: i + 1};
    return null;
  }

  function amounts(words) {
    const parts = words.replace(/([a-z])-(?=[a-z])/g, "$1 ").split(/\s+/);
    const found = [];
    for (let i = 0; i < parts.length;) {
      const token = parts[i].replace(/^و(?=\d)/, "");
      if (/^\d[\d,.]*$/.test(token)) {
        const valid = /^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?$/.test(token);
        found.push(valid ? token.replace(/,/g, "") : "");
        i++;
        continue;
      }
      const head = group(parts, i, false) || (token.startsWith("و") && group(parts, i, true));
      if (!head) {
        if (["thousand", "hundred", "الاف"].includes(token)) found.push("");
        i++;
        continue;
      }
      let value = head.value;
      i = head.end;
      for (const scale of [1000, 100]) {
        if (value < scale || value % scale !== 0) continue;
        const tail = group(parts, i, true);
        if (tail && tail.value > 0 && tail.value < scale) {
          value += tail.value;
          i = tail.end;
        }
      }
      found.push(String(value));
    }
    return found;
  }

  const aliases = [["fuel","petrol","بنزين"],["shell","شل"],["carrefour","كارفور"],["groceries","food groceries","بقاله"],["taxi","تاكسي"]];
  function matches(words, options) {
    const found = [];
    for (const option of options) {
      const name = normalize(option.label);
      const names = [name, ...(option.aliases || []).map(normalize), ...aliases.filter(pair => pair.includes(name)).flat()];
      for (const phrase of new Set(names)) {
        if (!phrase) continue;
        const pos = (" " + words + " ").indexOf(" " + phrase + " ");
        if (pos >= 0) found.push({option, pos, end: pos + phrase.length});
      }
    }
    return [...new Set(found.filter(a => !found.some(b => b.pos <= a.pos && b.end >= a.end &&
      b.end-b.pos > a.end-a.pos)).map(a => a.option))];
  }

  const monthNames = [
    ["january", "يناير"], ["february", "فبراير"], ["march", "مارس"], ["april", "ابريل"],
    ["may", "مايو"], ["june", "يونيو"], ["july", "يوليو"], ["august", "اغسطس"],
    ["september", "سبتمبر"], ["october", "اكتوبر"], ["november", "نوفمبر"], ["december", "ديسمبر"]
  ];
  const monthPattern = monthNames.flat().join("|");
  const calendarDay = new RegExp("(?:^| )(?:(\\d{1,2}) (" + monthPattern + ")|(" + monthPattern +
    ") (\\d{1,2}))(?: (\\d{4}))?(?= |$)", "g");

  function readDate(words, today) {
    const days = new Set();
    const record = (year, month, day) => {
      const iso = [year, month, day].map(n => String(n).padStart(2, "0")).join("-");
      const date = new Date(iso + "T12:00:00Z");
      days.add(!Number.isNaN(date.getTime()) && date.toISOString().startsWith(iso) ? iso : "");
      return " ";
    };
    words = words.replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, (_, y, m, d) => record(y, m, d));
    words = words.replace(calendarDay, (_, before, name1, name2, after, year) => {
      const month = monthNames.findIndex(names => names.includes(name1 || name2)) + 1;
      return record(year || today.slice(0, 4), month, before || after);
    });
    words = words.replace(/(?:^| )(yesterday|امبارح|مبارح|البارح|today|النهارده|النهاردا)(?= |$)/g, (_, word) => {
      const date = new Date(today + "T12:00:00Z");
      if (!["today", "النهارده", "النهاردا"].includes(word)) date.setUTCDate(date.getUTCDate() - 1);
      days.add(date.toISOString().slice(0, 10));
      return " ";
    });
    // Ask for ambiguous calendar expressions. Remove their numbers before reading the price.
    words = words.replace(/\b\d+[/-]\d+(?:[/-]\d+)?\b/g, () => { days.add(""); return " "; });
    words = words.replace(/(?:^| )(?:\d+ days? ago|من \d+ ايام)(?= |$)/g, () => { days.add(""); return " "; });
    const unclear = words.split(" ").some(word => monthNames.flat().includes(word) ||
      /^(?:last|ago|tomorrow|اول|بكره|السبت|الاحد|الاتنين|الثلاثاء|الاربعاء|الخميس|الجمعه|monday|tuesday|wednesday|thursday|friday|saturday|sunday)$/.test(word));
    if (unclear) days.add("");
    return {words: words.trim().replace(/\s+/g, " "), spoken: days.size > 0,
      value: days.size > 1 ? "" : days.size === 1 ? [...days][0] : today};
  }

  function parse(text, {categories, payees, today}) {
    const normalized = normalize(text).replace(/[.,](?!\d)/g, " ").replace(/\s+/g, " ").trim();
    const tokens = normalized.split(" ");
    const date = readDate(normalized, today);
    let words = date.words;
    const cats = matches(words,categories);
    const parties = matches(words,payees);
    // Strip matched names and their aliases before looking for prices (for example, "Studio 54").
    for (const option of [...cats, ...parties]) {
      for (const name of [option.label, ...(option.aliases || [])]) {
        words = (" " + words + " ").replaceAll(" " + normalize(name) + " ", " ").trim();
      }
    }
    const values = amounts(words);
    const half = /(?:جنيه|جنيها|pounds?) (?:ونص|and a half)(?: |$)/.test(words);
    const amount = values.length === 1 && Number(values[0]) > 0 ? values[0] : "";
    const unsupported = /[$€]/.test(text) || tokens.some(token =>
      /^(?:million|مليون|قرش|قروش|piastres?|cents?|dollars?|دولار|euros?|يورو|quarter|ربع|وربع|الا|point|فاصله|negative|minus|سالب)$/.test(token)) ||
      /(?:^| )-\d/.test(words);
    const unknownFraction = !half && tokens.some(word => ["ونص", "نص", "نصف", "half"].includes(word));
    const payee = parties.length === 1 ? parties[0] : null;
    const history = categories.filter(o => payee?.history?.includes(o.value));
    let category = "";
    if (cats.length === 1) category = cats[0].value;
    else if (!cats.length && payee) category = payee.defaultCategory || (history.length < 2 && payee.category) || "";

    let price = amount;
    if (unsupported || unknownFraction || (half && price.includes("."))) price = "";
    else if (price && half) price += ".50";
    return {
      amount: price,
      category,
      choices: cats.length ? cats : history,
      dateSpoken: date.spoken,
      payee: payee?.label || "",
      date: date.value,
      multipleAmounts: values.length > 1
    };
  }
  globalThis.lightningVoiceParse = parse;
})();
