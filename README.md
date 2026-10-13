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

M2 is done: a mock dataset of 70 synthetic invoices (30 seed, 40 held-out) whose expected
codings were written without access to the engine, and an evaluation harness. On the held-out
set the engine keeps every code valid (100%), but finds the full budget key for 61.5% of the
invoices and the economic code for 76.9%, short of the demo targets of 85% and 90%; 11 of 40
are wrong without being flagged for review. The four real precedents are still reproduced
exactly. The pages and the feedback store come with M3. The plan lives outside this
repository.

```sh
uv run riso code data/invoices/anchor/*.json
uv run riso eval
```

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
| `riso check` | Checks the committed data against the dictionaries: entity settings, supplier memory, counters, the knowledge base, every dataset case, schema drift |
| `riso export-schemas` | Writes the contracts as JSON Schema to `schemas/`; `--check` only reports stale files |
| `riso reset` | Restores the runtime state in `var/` from `data/initial_state/` |
| `riso serve` | Runs the API and the pages |
| `riso code <file>…` | Codes InvoiceDocuments or dataset cases and prints them as the accountant would type them in; for a dataset case it says whether the codes match the expected ones. `--json` prints the full CodingProposal |
| `riso eval` | Codes the held-out set against the memory of the anchor and seed cases, prints the metrics of plan section 9 and the misses, and stores the report in `var/<IČO>/eval-heldout.json`. `--split seed` or `anchor` codes those cases online, in booking-date order; `--all` lists every case, `--json` prints the EvalReport, `--strict` exits with 1 when a target is missed |

Run them with `uv run riso …`. `uv run ruff check .` and `uv run ruff format .` keep the code
tidy.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/entities` | Entities with reference data |
| `GET /api/reference/{ičo}` | The ReferenceBundle |
| `GET /api/invoices`, `GET /api/invoices/{id}` | The mock invoices, for the picker |
| `POST /api/code` | A CodingProposal for `{invoice, entity}` |
| `POST /api/feedback` | Records an accepted or corrected proposal (501 until M3) |
| `GET /api/eval` | The latest EvalReport of `riso eval` (`?split=`, default `heldout`); runs it when there is none, or with `?refresh=true` |

The interactive documentation is at `/docs` while the server runs.

## Layout

```
riso/
  contracts/      Pydantic models of the JSON contracts; schemas/ is generated from them
  ingest/         S0: Excel exports to ReferenceBundle
  reference/      reading bundles and entity settings, lookups, document numbering
  engine/         S1 to S8, one module per stage, and the pipeline
  knowledge/      the authored knowledge base: models, loader, term matching
  store/          runtime state: supplier memory, counters, feedback log, evaluation reports
  api/            FastAPI app
  web/            static pages (Slovak) and vendored Alpine.js
  eval/           scoring proposals against expected outcomes, the metrics, the text report
  checks.py       what `riso check` runs
  dataset.py      loading the mock dataset
  text.py         diacritics folding and word matching
data/
  bundles/        reference bundles built by `riso ingest`
  entities/       per-entity settings: VAT payer, default series and accounts
  invoices/       dataset cases: anchor/ (the four scans), seed/ (feeds supplier memory),
                  heldout/ (never does)
  initial_state/  supplier memory and counters at the start of a demo
knowledge/2026/   EK to SU bridge, AU rules, function map, lexicon, transfer, canteen and style rules
schemas/          JSON Schemas of the contracts
tests/
```

## Data handling

The raw exports and the scanned invoices stay outside this repository, in `../data` next to
the checkout, because they contain personal data. Tests that read them are skipped when they
are absent. What is committed has no personal data: the one natural person among the anchor
suppliers has a made-up name, IČO and address. The four anchor invoices were addressed to
another municipality and are re-addressed to Obec Boldog, whose dictionaries the demo has.
