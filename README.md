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

M3 is done: the web app and the feedback loop. The proposal page lays the coding out like the
accounting software's two tabs, with a copy button on every value and line, the evidence
behind each field, and alternatives that swap a whole line. The accountant accepts the
proposal, or corrects it with codes picked from the municipality's dictionaries; either way
the coding becomes the supplier's newest precedent and its number is used up, so the next
invoice from that supplier follows it. The pages are in Slovak, including the engine's
review reasons and evidence, which a message catalogue translates.

M2 measured the engine on 40 held-out synthetic invoices: every code valid, the full budget
key right for 61.5% and the economic code for 76.9%, short of the demo targets of 85% and 90%.
The plan lives outside this repository.

```sh
uv run riso serve --port 8001       # then open http://127.0.0.1:8001
uv run riso eval
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or later.

```sh
uv sync                    # the project and its dev tools (mypy, import-linter, ...)
scripts/check.sh fast
uv run riso migrate        # create or upgrade var/riso.db
uv run riso serve          # http://127.0.0.1:8000
```

`riso serve` refuses to start on a database that is not migrated. It runs the jobs worker in a
thread. When the SPA has been built into `riso/web/dist/`, it serves the SPA at `/` and at
every client route; the demo pages keep their paths, with the invoice picker at `/index.html`.
Without a built SPA it serves the demo pages at `/` as before.

The end-to-end click-through drives the four pages in a headless browser; it starts its own
server with empty state. Playwright is not a project dependency:

```sh
uv run --with playwright playwright install chromium     # once
uv run --with playwright python tests/e2e/clickthrough.py [screenshot dir]
```

`riso reset` clears what the pages recorded (supplier memory, counters, the feedback log), so
every demo starts from the same state.

## Checks

`scripts/check.sh` runs the gates. Run `fast` before and after every change, and `full` at
checkpoints that touch UI flows, the API contract, migrations or OCR:

```sh
scripts/check.sh fast    # ruff check and format, mypy, lint-imports, pytest without the ocr
                         # and e2e markers, riso check, schema drift, migrations, and the
                         # frontend's lint, typecheck and unit tests when frontend/ changed
scripts/check.sh full    # fast with a coverage report, plus pytest -m ocr, the frontend
                         # build, the API client drift check and the Playwright E2E specs
```

Every step runs and the summary names the ones that failed; the exit code is non-zero if any
did. A step whose tool is not set up yet is skipped with a message. The pytest markers are
`ocr`, `e2e` and `slow`. mypy is strict for the phase 2 packages (`riso.shared`,
`riso.platform` and the bounded contexts) and at its default level for the demo packages.

## Commands

| Command | Does |
|---|---|
| `riso ingest` | Builds `data/bundles/<IČO>/<period>.json` from the Excel exports in `../data` (or `--raw`, or `RISO_RAW_DIR`) |
| `riso check` | Checks the committed data against the dictionaries: entity settings, supplier memory, counters, the knowledge base, every dataset case, schema drift |
| `riso export-openapi` | Writes the API's OpenAPI document to `frontend/openapi.json`, which the frontend client is generated from; `--check` only reports a stale file |
| `riso export-schemas` | Writes the contracts as JSON Schema to `schemas/`; `--check` only reports stale files |
| `riso reset` | Restores the runtime state in `var/` from `data/initial_state/` |
| `riso serve` | Runs the API, the pages and the jobs worker; needs `riso migrate` first |
| `riso code <file>…` | Codes InvoiceDocuments or dataset cases and prints them as the accountant would type them in; for a dataset case it says whether the codes match the expected ones. `--json` prints the full CodingProposal |
| `riso migrate` | Upgrades the database (`RISO_DB_URL`, default `var/riso.db`) to the newest schema; `--revision` picks another |
| `riso worker` | Runs the background jobs (imports, OCR, exports, …) of the database in the foreground until Ctrl-C; `--once` runs the due jobs and exits. The app runs the same worker in a thread |
| `riso eval` | Codes the held-out set against the memory of the anchor and seed cases, prints the metrics of plan section 9 and the misses, and stores the report in `var/<IČO>/eval-heldout.json`. `--split seed` or `anchor` codes those cases online, in booking-date order; `--all` lists every case, `--json` prints the EvalReport, `--strict` exits with 1 when a target is missed |

Run them with `uv run riso …`. `uv run ruff check .` and `uv run ruff format .` keep the code
tidy.

## Configuration

Environment variables, all optional:

| Variable | Default | Meaning |
|---|---|---|
| `RISO_ENV` | unset | `dev`, `test` or `prod`; the seed command refuses unless `dev` or `test` |
| `RISO_VAR_DIR` | `var/` | runtime state: the database, uploaded files, OCR models, reports |
| `RISO_DB_URL` | `sqlite:///<var>/riso.db` | the SQLAlchemy database URL |
| `RISO_TESSDATA` | `<var>/tessdata` | the Tesseract models |
| `RISO_SMTP_HOST`, `RISO_SMTP_PORT`, `RISO_SMTP_USER`, `RISO_SMTP_PASSWORD`, `RISO_SMTP_FROM` | unset | optional mail sending; without them mail stays in the outbox |
| `RISO_RAW_DIR` | `../data` | the raw exports from the accounting software, for `riso ingest` and the tests that need them |

