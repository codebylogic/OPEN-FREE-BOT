"""stream_run ka integration test — asli subprocess + asli JSONL parsing.

Fake `opencode` binary use hoti hai, isliye asli opencode/API key ki zaroorat nahi.
Run: python tests/test_stream.py
"""
import asyncio
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot  # noqa: E402

EVENTS_OK = [
    {"type": "step_start", "sessionID": "ses_test123"},
    {"type": "tool_use", "sessionID": "ses_test123", "part": {"tool": "bash"}},
    {"type": "text", "sessionID": "ses_test123", "part": {"text": "Hello "}},
    {"type": "tool_use", "sessionID": "ses_test123", "part": {"tool": "read"}},
    {"type": "text", "sessionID": "ses_test123", "part": {"text": "world"}},
    {"type": "step_finish", "sessionID": "ses_test123"},
]


def write_fake(dirpath: Path, body: str, name: str = "opencode") -> Path:
    p = dirpath / name
    p.write_text("#!/usr/bin/env python3\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def setup(tmp: Path) -> None:
    bot.WORKDIR = tmp
    bot.STATE_DB = tmp / "state.db"
    bot.RUN_TIMEOUT = 30


def test_stream_ok():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        setup(tmp)
        events = "\n".join(json.dumps(e) for e in EVENTS_OK)
        fake = write_fake(
            tmp,
            f"""import sys, time
print("Warning: something non-json")
for line in {events!r}.splitlines():
    print(line); sys.stdout.flush(); time.sleep(0.02)
sys.exit(0)
""",
        )
        args = [str(fake), "run", "--format", "json", "hello"]
        res = asyncio.run(bot.stream_run(args, chat_id=42, timeout=20))
        assert res["text"] == "Hello world", res["text"]
        assert res["session_id"] == "ses_test123"
        assert res["tools"] == ["bash", "read"], res["tools"]
        assert res["returncode"] == 0
        assert not res["timed_out"]
        assert bot.get_state(42)["session_id"] == "ses_test123"
        assert bot.format_result(res) == "Hello world"


def test_stream_error():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        setup(tmp)
        fake = write_fake(
            tmp,
            """import sys, json
print(json.dumps({"type": "error", "error": {"message": "quota exceeded"}}))
sys.stderr.write("boom\\n")
sys.exit(1)
""",
        )
        res = asyncio.run(bot.stream_run([str(fake), "run"], chat_id=7, timeout=20))
        assert res["errors"] == ["quota exceeded"], res["errors"]
        assert res["returncode"] == 1
        out = bot.format_result(res)
        assert "quota exceeded" in out, out
        assert out.startswith("❌"), out


def test_stream_timeout():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        setup(tmp)
        fake = write_fake(
            tmp,
            """import time
print('{"type":"text","part":{"text":"start"}}', flush=True)
time.sleep(30)
""",
        )
        res = asyncio.run(bot.stream_run([str(fake), "run"], chat_id=9, timeout=1.5))
        assert res["timed_out"] is True
        assert "start" in res["text"]
        assert "khatam nahi hua" in bot.format_result(res)


def test_missing_binary():
    with tempfile.TemporaryDirectory() as d:
        setup(Path(d))
        try:
            asyncio.run(bot.stream_run(["/nonexistent/opencode", "run"], chat_id=5, timeout=5))
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("FileNotFoundError expected")


def test_progress_called():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        setup(tmp)
        fake = write_fake(
            tmp,
            """import sys, time
for i in range(6):
    print('{"type":"text","part":{"text":"chunk%d "}}' % i, flush=True)
    time.sleep(0.05)
""",
        )
        seen = []

        async def on_prog(tool, so_far):
            seen.append(so_far)

        res = asyncio.run(
            bot.stream_run([str(fake), "run"], chat_id=11, on_progress=on_prog,
                           progress_every=0.01, timeout=20)
        )
        assert seen, "progress callback kabhi nahi chala"
        assert res["text"].startswith("chunk0"), res["text"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as e:
                fails += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    print("all good" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
