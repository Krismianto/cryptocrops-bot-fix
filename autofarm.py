#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
autofarm.py - runner lengkap: checkpoint -> faucet -> orders -> farm.

Tampilan: dashboard satu frame (banner figlet + status + log terakhir).
Status FAUCET dan FARM dipisah baris, jadi countdown faucet tidak lagi
nyampur dengan log panen/jual/tanam.

Pemakaian:
  python autofarm.py --headless                 # akun aktif, loop
  python autofarm.py --once                     # satu putaran
  python autofarm.py --all-accounts --headless  # semua akun bergiliran
  python autofarm.py --no-faucet --no-orders
  python autofarm.py --plain                    # log polos, tanpa dashboard

Faucet dijalankan lewat faucet_run.py (subprocess) supaya otomatis pindah
ke interpreter yang punya browser Camoufox lengkap.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import CryptoCrops, ApiError
from checkpoint import Ocr, solve_once
import ui

MAX_FAILS = 5
HERE = os.path.dirname(os.path.abspath(__file__))


def clock(ms: int) -> str:
    return time.strftime("%H:%M", time.localtime(ms / 1000))


def fmt_left(ms: int) -> str:
    sec = max(0, int(ms / 1000))
    return f"{sec // 60:02d}:{sec % 60:02d}"


# ------------------------------------------------------------------ faucet ---
def faucet_via_cli(headless: bool, timeout: int = 420,
                   account: str | None = None) -> dict:
    cmd = [sys.executable, os.path.join(HERE, "faucet_run.py"),
           "--json", "--no-wait"]
    if headless:
        cmd.append("--headless")
    if account:
        cmd += ["--account", account]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    for raw in reversed((p.stdout or "").strip().splitlines()):
        raw = raw.strip()
        if raw.startswith("{"):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                continue
    return {"status": "error", "detail": (p.stderr or "")[-300:]}


def faucet_summary(res: dict) -> str:
    st = res.get("status")
    if st == "claimed":
        return (f"klaim berhasil · +{res.get('total_coins')} coin"
                f" · +{res.get('farm_xp_earned')} xp"
                f" · saldo {res.get('farm_coin_balance')}")
    if st == "cooldown":
        return "server masih cooldown"
    if st in ("not_ready", "page_error"):
        return f"widget gagal ({st})"
    if st == "timeout":
        return "timeout membuka browser"
    if st == "clicked":
        return "tombol terklik, response tidak tertangkap"
    if res.get("error"):
        return f"ditolak server: {res.get('error')}"
    return st or "tidak ada response"


# ------------------------------------------------------------------ status ---
def faucet_text(api: CryptoCrops) -> str:
    f = api.farm.get("faucet") or {}
    if f.get("available"):
        return ui.color("siap diklaim", ui.GREEN)
    nxt = int(f.get("next_claim_at") or 0)
    if not nxt:
        return ui.color("tidak aktif", ui.GRAY)
    left = fmt_left(nxt - api.now_ms())
    return f"cooldown {ui.color(left, ui.YELLOW)} · berikutnya {clock(nxt)}"


def farm_text(api: CryptoCrops) -> str:
    crops = api.farm.get("crops") or []
    ready = sum(1 for c in crops
                if int(c.get("ready_at") or 0) <= api.now_ms())
    orders = [o for o in (api.farm.get("orders") or [])
              if o.get("status") == "active"]
    order_ready = sum(1 for o in orders if o.get("ready"))
    return (f"plot {len(crops)}/{api.capacity()}"
            f" · siap panen {ready}"
            f" · order siap {order_ready}/{len(orders)}")


def stats_text(api: CryptoCrops, label: str = "") -> str:
    p = api.farm.get("profile") or {}
    pr = api.farm.get("farm_progression") or {}
    f = api.farm.get("faucet") or {}
    who = label or api.account or "?"
    return (f"  {ui.color(who, ui.BOLD)}"
            f" · coin {p.get('farm_coins')}"
            f" · xp {pr.get('xp')} (lvl {pr.get('level')})"
            f" · klaim {f.get('claim_count')}")


# ------------------------------------------------------------------- cycle ---
def run_cycle(api: CryptoCrops, ocr: Ocr, args, dash: ui.Dashboard,
              label: str = "") -> int:
    errors = 0
    api.bootstrap()
    dash.set_stats(stats_text(api, label))
    dash.set("faucet", faucet_text(api))
    dash.set("farm", farm_text(api))
    dash.render()
    if not dash.enabled:
        print(f"[{time.strftime('%H:%M:%S')}] "
              f"{stats_text(api, label).strip()} | "
              f"{farm_text(api)} | faucet {faucet_text(api)}", flush=True)

    # 1) checkpoint
    if not args.no_checkpoint and api.checkpoint_due():
        dash.log("checkpoint due · menyelesaikan OCR…", "info")
        res = solve_once(api, ocr, dump=True)
        if res.get("status") == "error":
            dash.log(f"checkpoint gagal: {res.get('detail')}", "err")
            return 1
        dash.log(f"checkpoint lolos · {res.get('answer') or 'ok'}", "ok")
        api.bootstrap()

    # 2) faucet
    if not args.no_faucet:
        f = api.farm.get("faucet") or {}
        if f.get("available"):
            dash.log("faucet · membuka browser…", "info")
            fres = faucet_via_cli(args.headless, account=label or None)
            kind = "ok" if fres.get("status") == "claimed" else "warn"
            dash.log("faucet · " + faucet_summary(fres), kind)
            if fres.get("status") not in ("claimed", "cooldown"):
                errors += 1
            if fres.get("status") == "claimed":
                api.bootstrap()
                dash.set_stats(stats_text(api, label))

    # 3) orders + farm
    t = api.tick(seeds=args.seeds, dry_run=args.dry_run,
                 do_orders=not args.no_orders)

    events: list[str] = []
    for o in t.orders:
        if o.get("dry"):
            events.append(f"order (dry) {o.get('title')} +{o.get('coins')} coin")
        else:
            extra = (f" +{o.get('farm_xp_earned')} xp"
                     if o.get("farm_xp_earned") else "")
            fert = (f" +{o.get('fertilizer_rarity')}"
                    if o.get("fertilizer_rarity") else "")
            events.append(f"order {o.get('title')} "
                          f"+{o.get('total_coins')} coin{extra}{fert}")

    parts = []
    if t.harvested:
        parts.append(f"panen {len(t.harvested)}")
    if t.sold:
        parts.append(f"jual {len(t.sold)}")
    if t.planted:
        parts.append(f"tanam {len(t.planted)}")
    if parts:
        events.append(" · ".join(parts))

    if events:
        dash.log(" · ".join(events), "ok")

    for e in t.errors[:2]:
        dash.log(f"! {e}", "err")
    errors += len(t.errors)

    dash.set_stats(stats_text(api, label))
    dash.set("faucet", faucet_text(api))
    dash.set("farm", farm_text(api))
    dash.render()
    return errors


