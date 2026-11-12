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

Phase 2 is complete (P2-M8 in review): a light version of the real application, built
milestone by milestone on top of the demo. P2-M0 laid the foundation: the database and migrations, the background jobs
worker, the app's security headers and error mapping, the React SPA shell served by
`riso serve`, the gate script, the E2E harness and CI. P2-M1 adds logins and access: users,
customers and service providers, sessions with CSRF and throttling, invitations and password
resets through a mail outbox, roles and permissions checked on every route, impersonation for
admins, the audit log, and `riso seed`. P2-M2 moves the code lists to the database: each
customer's lists per year in versions (a row edit makes a new one), the 2026 global lists (EK,
COFOG, funding sources, the framework chart) and the validation against them, Boldog's coding
conventions out of the knowledge base, coding from the database (`POST
/api/customers/{id}/code`, `riso eval --source db`), the knowledge health report, and the
Číselníky and Systém screens. P2-M3 adds the import tool: CSV, XLSX and XLS files mapped
column by column (with templates chosen by the headers, built in for TOPSET's exports), a dry
run whose report lists errors per row, and apply as a new version; past bookings as supplier
precedents; and creating a customer as a copy of another (Importy a exporty, Nový klient).
P2-M4 puts the invoices in the database: each with the lifecycle of plan §7.1 (checked, then
needing review or ready, booked, exported, paid, or discarded) and its history; supplier memory
and number series per customer, with booking by the handwritten number or by the date of supply
(plan §2 decision 61); the Faktúry table with filters, bulk actions and exports to CSV and
XLSX; the invoice page with the proposal laid out like the accounting software's two tabs, a
copy button on every value and line, the evidence, alternatives, the correction editor and the
booking; manual entry (Nová faktúra, also from a pasted JSON); and the number series under
Systém. The demo's Alpine pages and their routes are gone; the stateless coding and the
evaluation report remain, for admins (`/api/admin/code`, `/api/admin/eval`, since P2-M7).
P2-M5 adds scans and OCR: Nová faktúra uploads scans, photos and PDFs, several at once
(a file uploaded before is refused with a link to its invoice); a job reads each one
(Tesseract with the Slovak models, or a digital PDF's text layer), extracts the fields with
their confidences and finds the handwritten note; the check step (Kontrola údajov) shows the
document beside the fields, the doubtful ones marked and the note's date and number suggested,
and "Potvrdiť" codes the invoice; Úložisko lists the customer's files; `riso ocr-eval`
measures the reading on a synthetic scan set. P2-M6 adds e-invoices: Nová faktúra also takes
UBL (Peppol BIS Billing 3.0) and ISDOC files and PDFs carrying an ISDOC; they are read from
their XML without OCR (parsed safely, checked against the bundled UBL 2.1 and ISDOC 6.0.2
schemas and our own checks), the check step shows the invoice rendered from its XML, the PDF's
pages and the raw XML, suggests the upload date as the booking date and leaves the number to
the booking, which places the invoice by its date of supply; `riso testdata einvoices` writes
the synthetic e-invoices. P2-M7 adds the dashboards and tools: Domov (a month's tiles linking to
the filtered invoices, bookings per day and over 12 months, by type, supplier and unit, review
rate and time, the budget drawdown, what needs attention, the number series and the onboarding
checklist), Prehľad klientov for staff and Platforma for admins (where they now land), and the
admin's Audit, Úlohy (retry, cancel and the per-customer data export) and Vyhodnotenie. P2-M8
adds Pomocník (Slovak help articles and a "?" on every screen), consistent loading and error
states, a request size limit and other fixes from a security review, the invoice table measured
on 10,000 invoices (`riso seed --bulk`), starting a year from the previous one, and the phase 2
acceptance journey.

M2 measured the engine on 40 held-out synthetic invoices: every code valid, the full budget
key right for 61.5% and the economic code for 76.9%, short of the demo targets of 85% and 90%.
The plan lives outside this repository.

```sh
RISO_ENV=dev RISO_SEED_PASSWORD='Ukážkové-heslo-2026' uv run riso seed --reset
(cd frontend && pnpm install && pnpm build)
uv run riso ocr setup               # the OCR models (27 MB) for reading uploads
uv run riso serve --port 8001       # then open http://127.0.0.1:8001 and log in
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

Reading uploaded scans needs Tesseract's models (`slk` and `eng` from `tessdata_best` 4.1.0,
27 MB, checked by SHA-256; the `tesserocr` wheel brings Tesseract itself, no system package):

```sh
uv run riso ocr setup      # into var/tessdata (RISO_TESSDATA)
```

For a database to log in to, seed it (development only):

```sh
RISO_ENV=dev RISO_SEED_PASSWORD='Ukážkové-heslo-2026' uv run riso seed --reset
```

`riso seed` migrates, then creates Obec Boldog with its 2026 parameters and its 2026 code lists
(version 1 of each, from the committed bundle `data/bundles/00305863/2026-08.json`), its supplier
memory and number series (from `data/initial_state/00305863/`), the dataset's 74 invoices as
its own (channel `dataset`, checked and coded, without their expected codings), the global
lists of each year in `data/global/` (EK, COFOG, funding sources, the framework chart; sources in
`data/global/2026/README.md`; each goes through the import tool with its built-in template, so
its file lands in `var/files/global/`), the made-up provider
"Účtovníctvo Vzor, s.r.o.", two more made-up municipalities (one assigned to the provider, one
not), and one login per role, all under the reserved `.test` domain:

| Role | Login |
|---|---|
| Administrátor | `admin@riso.test` |
| Servisný účet (staff of the provider) | `peter.uctovnik@vzor.test` |
| Používateľ of Obec Boldog | `jana.vzorova@boldog.test` |
| Iba na čítanie in Obec Boldog | `ivan.citatel@boldog.test` |

Without `RISO_SEED_PASSWORD` the passwords are generated and printed once. The command refuses
unless `RISO_ENV` is `dev` or `test`, and refuses a database that has users unless `--reset`
drops it (and `var/files`) first. IDs come from a fixed seed, so customer URLs survive a reset.
Mail (invitations, reset links) is not sent: it waits in the outbox, which the admin reads at
`GET /api/admin/outbox`.

`riso serve` refuses to start on a database that is not migrated. It runs the jobs worker in a
thread. It serves the SPA built into `riso/web/dist/` at `/` and at every client route; without
a build, those paths answer 503 with a line saying how to build it. `riso seed --reset` brings
the demo back to its starting state.

## Frontend

The new UI is a React single-page app in `frontend/` (Vite, TypeScript, Mantine, TanStack
Router and Query, i18next). It needs Node 24 (`frontend/.nvmrc`) and pnpm through corepack:

```sh
nvm install 24 && nvm use 24     # or any Node 24
corepack enable pnpm
cd frontend
pnpm install
pnpm dev                          # http://localhost:5173, proxying /api to riso serve --port 8001
pnpm build                        # into ../riso/web/dist, which riso serve then serves at /
```

`pnpm lint`, `pnpm typecheck` and `pnpm test` (Vitest) check it. The E2E specs in
`frontend/e2e/` run Playwright against the real backend: the global setup migrates a
temporary database, starts `riso serve` on a free port serving the built SPA, and tears it
down. Every spec runs at 390, 820 and 1280 px, fails on any console error, and checks
accessibility with axe (WCAG 2.1 AA):

```sh
pnpm exec playwright install chromium   # once
pnpm build && pnpm e2e
```

The specs include the click-through of the demo's invoice pages, ported to the new UI
(`e2e/journeys-m4.spec.ts`), and the scans' journeys from upload to booking
(`e2e/journeys-m5.spec.ts`), and the e-invoices' (`e2e/journeys-m6.spec.ts`, a UBL file and
an ISDOC PDF from `testdata/einvoice/samples`, read from their XML), M7's (`e2e/journeys-m7.spec.ts`:
Domov after a booking, a provider's overview, the admin's audit search), `e2e/routes.spec.ts`,
which opens every route per role through axe and its "?" (P2-M8), `e2e/help.spec.ts` and the
phase 2 acceptance journey (`e2e/acceptance.spec.ts`, desktop width only: a provider copies
Boldog, imports a chart of accounts with a new mapping and saves the template, invites a user
who sets a password from the outbox link; the user uploads three scans and a UBL invoice,
books one outright, corrects one, enters a credit note by hand, exports to CSV and marks them
paid; Domov counts them; the admin finds them in the audit and impersonates the user): the global setup has the server read uploads with
`RISO_OCR_READER=recorded`, replaying the committed samples' layouts, so E2E needs no models. `RISO_E2E_SERVER_LOG=<file>` keeps the server's output, with the
traceback of a 500, in that file. The typed API client is
generated from the backend's OpenAPI document; after changing a route or its models, run
`uv run riso export-openapi` and `pnpm gen:api`, and commit both `frontend/openapi.json` and
`frontend/src/api/schema.d.ts` (`pnpm check:api` fails when either is stale).

## Checks

`scripts/check.sh` runs the gates. Run `fast` before and after every change, and `full` at
checkpoints that touch UI flows, the API contract, migrations or OCR:

```sh
scripts/check.sh fast    # ruff check and format, mypy, lint-imports, pytest without the ocr
                         # and e2e markers, riso check, schema drift, migrations, and the
                         # frontend's lint, typecheck and unit tests when frontend/ changed
scripts/check.sh full    # fast with coverage (at least 85% overall and 90% for the domain
                         # packages), plus pytest -m ocr (needs riso ocr setup and Python
                         # Playwright's Chromium), the frontend build, the API
                         # client drift check and the Playwright E2E specs
```

The `ocr` CI job also downloads the models, renders the synthetic set (cached by the generator's
and the dataset's hashes) and runs `riso ocr-eval --set synthetic --strict`; locally:

```sh
uv run riso ocr setup && uv run riso testdata scans && uv run riso ocr-eval
```

Every step runs and the summary names the ones that failed; the exit code is non-zero if any
did. A step whose tool is not set up yet is skipped with a message. The pytest markers are
`ocr`, `e2e` and `slow`. mypy is strict for the phase 2 packages (`riso.shared`,
`riso.platform` and the bounded contexts) and at its default level for the demo packages.

## Commands

| Command | Does |
|---|---|
| `riso ingest` | Builds `data/bundles/<IČO>/<period>.json` from the Excel exports in `../data` (or `--raw`, or `RISO_RAW_DIR`) |
| `riso check` | Checks the committed data against the dictionaries: entity settings, supplier memory, counters, the knowledge base (with Boldog's conventions), every dataset case, schema drift. `--customer <IČO> [--year YYYY]` prints that customer's knowledge health report from the database instead (missing lists, conventions naming missing accounts, budget EKs without a bridge rule, precedents outside the active lists); exit 1 when it has errors |
| `riso export-openapi` | Writes the API's OpenAPI document to `frontend/openapi.json`, which the frontend client is generated from; `--check` only reports a stale file |
| `riso export-schemas` | Writes the contracts as JSON Schema to `schemas/`; `--check` only reports stale files |
| `riso serve` | Runs the API, the built SPA and the jobs worker; needs `riso migrate` first |
| `riso code <file>…` | Codes InvoiceDocuments or dataset cases with the committed bundle and the supplier memory and counters of `data/initial_state`, and prints them as the accountant would type them in; for a dataset case it says whether the codes match the expected ones. `--json` prints the full CodingProposal |
| `riso migrate` | Upgrades the database (`RISO_DB_URL`, default `var/riso.db`) to the newest schema; `--revision` picks another |
| `riso seed` | Migrates and seeds the demo database (Boldog, a provider, a login per role); `--reset` drops it first. Only with `RISO_ENV=dev` or `test`; passwords from `RISO_SEED_PASSWORD` or generated. `--bulk N` adds N synthetic invoices to Boldog for measuring (variations of the dataset's cases over 2024 to 2026, mostly booked, exported or paid; supplier memory untouched); on an empty database, or with `--reset`, it seeds first. 10,000 take about 30 s |
| `riso worker` | Runs the background jobs (imports, OCR, exports, …) of the database in the foreground until Ctrl-C; `--once` runs the due jobs and exits. The app runs the same worker in a thread |
| `riso ocr setup` | Downloads the pinned Tesseract models (`slk`, `eng` from `tessdata_best` 4.1.0) into `RISO_TESSDATA` and checks their SHA-256; a file already there with the right hash is kept |
| `riso ocr record` | Reads the committed synthetic samples with Tesseract, preparing their pages as the extraction does, and writes their layouts to `testdata/ocr/recorded/` (`--out` elsewhere) for the fast tests and `RISO_OCR_READER=recorded`. Run it after changing the page preparation or the models |
| `riso ocr-eval` | Measures the OCR (plan §8.6): each scan of `--set synthetic` (the generated set, `--scans` elsewhere) or `--set anchor` (the four real scans in `../data/FA.xlsx`, read in place, the report naming fields, never values) goes the extraction's way with the reader of `RISO_OCR_READER`; it prints per field how often it was right and found and the silent wrongs (wrong at confidence 0.6 or more), the time per page, the invoices right after the check step's automatic fields and the note's crop, then plan §8.6's targets; the report is kept in `var/ocr-eval-<set>.json`. `--json` prints it, `--strict` exits with 1 below a target (the `ocr` CI job) |
| `riso testdata scans` | Renders the 70 seed and held-out cases as synthetic invoice scans (plan §8.6): each through its supplier's layout in headless Chromium, with a handwritten note, an approval stamp and seeded photo or scanner damage; per case the scan, a digital PDF and its truth (`ScanTruth`), into `testdata/ocr/generated/` (git-ignored; `--out` elsewhere). `--seed` (default 2026), `--case <id>` (repeatable), `--samples` rewrites the committed samples in `testdata/ocr/samples/`. The same seed gives the same bytes with the same Chromium build. Needs the dev group's Python Playwright and its Chromium (`uv run playwright install chromium` where `~/.cache/ms-playwright` lacks build 1254) |
| `riso testdata einvoices` | Writes the 70 seed and held-out cases as e-invoices (plan §8.4): per case a Peppol BIS Billing 3.0 UBL 2.1 file (`<case>.ubl.xml`, a CreditNote for a credit note), an ISDOC 6.0.2 file (`<case>.isdoc`) and the case's digital PDF with that ISDOC attached (`<case>.isdoc.pdf`), into `testdata/einvoice/generated/` (git-ignored; `--out` elsewhere). `--case <id>` (repeatable), `--samples` rewrites the committed samples in `testdata/einvoice/samples/`, `--blank-pdf` attaches the ISDOC to a blank page instead of rendering the invoice in Chromium. The same input gives the same bytes |
| `riso eval` | Codes the held-out set against the memory of the anchor and seed cases, prints the metrics of plan section 9 and the misses, and stores the report in `var/<IČO>/eval-heldout.json`. `--split seed` or `anchor` codes those cases online, in booking-date order; `--all` lists every case, `--json` prints the EvalReport, `--strict` exits with 1 when a target is missed. `--source db` takes the lists, parameters and conventions from the database of `RISO_DB_URL` (seed it first) instead of the committed files; the memory always comes from `data/initial_state`. `--customer <IČO>` picks the customer |

Run them with `uv run riso …`. `uv run ruff check .` and `uv run ruff format .` keep the code
tidy.

## Configuration

Environment variables, all optional:

| Variable | Default | Meaning |
|---|---|---|
| `RISO_ENV` | unset | `dev`, `test` or `prod`; the seed command refuses unless `dev` or `test` |
| `RISO_SEED_PASSWORD` | unset | the password `riso seed` gives every seeded login; generated when unset |
| `RISO_PUBLIC_URL` | `http://localhost:8001` | the app's address, for the links in mail |
| `RISO_COOKIE_SECURE` | `false` | mark the session and CSRF cookies `Secure` (behind HTTPS, phase 2.5) |
| `RISO_REQUEST_THREADS` | `4` | threads serving the synchronous routes at once; SQLite in one process serves many clients faster with few threads than with many |
| `RISO_VAR_DIR` | `var/` | runtime state: the database, uploaded files, OCR models, reports |
| `RISO_DB_URL` | `sqlite:///<var>/riso.db` | the SQLAlchemy database URL |
| `RISO_TESSDATA` | `<var>/tessdata` | the Tesseract models |
| `RISO_OCR_READER` | `tesseract` | how uploads are read: `tesseract`, or `recorded` to replay the layouts in `RISO_OCR_RECORDINGS` (the E2E journeys) |
| `RISO_OCR_RECORDINGS` | `testdata/ocr/recorded` | the recorded layouts (`riso ocr record`) |
| `RISO_SMTP_HOST`, `RISO_SMTP_PORT`, `RISO_SMTP_USER`, `RISO_SMTP_PASSWORD`, `RISO_SMTP_FROM` | unset | optional mail sending; without them mail stays in the outbox |
| `RISO_RAW_DIR` | `../data` | the raw exports from the accounting software, for `riso ingest` and the tests that need them |

The schema lives in Alembic migrations (`migrations/`). After changing the ORM models, generate
a migration and read it before committing:

```sh
uv run alembic revision --autogenerate -m "<context>: <what>"
uv run alembic upgrade head
```

## API

Two routes remain from the demo, for admins since P2-M7 (`evaluation.read`):

| Endpoint | Returns |
|---|---|
| `POST /api/admin/code` | A CodingProposal for `{invoice, entity}`, coded with the committed bundle and the memory of `data/initial_state`; nothing is stored |
| `GET /api/admin/eval` | The latest EvalReport of `riso eval` (`?split=`, default `heldout`); runs it when there is none, or with `?refresh=true`. Vyhodnotenie shows it |

The phase 2 API (logins, customers, providers, users, the outbox and the audit) is described
at `/docs` while the server runs. In short:

- `POST /api/auth/login` sets two cookies: `riso_session` (HttpOnly) and `riso_csrf`. Every
  unsafe request sends the `riso_csrf` value back in the `X-CSRF-Token` header; before a login
  the cookie holds a random value, set on the first response. Sessions end after 8 hours
  without a request or 7 days after the login. Five failed logins block the account and the
  address for 1, then 2, 4, 8 and at most 15 minutes (429 with `Retry-After`).
- `GET /api/me` returns the caller, its memberships and what it may do: on the platform, in
  each of its providers, and in each customer it can open.
- Customer data lives under `/api/customers/{customer_id}/…`, provider routes under
  `/api/providers/{provider_id}/…`, admin tools under `/api/admin/…`. A customer the caller
  cannot reach answers 404; a missing permission 403; no session 401.
- An import is a run: `POST /api/customers/{id}/imports` (multipart `file`, `import_type`,
  `year`), then `GET …/preview`, `PUT …/mapping`, `POST …/dry-run` and `POST …/apply`
  (`confirm_errors` lets errors against the global lists through). The dry run and the apply
  are jobs of the worker; the run's state and report show their outcome. The global lists'
  imports are the same under `/api/admin/imports`. `POST /api/providers/{id}/customers/copy`
  starts a copy, followed at `GET /api/customers/{id}/jobs/{job_id}`.
- Invoices: `GET /api/customers/{id}/invoices` is the table (filters `q`, `supplier_ico`,
  `state`, `series`, `channel`, `needs_review`, `uploaded_by`, `<issue|due|booking|uploaded|
  exported|paid>_from`/`_to`, `amount_min`/`_max`, `budget`, `md`, `dal`; `sort=-booking_date`;
  `page`, `size` up to 200), `…/invoices/suppliers?q=` suggests suppliers, `GET
  …/invoices/{invoice_id}` and `…/history` read one, and `POST …/invoices/bulk/pay|recode|discard`
  act on several, reporting each. `POST /api/customers/{id}/invoices` enters one from typed
  fields (checked and coded at once); under `…/invoices/{invoice_id}/`, `check`, `recode`, `line` (the whole line
  of a picked budget position), `booking-preview`, `book`, `unbook`, `discard` and `pay`.
  Booking takes the handwritten number, or a place by date of supply, and may move later
  booked invoices up (plan §2 decision 61).
- Exports (plan §7.4): `POST /api/customers/{id}/exports/preview` and `POST …/exports` take
  `{format: csv|xlsx, invoice_ids}` or `{format, filter, sort}` (the table's filters); the
  `export_build` job writes the file (CSV: UTF-8 with BOM, `;`, decimal comma; formulas
  neutralised), keeps it in storage and marks the invoices exported. `GET …/exports`,
  `…/exports/{id}` and `…/exports/{id}/file` read the history and the file.
- `GET /api/customers/{id}/number-series?year=` lists the invoice series with their counters,
  the numbers held and the gaps; `PUT …/number-series/{series}/{year}` edits a counter
  (audited). Supplier memory and number series live in the database.

The interactive documentation is at `/docs` while the server runs.

Every response carries an `X-Request-ID` (the client's, when it sends a well-formed one) and
the security headers: a Content-Security-Policy without inline or evaluated scripts (only
`/docs` and `/redoc` may load Swagger UI and ReDoc from their CDN), `nosniff`, frame
denial and `Referrer-Policy: same-origin`. API responses are `Cache-Control: no-store`. Errors
are JSON: 401, 403, 404, 409 with `{detail, code}`, 422 with a list of `{loc, msg, type}` like
FastAPI's own validation errors, 429 with `retry_after`, and an unknown `/api` path is a JSON
404. Every API route is named and listed in `riso/api/permissions_matrix.py` with the
permission it needs; a generated test calls every route as every role and fails for a route
without an entry or with a dependency that disagrees with it.

Pomocník's articles are Markdown files in `frontend/src/help/sk/`, one per article, rendered
with react-markdown (no raw HTML). `frontend/src/help/topics.ts` lists them with their role
group and maps each route to the article its "?" opens; the unit tests fail when a route has
no article, a file is not listed, or an article links to one that does not exist.

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
  api/            FastAPI app: composition, the frame, the permission matrix, the seed
  web/dist/       where `pnpm build` puts the SPA (git-ignored)
  eval/           scoring proposals against expected outcomes, the metrics, the text report,
                  its files (the initial memory, the reports in var/<IČO>/)
  testdata/       development tooling, never imported by the app: the synthetic scan generator
                  (layouts, handwriting, capture damage, `ScanTruth`) and the e-invoice writer
  checks.py       what `riso check` runs
  dataset.py      loading the mock dataset
  text.py         diacritics folding and word matching
data/
  bundles/        reference bundles built by `riso ingest`
  entities/       per-entity settings: VAT payer, default series and accounts
  invoices/       dataset cases: anchor/ (the four scans), seed/ (feeds supplier memory),
                  heldout/ (never does)
  initial_state/  supplier memory and counters that the seed and the evaluation start from
testdata/
  fonts/          the vendored OFL fonts of the synthetic scans (README.md has their sources)
  ocr/samples/    ten committed synthetic scans with their digital PDFs and truth
  ocr/generated/  the full synthetic set, generated (git-ignored)
  ocr/recorded/   the samples' layouts as Tesseract read them (riso ocr record)
  einvoice/samples/   ten committed synthetic e-invoices (UBL, ISDOC, ISDOC in a PDF)
  einvoice/generated/ the full set, generated (git-ignored)
knowledge/2026/   EK to SU bridge, AU rules, function map, lexicon, transfer, canteen and style rules
schemas/          JSON Schemas of the contracts
migrations/       Alembic migrations of the database
scripts/check.sh  the gates
frontend/         the React SPA, its unit tests and the Playwright E2E specs (e2e/)
tests/            pytest
```

## Data handling

The raw exports and the scanned invoices stay outside this repository, in `../data` next to
the checkout, because they contain personal data. Tests that read them are skipped when they
are absent. What is committed has no personal data: the one natural person among the anchor
suppliers has a made-up name, IČO and address. The four anchor invoices were addressed to
another municipality and are re-addressed to Obec Boldog, whose dictionaries the demo has. The
synthetic scans in `testdata/ocr/` and e-invoices in `testdata/einvoice/` show only the seed and held-out cases (real companies with
their registry data, made-up natural persons, made-up tax numbers and accounts).
