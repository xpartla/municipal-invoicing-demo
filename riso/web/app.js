// Shared helpers and the Alpine components of the pages. Every page talks to the JSON API only.

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = describeDetail((await response.json()).detail) ?? detail;
    } catch {
      // Not JSON; keep the status text.
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

function postJSON(url, body) {
  return fetchJSON(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// FastAPI reports validation errors as a list of {loc, msg}; our own endpoints as strings.
function describeDetail(detail) {
  if (detail == null) return null;
  if (typeof detail === "string") return sk(detail);
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item === "string" ? sk(item) : `${(item.loc ?? []).slice(1).join(".")}: ${item.msg}`,
      )
      .join("; ");
  }
  return JSON.stringify(detail);
}

const amountFormat = new Intl.NumberFormat("sk-SK", { style: "currency", currency: "EUR" });

function formatAmount(value) {
  return value == null || Number.isNaN(Number(value)) ? "—" : amountFormat.format(value);
}

// An amount as typed into the accounting software: decimal comma, two places, no spaces.
function amountText(value) {
  return value == null ? "" : Number(value).toFixed(2).replace(".", ",");
}

function parseAmount(text) {
  const cleaned = String(text ?? "").replace(/\s/g, "").replace(",", ".");
  return cleaned === "" || Number.isNaN(Number(cleaned)) ? null : Number(cleaned);
}

function formatDate(value) {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return `${Number(day)}.${Number(month)}.${year}`;
}

function formatPercent(value) {
  if (value == null) return "—";
  return `${(value * 100).toLocaleString("sk-SK", { maximumFractionDigits: 1 })} %`;
}

// An entry's gross as printed, or its net plus VAT when only those are.
function entryGross(entry) {
  if (entry.gross != null) return entry.gross;
  return entry.net != null && entry.vat != null ? entry.net + entry.vat : null;
}

const SPLIT_LABELS = { anchor: "sken", seed: "syntetická", heldout: "testovacia" };

function splitLabel(split) {
  return SPLIT_LABELS[split] ?? split;
}

// Diacritics- and case-insensitive text matching for the filters.
function folded(text) {
  return String(text ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

function matches(query, ...values) {
  const wanted = folded(query).trim();
  return !wanted || values.some((value) => folded(value).includes(wanted));
}

// --- Slovak wording of the engine's English messages (messages-sk.json) ---

const catalogue = { data: null, loading: null };

function loadMessages() {
  catalogue.loading ??= fetch("/messages-sk.json")
    .then((response) => response.json())
    .then((data) => {
      data.compiled = data.messages.map(([pattern, text]) => [new RegExp(pattern), text]);
      catalogue.data = data;
    })
    .catch(() => {
      // Without the catalogue the messages stay in English.
    });
  return catalogue.loading;
}

function sk(text) {
  const data = catalogue.data;
  if (!data || !text) return text;
  for (const [pattern, template] of data.compiled) {
    const found = text.match(pattern);
    if (found) {
      return template.replace(/\{(\d+)(?::(\w+))?\}/g, (_, n, kind) =>
        convert(found[Number(n)] ?? "", kind, data),
      );
    }
  }
  return text;
}

function convert(value, kind, data) {
  switch (kind) {
    case "amount":
      return formatAmount(Number(value));
    case "date":
      return formatDate(value);
    case "percent":
      return formatPercent(Number(value));
    case "role":
      return data.roles[value] ?? value;
    case "confidence":
      return data.confidence[value] ?? value;
    case "field":
      return fieldName(value, data);
    case "path":
      return pathName(value);
    case "concepts":
      return value
        .split(", ")
        .map((name) => data.concepts[name] ?? name)
        .join(", ");
    case "function":
      return functionName(value, data);
    case "functions":
      return value
        .split(", ")
        .map((code) => functionName(code, data))
        .join(", ");
    case "document":
      return value === "an earlier invoice" ? "skoršia faktúra" : value;
    case "au":
      return auReason(value, data);
    default:
      return value;
  }
}

function functionName(code, data) {
  const name = data.functions[code];
  return name ? `${code} (${name})` : code;
}

// Where in the invoice a word was found, after the preposition "v".
function pathName(path) {
  let found;
  if ((found = path.match(/^lines\[(\d+)\]\.\w+$/))) return `položke ${Number(found[1]) + 1}`;
  if ((found = path.match(/^free_text\[(\d+)\]$/))) return `poznámke ${Number(found[1]) + 1}`;
  if (path === "supplier.name") return "názve dodávateľa";
  return path;
}

function fieldName(path, data) {
  let found;
  if ((found = path.match(/^lines\[(\d+)\]\.gross$/))) return `suma položky ${Number(found[1]) + 1}`;
  if ((found = path.match(/^lines\[(\d+)\]\.\w+$/))) return `položka ${Number(found[1]) + 1}`;
  return data.fields[path] ?? path;
}

function auReason(reason, data) {
  if (reason === "default") return "predvolená";
  return reason
    .split("; ")
    .map((part) => {
      let found;
      if ((found = part.match(/^concept (.+)$/))) return `pojem ${convert(found[1], "concepts", data)}`;
      if ((found = part.match(/^function (.+)$/))) return `funkcia ${convert(found[1], "functions", data)}`;
      if ((found = part.match(/^term (.+)$/))) return `slovo ${found[1]}`;
      return part;
    })
    .join("; ");
}

function checkName(name) {
  return catalogue.data?.checks[name] ?? name;
}

const FIELD_LABELS = {
  ek: "EK",
  cofog: "Oddiel, trieda",
  zdroj: "Zdroj",
  analytika: "Analytika",
  md: "Účet MD",
  dal: "Účet DAL",
  transfer: "Transfer",
  booking_date: "Dátum zaúčtovania",
  document_number: "Číslo dokladu",
  series: "Rada",
  supplier: "Dodávateľ",
};

const SOURCE_LABELS = {
  supplier_memory: "precedens dodávateľa",
  rule: "pravidlo",
  lexicon: "slovník pojmov",
  similarity: "podobnosť popisu",
  handwritten: "rukou na doklade",
  counter: "počítadlo dokladov",
  invoice: "faktúra",
};

// --- Copying to the clipboard ---

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch {
      copied = false;
    }
    area.remove();
    return copied;
  }
}

// Mixed into components with copy buttons; copiedKey marks the button that just copied.
function copier() {
  return {
    copiedKey: null,
    async copy(text, key) {
      if (await copyText(String(text ?? ""))) {
        this.copiedKey = key;
        setTimeout(() => {
          if (this.copiedKey === key) this.copiedKey = null;
        }, 1500);
      }
    },
  };
}

// --- Invoice picker ---

function invoicePicker() {
  return {
    items: [],
    done: {},
    query: "",
    split: "",
    pasted: "",
    pasteError: null,
    error: null,
    async load() {
      try {
        const [items, feedback] = await Promise.all([
          fetchJSON("/api/invoices"),
          fetchJSON("/api/feedback"),
        ]);
        this.items = items;
        for (const row of feedback) this.done[row.invoice_id] = row;
      } catch (error) {
        this.error = error.message;
      }
    },
    get shown() {
      return this.items.filter(
        (item) =>
          (!this.split || item.split === this.split) &&
          matches(this.query, item.supplier, item.number, item.id),
      );
    },
    status(item) {
      const row = this.done[item.id];
      if (!row) return null;
      return row.action === "accepted" ? "prijatá" : "opravená";
    },
    propose() {
      this.pasteError = null;
      try {
        JSON.parse(this.pasted);
      } catch (error) {
        this.pasteError = `Nie je to platný JSON: ${error.message}`;
        return;
      }
      try {
        sessionStorage.setItem("riso.pasted", this.pasted);
      } catch {
        this.pasteError = "Prehliadač nedovolil faktúru odložiť; skúste iné okno.";
        return;
      }
      location.href = "/proposal.html?pasted=1";
    },
  };
}

// --- Proposal: the two software tabs, alternatives, accept and correct ---

const KEY_PARTS = [
  ["ek", "EK"],
  ["zdroj", "Zdroj"],
  ["oddiel", "Oddiel"],
  ["trieda", "Trieda"],
  ["analytika", "Analytika"],
];
const KEY_PATTERN = /^\d{6} \d[0-9A-Za-z]{1,3} \d{2} \d{3} \d{3}$/;

function keyParts(key) {
  const [ek, zdroj, oddiel, trieda, analytika] = (key ?? "").split(" ");
  return { ek, zdroj, oddiel, trieda, analytika };
}

function lineFromProposal(post, budget) {
  return {
    key: budget.key,
    md: post.md,
    dal: post.dal,
    amount: amountText(budget.amount),
    budgetText: budget.text,
    postingText: post.text,
    transfer: budget.transfer ?? "",
    choice: "",
  };
}

function proposalPage() {
  return {
    ...copier(),
    id: null,
    pasted: false,
    invoice: null,
    proposal: null,
    lines: [],
    proposedLines: [],
    doc: { series: "FD", number: "", booking_date: "" },
    mode: "view", // view | correct | saved
    reference: null,
    note: "",
    saving: false,
    receipt: null,
    saveError: null,
    nextId: null,
    error: null,
    loading: false,
    showEvidence: false,
    KEY_PARTS,
    FIELD_LABELS,
    SOURCE_LABELS,

    async load() {
      await loadMessages();
      const params = new URLSearchParams(location.search);
      this.id = params.get("id");
      this.pasted = params.has("pasted");
      if (!this.id && !this.pasted) {
        this.error = "Najprv vyberte faktúru v zozname.";
        return;
      }
      try {
        if (this.pasted) {
          const text = sessionStorage.getItem("riso.pasted");
          if (!text) throw new Error("Vložená faktúra sa nenašla; vložte ju znova v zozname.");
          this.invoice = JSON.parse(text);
        } else {
          this.invoice = await fetchJSON(`/api/invoices/${encodeURIComponent(this.id)}`);
          this.findNext();
        }
        await this.propose();
        this.loadReference().catch(() => {
          // Names of positions and accounts are a convenience; the codes show without them.
        });
      } catch (error) {
        this.error = error.message;
      }
    },

    async propose() {
      this.loading = true;
      this.error = null;
      try {
        this.proposal = await postJSON("/api/code", { invoice: this.invoice });
        this.reset();
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },

    // Back to the engine's proposal, discarding swaps and corrections.
    reset() {
      const proposal = this.proposal;
      this.proposedLines = proposal.budget.map((budget, i) =>
        lineFromProposal(proposal.posting[i], budget),
      );
      this.lines = this.proposedLines.map((line) => ({ ...line }));
      this.doc = {
        series: proposal.document.series,
        number: proposal.document.number ?? "",
        booking_date: proposal.document.booking_date ?? "",
      };
      this.mode = "view";
      this.note = "";
      this.receipt = null;
      this.saveError = null;
    },

    async findNext() {
      try {
        const items = await fetchJSON("/api/invoices");
        const at = items.findIndex((item) => item.id === this.id);
        this.nextId = at >= 0 && at + 1 < items.length ? items[at + 1].id : null;
      } catch {
        this.nextId = null;
      }
    },

    get gross() {
      return this.proposal?.invoice.gross ?? this.invoice?.totals?.gross ?? null;
    },
    get manual() {
      return this.proposal && this.proposal.budget.length === 0;
    },
    get coding() {
      return {
        document: {
          series: this.doc.series,
          number: this.doc.number || null,
          booking_date: this.doc.booking_date || null,
        },
        posting: this.lines.map((line) => ({
          md: line.md,
          dal: line.dal,
          amount: parseAmount(line.amount),
          text: line.postingText,
          stredisko: null,
          transfer: line.transfer || null,
        })),
        budget: this.lines.map((line) => ({
          key: line.key,
          ...keyParts(line.key),
          amount: parseAmount(line.amount),
          text: line.budgetText,
          stredisko: null,
          transfer: line.transfer || null,
        })),
      };
    },
    get proposedCoding() {
      const { document, posting, budget } = this.proposal;
      return { document, posting, budget };
    },
    get changed() {
      if (!this.proposal || this.manual) return this.lines.length > 0;
      const strip = (coding) =>
        JSON.stringify({
          document: coding.document,
          lines: coding.budget.map((b, i) => [
            b.key,
            coding.posting[i].md,
            coding.posting[i].dal,
            Number(b.amount),
            b.text,
            coding.posting[i].text,
            b.transfer ?? null,
          ]),
        });
      const proposed = this.proposedCoding;
      return (
        strip(this.coding) !==
        strip({
          ...proposed,
          document: {
            series: proposed.document.series,
            number: proposed.document.number ?? null,
            booking_date: proposed.document.booking_date ?? null,
          },
        })
      );
    },
    get total() {
      return this.lines.reduce((sum, line) => sum + (parseAmount(line.amount) ?? 0), 0);
    },
    get confidenceClass() {
      const value = this.proposal?.confidence.overall ?? 0;
      return value >= 0.85 ? "good" : value >= 0.75 ? "fair" : "weak";
    },
    get evidenceByField() {
      const groups = {};
      for (const item of this.proposal?.evidence ?? []) {
        (groups[item.field] ??= []).push(item);
      }
      return Object.entries(groups);
    },
    confidenceRows() {
      const confidence = this.proposal?.confidence ?? {};
      return [
        ["EK", confidence.ek],
        ["Oddiel, trieda", confidence.cofog],
        ["Zdroj", confidence.zdroj],
        ["Analytika", confidence.analytika],
        ["Účet MD", confidence.md],
        ["Účet DAL", confidence.dal],
        ["Dátum zaúčtovania", confidence.booking_date],
        ["Číslo dokladu", confidence.document_number],
      ].filter(([, value]) => value != null);
    },

    // The line as one tab-separated row, in the order of the software's columns.
    postingRow(line) {
      return [line.md, line.dal, amountText(parseAmount(line.amount)), line.postingText].join("\t");
    },
    budgetRow(line) {
      return [line.key, amountText(parseAmount(line.amount)), line.budgetText].join("\t");
    },

    alternativeLabel(alternative) {
      const description = this.positionName(alternative.budget_key);
      return `${alternative.budget_key} · ${description || alternative.budget_text || ""} · MD ${
        alternative.md ?? "—"
      } · ${Math.round(alternative.score * 100)} %`;
    },
    positionName(key) {
      return this.reference?.positions.get(key)?.description ?? "";
    },
    accountName(key) {
      return this.reference?.accounts.get(key)?.description ?? "";
    },

    // Swaps the whole line for an alternative, or back to the proposal ("").
    swap(i) {
      const line = this.lines[i];
      if (line.choice === "") {
        Object.assign(line, this.proposedLines[i], { choice: "" });
        return;
      }
      const alternative = this.proposal.alternatives[Number(line.choice)];
      Object.assign(line, {
        key: alternative.budget_key,
        md: alternative.md ?? line.md,
        dal: alternative.dal ?? line.dal,
        transfer: alternative.transfer ?? "",
        budgetText: alternative.budget_text ?? line.budgetText,
        postingText: alternative.posting_text ?? line.postingText,
      });
    },

    async loadReference() {
      if (this.reference) return;
      const ico = (this.invoice?.customer?.ico ?? "").replace(/\s/g, "");
      const bundle = await fetchJSON(`/api/reference/${encodeURIComponent(ico)}`);
      this.reference = {
        bundle,
        positions: new Map(bundle.budget_positions_expense.map((p) => [p.key, p])),
        accounts: new Map(bundle.accounts.map((a) => [a.key, a])),
        supplierAccounts: bundle.accounts.filter((a) => a.su.startsWith("32")),
        series: bundle.document_series.filter((s) => s.code.startsWith("FD")),
        transfers: bundle.transfers,
      };
    },

    async startCorrecting() {
      try {
        await this.loadReference();
      } catch (error) {
        this.saveError = error.message;
        return;
      }
      if (this.lines.length === 0) this.addLine();
      this.mode = "correct";
    },
    cancelCorrecting() {
      this.reset();
    },
    addLine() {
      const remaining = (this.gross ?? 0) - this.total;
      this.lines.push({
        key: "",
        md: "",
        dal: this.proposal?.document.series === "FDŠJ" ? "321 080" : "321 000",
        amount: amountText(Math.round(remaining * 100) / 100),
        budgetText: "",
        postingText: "",
        transfer: "",
        choice: "",
      });
    },
    removeLine(i) {
      this.lines.splice(i, 1);
    },
    transfersFor(line) {
      const zdroj = keyParts(line.key).zdroj;
      const all = this.reference?.transfers ?? [];
      const own = all.filter((t) => t.zdroj === zdroj);
      return own.length ? own : all;
    },

    // A position picked from the budget brings MD, DAL, transfer and texts by the rules.
    async picked(i) {
      const line = this.lines[i];
      if (!this.reference?.positions.has(line.key)) return;
      try {
        const derived = await postJSON("/api/line", {
          invoice: this.invoice,
          budget_key: line.key,
        });
        Object.assign(line, {
          md: derived.md ?? line.md,
          dal: derived.dal ?? line.dal,
          transfer: derived.transfer ?? "",
          budgetText: derived.budget_text ?? line.budgetText,
          postingText: derived.posting_text ?? line.postingText,
        });
      } catch (error) {
        this.saveError = error.message;
      }
    },

    // What keeps the correction from being saved (errors) or deserves a look (warnings).
    get problems() {
      const errors = [];
      const warnings = [];
      if (this.mode !== "correct" || !this.reference) return { errors, warnings };
      this.lines.forEach((line, i) => {
        const n = i + 1;
        if (!KEY_PATTERN.test(line.key) || !this.reference.positions.has(line.key)) {
          errors.push(`Riadok ${n}: položka „${line.key || "—"}“ nie je v rozpočte.`);
        }
        if (!this.reference.accounts.has(line.md)) {
          errors.push(`Riadok ${n}: účet MD „${line.md || "—"}“ nie je v účtovom rozvrhu.`);
        }
        if (!this.reference.accounts.has(line.dal)) {
          errors.push(`Riadok ${n}: účet DAL „${line.dal || "—"}“ nie je v účtovom rozvrhu.`);
        }
        if (parseAmount(line.amount) == null) errors.push(`Riadok ${n}: suma nie je číslo.`);
        if (!line.budgetText.trim() || !line.postingText.trim()) {
          warnings.push(`Riadok ${n}: chýba popis.`);
        }
      });
      if (this.lines.length === 0) errors.push("Doklad nemá žiadny riadok.");
      const gross = this.gross;
      if (gross != null && Math.abs(this.total - gross) > 0.004) {
        warnings.push(
          `Riadky dávajú spolu ${formatAmount(this.total)}, faktúra ${formatAmount(gross)}.`,
        );
      }
      if (!/^[^/]+\/\d{3}\/\d{2}$/.test(this.doc.number)) {
        warnings.push("Číslo dokladu nemá tvar FD/NNN/RR.");
      }
      if (!this.doc.booking_date) warnings.push("Chýba dátum zaúčtovania.");
      return { errors, warnings };
    },

    async save() {
      this.saving = true;
      this.saveError = null;
      // An unchanged proposal is accepted as it is; anything else is the accountant's correction.
      const accepted = !this.changed;
      const feedback = {
        invoice_id: this.proposal.invoice_id,
        bundle_id: this.proposal.bundle_id,
        action: accepted ? "accepted" : "corrected",
        proposal: this.proposal,
        final: accepted ? this.proposedCoding : this.coding,
        supplier_ico: this.proposal.supplier.ico ?? null,
        note: this.note.trim() || null,
      };
      try {
        this.receipt = await postJSON("/api/feedback", feedback);
        this.mode = "saved";
      } catch (error) {
        this.saveError = error.message;
      } finally {
        this.saving = false;
      }
    },
  };
}

// --- Reference browser ---

const ACCOUNT_TYPES = { active: "aktívny", passive: "pasívny", cost: "nákladový", revenue: "výnosový" };

const REFERENCE_TABS = [
  ["expense", "Rozpočet – výdavky"],
  ["accounts", "Účtový rozvrh"],
  ["income", "Rozpočet – príjmy"],
  ["series", "Číselné rady"],
  ["transfers", "Transfery"],
  ["centres", "Strediská"],
  ["warnings", "Upozornenia"],
];

function referencePage() {
  return {
    entity: null,
    bundle: null,
    tab: "expense",
    query: "",
    error: null,
    REFERENCE_TABS,
    ACCOUNT_TYPES,
    async load() {
      await loadMessages();
      try {
        const entities = await fetchJSON("/api/entities");
        if (entities.length === 0) {
          this.error = "Žiadne číselníky. Spustite riso ingest.";
          return;
        }
        this.entity = entities[0];
        this.bundle = await fetchJSON(`/api/reference/${this.entity.ico}`);
        const tab = new URLSearchParams(location.search).get("tab");
        if (REFERENCE_TABS.some(([key]) => key === tab)) this.tab = tab;
      } catch (error) {
        this.error = error.message;
      }
    },
    count(tab) {
      if (!this.bundle) return 0;
      return this.rows(tab, "").length;
    },
    rows(tab, query = this.query) {
      const bundle = this.bundle;
      if (!bundle) return [];
      const positions = (list) =>
        list.filter((p) => matches(query, p.key, p.description, ...(p.aliases ?? [])));
      switch (tab) {
        case "expense":
          return positions(bundle.budget_positions_expense);
        case "income":
          return positions(bundle.budget_positions_income);
        case "accounts":
          return bundle.accounts.filter((a) => matches(query, a.key, a.description));
        case "series":
          return bundle.document_series.filter((s) =>
            matches(query, s.code, s.pattern, s.description, s.bank_account),
          );
        case "transfers":
          return bundle.transfers.filter((t) => matches(query, t.id, t.name, t.zdroj));
        case "centres":
          return bundle.cost_centres.filter((c) => matches(query, ...Object.values(c)));
        case "warnings":
          return bundle.warnings.filter((w) => matches(query, w.source, w.message, sk(w.message)));
        default:
          return [];
      }
    },
  };
}

// --- Evaluation ---

const METRIC_LABELS = {
  correct: "Celý výsledok správne",
  full_key: "Celá rozpočtová položka",
  full_line: "Položka, MD aj DAL",
  ek: "Ekonomická klasifikácia (EK)",
  zdroj: "Zdroj",
  cofog: "Oddiel a trieda",
  analytika: "Analytika",
  md: "Účet MD",
  dal: "Účet DAL",
  top3: "Správna položka medzi prvými tromi",
  split: "Počet riadkov",
  manual_entry: "Dobropisy na ručné zaúčtovanie",
  validation: "Platné kódy",
  document_number: "Číslo dokladu",
  booking_date: "Dátum zaúčtovania",
  review_rate: "Podiel na kontrolu",
  review_precision: "Označené na kontrolu a naozaj chybné",
  review_recall: "Chybné a označené na kontrolu",
  silent_errors: "Tiché chyby (chybné bez kontroly)",
  expected_review: "Očakávané označenie na kontrolu",
};

const TAG_LABELS = {
  energy: "energie",
  water: "voda",
  telecom: "telekomunikácie",
  post: "pošta",
  waste: "odpad",
  fuel: "palivo",
  materials: "materiál",
  it: "IT",
  insurance: "poistenie",
  membership: "členské",
  training: "školenia",
  repairs: "opravy",
  services: "služby",
  rent: "nájom",
  events: "podujatia",
  kindergarten: "materská škola",
  canteen: "školská jedáleň",
  capital: "kapitálové",
  split: "rozdelenie",
  "credit-note": "dobropis",
  grant: "dotácia",
  "ocr-noise": "chyba OCR",
  ambiguous: "nejasný text",
  "precedent-trap": "iný nákup známeho dodávateľa",
};

const GROUP_COLUMNS = [
  ["correct", "Správne"],
  ["full_key", "Položka"],
  ["ek", "EK"],
  ["md", "MD"],
  ["review_rate", "Na kontrolu"],
  ["silent_errors", "Tiché chyby"],
];

const CASE_FILTERS = [
  ["wrong", "Chybné"],
  ["silent", "Tiché chyby"],
  ["review", "Na kontrolu"],
  ["all", "Všetky"],
];

function evalPage() {
  return {
    split: "heldout",
    report: null,
    loading: false,
    error: null,
    filter: "wrong",
    METRIC_LABELS,
    TAG_LABELS,
    GROUP_COLUMNS,
    CASE_FILTERS,
    async load(refresh = false) {
      this.loading = true;
      this.error = null;
      try {
        const params = new URLSearchParams({ split: this.split, refresh: String(refresh) });
        this.report = await fetchJSON(`/api/eval?${params}`);
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },
    get metrics() {
      return Object.entries(this.report?.metrics ?? {});
    },
    target(name) {
      return this.report?.targets.find((t) => t.metric === name) ?? null;
    },
    get groups() {
      if (!this.report) return [];
      const suppliers = Object.entries(this.report.by_supplier).map(([name, group]) => [
        name === "known" ? "Známy dodávateľ" : "Nový dodávateľ",
        group,
      ]);
      const tags = Object.entries(this.report.by_tag).map(([tag, group]) => [
        TAG_LABELS[tag] ?? tag,
        group,
      ]);
      return [...suppliers, ...tags];
    },
    get cases() {
      const cases = this.report?.cases ?? [];
      switch (this.filter) {
        case "wrong":
          return cases.filter((c) => !c.correct);
        case "silent":
          return cases.filter((c) => !c.correct && !c.needs_review);
        case "review":
          return cases.filter((c) => c.needs_review);
        default:
          return cases;
      }
    },
    codes(lines, outcome) {
      if (outcome === "manual_entry" && lines.length === 0) return "ručné zaúčtovanie";
      if (lines.length === 0) return "bez návrhu";
      return lines.map((l) => `${l.key} · ${l.md}/${l.dal}`).join(" + ");
    },
  };
}
