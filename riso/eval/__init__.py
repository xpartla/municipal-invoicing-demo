"""Evaluation on the held-out set (plan section 9): exact key match, per-field accuracy, top-three
hit rate, split correctness, validation pass rate, review rate and precision."""

from riso.contracts import DatasetCase


def evaluate(cases: list[DatasetCase]) -> dict[str, float]:
    raise NotImplementedError("The evaluation is built in M2")
