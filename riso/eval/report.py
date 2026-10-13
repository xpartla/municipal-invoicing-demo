"""The evaluation report as text, for `riso eval`."""

from riso.contracts import CaseResult, EvalReport, LineCodes, Rate

SPLIT_NAMES = {"heldout": "held-out", "seed": "seed", "anchor": "anchor"}
GROUP_COLUMNS = ("correct", "full_key", "ek", "md", "review_rate", "silent_errors")


def render(report: EvalReport, *, all_cases: bool = False) -> str:
    targets = {t.metric: t for t in report.targets}
    memory = (
        f"memory frozen after {report.precedent_cases} anchor and seed cases"
        if report.memory == "frozen"
        else "memory grows online, in booking-date order"
    )
    lines = [
        f"{SPLIT_NAMES[report.split]}: {len(report.cases)} cases of {report.entity_ico}, {memory}",
        f"  bundle {report.bundle_id}, engine {report.engine_version}, "
        f"dataset sha256 {report.dataset_sha256[:16]}",
        "",
        f"{'metric':18} {'value':>7} {'hits/n':>8}  target",
    ]
    for name, rate in report.metrics.items():
        target = targets.get(name)
        verdict = ""
        if target is not None:
            verdict = f"≥ {target.target:.0%}  {'met' if target.met else 'MISSED'}"
        lines.append(f"{name:18} {_percent(rate):>7} {_count(rate):>8}  {verdict}".rstrip())

    lines += ["", f"{'group':18} {'n':>3}" + "".join(f" {c:>13}" for c in GROUP_COLUMNS)]
    groups = [(f"{name} supplier", g) for name, g in report.by_supplier.items()]
    groups += [(f"#{tag}", g) for tag, g in report.by_tag.items()]
    for label, group in groups:
        n = group["correct"].n
        cells = "".join(f" {_percent(group[c]):>13}" for c in GROUP_COLUMNS)
        lines.append(f"{label:18} {n:>3}{cells}")

    shown = [c for c in report.cases if all_cases or not c.correct or c.needs_review]
    if shown:
        lines += ["", "cases" if all_cases else "cases that are wrong or flagged for review"]
        lines += [_case(c) for c in shown]
    return "\n".join(lines)


def _case(result: CaseResult) -> str:
    verdict = "ok   " if result.correct else "WRONG"
    review = "review" if result.needs_review else "      "
    expected = _codes(result.expected) if result.expected_outcome == "coded" else "manual entry"
    proposed = _codes(result.proposed) if result.proposed else "no lines"
    detail = "" if result.correct and expected == proposed else f"\n      proposed {proposed}"
    header = []
    if result.number_ok is False:
        header.append("number")
    if result.date_ok is False:
        header.append("booking date")
    if header:
        detail += f"\n      wrong {' and '.join(header)}"
    if result.needs_review and result.review_reasons:
        detail += f"\n      review: {'; '.join(result.review_reasons)}"
    return f"  {verdict} {review} {result.case_id}\n      expected {expected}{detail}"


def _codes(lines: list[LineCodes]) -> str:
    return " + ".join(f"{line.key}  {line.md}/{line.dal}" for line in lines)


def _percent(rate: Rate) -> str:
    return "—" if rate.value is None else f"{rate.value:.1%}"


def _count(rate: Rate) -> str:
    return f"{rate.hits}/{rate.n}"
