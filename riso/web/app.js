// Shared helpers and the Alpine components of the pages. Every page talks to the JSON API only.

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      // Not JSON; keep the status text.
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

const amountFormat = new Intl.NumberFormat("sk-SK", { style: "currency", currency: "EUR" });

function formatAmount(value) {
  return value == null ? "—" : amountFormat.format(value);
}

function formatDate(value) {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return `${Number(day)}.${Number(month)}.${year}`;
}

const SPLIT_LABELS = { anchor: "sken", seed: "syntetická", heldout: "testovacia" };

function splitLabel(split) {
  return SPLIT_LABELS[split] ?? split;
}

function invoicePicker() {
  return {
    items: [],
    error: null,
    async load() {
      try {
        this.items = await fetchJSON("/api/invoices");
      } catch (error) {
        this.error = error.message;
      }
    },
  };
}

function proposalPage() {
  return {
    invoice: null,
    error: null,
    async load() {
      const id = new URLSearchParams(location.search).get("id");
      if (!id) {
        this.error = "Najprv vyberte faktúru v zozname.";
        return;
      }
      try {
        this.invoice = await fetchJSON(`/api/invoices/${encodeURIComponent(id)}`);
      } catch (error) {
        this.error = error.message;
      }
    },
  };
}

function referencePage() {
  return {
    entity: null,
    bundle: null,
    error: null,
    async load() {
      try {
        const entities = await fetchJSON("/api/entities");
        if (entities.length === 0) {
          this.error = "Žiadne číselníky. Spustite riso ingest.";
          return;
        }
        this.entity = entities[0];
        this.bundle = await fetchJSON(`/api/reference/${this.entity.ico}`);
      } catch (error) {
        this.error = error.message;
      }
    },
    get counts() {
      if (!this.bundle) return [];
      return [
        ["Účtový rozvrh", this.bundle.accounts.length],
        ["Rozpočet, výdavky", this.bundle.budget_positions_expense.length],
        ["Rozpočet, príjmy", this.bundle.budget_positions_income.length],
        ["Číselné rady dokladov", this.bundle.document_series.length],
        ["Transfery (simulované)", this.bundle.transfers.length],
        ["Strediská", this.bundle.cost_centres.length],
      ];
    },
  };
}
