"""Command-level test: /start ka access-code gate aur auth guard.

Telegram network ke bina chalta hai (Update/Message ke stubs).
Run: python tests/test_commands.py
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot  # noqa: E402


class StubMessage:
    def __init__(self):
        self.texts = []
        self.markups = []

    async def reply_text(self, text, **kw):
        self.texts.append(text)
        self.markups.append(kw.get("reply_markup"))
        return self

    async def edit_text(self, text, **kw):
        self.texts.append(text)
        return self


class StubChat:
    def __init__(self, cid):
        self.id = cid


class StubUser:
    def __init__(self, uid):
        self.id = uid


class StubUpdate:
    def __init__(self, chat_id=1, user_id=99):
        self.message = StubMessage()
        self.effective_message = self.message
        self.effective_chat = StubChat(chat_id)
        self.effective_user = StubUser(user_id)


class StubCtx:
    def __init__(self, args=None):
        self.args = args or []
        self.bot = None


def fresh(tmp: Path, access_code="secret-123"):
    bot.STATE_DB = tmp / "state.db"
    bot.ACCESS_CODE = access_code
    bot.ALLOWED_USERS = set()


def test_start_flow():
    with tempfile.TemporaryDirectory() as d:
        fresh(Path(d))
        up = StubUpdate(chat_id=1)
        asyncio.run(bot.cmd_start(up, StubCtx([])))
        assert "YOUR_CODE" in up.message.texts[-1], up.message.texts
        assert bot.get_state(1)["authed"] == 0

        up = StubUpdate(chat_id=1)
        asyncio.run(bot.cmd_start(up, StubCtx(["galat"])))
        assert "galat hai" in up.message.texts[-1]
        assert bot.get_state(1)["authed"] == 0

        up = StubUpdate(chat_id=1)
        asyncio.run(bot.cmd_start(up, StubCtx(["secret-123"])))
        assert "OpenCode Telegram Bot" in up.message.texts[-1], up.message.texts
        assert bot.get_state(1)["authed"] == 1

        # dobara start = dobara help, error nahi
        up = StubUpdate(chat_id=1)
        asyncio.run(bot.cmd_start(up, StubCtx(["secret-123"])))
        assert "OpenCode Telegram Bot" in up.message.texts[-1]


def test_guard_blocks_unauth():
    with tempfile.TemporaryDirectory() as d:
        fresh(Path(d))
        up = StubUpdate(chat_id=2)
        blocked = asyncio.run(bot.need_auth(up))
        assert blocked is True
        assert "login" in up.effective_message.texts[-1].lower()


def test_guard_allows_auth():
    with tempfile.TemporaryDirectory() as d:
        fresh(Path(d))
        bot.set_state(3, authed=1)
        up = StubUpdate(chat_id=3)
        assert asyncio.run(bot.need_auth(up)) is False
        assert up.effective_message.texts == []


def test_allowed_users():
    with tempfile.TemporaryDirectory() as d:
        fresh(Path(d))
        bot.ALLOWED_USERS = {555}
        up = StubUpdate(chat_id=4, user_id=99)
        assert asyncio.run(bot.need_auth(up)) is True
        assert "private" in up.effective_message.texts[-1].lower()

        bot.set_state(4, authed=1)
        up = StubUpdate(chat_id=4, user_id=555)
        assert asyncio.run(bot.need_auth(up)) is False


def test_model_and_thinking_commands():
    with tempfile.TemporaryDirectory() as d:
        fresh(Path(d))
        bot.set_state(5, authed=1)

        up = StubUpdate(chat_id=5)
        asyncio.run(bot.cmd_model(up, StubCtx(["opencode/glm-5.3-flash-free"])))
        assert bot.get_state(5)["model"] == "opencode/glm-5.3-flash-free"

        up = StubUpdate(chat_id=5)
        asyncio.run(bot.cmd_model(up, StubCtx(["glm-5.3-flash-free"])))
        assert "provider/model" in up.message.texts[-1]

        up = StubUpdate(chat_id=5)
        asyncio.run(bot.cmd_thinking(up, StubCtx(["high"])))
        assert bot.get_state(5)["thinking"] == "high"

        up = StubUpdate(chat_id=5)
        asyncio.run(bot.cmd_thinking(up, StubCtx(["ultra"])))
        assert "Options" in up.message.texts[-1]


def test_new_and_exit_clear_session():
    with tempfile.TemporaryDirectory() as d:
        fresh(Path(d))
        bot.set_state(6, authed=1, session_id="ses_1")
        asyncio.run(bot.cmd_new(StubUpdate(chat_id=6), StubCtx()))
        assert bot.get_state(6)["session_id"] is None
        bot.set_state(6, session_id="ses_2")
        asyncio.run(bot.cmd_exit(StubUpdate(chat_id=6), StubCtx()))
        assert bot.get_state(6)["session_id"] is None
        assert bot.get_state(6)["authed"] == 1


def test_no_access_code_configured():
    with tempfile.TemporaryDirectory() as d:
        fresh(Path(d), access_code="")
        up = StubUpdate(chat_id=8)
        asyncio.run(bot.cmd_start(up, StubCtx(["anything"])))
        assert "ACCESS_CODE" in up.message.texts[-1]
        assert bot.get_state(8)["authed"] == 0


def test_kb_models_buttons():
    kb = bot.kb_models(["opencode/big-pickle", "opencode/glm-5.3-flash-free"], "opencode/big-pickle", "high")
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "m|opencode/big-pickle" in datas
    assert "v|high" in datas
    assert "f|refresh" in datas
    first = kb.inline_keyboard[0][0].text
    assert first.startswith("✅"), first


def test_handler_wiring():
    """main() jo handlers lagata hai, wo sahi callbacks par jaate hain."""
    app = bot.Application.builder().token("123456:TESTTOKEN").build()
    bot.register_handlers(app)
    cmds = {}
    for h in app.handlers[0]:
        if isinstance(h, bot.CommandHandler):
            for c in h.commands:
                cmds[c] = h.callback
    assert cmds["start"] is bot.cmd_start
    assert cmds["model"] is bot.cmd_model and cmds["modal"] is bot.cmd_model
    assert cmds["free"] is bot.cmd_free
    assert cmds["new"] is bot.cmd_new
    assert cmds["exit"] is bot.cmd_exit
    assert cmds["thinking"] is bot.cmd_thinking
    assert cmds["status"] is bot.cmd_status
    assert cmds["stop"] is bot.cmd_stop
    assert cmds["logout"] is bot.cmd_logout
    assert any(isinstance(h, bot.CallbackQueryHandler) for h in app.handlers[0])
    assert any(isinstance(h, bot.MessageHandler) for h in app.handlers[0])


def test_startup_error_messages():
    """Token galat / network band par aasan message mile, warna None."""
    from telegram.error import InvalidToken, NetworkError

    tok = bot.startup_error_message(InvalidToken("bad token"))
    assert tok and "BotFather" in tok, tok

    net = bot.startup_error_message(NetworkError("boom"))
    assert net and "network" in net.lower(), net

    assert bot.startup_error_message(ValueError("kuch aur")) is None


def test_startup_error_proxy_case():
    """Proxy/captive portal se aaya 'Invalid server response' bhi samajh aaye."""
    from telegram.error import TelegramError

    msg = bot.startup_error_message(TelegramError("Invalid server response"))
    assert msg and "proxy" in msg.lower(), msg
    assert bot.startup_error_message(TelegramError("Forbidden: bot was blocked")) is None


def test_time_based_access_code():
    """cblai$HHMM$ — current minute + pichla/agla minute valid, baaki nahi."""
    from datetime import datetime, timedelta, timezone

    ist = timezone(timedelta(hours=5, minutes=30))
    t = datetime(2026, 11, 26, 14, 30, tzinfo=ist)
    tpl = "cblai$HHMM$"

    assert bot.current_access_code(tpl, t) == "cblai$1430$"
    assert bot.access_code_variants(tpl, t) == ["cblai$1429$", "cblai$1430$", "cblai$1431$"]

    assert bot.access_code_ok("cblai$1430$", tpl, t) is True   # exact
    assert bot.access_code_ok("cblai$1429$", tpl, t) is True   # minute boundary
    assert bot.access_code_ok("cblai$1431$", tpl, t) is True
    assert bot.access_code_ok("cblai$1428$", tpl, t) is False  # bahut purana
    assert bot.access_code_ok("cblai$1432$", tpl, t) is False
    assert bot.access_code_ok("cblai1430", tpl, t) is False    # $ ke bina
    assert bot.access_code_ok("", tpl, t) is False
    assert bot.access_code_ok("  cblai$1430$  ", tpl, t) is True  # trim

    # static code (template nahi) purani tarah chalta rahe
    assert bot.access_code_ok("mera-secret", "mera-secret", t) is True
    assert bot.access_code_ok("cblai$1430$", "mera-secret", t) is False


def test_time_code_midnight_and_leading_zero():
    """Raat 00:00 aur single-digit ghante par bhi sahi format."""
    from datetime import datetime, timedelta, timezone

    ist = timezone(timedelta(hours=5, minutes=30))
    t = datetime(2026, 11, 26, 0, 0, tzinfo=ist)
    assert bot.current_access_code("cblai$HHMM$", t) == "cblai$0000$"
    assert bot.access_code_variants("cblai$HHMM$", t)[0] == "cblai$2359$"  # pichla din

    t2 = datetime(2026, 11, 26, 7, 5, tzinfo=ist)
    assert bot.current_access_code("cblai$HHMM$", t2) == "cblai$0705$"


def test_start_accepts_time_code():
    """cmd_start time-based code accept kare aur galat par login na ho."""
    from datetime import datetime, timedelta, timezone

    with tempfile.TemporaryDirectory() as d:
        fresh(Path(d))
        ist = timezone(timedelta(hours=5, minutes=30))
        bot.ACCESS_CODE = "cblai$HHMM$"
        code = bot.current_access_code("cblai$HHMM$", datetime.now(ist))

        up = StubUpdate(chat_id=21)
        asyncio.run(bot.cmd_start(up, StubCtx([code])))
        assert bot.get_state(21)["authed"] == 1, up.message.texts

        up = StubUpdate(chat_id=22)
        asyncio.run(bot.cmd_start(up, StubCtx(["cblai$9999$"])))
        assert bot.get_state(22)["authed"] == 0
        assert "galat" in up.message.texts[-1].lower()


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
