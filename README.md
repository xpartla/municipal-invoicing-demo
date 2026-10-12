# municipal-invoicing-demo

Demo of an invoice coding engine for Slovak municipalities. Given one supplier invoice, as an
OCR step would deliver it, and the municipality's dictionaries exported from its accounting
software, the engine proposes what the accountant types in by hand today:

- **Zaúčtovanie záväzku**, the posting: debit and credit account (`518 003` / `321 000`).
- **Rozpočet záväzku**, the budget position: `EK zdroj oddiel trieda analytika`
  (`632005 41 01 110 000`).
- The document header: series and number (`FD/144/26`) and the booking date, both taken from
  the note handwritten on the scan.

The engine is deterministic: supplier precedent, authored rules and lexical matching, with no
language model or other AI. Every proposed code must exist in the municipality's dictionaries.

The demo entity is Obec Boldog (IČO 00305863), with reference data for 08/2026.

## Status

M0 is done: the contracts, the Excel ingestion, the four anchor invoices and the checks that
hold them to the dictionaries. The engine stages S1 to S8 are typed stubs, so `POST /api/code`
answers 501 until M1. The plan lives outside this repository.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or later.

```sh
uv sync
uv run pytest
uv run riso serve          # http://127.0.0.1:8000
```

## Commands

| Command | Does |
|---|---|
| `riso ingest` | Builds `data/bundles/<IČO>/<period>.json` from the Excel exports in `../data` (or `--raw`, or `RISO_RAW_DIR`) |
| `riso check` | Checks the committed data against the dictionaries: entity settings, supplier memory, counters, every dataset case, schema drift |
| `riso export-schemas` | Writes the contracts as JSON Schema to `schemas/`; `--check` only reports stale files |
| `riso reset` | Restores the runtime state in `var/` from `data/initial_state/` |
| `riso serve` | Runs the API and the pages |
| `riso code <file>` | Codes one InvoiceDocument or dataset case (from M1) |
| `riso eval` | Evaluates the held-out set (from M2) |

Run them with `uv run riso …`. `uv run ruff check .` and `uv run ruff format .` keep the code
tidy.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/entities` | Entities with reference data |
| `GET /api/reference/{ičo}` | The ReferenceBundle |
| `GET /api/invoices`, `GET /api/invoices/{id}` | The mock invoices, for the picker |
| `POST /api/code` | A CodingProposal for `{invoice, entity}` (501 until M1) |
| `POST /api/feedback` | Records an accepted or corrected proposal (501 until M3) |
| `GET /api/eval` | The latest metrics (501 until M2) |

The interactive documentation is at `/docs` while the server runs.

## Layout

```
riso/
  contracts/      Pydantic models of the JSON contracts; schemas/ is generated from them
  ingest/         S0: Excel exports to ReferenceBundle
  reference/      reading bundles and entity settings, lookups, document numbering
  engine/         S1 to S8 and the pipeline; S6's dictionary checks are built
  knowledge/      loader for the authored knowledge base in knowledge/<year>/
  store/          runtime state: supplier memory, counters, feedback log
  api/            FastAPI app
  web/            static pages (Slovak) and vendored Alpine.js
  eval/           metrics
  checks.py       what `riso check` runs
  dataset.py      loading the mock dataset
data/
  bundles/        reference bundles built by `riso ingest`
  entities/       per-entity settings: VAT payer, default series and accounts
  invoices/       anchor/, seed/ and heldout/ dataset cases
  initial_state/  supplier memory and counters at the start of a demo
knowledge/2026/   authored knowledge base (M1)
schemas/          JSON Schemas of the contracts
tests/
```

## Data handling

The raw exports and the scanned invoices stay outside this repository, in `../data` next to
the checkout, because they contain personal data. Tests that read them are skipped when they
are absent. What is committed has no personal data: the one natural person among the anchor
suppliers has a made-up name, IČO and address. The four anchor invoices were addressed to
another municipality and are re-addressed to Obec Boldog, whose dictionaries the demo has.