The schema lives in Alembic migrations (`migrations/`). After changing the ORM models, generate
a migration and read it before committing:

```sh
uv run alembic revision --autogenerate -m "<context>: <what>"
uv run alembic upgrade head
```

## API

| Endpoint | Returns |
|---|---|
| `GET /api/entities` | Entities with reference data |
| `GET /api/reference/{ičo}` | The ReferenceBundle |
| `GET /api/invoices`, `GET /api/invoices/{id}` | The mock invoices, for the picker |
| `POST /api/code` | A CodingProposal for `{invoice, entity}` |
| `POST /api/line` | The whole line (MD, DAL, transfer, texts) a budget position brings for `{invoice, budget_key}`, for the correction pickers |
| `POST /api/feedback` | Records an accepted or corrected proposal: checks the codes against the dictionaries, makes the coding the supplier's newest precedent, uses up its number, appends to the feedback log |
| `GET /api/feedback` | The feedback recorded since the last `riso reset` |
| `GET /api/eval` | The latest EvalReport of `riso eval` (`?split=`, default `heldout`); runs it when there is none, or with `?refresh=true` |

The interactive documentation is at `/docs` while the server runs.

Every response carries an `X-Request-ID` (the client's, when it sends a well-formed one) and
the security headers: a Content-Security-Policy without inline or evaluated scripts (the demo
pages, which use Alpine.js, get `'unsafe-eval'` until they are replaced), `nosniff`, frame
denial and `Referrer-Policy: same-origin`. API responses are `Cache-Control: no-store`. Errors
are JSON: 404, 403, 409 with `{detail, code}`, 422 with a list of `{loc, msg, type}` like
FastAPI's own validation errors, and an unknown `/api` path is a JSON 404. Every API route is
named and listed in `riso/api/permissions_matrix.py`; a test fails for a route without an entry.

## Layout

```
riso/
  shared/         the kernel: IDs (UUIDv7), clock, errors, events, request context, unit of
                  work protocol, IČO, IBAN and money
  platform/       settings, the database (SQLite in WAL mode), migrations, the unit of work,
                  content-addressed file storage (var/files/<owner>/<yyyy>/<mm>/<sha256>.<ext>)
                  and the mail outbox
  identity/ tenancy/ codelists/ intake/ invoicing/ exchange/ reporting/ audit/ jobs/
                  the bounded contexts of phase 2, each in layers: domain/, application/,
                  infrastructure/, api/; other code imports only a context's __init__
                  (.importlinter has the rules, `lint-imports` checks them)
  contracts/      Pydantic models of the JSON contracts; schemas/ is generated from them
  ingest/         S0: Excel exports to ReferenceBundle
  reference/      reading bundles and entity settings, lookups, document numbering
  engine/         S1 to S8, one module per stage, and the pipeline
  knowledge/      the authored knowledge base: models, loader, term matching
  store/          runtime state: supplier memory, counters, feedback log, evaluation reports
  api/            FastAPI app
  web/            static pages (Slovak), app.js, messages-sk.json (Slovak wording of the
                  engine's messages), vendored Alpine.js
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
migrations/       Alembic migrations of the database
scripts/check.sh  the gates
tests/            pytest; e2e/clickthrough.py is the browser click-through
```

## Data handling

The raw exports and the scanned invoices stay outside this repository, in `../data` next to
the checkout, because they contain personal data. Tests that read them are skipped when they
are absent. What is committed has no personal data: the one natural person among the anchor
suppliers has a made-up name, IČO and address. The four anchor invoices were addressed to
another municipality and are re-addressed to Obec Boldog, whose dictionaries the demo has.
