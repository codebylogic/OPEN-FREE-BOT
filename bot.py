#!/usr/bin/env python3
"""
OpenCode <-> Telegram bridge bot.

Features
--------
/start <code>   access code se login
/free           free (Zen) models ki list + tap karke select
/model (/modal) model change, aur thinking level set
/thinking       reasoning effort (low / medium / high / default)
/new            naya session
/exit           current chat session band
/status         kya chal raha hai
/stop           chal raha run kill
baaki koi bhi text -> usi session me `opencode run` chalta hai

Python 3.10+, python-telegram-bot v21+
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import InvalidToken, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ACCESS_CODE = os.getenv("ACCESS_CODE", "").strip()
# India time — time-based code ($HHMM$) isi se banta hai.
IST = timezone(timedelta(hours=5, minutes=30))
OPENCODE_BIN = os.getenv("OPENCODE_BIN", "opencode").strip()
WORKDIR = Path(os.getenv("OPENCODE_WORKDIR", "~/opencode-workspace")).expanduser()
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "").strip()
DEFAULT_THINKING = os.getenv("DEFAULT_THINKING", "").strip()
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "true").lower() in {"1", "true", "yes", "on"}
RUN_TIMEOUT = int(os.getenv("RUN_TIMEOUT", "900"))
VARIANT_STYLE = os.getenv("OPENCODE_VARIANT_STYLE", "auto").strip().lower()
STATE_DB = Path(os.getenv("STATE_DB", str(Path(__file__).parent / "data" / "state.db"))).expanduser()
ALLOWED_USERS = {
    int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x.strip().isdigit()
}

# Webhook mode (Render/Koyeb jaise free hosts ke liye). Khali = long polling.
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
PORT = int(os.getenv("PORT", "8080"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()

# Agar `opencode models` fail ho jaye to ye list dikhegi.
FALLBACK_FREE_MODELS = [
    "opencode/big-pickle",
    "opencode/deepseek-v4.1-flash-free",
    "opencode/glm-5.3-flash-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/minimax-m3.1-flash-free",
    "opencode/longcat-2.5-preview-free",
]

THINKING_LEVELS = ["default", "low", "medium", "high"]
MAX_TG = 4000  # Telegram limit 4096, thoda margin

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("opencode-bot")

VERSION = "1.3.0"

# --------------------------------------------------------------------------- #
# State (sqlite)
# --------------------------------------------------------------------------- #
LOCKS: dict[int, asyncio.Lock] = {}
PROCS: dict[int, asyncio.subprocess.Process] = {}
MODEL_CACHE: dict[str, Any] = {"at": 0.0, "free": [], "all": []}


def db() -> sqlite3.Connection:
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STATE_DB, timeout=30)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chat_state (
               chat_id    INTEGER PRIMARY KEY,
               authed     INTEGER DEFAULT 0,
               session_id TEXT,
               model      TEXT,
               thinking   TEXT,
               updated    REAL
           )"""
    )
    return conn


def get_state(chat_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            "SELECT authed, session_id, model, thinking FROM chat_state WHERE chat_id=?",
            (chat_id,),
        ).fetchone()
    if not row:
        return {"authed": 0, "session_id": None, "model": None, "thinking": None}
    return {"authed": row[0], "session_id": row[1], "model": row[2], "thinking": row[3]}


def set_state(chat_id: int, **fields: Any) -> None:
    allowed = {"authed", "session_id", "model", "thinking"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chat_state (chat_id, updated) VALUES (?, ?)",
            (chat_id, time.time()),
        )
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE chat_state SET {sets}, updated=? WHERE chat_id=?",
            (*fields.values(), time.time(), chat_id),
        )


# --------------------------------------------------------------------------- #
# Pure helpers (tested in tests/test_helpers.py)
# --------------------------------------------------------------------------- #
def chunk_text(text: str, size: int = MAX_TG) -> list[str]:
    """Long reply ko Telegram ke limit me todo, line boundaries par."""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = text.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def filter_free_models(lines: list[str]) -> list[str]:
    """`opencode models` output se free Zen models chhaanto."""
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "/" not in line:
            continue
        if not line.startswith("opencode/"):
            continue
        if line.endswith("-free") or "-free-" in line or line.endswith("/big-pickle") or "pickle" in line:
            if line not in out:
                out.append(line)
    return out


