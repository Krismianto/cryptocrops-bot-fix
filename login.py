#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
login.py — kelola banyak akun CryptoCrops tanpa ngoprek format cookie.

Tempel apa saja dari browser:
  * token mentah        xtoNAwYXNTli-2QIFL16MtPxiyI5TfS6cG83uP9K-y8
  * name=value          cc_session_v1=xtoNAw...
  * header cookie       cc_session_v1=xto...; cc_registration_v1=...
  * satu blok akun      cc_registration_v1=... lalu cc_session_v1=...
  * banyak akun         cc_registration_v1|cc_session_v1  (satu baris = satu akun)
  * baris Netscape      cryptocrops.net<TAB>FALSE<TAB>/<TAB>TRUE<TAB>...<TAB>cc_session_v1<TAB>...

Pemakaian:
    python login.py                 # tambah / perbarui akun (paste, Enter)
    python login.py --clip          # ambil dari clipboard
    python login.py --import FILE   # impor cookies.txt (banyak akun sekaligus)
    python login.py --export FILE   # tulis semua akun: reg|session per baris
    python login.py --list          # daftar akun
    python login.py --use NAMA      # jadikan akun aktif (tulis cookies.txt)
    python login.py --remove NAMA
    python login.py --check         # cek semua akun ke server
    python login.py --cookies "cc_session_v1=..."

Akun disimpan di accounts.json. Nama akun diambil otomatis dari display name
server (SawitDES, dst). `cookies.txt` selalu ditulis ulang untuk akun aktif
dalam format simpel (lihat cookiefile.py), jadi gampang dibaca manusia.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import accounts  # noqa: E402
import cookiefile  # noqa: E402

BASE = "https://cryptocrops.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")
COOKIE_FILE = os.path.join(HERE, "cookies.txt")


# ------------------------------------------------------------------ input ---
def _clipboard() -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-Clipboard -Raw"],
                             capture_output=True, text=True, timeout=15)
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def parse(text: str) -> tuple[str, dict[str, str]]:
    """Ambil sesi + cookie cc_* lain dari input bentuk apa pun (akun pertama)."""
    found = cookiefile.parse(text)
    if not found:
        return "", {}
    first = found[0]
    return first.get("session") or "", dict(first.get("extra") or {})


def parse_many(text: str) -> list[dict]:
    return cookiefile.parse(text)


# ------------------------------------------------------------------ server ---
def verify(session: str, extra: dict[str, str]) -> dict | None:
    header = accounts.cookie_header_from(session, extra)
    try:
        r = requests.get(f"{BASE}/api/bootstrap", timeout=20,
                         headers={"user-agent": UA, "cookie": header,
                                  "accept": "*/*", "referer": f"{BASE}/farm/"})
    except requests.RequestException as exc:
        print(f"  gagal konek: {exc}")
        return None
    if r.status_code != 200:
        print(f"  ditolak server: HTTP {r.status_code} — {r.text[:120]}")
        return None
    try:
        return r.json()
    except ValueError:
        print("  server balas bukan JSON")
        return None


def show_one(b: dict, label: str = "") -> None:
    farm = b.get("farm") or {}
    pl = b.get("player") or {}
    prof = farm.get("profile") or {}
    prog = farm.get("farm_progression") or {}
    f = farm.get("faucet") or {}
    name = pl.get("display_name") or pl.get("username") or "-"
    tag = f"[{label}] " if label else ""
    print(f"  {tag}{name}{' · premium' if pl.get('premium') else ''}"
          f" · coin {prof.get('farm_coins')}"
          f" · xp {prog.get('xp')}/lvl {prog.get('level')}"
          f" · faucet {f.get('claim_count')}x"
          f"{' siap' if f.get('available') else ''}")


# ------------------------------------------------------------------- aksi ---
def add_one(session: str, extra: dict[str, str], label: str = "") -> int:
    """Verifikasi lalu simpan satu akun. 0 = ok, 1 = gagal."""
    tag = f"[{label}] " if label else ""
    print(f"  {tag}token : {session[:10]}…{session[-6:]} ({len(session)} char)")
    if not session and not extra:
        print(f"  {tag}tidak menemukan cc_session_v1 di input itu")
        print("  contoh: cc_registration_v1=... lalu cc_session_v1=...")
        return 1

    print(f"  {tag}cek ke server…")
    b = verify(session, extra)
    if not b:
        print(f"  {tag}cookie tidak valid / kedaluwarsa — tidak disimpan")
        return 1

    pl = b.get("player") or {}
    name = pl.get("display_name") or pl.get("username") or None
    key = accounts.upsert(session, extra, name=name)
    accounts.set_active(key)
    accounts.write_cookie_file(key, COOKIE_FILE)
    print(f"  {tag}tersimpan sebagai akun: {key} · sekarang aktif")
    show_one(b)
    return 0


