#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
faucet_run.py - klaim faucet CryptoCrops: countdown, klaim, ringkasan singkat.

Mesin: Camoufox (Firefox stealth) membuka /faucet/ asli, jadi Turnstile
di-render oleh situs sendiri dan tokennya sah. Chromium selalu gagal 600010.

Pemakaian:
  python faucet_run.py                 # tunggu cooldown lalu klaim
  python faucet_run.py --loop
  python faucet_run.py --headless
  python faucet_run.py --account SawitDES
  python faucet_run.py --json          # satu baris JSON (untuk piping)
  python faucet_run.py --no-wait       # langsung keluar kalau cooldown
  python faucet_run.py --dry-run       # sampai token siap, tidak klik klaim

Output manusiawi dibuat ringkas: hasil klaim, saldo, jadwal berikutnya.
Payload mentah hanya keluar lewat --json.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BAR = "─" * 62


# ---------------------------------------------------------------- re-exec ---
def _ensure_camoufox() -> None:
    """Pastikan interpreter ini punya camoufox; kalau tidak, re-exec ke venv."""
    try:
        import camoufox  # noqa: F401
    except ImportError:
        pass
    else:
        try:
            from camoufox.pkgman import camoufox_path
            camoufox_path()
            return
        except Exception:  # noqa: BLE001
            pass

    if os.environ.get("CC_REEXEC") == "1":
        raise SystemExit(
            "  camoufox di interpreter ini belum siap (biner belum di-fetch).\n"
            "  jalankan: camoufox fetch\n"
            "  atau set CC_PY=<path python yang punya camoufox lengkap>")

    candidates = [
        os.environ.get("CC_PY", ""),
        os.path.join(os.environ.get("TEMP", ""), "opencode", "Turnstile-Solver",
                     ".venv", "Scripts", "python.exe"),
    ]
    for exe in candidates:
        if exe and os.path.isfile(exe):
            env = dict(os.environ, CC_REEXEC="1")
            rc = subprocess.call([exe, os.path.abspath(__file__)] + sys.argv[1:],
                                 env=env)
            raise SystemExit(rc)

    raise SystemExit(
        "  camoufox tidak terpasang di python ini.\n"
        "  pip install camoufox   (atau set CC_PY ke python yang punya)")


# ------------------------------------------------------------------ utils ---
def hr(title: str = "") -> None:
    print(BAR)
    if title:
        print(title)


