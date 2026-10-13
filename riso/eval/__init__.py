"""Evaluation against the dataset's expected outcomes (plan section 9): `compare` checks one
proposal, `evaluate` runs a whole split and reports the metrics."""

from riso.eval.compare import coded_lines, compare
from riso.eval.run import TARGETS, evaluate

__all__ = ["TARGETS", "coded_lines", "compare", "evaluate"]
