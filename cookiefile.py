#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
cookiefile.py - baca/tulis cookies.txt tanpa bikin pusing.

Satu akun (format yang disarankan):

    cc_registration_v1=0de0566b-6a14-4b97-8ecf-7f759782bd2a.1792480912945.36c7...
    cc_session_v1=xtoNAwYXNTli-2QIFL16MtPxiyI5TfS6cG83uP9K-y8

Banyak akun (satu baris = satu akun, urutan reg|session):

    cc_registration_v1|cc_session_v1
    cc_registration_v1|cc_session_v1

Format lain yang tetap diterima: `name=value` dipisah `|` / `;` / spasi,
header cookie utuh dari DevTools, baris Netscape, dan token mentah.
Baris yang diawali `#` diabaikan, jadi komentar aman ditulis di file.
"""

from __future__ import annotations

import os
import re

SESSION = "cc_session_v1"
REGISTRATION = "cc_registration_v1"

_SPLIT = re.compile(r"[|;&\s]+")
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
HEXISH = re.compile(r"^[0-9a-f]+$", re.I)

HEADER = (
    "# CryptoCrops cookies - created by Z3R0 0N3 ID | Airdrop 888",
    "# satu akun   : cc_registration_v1=<nilai> lalu cc_session_v1=<nilai>",
    "# banyak akun : satu baris per akun -> cc_registration_v1|cc_session_v1",
    "# nama=value, header cookie utuh, dan format Netscape juga diterima",
)


# ------------------------------------------------------------------ helpers ---
def guess_name(value: str) -> str:
    """Tebak sebuah nilai itu registration atau session."""
    value = value.strip()
    if _UUID.match(value) or value.count(".") >= 2:
        return REGISTRATION
    return SESSION


def _looks_value(token: str) -> bool:
    token = token.strip()
    if len(token) < 16 or "://" in token:
        return False
    if HEXISH.match(token) and len(token) < 24:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.%+/=:-]+", token))


# -------------------------------------------------------------------- parse ---
def parse(text: str) -> list[dict]:
    """Balikan list akun: [{'session': ..., 'extra': {...}}, ...]."""
    accounts: list[dict] = []
    cur: dict[str, str] = {}

    def flush() -> None:
        nonlocal cur
        session = cur.get(SESSION, "")
        extra = {k: v for k, v in cur.items() if k != SESSION and v}
        if session or extra:
            accounts.append({"session": session, "extra": extra})
        cur = {}

    def put(name: str, value: str) -> None:
        value = value.strip().strip('"').strip("'")
        if not value:
            return
        name = name.strip()
        if name == SESSION:
            if cur.get(SESSION):
                flush()
            cur[SESSION] = value
            return
        if not name.startswith("cc_"):
            return
        if cur.get(name):          # nilai kedua = akun baru
            flush()
        cur[name] = value

    def bare(token: str) -> None:
        token = token.strip().strip('"').strip("'")
        if not _looks_value(token):
            return
        put(guess_name(token), token)

    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue

        if "\t" in line:                        # Netscape
            parts = line.split("\t")
            if len(parts) >= 7:
                name = parts[5].strip()
                if name.startswith("#HttpOnly_"):
                    name = name[len("#HttpOnly_"):]
                put(name, parts[6])
                continue

        if "=" in line:
            for chunk in _SPLIT.split(line):
                if not chunk:
                    continue
                if "=" not in chunk:
                    bare(chunk)
                    continue
                name, _, value = chunk.partition("=")
                if name.strip().startswith("cc_"):
                    put(name, value)
                elif _looks_value(name.strip()) and not _looks_value(value):
                    bare(name)              # "TOKEN=" aneh dari copy-paste
            continue

        if "|" in line:
            for chunk in line.split("|"):
                bare(chunk)
            continue

        bare(line)

    flush()
    return accounts


# ------------------------------------------------------------------- format ---
def format_accounts(accounts: list[dict], style: str = "block") -> str:
    """Teks cookies.txt. style: 'block' (per akun, nama=value) / 'line'."""
    out = list(HEADER) + [""]
    for acct in accounts or []:
        session = (acct.get("session") or "").strip()
        reg = ((acct.get("extra") or {}).get(REGISTRATION) or "").strip()
        if style == "line":
            if not (session or reg):
                continue
            out.append(f"{reg}|{session}" if reg and session
                       else (session or reg))
            continue
        if reg:
            out.append(f"{REGISTRATION}={reg}")
        if session:
            out.append(f"{SESSION}={session}")
        if reg or session:
            out.append("")
    if out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def header_for(session: str, extra: dict[str, str] | None = None) -> str:
    """Header `Cookie:` siap pakai untuk requests."""
    pairs = {k: v for k, v in (extra or {}).items() if k.startswith("cc_") and v}
    if session:
        pairs[SESSION] = session
    return "; ".join(f"{k}={v}" for k, v in pairs.items())


# --------------------------------------------------------------------- file ---
def load(path: str) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return parse(fh.read())


def load_first(path: str) -> dict:
    found = load(path)
    return found[0] if found else {"session": "", "extra": {}}


def write(path: str, accounts: list[dict], style: str = "block") -> str:
    text = format_accounts(accounts, style=style)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return path


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "cookies.txt"
    items = load(target)
    print(f"{target}: {len(items)} akun")
    for n, acct in enumerate(items, 1):
        sess = acct.get("session") or ""
        reg = (acct.get("extra") or {}).get(REGISTRATION) or ""
        print(f"  {n}. session {sess[:10]}…{sess[-4:]} ({len(sess)})"
              f" · reg {reg[:8]}…")