# -------------------------------------------------------------------- wait ---
def wait_loop(api: CryptoCrops, dash: ui.Dashboard, seconds: float) -> None:
    """Tunggu sambil menghidupkan countdown faucet di barisnya sendiri."""
    end = time.time() + max(0.0, seconds)
    last = ""
    last_print = 0.0
    while True:
        left = end - time.time()
        if left <= 0:
            break
        text = faucet_text(api)
        if text != last:
            dash.set("faucet", text)
            dash.render()
            last = text
        if not dash.enabled and time.time() - last_print >= 60:
            last_print = time.time()
            print(f"  {time.strftime('%H:%M:%S')}  {text}", flush=True)
        time.sleep(min(1.0, max(0.05, left)))


def next_event_wait(api: CryptoCrops, cap: float) -> float:
    now = api.now_ms()
    waits = [cap]
    for c in api.farm.get("crops") or []:
        d = int(c.get("ready_at") or 0) - now
        if 0 < d < cap * 1000:
            waits.append(d / 1000 + 2)
    f = api.farm.get("faucet") or {}
    if f.get("available"):
        waits.append(90)
    else:
        d = int(f.get("next_claim_at") or 0) - now
        if 0 < d < cap * 1000:
            waits.append(d / 1000 + 2)
    return max(5.0, min(waits))


# -------------------------------------------------------------------- main ---
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=120)
    ap.add_argument("--no-faucet", action="store_true")
    ap.add_argument("--no-checkpoint", action="store_true")
    ap.add_argument("--no-orders", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--plain", action="store_true", help="log polos tanpa dashboard")
    ap.add_argument("--log-history", type=int, default=1,
                    help="jumlah baris aktivitas di dashboard (default 1)")
    ap.add_argument("--align", choices=("center", "left"), default="center",
                    help="perataan header & isi (default center)")
    ap.add_argument("--seeds", nargs="*", help="batasi seed yang ditanam")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--account", help="nama akun dari accounts.json")
    ap.add_argument("--all-accounts", action="store_true")
    args = ap.parse_args()

    import accounts

    if args.all_accounts:
        targets: list[str | None] = list(accounts.names())
        if not targets:
            print("belum ada akun - jalankan: python login.py")
            return 2
    elif args.account:
        key = accounts.key_of(args.account)
        if not key:
            print(f"akun {args.account!r} tidak ada di accounts.json")
            return 2
        targets = [key]
    else:
        targets = [None]

    clients: dict[str | None, CryptoCrops] = {
        name: CryptoCrops(account=name) for name in targets}

    label = ", ".join(t or (clients[t].account or "?") for t in targets)
    dash = ui.Dashboard(
        "CryptoCrops",
        f"autofarm · {label}"
        f"{' · dry-run' if args.dry_run else ''}"
        f"{' · tanpa faucet' if args.no_faucet else ''}",
        maxlog=max(0, args.log_history),
        align=args.align,
        enabled=(not args.plain) and sys.stdout.isatty())

    ocr = Ocr()
    ui.clear()
    dash.render()

    fails = 0
    while True:
        for name in targets:
            who = name or (clients[name].account or "")
            try:
                errors = run_cycle(clients[name], ocr, args, dash, who)
                fails = 0 if errors == 0 else fails + 1
            except ApiError as exc:
                dash.log(f"[{who or 'default'}] API error: {exc}", "err")
                if exc.status == 401:
                    dash.log(f"[{who or 'default'}] cookie mati - "
                             "python login.py --use <nama>", "err")
                    if len(targets) == 1:
                        return 2
                fails += 1
            except KeyboardInterrupt:
                return 0
            except Exception as exc:  # noqa: BLE001
                dash.log(f"[{who or 'default'}] {exc}", "err")
                fails += 1

        if fails >= MAX_FAILS:
            dash.log("terlalu banyak kegagalan - stop", "err")
            return 1
        if args.once:
            dash.log("selesai (--once)", "info")
            return 0 if fails == 0 else 1

        cap = args.interval + random.randint(0, 20)
        waits = []
        for name in targets:
            try:
                waits.append(next_event_wait(clients[name], cap))
            except Exception:  # noqa: BLE001
                pass
        wait_loop(clients[targets[0]], dash,
                  min(waits) if waits else cap)


if __name__ == "__main__":
    sys.exit(main())
