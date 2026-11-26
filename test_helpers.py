"""Pure helper functions ka test — opencode ya telegram ke bina chalta hai.

Run: python tests/test_helpers.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot  # noqa: E402


def test_filter_free_models():
    lines = [
        "opencode/big-pickle",
        "opencode/glm-5.3-flash-free",
        "opencode/claude-sonnet-5-5",
        "anthropic/claude-haiku-5-5",
        "opencode/nemotron-3.5-lightning-free",
        "",
        "# comment",
    ]
    got = bot.filter_free_models(lines)
    assert got == [
        "opencode/big-pickle",
        "opencode/glm-5.3-flash-free",
        "opencode/nemotron-3.5-lightning-free",
    ], got


def test_chunk_text():
    text = "\n".join(f"line {i}" for i in range(3000))
    chunks = bot.chunk_text(text, 1000)
    assert all(len(c) <= 1000 for c in chunks), [len(c) for c in chunks]
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")
    assert bot.chunk_text("") == []
    assert bot.chunk_text("hi") == ["hi"]


def test_parse_and_extract():
    line = json.dumps({"type": "text", "sessionID": "ses_abc", "part": {"text": "hello"}})
    ev = bot.parse_event(line)
    assert ev["type"] == "text"
    assert bot.event_text(ev) == "hello"
    assert bot.parse_event("Warning: something") is None
    assert bot.parse_event(b"{not json") is None

    err = bot.parse_event(json.dumps({"type": "error", "error": {"message": "quota exceeded"}}))
    assert bot.event_error(err) == "quota exceeded"

    tool = bot.parse_event(json.dumps({"type": "tool_use", "part": {"tool": "bash"}}))
    assert bot.event_tool(tool) == "bash"


def test_build_args_hash_style():
    args = bot.build_args("fix bug", "opencode/glm-5.3-flash-free", "high", "ses_1", True)
    assert args[:4] == ["opencode", "run", "--format", "json"], args
    assert "-s" in args and "ses_1" in args
    assert "-m" in args
    assert args[args.index("-m") + 1] == "opencode/glm-5.3-flash-free#high"
    assert "--variant" not in args
    assert "--auto" in args
    assert args[-1] == "fix bug"


def test_build_args_flag_style():
    args = bot.build_args("hi", "opencode/big-pickle", "low", None, False, auto=False)
    assert args[args.index("-m") + 1] == "opencode/big-pickle"
    assert args[args.index("--variant") + 1] == "low"
    assert "-s" not in args
    assert "--auto" not in args


def test_build_args_default_thinking():
    args = bot.build_args("hi", "opencode/big-pickle", "default", None, True)
    assert "#" not in args[args.index("-m") + 1]
    assert "--variant" not in args


def test_state_roundtrip(tmp_path):
    bot.STATE_DB = tmp_path / "state.db"
    bot.set_state(7, authed=1, model="opencode/big-pickle", thinking="high")
    st = bot.get_state(7)
    assert st["authed"] == 1 and st["model"] == "opencode/big-pickle"
    bot.set_state(7, session_id="ses_x")
    assert bot.get_state(7)["session_id"] == "ses_x"
    bot.set_state(7, session_id=None)
    assert bot.get_state(7)["session_id"] is None
    assert bot.get_state(999) == {"authed": 0, "session_id": None, "model": None, "thinking": None}


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                if fn.__code__.co_argcount:
                    import tempfile

                    with tempfile.TemporaryDirectory() as d:
                        fn(Path(d))
                else:
                    fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    print("all good" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