def parse_event(line: bytes | str) -> dict[str, Any] | None:
    if isinstance(line, bytes):
        try:
            line = line.decode("utf-8", "replace")
        except Exception:
            return None
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return None
    return ev if isinstance(ev, dict) else None


def event_text(ev: dict[str, Any]) -> str:
    part = ev.get("part") or {}
    if not isinstance(part, dict):
        return ""
    for key in ("text", "content"):
        val = part.get(key)
        if isinstance(val, str):
            return val
    return ""


def event_tool(ev: dict[str, Any]) -> str:
    part = ev.get("part") or {}
    if not isinstance(part, dict):
        return ""
    for key in ("tool", "name", "title"):
        val = part.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def event_error(ev: dict[str, Any]) -> str:
    err = ev.get("error")
    if isinstance(err, str):
        return err
    if isinstance(err, dict):
        for key in ("message", "name", "type"):
            if isinstance(err.get(key), str):
                return err[key]
    part = ev.get("part") or {}
    if isinstance(part, dict) and isinstance(part.get("error"), str):
        return part["error"]
    return ""


def tail(text: str, n: int) -> str:
    return text[-n:] if len(text) > n else text


def build_model_arg(model: str, thinking: str | None, hash_style: bool) -> tuple[str, list[str]]:
    """(model arg, extra args). v2 => provider/model#high, v1 => --variant high."""
    extra: list[str] = []
    if not model:
        return "", extra
    if thinking and thinking != "default":
        if hash_style:
            return f"{model}#{thinking}", extra
        extra = ["--variant", thinking]
    return model, extra


def build_args(
    prompt: str,
    model: str,
    thinking: str | None,
    session_id: str | None,
    hash_style: bool,
    auto: bool = True,
) -> list[str]:
    args = [OPENCODE_BIN, "run", "--format", "json"]
    if session_id:
        args += ["-s", session_id]
    model_arg, extra = build_model_arg(model, thinking, hash_style)
    if model_arg:
        args += ["-m", model_arg]
        args += extra
    if auto:
        args.append("--auto")
    args.append(prompt)
    return args


