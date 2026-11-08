#!/usr/bin/env bash
# The gates (implementation guide §5.1).
#
#   scripts/check.sh fast   before and after every change set
#   scripts/check.sh full   at checkpoints touching UI flows, the API contract, migrations or
#                           OCR, and at every milestone close
#
# Every step runs, even after a failure, and the summary lists what failed. The exit code is
# non-zero when any step failed. A step whose tool does not exist yet is skipped with a
# message, never silently.
set -uo pipefail

mode="${1:-fast}"
case "$mode" in
fast | full) ;;
*)
    echo "usage: scripts/check.sh [fast|full]" >&2
    exit 2
    ;;
esac

cd "$(dirname "$0")/.."
root="$PWD"
failed=()
skipped=()

step() {
    local name="$1"
    shift
    printf '\n==> %s\n' "$name"
    if "$@"; then
        printf '    ok: %s\n' "$name"
    else
        printf '    FAILED: %s\n' "$name"
        failed+=("$name")
    fi
}

skip() {
    printf '\n==> %s\n    skipped: %s\n' "$1" "$2"
    skipped+=("$1")
}

# --- backend ---------------------------------------------------------------------------------

step "ruff check" uv run ruff check .
step "ruff format --check" uv run ruff format --check .
step "mypy" uv run mypy

if [[ -f .importlinter ]]; then
    step "lint-imports" uv run lint-imports
else
    skip "lint-imports" "no .importlinter yet (P2-M0-T03)"
fi

pytest_args=(-m "not ocr and not e2e")
if [[ "$mode" == full ]]; then
    # Reported only during P2-M0; enforced from P2-M1 (plan §13.2).
    pytest_args+=(--cov=riso --cov-report=term:skip-covered)
fi
step "pytest (not ocr, not e2e)" uv run pytest "${pytest_args[@]}"

step "riso check" uv run riso check
step "schema drift" uv run riso export-schemas --check

alembic_check() {
    # Upgrade an empty temporary database to head, then compare the models with it.
    local tmp status
    tmp="$(mktemp -d)"
    RISO_VAR_DIR="$tmp" RISO_DB_URL="sqlite:///$tmp/check.db" uv run alembic upgrade head &&
        RISO_VAR_DIR="$tmp" RISO_DB_URL="sqlite:///$tmp/check.db" uv run alembic check
    status=$?
    rm -rf "$tmp"
    return "$status"
}
if [[ -f alembic.ini ]]; then
    step "alembic upgrade head + check" alembic_check
else
    skip "alembic upgrade head + check" "no alembic.ini yet (P2-M0-T02)"
fi

# --- frontend --------------------------------------------------------------------------------

frontend_changed() {
    # In fast mode the frontend steps run only when frontend/ differs from master or has
    # uncommitted changes. Without git, or without master, they always run.
    git rev-parse --verify --quiet master >/dev/null 2>&1 || return 0
    ! git diff --quiet master...HEAD -- frontend 2>/dev/null && return 0
    [[ -n "$(git status --porcelain -- frontend 2>/dev/null)" ]]
}

pnpm_in_frontend() {
    (cd "$root/frontend" && pnpm "$@")
}

if [[ ! -f frontend/package.json ]]; then
    skip "frontend lint, typecheck, test" "no frontend/ yet (P2-M0-T06)"
elif [[ "$mode" == fast ]] && ! frontend_changed; then
    skip "frontend lint, typecheck, test" "frontend/ unchanged against master"
else
    step "frontend lint" pnpm_in_frontend lint
    step "frontend typecheck" pnpm_in_frontend typecheck
    step "frontend unit tests" pnpm_in_frontend test
fi

# --- full only -------------------------------------------------------------------------------

if [[ "$mode" == full ]]; then
    if [[ -d tests/ocr ]]; then
        step "pytest -m ocr" uv run pytest -m ocr
    else
        skip "pytest -m ocr" "no tests/ocr yet (P2-M5)"
    fi

    if [[ -f frontend/package.json ]]; then
        step "frontend build" pnpm_in_frontend build
        step "API client drift" pnpm_in_frontend check:api
    else
        skip "frontend build" "no frontend/ yet (P2-M0-T06)"
        skip "API client drift" "no frontend/ yet (P2-M0-T06)"
    fi

    if [[ -f frontend/playwright.config.ts ]]; then
        step "Playwright E2E" pnpm_in_frontend e2e
    else
        skip "Playwright E2E" "no Playwright config yet (P2-M0-T07)"
    fi
fi

# --- summary ---------------------------------------------------------------------------------

printf '\n%s gate: ' "$mode"
if ((${#failed[@]})); then
    printf 'FAILED (%s)\n' "$(IFS=,; echo "${failed[*]}")"
    exit 1
fi
if ((${#skipped[@]})); then
    printf 'green, %d step(s) skipped\n' "${#skipped[@]}"
else
    printf 'green\n'
fi
