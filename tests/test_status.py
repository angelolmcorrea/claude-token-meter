from claude_token_meter import status as st


def test_write_then_read_roundtrip(tmp_path):
    path = tmp_path / "status.json"
    st.write_status("working", path)
    assert st.read_status(path) == "working"


def test_read_missing_file_returns_none(tmp_path):
    path = tmp_path / "status.json"
    assert st.read_status(path) is None


def test_read_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("{ not json", encoding="utf-8")
    assert st.read_status(path) is None


def test_read_unknown_state_returns_none(tmp_path):
    path = tmp_path / "status.json"
    st.write_status("working", path)
    path.write_text('{"state": "banana"}', encoding="utf-8")
    assert st.read_status(path) is None


def test_write_rejects_invalid_state(tmp_path):
    path = tmp_path / "status.json"
    try:
        st.write_status("banana", path)
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid state")
