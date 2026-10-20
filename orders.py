#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""orders.py - lihat dan kerjakan farm order tanpa loop.

  python orders.py                  # daftar order aktif + kebutuhan
  python orders.py --preview 2      # rincian produce yang akan dipakai
  python orders.py --fulfill        # kirim semua order yang siap
  python orders.py --reroll 3       # reroll slot 3 (kuota harian terbatas)
  python orders.py --account SawitDES
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import CryptoCrops, ApiError
import ui


def line(api: CryptoCrops, o: dict, size: int = 0) -> str:
    """Satu baris order. Kalau kepanjangan, ikon lalu sisa waktu dibuang
    lebih dulu supaya tidak dipotong paksa."""
    reqs = []
    for r in o.get("requirements") or []:
        have, need = r.get("available_quantity"), r.get("quantity")
        mark = ui.color(str(have), ui.GREEN if have >= need else ui.RED)
        reqs.append(f"{r.get('seed_id')} {mark}/{need}")
    req_txt = " · ".join(reqs) or "-"
    exp = int(o.get("expires_at") or 0)
    left = max(0, (exp - api.now_ms()) // 60000) if exp else 0

    reward = f"+{o.get('base_coin_reward')} coin"
    reward = ui.color(reward.ljust(9), ui.YELLOW)
    state = ui.color("SIAP".ljust(7), ui.GREEN) if o.get("ready") \
        else ui.color("kurang".ljust(7), ui.GRAY)
    slot = f"#{o.get('slot_index'):<2}"
    icon = str(o.get("icon") or "")
    title = str(o.get("title") or "")[:18]

    def build(with_icon: bool, with_time: bool) -> str:
        head = f"  {slot} {icon + ' ' if with_icon else ''}{title:<18} {reward} {state}"
        tail = f" {req_txt}"
        if with_time:
            tail += f"  ({left}m)"
        return head + tail

    text = build(True, True)
    if size and ui.visible_len(text) > size:
        text = build(False, True)
    if size and ui.visible_len(text) > size:
        text = build(False, False)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account")
    ap.add_argument("--preview", type=int, help="slot index")
    ap.add_argument("--fulfill", action="store_true")
    ap.add_argument("--reroll", type=int, help="slot index")
    args = ap.parse_args()

    api = CryptoCrops(account=args.account)
    try:
        api.bootstrap()
    except ApiError as exc:
        print(f"gagal bootstrap: {exc}")
        return 2

    orders = api.orders()
    rerolls = (api.farm.get("order_rerolls") or {})
    ui.show_banner("Orders", f"{api.account or 'default'} · coin "
                              f"{(api.farm.get('profile') or {}).get('farm_coins')} · "
                              f"reroll sisa {rerolls.get('remaining')}/"
                              f"{rerolls.get('daily_limit')}")
    for o in orders:
        if o.get("status") == "active":
            print(line(api, o, ui.width() - 1))

    if args.preview:
        target = next((o for o in orders
                       if o.get("slot_index") == args.preview), None)
        if not target:
            print(f"  slot {args.preview} tidak ada")
            return 2
        try:
            p = (api.order_preview(target["order_id"]) or {}).get("preview", {})
        except ApiError as exc:
            print(f"  preview gagal: {exc}")
            return 1
        print(ui.color("─" * max(20, ui.width() - 1), ui.GRAY))
        for key in ("total_coins", "farm_xp_earned", "harvest_pass_xp_reward",
                    "fresh_points_surrendered", "fertilizer_rarity",
                    "fertilizer_quantity"):
            if key in p:
                print(f"  {key:<26} {p[key]}")

    if args.fulfill:
        sent = 0
        for o in api.orders():
            if o.get("status") != "active" or not o.get("ready"):
                continue
            try:
                r = (api.fulfill_order(o["order_id"]) or {}).get("fulfilled", {})
                print(f"  ✓ {o.get('title')} · +{r.get('total_coins')} coin"
                      f" · +{r.get('farm_xp_earned')} xp")
                sent += 1
            except ApiError as exc:
                print(f"  × {o.get('title')}: {exc}")
        if not sent:
            print("  tidak ada order yang siap")

    if args.reroll:
        target = next((o for o in orders
                       if o.get("slot_index") == args.reroll), None)
        if not target:
            print(f"  slot {args.reroll} tidak ada")
            return 2
        try:
            r = (api.reroll_order(target["order_id"]) or {}).get("rerolled", {})
            print(f"  ✓ reroll slot {args.reroll} · sisa {r.get('rerolls_remaining')}")
        except ApiError as exc:
            print(f"  × reroll gagal: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