# --------------------------------------------------------------------------- #
# opencode helpers
# --------------------------------------------------------------------------- #
async def sh(cmd: list[str], timeout: float = 60.0, cwd: Path | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", f"timeout after {timeout}s"
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


_HASH_STYLE: bool | None = None


async def detect_hash_style() -> bool:
    """OpenCode 2 me variant model string ke andar (#high) aata hai, 1.x me flag.

    Ek hi baar detect hota hai, phir cache — har message par process spawn nahi.
    """
    global _HASH_STYLE
    if VARIANT_STYLE == "hash":
        return True
    if VARIANT_STYLE == "flag":
        return False
    if _HASH_STYLE is not None:
        return _HASH_STYLE
    code, out, _ = await sh([OPENCODE_BIN, "--version"], timeout=30)
    if code != 0:
        return False  # fail ho to 1.x syntax (safe default), cache nahi karte
    m = re.search(r"(\d+)\.", out)
    _HASH_STYLE = bool(m) and int(m.group(1)) >= 2
    return _HASH_STYLE


async def load_models(force: bool = False) -> tuple[list[str], list[str]]:
    if not force and MODEL_CACHE["free"] and time.time() - MODEL_CACHE["at"] < 600:
        return MODEL_CACHE["free"], MODEL_CACHE["all"]
    code, out, err = await sh([OPENCODE_BIN, "models"], timeout=120)
    lines = out.splitlines() if code == 0 else []
    all_models = [ln.strip() for ln in lines if "/" in ln and not ln.startswith("#")]
    free = filter_free_models(lines)
    if not free:
        free = list(FALLBACK_FREE_MODELS)
        if code != 0:
            log.warning("`opencode models` failed (%s): %s", code, err.strip()[:300])
    MODEL_CACHE.update({"at": time.time(), "free": free, "all": all_models})
    return free, all_models


# --------------------------------------------------------------------------- #
# UI text
# --------------------------------------------------------------------------- #
HELP = (
    "<b>OpenCode Telegram Bot</b>\n\n"
    "<b>Commands</b>\n"
    "/free &mdash; free models ki list, tap karke choose karo\n"
    "/model (ya /modal) &mdash; model change + thinking level\n"
    "/thinking &mdash; low / medium / high\n"
    "/new &mdash; naya session shuru\n"
    "/exit &mdash; current chat session band\n"
    "/status &mdash; abhi kya set hai\n"
    "/stop &mdash; chal raha kaam rok do\n"
    "/logout &mdash; access code dobara maango\n\n"
    "Baaki koi bhi message bhejo &mdash; wahi prompt OpenCode ko jayega.\n"
    f"Working directory: <code>{WORKDIR}</code>"
)


def kb_models(models: list[str], current: str | None, thinking: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in models[:40]:
        short = m.replace("opencode/", "")
        mark = "✅ " if m == current else ""
        rows.append([InlineKeyboardButton(f"{mark}{short}", callback_data=f"m|{m}")])
    rows.append(
        [
            InlineKeyboardButton(f"{'✅ ' if (thinking or 'default') == 'default' else ''}thinking: default", callback_data="v|default"),
            InlineKeyboardButton("low", callback_data="v|low"),
            InlineKeyboardButton("medium", callback_data="v|medium"),
            InlineKeyboardButton("high", callback_data="v|high"),
        ]
    )
    rows.append([InlineKeyboardButton("🔄 refresh list", callback_data="f|refresh")])
    return InlineKeyboardMarkup(rows)


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #
def user_blocked(update: Update) -> bool:
    if not ALLOWED_USERS:
        return False
    user = update.effective_user
    return not user or user.id not in ALLOWED_USERS


async def need_auth(update: Update) -> bool:
    """True bheja to reply ho chuka hai aur handler rukna chahiye."""
    if user_blocked(update):
        await update.effective_message.reply_text("⛔ Ye bot private hai.")
        return True
    st = get_state(update.effective_chat.id)
    if not st["authed"]:
        await update.effective_message.reply_text(
            "🔒 Pehle login karo: <code>/start YOUR_CODE</code>", parse_mode="HTML"
        )
        return True
    return False


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def _stamp_code(template: str, stamp: str) -> str:
    """`$HHMM$` -> `$1430$` (dollar sign code ka hissa hai, isliye rehta hai).

    Plain `HHMM` (bina dollar) bhi support hai.
    """
    if "$HHMM$" in template:
        return template.replace("$HHMM$", f"${stamp}$")
    return template.replace("HHMM", stamp)


def access_code_variants(template: str, now: datetime | None = None) -> list[str]:
    """ACCESS_CODE template se acceptable codes banao.

    `$HHMM$` ko IST ke ghante+minut se badla jata hai — `cblai$HHMM$` ka matlab
    `cblai$1430$` (dollar sign code me hi rehta hai). Pichla aur agla minute bhi
    shamil hote hain, warna minute boundary par login fail hota hai.
    """
    if "$HHMM$" not in template and "HHMM" not in template:
        return [template]
    now = now or datetime.now(IST)
    return [
        _stamp_code(template, (now + timedelta(minutes=d)).strftime("%H%M"))
        for d in (-1, 0, 1)
    ]


def current_access_code(template: str, now: datetime | None = None) -> str:
    """Abhi ka code (sirf dikhane ke liye, CLI me)."""
    now = now or datetime.now(IST)
    return _stamp_code(template, now.strftime("%H%M"))


def access_code_ok(given: str, template: str, now: datetime | None = None) -> bool:
    """Constant-time compare, template ke saare valid variants par."""
    given = (given or "").strip()
    if not given or not template:
        return False
    return any(hmac.compare_digest(given, v) for v in access_code_variants(template, now))


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if user_blocked(update):
        await update.message.reply_text("⛔ Ye bot private hai.")
        return
    code = (ctx.args[0] if ctx.args else "").strip()
    if not ACCESS_CODE:
        await update.message.reply_text(
            "⚠️ Server par ACCESS_CODE set nahi hai. .env me ACCESS_CODE daalo, phir restart karo."
        )
        return
    if not code:
        await update.message.reply_text("🔑 <code>/start YOUR_CODE</code> bhejo.", parse_mode="HTML")
        return
    if not access_code_ok(code, ACCESS_CODE):
        await update.message.reply_text(
            "❌ Code galat hai. Agar time-based code hai to minute badal gaya hoga — naya code try karo."
        )
        return
    set_state(chat_id, authed=1)
    await update.message.reply_text(HELP, parse_mode="HTML")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await need_auth(update):
        return
    await update.message.reply_text(HELP, parse_mode="HTML")


async def cmd_free(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await need_auth(update):
        return
    chat_id = update.effective_chat.id
    st = get_state(chat_id)
    free, _ = await load_models()
    lines = [f"• <code>{m}</code>" for m in free]
    text = (
        "<b>Free models (OpenCode Zen)</b>\n"
        + "\n".join(lines)
        + "\n\nTap karke select karo. Ye free offers limited time ke liye hote hain, "
        "aur data terms model ke hisaab se badalte hain.\n"
        f"\nAbhi: <code>{st['model'] or DEFAULT_MODEL or 'default (opencode config)'}</code>"
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=kb_models(free, st["model"] or DEFAULT_MODEL, st["thinking"] or DEFAULT_THINKING),
    )


async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/model ya /modal — argument ke saath seedha set, warna buttons."""
    if await need_auth(update):
        return
    chat_id = update.effective_chat.id
    if ctx.args:
        model = ctx.args[0].strip()
        if "/" not in model:
            await update.message.reply_text(
                "Format: <code>/model provider/model</code>  jaise <code>/model opencode/glm-5.3-flash-free</code>",
                parse_mode="HTML",
            )
            return
        set_state(chat_id, model=model)
        await update.message.reply_text(f"✅ Model set: <code>{model}</code>", parse_mode="HTML")
        return
    free, _ = await load_models()
    st = get_state(chat_id)
    await update.message.reply_text(
        "Model chuno (thinking level bhi neeche se set kar sakte ho):",
        reply_markup=kb_models(free, st["model"] or DEFAULT_MODEL, st["thinking"] or DEFAULT_THINKING),
    )


async def cmd_thinking(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await need_auth(update):
        return
    chat_id = update.effective_chat.id
    st = get_state(chat_id)
    if ctx.args:
        level = ctx.args[0].strip().lower()
        if level not in THINKING_LEVELS:
            await update.message.reply_text("Options: " + ", ".join(THINKING_LEVELS))
            return
        set_state(chat_id, thinking=level)
        await update.message.reply_text(f"🧠 Thinking: {level}")
        return
    cur = st["thinking"] or DEFAULT_THINKING or "default"
    rows = [
        [InlineKeyboardButton(f"{'✅ ' if cur == lvl else ''}{lvl}", callback_data=f"v|{lvl}")]
        for lvl in THINKING_LEVELS
    ]
    await update.message.reply_text(
        "Reasoning effort chuno (sirf reasoning models par asar karta hai):",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await need_auth(update):
        return
    chat_id = update.effective_chat.id
    proc = PROCS.get(chat_id)
    if proc and proc.returncode is None:
        proc.kill()
    set_state(chat_id, session_id=None)
    await update.message.reply_text("🆕 Session reset. Agla message naya session banayega.")


async def cmd_exit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await need_auth(update):
        return
    chat_id = update.effective_chat.id
    proc = PROCS.get(chat_id)
    if proc and proc.returncode is None:
        proc.kill()
    set_state(chat_id, session_id=None)
    await update.message.reply_text(
        "👋 Session band. Model/thinking yaad rahega. Naya session: seedha message bhejo ya /new."
    )


async def cmd_logout(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    set_state(chat_id, authed=0, session_id=None)
    await update.message.reply_text("🔒 Logged out. Dobara login: /start YOUR_CODE")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await need_auth(update):
        return
    chat_id = update.effective_chat.id
    st = get_state(chat_id)
    proc = PROCS.get(chat_id)
    running = "haan" if (proc and proc.returncode is None) else "nahi"
    await update.message.reply_text(
        "<b>Status</b>\n"
        f"model: <code>{st['model'] or DEFAULT_MODEL or 'default'}</code>\n"
        f"thinking: {st['thinking'] or DEFAULT_THINKING or 'default'}\n"
        f"session: <code>{st['session_id'] or 'naya banega'}</code>\n"
        f"running: {running}\n"
        f"workdir: <code>{WORKDIR}</code>",
        parse_mode="HTML",
    )


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await need_auth(update):
        return
    chat_id = update.effective_chat.id
    proc = PROCS.get(chat_id)
    if proc and proc.returncode is None:
        proc.kill()
        await update.message.reply_text("🛑 Rok diya.")
    else:
        await update.message.reply_text("Kuch nahi chal raha.")


# --------------------------------------------------------------------------- #
# Buttons
# --------------------------------------------------------------------------- #
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if user_blocked(update):
        return
    chat_id = update.effective_chat.id
    if not get_state(chat_id)["authed"]:
        await query.edit_message_text("🔒 Pehle /start YOUR_CODE")
        return
    kind, _, value = (query.data or "").partition("|")
    if kind == "m":
        set_state(chat_id, model=value)
        await query.edit_message_text(
            f"✅ Model: <code>{value}</code>\nThinking: {get_state(chat_id)['thinking'] or 'default'}\n\n"
            "Ab message bhejo.",
            parse_mode="HTML",
        )
    elif kind == "v":
        set_state(chat_id, thinking=value)
        await query.edit_message_text(f"🧠 Thinking: {value}\n\nAb message bhejo.")
    elif kind == "f":
        free, _ = await load_models(force=True)
        st = get_state(chat_id)
        await query.edit_message_text(
            "🔄 List refresh ho gayi.",
            reply_markup=kb_models(free, st["model"] or DEFAULT_MODEL, st["thinking"] or DEFAULT_THINKING),
        )


# --------------------------------------------------------------------------- #
# Prompt -> opencode run
# --------------------------------------------------------------------------- #
async def typing_loop(bot, chat_id: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=4.5)
        except asyncio.TimeoutError:
            continue


async def stream_run(
    args: list[str],
    chat_id: int,
    on_progress: Any = None,
    progress_every: float = 4.0,
    timeout: float | None = None,
) -> dict[str, Any]:
    """`opencode run --format json` chalao aur JSONL events padho.

    Ek dict lautaata hai: text, errors, stderr, returncode, timed_out,
    session_id, tools.
    """
    limit = float(RUN_TIMEOUT if timeout is None else timeout)
    res: dict[str, Any] = {
        "text": "",
        "errors": [],
        "stderr": "",
        "returncode": None,
        "timed_out": False,
        "session_id": None,
        "tools": [],
    }
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(WORKDIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    PROCS[chat_id] = proc
    stderr_task = asyncio.create_task(proc.stderr.read())
    out_parts: list[str] = []
    tool_now = ""
    deadline = time.monotonic() + limit
    last_progress = 0.0
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                res["timed_out"] = True
                proc.kill()
                break
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                res["timed_out"] = True
                proc.kill()
                break
            if not raw:
                break
            ev = parse_event(raw)
            if not ev:
                continue
            if not res["session_id"] and isinstance(ev.get("sessionID"), str):
                res["session_id"] = ev["sessionID"]
                set_state(chat_id, session_id=res["session_id"])
            etype = ev.get("type")
            if etype == "text":
                piece = event_text(ev)
                if piece:
                    out_parts.append(piece)
            elif etype == "tool_use":
                tool_now = event_tool(ev) or tool_now
                if tool_now and tool_now not in res["tools"]:
                    res["tools"].append(tool_now)
            elif etype == "error":
                msg = event_error(ev)
                if msg:
                    res["errors"].append(msg)

            now = time.monotonic()
            if on_progress and now - last_progress > progress_every:
                last_progress = now
                await on_progress(tool_now, "".join(out_parts))
    finally:
        try:
            await proc.wait()
        except Exception:
            pass
        PROCS.pop(chat_id, None)
        try:
            res["stderr"] = (await asyncio.wait_for(stderr_task, timeout=10)).decode("utf-8", "replace")
        except Exception:
            stderr_task.cancel()
    res["text"] = "".join(out_parts).strip()
    res["returncode"] = proc.returncode
    return res


def format_result(res: dict[str, Any]) -> str:
    """stream_run ke result se Telegram ke liye final text banao."""
    answer = res["text"]
    if res["timed_out"]:
        answer = (answer + f"\n\n⏱ {RUN_TIMEOUT}s me khatam nahi hua, kill kar diya.").strip()
    if not answer:
        detail = "\n".join(res["errors"]) or (res["stderr"] or "").strip()[-1500:] or "koi output nahi mila"
        return f"❌ OpenCode se jawab nahi aaya:\n{detail}"
    if res["returncode"] not in (0, None) and res["errors"]:
        answer += "\n\n⚠️ " + "\n".join(res["errors"])[-800:]
    return answer


async def handle_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await need_auth(update):
        return
    chat_id = update.effective_chat.id
    prompt = (update.message.text or "").strip()
    if not prompt:
        return

    lock = LOCKS.setdefault(chat_id, asyncio.Lock())
    if lock.locked():
        await update.message.reply_text("⏳ Pehla message abhi chal raha hai. /stop se rok sakte ho.")
        return

    async with lock:
        st = get_state(chat_id)
        model = st["model"] or DEFAULT_MODEL
        thinking = st["thinking"] or DEFAULT_THINKING
        hash_style = await detect_hash_style()
        args = build_args(prompt, model, thinking, st["session_id"], hash_style, AUTO_APPROVE)

        status_msg = await update.message.reply_text(
            f"⏳ chal raha hai…\nmodel: <code>{model or 'default'}</code>", parse_mode="HTML"
        )
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(typing_loop(ctx.bot, chat_id, stop_typing))

        async def on_progress(tool_now: str, so_far: str) -> None:
            preview = (
                "⏳ chal raha hai…\n"
                + (f"🔧 {tool_now}\n" if tool_now else "")
                + (f"\n{tail(so_far, 2500)}" if so_far else "")
            )
            try:
                await status_msg.edit_text(preview)
            except Exception:
                pass

        try:
            res = await stream_run(args, chat_id, on_progress=on_progress)
        except FileNotFoundError:
            await status_msg.edit_text(
                f"❌ <code>{OPENCODE_BIN}</code> nahi mila. Server par opencode install karo "
                "(README ka step 4) ya .env me OPENCODE_BIN ka poora path do.",
                parse_mode="HTML",
            )
            return
        finally:
            stop_typing.set()
            typing_task.cancel()

        answer = format_result(res)
        chunks = chunk_text(answer) or ["(khaali jawab)"]
        try:
            await status_msg.edit_text(chunks[0])
        except Exception:
            await update.message.reply_text(chunks[0])
        for extra in chunks[1:]:
            await update.message.reply_text(extra)

# --------------------------------------------------------------------------- #
# Boot
# --------------------------------------------------------------------------- #
async def post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "access code se login"),
            BotCommand("free", "free models list"),
            BotCommand("model", "model + thinking change"),
            BotCommand("thinking", "reasoning level"),
            BotCommand("new", "naya session"),
            BotCommand("exit", "session band"),
            BotCommand("status", "abhi kya set hai"),
            BotCommand("stop", "chal raha kaam roko"),
            BotCommand("help", "commands"),
        ]
    )
    free, _ = await load_models()
    hash_style = await detect_hash_style()
    log.info(
        "ready v%s | workdir=%s | free_models=%d | variant_style=%s | auto_approve=%s",
        VERSION, WORKDIR, len(free), "hash" if hash_style else "flag", AUTO_APPROVE,
    )


def build_http_app(app: Application) -> tuple[Any, dict[str, int]]:
    """Webhook + health ke liye chhota aiohttp app.

    Telegram ko 200 turant lautaate hain aur update queue me daal dete hain —
    warna 5-10 minute chalne wale agent run par Telegram dobara bhejta rehta
    hai aur kaam duplicate ho jata hai.
    """
    from aiohttp import web

    accepted = {"n": 0}

    async def handle_webhook(request: web.Request) -> web.Response:
        if WEBHOOK_SECRET:
            got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if got != WEBHOOK_SECRET:
                return web.Response(status=403, text="forbidden")
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="bad json")
        try:
            update = Update.de_json(data, app.bot)
        except Exception:
            return web.Response(text="ok")  # kachra update, chhod do
        if update is not None:
            await app.update_queue.put(update)
            accepted["n"] += 1
        return web.Response(text="ok")

    async def health(request: web.Request) -> web.Response:
        return web.json_response(
            {"status": "ok", "version": VERSION, "accepted": accepted["n"]}
        )

    srv = web.Application()
    srv.router.add_post("/webhook", handle_webhook)
    srv.router.add_get("/health", health)
    srv.router.add_get("/", health)
    return srv, accepted


async def run_webhook(app: Application) -> None:
    """Webhook mode — host ka HTTPS URL chahiye (Render, Koyeb, VPS...)."""
    from aiohttp import web

    srv, _ = build_http_app(app)
    runner = web.AppRunner(srv)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

    await app.initialize()
    await app.start()
    await app.bot.set_webhook(
        url=f"{WEBHOOK_URL}/webhook",
        secret_token=WEBHOOK_SECRET or None,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )
    log.info("webhook mode: %s/webhook | port=%s | health=/health", WEBHOOK_URL, PORT)
    try:
        await asyncio.Event().wait()
    finally:
        await app.bot.delete_webhook()
        await app.stop()
        await app.shutdown()
        await runner.cleanup()


def startup_error_message(exc: Exception) -> str | None:
    """Shuru me aane wali common galtiyon ko aasan bhasha me badlo."""
    if isinstance(exc, InvalidToken):
        return (
            "BOT_TOKEN galat ya revoke ho chuka hai. @BotFather → /mybots → API Token se "
            "naya token lo, phir .env / GitHub secret / Render env me update karke restart karo."
        )
    if isinstance(exc, NetworkError):
        return (
            "Telegram tak network nahi pahunch raha (internet/firewall/proxy). "
            "Server par `curl -s https://api.telegram.org` chala kar check karo."
        )
    if isinstance(exc, TelegramError) and "Invalid server response" in str(exc):
        return (
            "Telegram ka jawab samajh nahi aaya — beech me proxy, firewall ya captive portal ho sakta hai "
            "(college/office Wi-Fi par aam hai). Server par `curl -I https://api.telegram.org` chala kar dekho."
        )
    return None


def main() -> None:
    if "--version" in sys.argv:
        print(f"opencode-telegram-bot {VERSION}")
        return
    if "--code" in sys.argv:
        if not ACCESS_CODE:
            print("ACCESS_CODE set nahi hai — .env me daalo (jaise cblai$HHMM$)")
            return
        now = datetime.now(IST)
        print(f"template : {ACCESS_CODE}")
        print(f"abhi     : {current_access_code(ACCESS_CODE, now)}   (IST {now:%H:%M})")
        print(f"valid    : {', '.join(access_code_variants(ACCESS_CODE, now))}")
        return
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN missing — .env banao (.env.example dekho)")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    db().close()

    use_webhook = bool(WEBHOOK_URL)
    builder = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(post_init)
    )
    if use_webhook:
        builder = builder.updater(None)  # updates HTTP se aayenge
    app = builder.build()
    register_handlers(app)

    try:
        if use_webhook:
            asyncio.run(run_webhook(app))
        else:
            log.info("polling start")
            app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as exc:  # token galat / network band — saaf message do
        msg = startup_error_message(exc)
        if msg:
            raise SystemExit(f"❌ {msg}") from None
        raise


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler(["help"], cmd_help))
    app.add_handler(CommandHandler(["free"], cmd_free))
    app.add_handler(CommandHandler(["model", "modal"], cmd_model))
    app.add_handler(CommandHandler(["thinking", "think"], cmd_thinking))
    app.add_handler(CommandHandler(["new"], cmd_new))
    app.add_handler(CommandHandler(["exit"], cmd_exit))
    app.add_handler(CommandHandler(["logout"], cmd_logout))
    app.add_handler(CommandHandler(["status"], cmd_status))
    app.add_handler(CommandHandler(["stop"], cmd_stop))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))


if __name__ == "__main__":
    main()