def fmt(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def clock(ms: int) -> str:
    return time.strftime("%H:%M", time.localtime(int(ms) / 1000))


def show_state(api) -> dict:
    b = api.bootstrap()
    farm = b.get("farm") or {}
    f = farm.get("faucet") or {}
    prof = farm.get("profile") or {}
    prog = farm.get("farm_progression") or {}
    pl = b.get("player") or {}
    print(f"  akun   {pl.get('display_name') or pl.get('username') or '-'}"
          f" · coin {prof.get('farm_coins')}"
          f" · xp {prog.get('xp')}"
          f" · klaim {f.get('claim_count')}")
    return f


def countdown(api, next_claim_at: int) -> None:
    """Hitung mundur satu baris, berhenti tepat di 0."""
    while True:
        left = int(next_claim_at) - api.now_ms()
        if left <= 0:
            print(f"\r  cooldown  {fmt(0)}  · siap klaim            ")
            return
        print(f"\r  cooldown  {fmt(left / 1000)}  ({left // 1000} dtk)      ",
              end="", flush=True)
        sys.stdout.flush()
        time.sleep(min(1.0, max(0.05, left / 1000)))


# ------------------------------------------------------------------- flow ---
def run_once(api, *, headed: bool, wait: bool, dry_run: bool,
             cookies: str = "cookies.txt", quiet: bool = False) -> dict:
    from camoufox_claim import claim

    hr("  faucet")
    try:
        faucet = show_state(api)
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status", None)
        print(f"  gagal bootstrap: {exc}")
        if status == 401:
            print("  cookie kedaluwarsa - python login.py")
        return {"status": "error", "detail": str(exc)}

    if not faucet.get("available"):
        nxt = int(faucet.get("next_claim_at") or 0)
        if not wait:
            print(f"  cooldown {fmt((nxt - api.now_ms()) / 1000)} tersisa"
                  f" · berikutnya {clock(nxt)}")
            return {"status": "cooldown", "next_claim_at": nxt}
        countdown(api, nxt)
        api.bootstrap()

    print("  membuka browser · menunggu Turnstile…")
    t0 = time.time()
    res = claim(headed=headed, timeout=300, cookie_path=cookies,
                dry_run=dry_run,
                log=(lambda m: None) if quiet else
                (lambda m: print(m, flush=True)))
    elapsed = round(time.time() - t0, 1)

    # response tidak tertangkap (tab keburu tutup)? cek langsung ke server
    if res.get("status") not in ("claimed", "dry_run", "cooldown", "not_ready"):
        try:
            b2 = api.bootstrap()
            f2 = (b2.get("farm") or {}).get("faucet") or {}
            p2 = (b2.get("farm") or {}).get("profile") or {}
            if int(f2.get("claim_count") or 0) > int(faucet.get("claim_count") or 0):
                res = {"status": "claimed", "claim_count": f2.get("claim_count"),
                       "total_coins": 10,
                       "farm_coin_balance": p2.get("farm_coins"),
                       "next_claim_at": f2.get("next_claim_at")}
        except Exception:  # noqa: BLE001
            pass

    print(f"  selesai dalam {elapsed}s")
    st = res.get("status")
    if st == "claimed":
        xp = res.get("farm_xp_earned")
        print("  ✓ klaim berhasil")
        print(f"    +{res.get('total_coins')} coin"
              f"{f' · +{xp} xp' if xp else ''}"
              f" · saldo {res.get('farm_coin_balance')}")
        nxt = res.get("next_claim_at")
        if nxt:
            print(f"    berikutnya {fmt((int(nxt) - api.now_ms()) / 1000)}"
                  f" ({clock(nxt)})")
    elif st == "dry_run":
        print(f"  ✓ token siap ({res.get('token_len')} char) · klaim tidak diklik")
    elif st == "cooldown":
        print("  · server masih cooldown")
    elif st == "not_ready":
        print("  × widget tidak selesai (screenshot: captures/claim_not_ready.png)")
    elif st == "page_error":
        print("  × halaman tidak merender (captures/claim_page_error.png)")
    elif st == "clicked":
        print("  · tombol terklik, response tidak tertangkap - cek saldo di atas")
    elif st == "timeout":
        print("  × timeout menunggu browser")
    elif res.get("error"):
        err = str(res.get("error"))
        print(f"  × ditolak server: {err}")
        if "CAPTCHA_FAILED" in err:
            print("    token tidak diterima - satu sesi: challenge -> solve -> claim")
        elif "RATE_LIMITED" in err:
            print("    rate limit - tunggu, jangan retry")
    elif st:
        print(f"  · {st}")
    return res


def main() -> int:
    _ensure_camoufox()

    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--headed", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--cookies", default=None,
                    help="file cookie (default: akun aktif)")
    ap.add_argument("--account", help="nama akun dari accounts.json")
    args = ap.parse_args()

    from client import CryptoCrops

    account = args.account or os.environ.get("CC_ACCOUNT") or None
    cookie_file = args.cookies or os.path.join(HERE, "cookies.txt")
    if args.cookies is None:
        try:
            import accounts
            key = accounts.key_of(account) if account else accounts.active_name()
            if account and not key:
                print(f"  akun {account!r} tidak ada di accounts.json")
                return 2
            if key:
                cookie_file = os.path.join(
                    HERE, f"cookies.{accounts.safe_name(key)}.txt")
                accounts.write_cookie_file(key, cookie_file)
                os.environ["CC_ACCOUNT"] = key
                account = key
        except Exception:  # noqa: BLE001
            pass

    if not args.json:
        import ui
        global BAR
        BAR = ui.color("─" * max(40, ui.width() - 1), ui.GRAY)
        ui.clear()
        ui.show_banner("CryptoCrops", "faucet claim"
                       + (f" · {account}" if account else ""))
        print(f"  akun aktif: {account or 'default'}")
        print(BAR)

    api = CryptoCrops(account=account)
    headed = not args.headless
    last: dict = {}

    real_out = sys.stdout
    if args.json:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")

    try:
        while True:
            for attempt in range(1, args.retries + 1):
                res = run_once(api, headed=headed, wait=not args.no_wait,
                               dry_run=args.dry_run, cookies=cookie_file,
                               quiet=args.json)
                last = res
                if res.get("status") in ("claimed", "clicked", "cooldown",
                                         "dry_run"):
                    break
                if attempt < args.retries:
                    print(f"\n  percobaan {attempt} gagal - ulang 20s")
                    time.sleep(20)

            if not args.loop:
                break

            b = api.bootstrap()
            f = (b.get("farm") or {}).get("faucet") or {}
            nxt = f.get("next_claim_at") or 0
            if nxt:
                countdown(api, int(nxt))
            else:
                time.sleep(60)
    finally:
        if args.json:
            sys.stdout.close()
            sys.stdout = real_out

    if args.json:
        print(json.dumps(last, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  dihentikan")
        sys.exit(0)
