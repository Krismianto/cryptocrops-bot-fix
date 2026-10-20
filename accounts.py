#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
accounts.py — simpan banyak akun CryptoCrops dalam satu file.

Format `accounts.json`:

    {
      "active": "SawitDES",
      "accounts": {
        "SawitDES": {
          "session": "xtoNAwYXNTli-...",
          "extra": {"cc_registration_v1": "..."},
          "added_at": 1792500000,
          "last_seen": 1792500000
        }
      }
    }

Yang dipakai di request cuma dua cookie: `cc_session_v1` (sesi) dan
`cc_registration_v1` (id tamu). Sisanya disimpan apa adanya supaya tidak hilang.

`cookies.txt` ditulis ulang tiap kali akun aktif dipilih, dalam format simpel
(lihat `cookiefile.py`), jadi gampang dibaca/diedit manusia maupun script lain.
"""

from __future__ import annotations

import json
import os
import re
import time

import cookiefile

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "accounts.json")
LEGACY = os.path.join(HERE, "cookies.txt")
SESSION = "cc_session_v1"
LIFETIME = 30 * 24 * 3600

_cache: dict | None = None


# ------------------------------------------------------------------ store ---
def load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    data: dict = {"active": None, "accounts": {}}
    if os.path.exists(STORE):
        try:
            with open(STORE, encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict) and isinstance(raw.get("accounts"), dict):
                data = {"active": raw.get("active"),
                        "accounts": raw["accounts"]}
        except (OSError, ValueError):
            pass
    elif os.path.exists(LEGACY):
        # migrasi sekali: cookies.txt lama jadi akun pertama
        found = cookiefile.load(LEGACY)
        if found:
            first = found[0]
            data["accounts"]["akun1"] = {
                "session": first.get("session") or "",
                "extra": {k: v for k, v in (first.get("extra") or {}).items()
                          if k.startswith("cc_")},
                "added_at": int(time.time()),
                "last_seen": int(time.time()),
            }
            data["active"] = "akun1"
            save(data)
        # berkas berisi banyak akun sekaligus: impor semuanya
        for idx, acct in enumerate(found[1:], start=2):
            if acct.get("session"):
                data["accounts"][f"akun{idx}"] = {
                    "session": acct["session"],
                    "extra": {k: v for k, v in (acct.get("extra") or {}).items()
                              if k.startswith("cc_")},
                    "added_at": int(time.time()),
                    "last_seen": int(time.time()),
                }
        if found:
            save(data)
    _cache = data
    return data


def save(data: dict) -> None:
    global _cache
    _cache = data
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, STORE)


def reset_cache() -> None:
    global _cache
    _cache = None


# ------------------------------------------------------------------ query ---
def names() -> list[str]:
    return list(load()["accounts"].keys())


def get(name: str | None) -> dict | None:
    data = load()
    if not name:
        name = data.get("active")
    if not name:
        return None
    if name in data["accounts"]:
        return data["accounts"][name]
    low = name.lower()
    for key, acct in data["accounts"].items():
        if key.lower() == low:
            return acct
    return None


def key_of(name: str | None) -> str | None:
    data = load()
    if not name:
        return data.get("active")
    if name in data["accounts"]:
        return name
    low = name.lower()
    for key in data["accounts"]:
        if key.lower() == low:
            return key
    return None


def active_name() -> str | None:
    return load().get("active")


def set_active(name: str) -> str:
    data = load()
    key = key_of(name)
    if not key:
        raise KeyError(f"akun {name!r} tidak ada")
    data["active"] = key
    data["accounts"][key]["last_seen"] = int(time.time())
    save(data)
    return key


# ------------------------------------------------------------------- write ---
def upsert(session: str, extra: dict[str, str] | None = None,
           name: str | None = None) -> str:
    """Simpan/perbarui akun; balikan nama yang dipakai."""
    data = load()
    extra = {k: v for k, v in (extra or {}).items() if k.startswith("cc_")}
    now = int(time.time())

    # sesi yang sama sudah ada -> update, jangan bikin duplikat
    for key, acct in data["accounts"].items():
        if acct.get("session") == session:
            acct["extra"] = extra or acct.get("extra") or {}
            acct["last_seen"] = now
            if name and name != key:
                data["accounts"][name] = data["accounts"].pop(key)
                if data.get("active") == key:
                    data["active"] = name
                key = name
            save(data)
            return key

    key = (name or f"akun{len(data['accounts']) + 1}").strip()
    data["accounts"][key] = {"session": session, "extra": extra,
                             "added_at": now, "last_seen": now}
    if not data.get("active"):
        data["active"] = key
    save(data)
    return key


def remove(name: str) -> bool:
    data = load()
    key = key_of(name)
    if not key:
        return False
    data["accounts"].pop(key, None)
    if data.get("active") == key:
        data["active"] = next(iter(data["accounts"]), None)
    save(data)
    return True


def rename(old: str, new: str) -> str:
    data = load()
    key = key_of(old)
    if not key:
        raise KeyError(old)
    if new != key:
        data["accounts"][new] = data["accounts"].pop(key)
        if data.get("active") == key:
            data["active"] = new
        save(data)
    return new


# ---------------------------------------------------------------- cookies ---
def cookie_header_from(session: str, extra: dict[str, str] | None = None) -> str:
    return cookiefile.header_for(session, extra)


def cookie_header(name: str | None = None) -> str:
    acct = get(name)
    if not acct:
        return ""
    return cookie_header_from(acct.get("session") or "",
                              acct.get("extra") or {})


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "akun"


def as_cookie(name: str | None = None) -> dict:
    """Akun siap ditulis: {'session': ..., 'extra': {...}, 'name': ...}."""
    acct = get(name)
    if not acct:
        return {"session": "", "extra": {}, "name": ""}
    return {"session": acct.get("session") or "",
            "extra": dict(acct.get("extra") or {}),
            "name": key_of(name) or "akun"}


def write_cookie_file(name: str | None, path: str, note: bool = True) -> str:
    """Tulis satu akun ke `path` dengan format cookies.txt yang simpel."""
    item = as_cookie(name)
    if not item.get("session") and not item.get("extra"):
        return ""
    text = cookiefile.format_accounts([item])
    if note and item.get("name"):
        head, sep, body = text.partition("\n\n")
        text = f"{head}\n# akun: {item['name']}{sep}{body}"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return path


def write_netscape(name: str | None, path: str) -> str:
    """Alias lama — sekarang menulis format simpel, bukan Netscape."""
    return write_cookie_file(name, path)


def export_all(path: str) -> str:
    """Tulis semua akun: satu baris per akun, `reg|session`."""
    data = load()
    items = [{"session": a.get("session") or "",
              "extra": dict(a.get("extra") or {})}
             for a in data["accounts"].values()]
    return cookiefile.write(path, items, style="line")


def import_file(path: str) -> list[dict]:
    """Baca cookies.txt (format apa pun) -> list akun."""
    return cookiefile.load(path)


def _read_netscape(path: str) -> dict[str, str]:
    first = cookiefile.load_first(path)
    pairs = dict(first.get("extra") or {})
    if first.get("session"):
        pairs[SESSION] = first["session"]
    return pairs



def summary() -> list[dict]:
    data = load()
    rows = []
    for key, acct in data["accounts"].items():
        rows.append({"name": key, "active": key == data.get("active"),
                     "session": (acct.get("session") or "")[:8] + "…",
                     "added_at": acct.get("added_at")})
    return rows
