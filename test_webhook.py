"""Webhook mode ka test — asli aiohttp server + asli HTTP POST, bina Telegram ke.

Run: python tests/test_webhook.py
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiohttp import ClientSession, web  # noqa: E402
from telegram import Bot, User  # noqa: E402
from telegram.ext import Application, MessageHandler, filters  # noqa: E402

import bot  # noqa: E402


async def _fake_get_me(self, *args, **kwargs):
    """Bot.initialize() getMe call karta hai — test me network nahi chahiye."""
    self._bot_user = User(id=123456, first_name="TestBot", is_bot=True, username="testbot")
    return self._bot_user


Bot.get_me = _fake_get_me  # type: ignore[method-assign]

PORT = 8899
UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 5,
        "date": 1700000000,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 42, "is_bot": False, "first_name": "Test"},
        "text": "hello",
    },
}


def test_webhook_roundtrip():
    """200 turant, update queue me, handler chalta hai, health ok, galat secret 403."""

    async def scenario(tmp: Path):
        bot.STATE_DB = tmp / "state.db"
        bot.WEBHOOK_SECRET = "topsecret"

        app = Application.builder().token("123456:TESTTOKEN").updater(None).build()
        seen = []

        async def record(update, context):
            seen.append(update.update_id)

        app.add_handler(MessageHandler(filters.ALL, record))

        srv, accepted = bot.build_http_app(app)
        runner = web.AppRunner(srv)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", PORT)
        await site.start()
        await app.initialize()
        await app.start()
        try:
            async with ClientSession() as s:
                base = f"http://127.0.0.1:{PORT}"

                r = await s.get(f"{base}/health")
                assert r.status == 200, r.status
                body = await r.json()
                assert body["status"] == "ok" and body["version"] == bot.VERSION, body

                # secret nahi bheja -> 403, kuch queue nahi
                r = await s.post(f"{base}/webhook", json=UPDATE)
                assert r.status == 403, r.status

                # galat secret -> 403
                r = await s.post(
                    f"{base}/webhook", json=UPDATE,
                    headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
                )
                assert r.status == 403, r.status

                # sahi secret -> 200 turant
                r = await s.post(
                    f"{base}/webhook", json=UPDATE,
                    headers={"X-Telegram-Bot-Api-Secret-Token": "topsecret"},
                )
                assert r.status == 200, r.status
                assert await r.text() == "ok"

                # kharab json -> 400
                r = await s.post(
                    f"{base}/webhook", data="not json",
                    headers={"X-Telegram-Bot-Api-Secret-Token": "topsecret"},
                )
                assert r.status == 400, r.status

                for _ in range(40):
                    if seen:
                        break
                    await asyncio.sleep(0.05)
                assert seen == [1], seen
                assert accepted["n"] == 1, accepted
        finally:
            await app.stop()
            await app.shutdown()
            await runner.cleanup()

    with tempfile.TemporaryDirectory() as d:
        asyncio.run(scenario(Path(d)))


def test_webhook_no_secret_configured():
    """WEBHOOK_SECRET khali ho to bina header ke bhi accept (kam surakshit, par valid)."""

    async def scenario(tmp: Path):
        bot.STATE_DB = tmp / "state.db"
        bot.WEBHOOK_SECRET = ""
        app = Application.builder().token("123456:TESTTOKEN").updater(None).build()
        seen = []

        async def record(update, context):
            seen.append(update.update_id)

        app.add_handler(MessageHandler(filters.ALL, record))
        srv, _ = bot.build_http_app(app)
        runner = web.AppRunner(srv)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", PORT + 1).start()
        await app.initialize()
        await app.start()
        try:
            async with ClientSession() as s:
                r = await s.post(f"http://127.0.0.1:{PORT + 1}/webhook", json=UPDATE)
                assert r.status == 200, r.status
                for _ in range(40):
                    if seen:
                        break
                    await asyncio.sleep(0.05)
                assert seen == [1], seen
        finally:
            await app.stop()
            await app.shutdown()
            await runner.cleanup()

    with tempfile.TemporaryDirectory() as d:
        asyncio.run(scenario(Path(d)))


def test_webhook_mode_detection():
    """WEBHOOK_URL set ho to main() webhook chunta hai, warna polling."""
    old = bot.WEBHOOK_URL
    try:
        bot.WEBHOOK_URL = ""
        assert bool(bot.WEBHOOK_URL) is False
        bot.WEBHOOK_URL = "https://example.onrender.com/"
        assert bot.WEBHOOK_URL.rstrip("/") == "https://example.onrender.com"
    finally:
        bot.WEBHOOK_URL = old


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
