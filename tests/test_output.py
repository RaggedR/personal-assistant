import json

from pa import output


def test_truncate_collapses_whitespace_and_adds_ellipsis():
    assert output.truncate("a   b\n c", 20) == "a b c"
    got = output.truncate("abcdefghij", 5)
    assert len(got) == 5 and got.endswith("…")
    assert output.truncate(None, 5) == ""


def test_table_includes_header_and_rule():
    lines = output.table([["1", "one"], ["2", "two"]], headers=["N", "NAME"])
    assert lines[0].startswith("N")
    assert set(lines[1].replace(" ", "")) == {"-"}
    assert len(lines) == 4


def test_table_of_no_rows_is_empty():
    assert output.table([]) == []


def test_table_pads_ragged_rows():
    lines = output.table([["a", "b", "c"], ["d"]])
    assert len(lines) == 2


def test_emit_json_mode_writes_parseable_json(capsys):
    output.set_json(True)
    try:
        output.emit({"a": 1}, lambda p: ["should not appear"])
        captured = capsys.readouterr().out
        assert json.loads(captured) == {"a": 1}
        assert "should not appear" not in captured
    finally:
        output.set_json(False)


def test_note_is_suppressed_in_json_mode(capsys):
    output.set_json(True)
    try:
        output.note("chatty commentary")
        assert capsys.readouterr().out == ""
    finally:
        output.set_json(False)


def test_emit_text_mode_uses_renderer(capsys):
    output.set_json(False)
    output.emit({"a": 1}, lambda p: [f"a={p['a']}"])
    assert capsys.readouterr().out.strip() == "a=1"


def test_emit_accepts_a_string_renderer(capsys):
    output.set_json(False)
    output.emit({"a": 1}, lambda p: "one line")
    assert capsys.readouterr().out.strip() == "one line"
