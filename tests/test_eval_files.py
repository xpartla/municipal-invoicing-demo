"""The evaluation's files (P2-M4-T10): the initial memory and counters it starts from, and the
reports `riso eval` keeps for `GET /api/eval`."""

from riso import paths
from riso.contracts import EvalReport
from riso.eval import evaluate
from riso.eval.files import initial_counters, initial_memory, load_report, save_report

BOLDOG = "00305863"


def test_the_initial_state_is_read_from_its_files():
    memory, counters = initial_memory(BOLDOG), initial_counters(BOLDOG)
    assert memory.entity_ico == counters.entity_ico == BOLDOG
    assert memory.suppliers and counters.last_used["FD/2026"] == 222
    assert initial_memory(BOLDOG, paths.INITIAL_STATE_DIR) == memory


def test_a_report_is_saved_and_read_back(tmp_path):
    assert load_report(BOLDOG, "anchor", tmp_path) is None
    report = evaluate("anchor", entity=BOLDOG)
    path = save_report(report, tmp_path)
    assert path == tmp_path / BOLDOG / "eval-anchor.json"
    assert load_report(BOLDOG, "anchor", tmp_path) == EvalReport.model_validate_json(
        path.read_bytes()
    )
