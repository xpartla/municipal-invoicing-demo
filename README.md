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

Phase 2 has started: a light version of the real application, built milestone by milestone on
top of the demo. P2-M0 laid the foundation: the database and migrations, the background jobs
worker, the app's security headers and error mapping, the React SPA shell served by
`riso serve`, the gate script, the E2E harness and CI. P2-M1 adds logins and access: users,
customers and service providers, sessions with CSRF and throttling, invitations and password
resets through a mail outbox, roles and permissions checked on every route, impersonation for
admins, the audit log, and `riso seed`. P2-M2 moves the code lists to the database: each
customer's lists per year in versions (a row edit makes a new one), the 2026 global lists (EK,
COFOG, funding sources, the framework chart) and the validation against them, Boldog's coding
conventions out of the knowledge base, coding from the database (`POST
/api/customers/{id}/code`, `riso eval --source db`), the knowledge health report, and the
Číselníky and Systém screens. The import tool, invoices, OCR and e-invoices follow. The demo
below keeps working until its pages are replaced.

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
uv run riso migrate
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

For a database to log in to, seed it (development only):

```sh
RISO_ENV=dev RISO_SEED_PASSWORD='Ukážkové-heslo-2026' uv run riso seed --reset
```

`riso seed` migrates, then creates Obec Boldog with its 2026 parameters and its 2026 code lists
(version 1 of each, from the committed bundle `data/bundles/00305863/2026-08.json`), the global
lists of each year in `data/global/` (EK, COFOG, funding sources, the framework chart; sources in
`data/global/2026/README.md`), the made-up provider
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
``` The typed API client is
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
                         # packages), plus pytest -m ocr, the frontend build, the API
                         # client drift check and the Playwright E2E specs
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
| `riso reset` | Restores the runtime state in `var/` from `data/initial_state/` |
| `riso serve` | Runs the API, the pages and the jobs worker; needs `riso migrate` first |
| `riso code <file>…` | Codes InvoiceDocuments or dataset cases and prints them as the accountant would type them in; for a dataset case it says whether the codes match the expected ones. `--json` prints the full CodingProposal |
| `riso migrate` | Upgrades the database (`RISO_DB_URL`, default `var/riso.db`) to the newest schema; `--revision` picks another |
| `riso seed` | Migrates and seeds the demo database (Boldog, a provider, a login per role); `--reset` drops it first. Only with `RISO_ENV=dev` or `test`; passwords from `RISO_SEED_PASSWORD` or generated |
| `riso worker` | Runs the background jobs (imports, OCR, exports, …) of the database in the foreground until Ctrl-C; `--once` runs the due jobs and exits. The app runs the same worker in a thread |
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

The interactive documentation is at `/docs` while the server runs.

Every response carries an `X-Request-ID` (the client's, when it sends a well-formed one) and
the security headers: a Content-Security-Policy without inline or evaluated scripts (the demo
pages, which use Alpine.js, get `'unsafe-eval'` until they are replaced), `nosniff`, frame
denial and `Referrer-Policy: same-origin`. API responses are `Cache-Control: no-store`. Errors
are JSON: 401, 403, 404, 409 with `{detail, code}`, 422 with a list of `{loc, msg, type}` like
FastAPI's own validation errors, 429 with `retry_after`, and an unknown `/api` path is a JSON
404. Every API route is named and listed in `riso/api/permissions_matrix.py` with the
permission it needs; a generated test calls every route as every role and fails for a route
without an entry or with a dependency that disagrees with it.

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
