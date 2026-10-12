from riso.store import FEEDBACK_FILE, StateStore


def test_reset_restores_the_initial_state(tmp_path):
    store = StateStore(var_dir=tmp_path)
    (tmp_path / "00305863").mkdir()
    (tmp_path / "00305863" / FEEDBACK_FILE).write_text("{}\n", encoding="utf-8")
    (tmp_path / "unrelated.txt").write_text("kept", encoding="utf-8")

    assert store.reset() == ["00305863"]

    assert not (tmp_path / "00305863" / FEEDBACK_FILE).exists()
    assert (tmp_path / "unrelated.txt").read_text(encoding="utf-8") == "kept"
    assert [s.ico for s in store.supplier_memory("00305863").suppliers] == [
        "12345679",
        "35763469",
        "50528041",
        "52823831",
    ]


def test_state_falls_back_to_the_initial_files_and_saves_into_var(tmp_path):
    store = StateStore(var_dir=tmp_path)

    counters = store.counters("00305863")
    assert counters.last_used == {"FD/2026": 222, "FDŠJ/2026": 0}

    store.save_counters(counters.model_copy(update={"last_used": {"FD/2026": 223}}))
    assert store.counters("00305863").last_used == {"FD/2026": 223}
    assert StateStore(var_dir=tmp_path / "fresh").counters("00305863").last_used["FD/2026"] == 222