def add_account(raw: str) -> int:
    items = parse_many(raw)
    if not items:
        print("  tidak menemukan cookie di input itu")
        print("  contoh: cc_session_v1=xtoNAw...")
        return 1
    print(f"  {len(items)} akun terdeteksi di input" if len(items) > 1 else "")
    ok = 0
    for n, item in enumerate(items, 1):
        label = f"{n}/{len(items)}" if len(items) > 1 else ""
        ok += add_one(item.get("session") or "",
                      dict(item.get("extra") or {}), label) == 0
    if len(items) > 1:
        print(f"  selesai: {ok}/{len(items)} akun tersimpan")
    return 0 if ok else 1


def cmd_list() -> int:
    rows = accounts.summary()
    if not rows:
        print("  belum ada akun — jalankan: python login.py")
        return 1
    print(f"  {'':2} {'nama':24} {'sesi':10}  ditambahkan")
    for r in rows:
        mark = "*" if r["active"] else " "
        when = time.strftime("%Y-%m-%d %H:%M",
                             time.localtime(r["added_at"] or 0))
        print(f"  {mark:2} {r['name'][:24]:24} {r['session']:10}  {when}")
    print("  (* = aktif, dipakai cookies.txt)")
    return 0


def cmd_use(name: str) -> int:
    try:
        key = accounts.set_active(name)
    except KeyError:
        print(f"  akun {name!r} tidak ada")
        return 1
    accounts.write_cookie_file(key, COOKIE_FILE)
    print(f"  akun aktif: {key} · cookies.txt ditulis ulang")
    return 0


def cmd_remove(name: str) -> int:
    if not accounts.remove(name):
        print(f"  akun {name!r} tidak ada")
        return 1
    active = accounts.active_name()
    if active:
        accounts.write_cookie_file(active, COOKIE_FILE)
    print(f"  dihapus: {name}" + (f" · aktif sekarang {active}" if active else ""))
    return 0


def cmd_check() -> int:
    rows = accounts.summary()
    if not rows:
        print("  belum ada akun")
        return 1
    bad = 0
    for r in rows:
        acct = accounts.get(r["name"]) or {}
        b = verify(acct.get("session") or "", acct.get("extra") or {})
        if not b:
            print(f"  [×] {r['name']}: cookie mati")
            bad += 1
            continue
        show_one(b, r["name"])
    return 0 if bad == 0 else 1


def cmd_import(path: str) -> int:
    if not os.path.exists(path):
        print(f"  file tidak ada: {path}")
        return 1
    items = accounts.import_file(path)
    if not items:
        print(f"  tidak ada akun yang bisa dibaca dari {path}")
        return 1
    print(f"  {len(items)} akun di {path}")
    ok = 0
    for n, item in enumerate(items, 1):
        ok += add_one(item.get("session") or "",
                      dict(item.get("extra") or {}),
                      f"{n}/{len(items)}") == 0
    print(f"  selesai: {ok}/{len(items)} akun tersimpan")
    return 0 if ok else 1


def cmd_export(path: str) -> int:
    rows = accounts.summary()
    if not rows:
        print("  belum ada akun")
        return 1
    accounts.export_all(path)
    print(f"  {len(rows)} akun ditulis ke {path} (format: reg|session per baris)")
    return 0


# -------------------------------------------------------------------- main ---
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cookie", nargs="?", help="nilai cookie (opsional)")
    ap.add_argument("--clip", action="store_true", help="ambil dari clipboard")
    ap.add_argument("--import", dest="import_from", metavar="FILE",
                    help="impor akun dari cookies.txt")
    ap.add_argument("--export", dest="export_to", metavar="FILE",
                    help="tulis semua akun (reg|session per baris)")
    ap.add_argument("--list", action="store_true", help="daftar akun")
    ap.add_argument("--use", metavar="NAMA", help="jadikan akun aktif")
    ap.add_argument("--remove", metavar="NAMA", help="hapus akun")
    ap.add_argument("--check", action="store_true", help="verifikasi semua akun")
    ap.add_argument("--cookies", metavar="STR", help="cookie langsung (non-interaktif)")
    args = ap.parse_args()

    if args.list:
        return cmd_list()
    if args.use:
        return cmd_use(args.use)
    if args.remove:
        return cmd_remove(args.remove)
    if args.check:
        return cmd_check()
    if args.import_from:
        return cmd_import(args.import_from)
    if args.export_to:
        return cmd_export(args.export_to)

    raw = args.cookies or args.cookie or (_clipboard() if args.clip else "")
    if not raw:
        if accounts.names():
            print(f"  akun tersimpan: {', '.join(accounts.names())}")
            print(f"  aktif: {accounts.active_name() or '-'}")
            print()
        print("  tempel cookie / token, lalu Enter:")
        print("  (DevTools -> Application -> Cookies -> cryptocrops.net -> cc_session_v1)")
        try:
            raw = sys.stdin.readline()
        except KeyboardInterrupt:
            return 1
    if not raw.strip():
        print("  kosong — batal")
        return 1
    return add_account(raw)


if __name__ == "__main__":
    sys.exit(main())
