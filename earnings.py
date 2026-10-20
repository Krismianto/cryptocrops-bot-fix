#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
earnings.py - kalkulator: butuh berapa akun untuk mencapai target USD.

Angka diambil dari server (bootstrap + catalog), bukan tebakan:
  * pts/jam per plot     -> seed terbaik yang benar-benar bisa dipakai akun
  * nilai per poin (HC)  -> estimatedHarvestCredits / total_points
  * HC per USD           -> pool.creditsPerUsd (sekarang 10.000)
  * ukuran pool          -> pool.harvestCredits tiap siklus 6 jam

"Seed yang bisa dipakai" = sudah ada di inventory, atau bisa dibeli dengan
saldo coin sekarang. Seed event (harga null, tidak di-drop) diabaikan supaya
angkanya tidak fantastis.

Pemakaian:
    python earnings.py                     # target $10/hari
    python earnings.py --target 50 --unit week
    python earnings.py --uptime 1 --hours 24
    python earnings.py --seed green-peas --coins 5000
    python earnings.py --once --fleet 10
    python earnings.py --json

Pool dibagi ke semua pemain: makin banyak poin kamu, nilai per poin turun.
Skrip ini menghitung dua angka - linear (optimis) dan setelah dilusi (realistis).
"""

from __future__ import annotations

import argparse
import json
import math
import sys

from client import ApiError, CryptoCrops


def hc(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def usd(x: float) -> str:
    if abs(x) >= 1:
        return "$" + f"{x:,.2f}".replace(",", ".")
    return f"${x:.4f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="estimasi pendapatan CryptoCrops")
    ap.add_argument("--target", type=float, default=10.0, help="target USD")
    ap.add_argument("--unit", choices=("day", "week", "once"), default="day",
                    help="target per hari / per minggu / sekali")
    ap.add_argument("--uptime", type=float, default=0.85,
                    help="fraksi waktu bot benar-benar jalan (0-1)")
    ap.add_argument("--hours", type=float, default=24.0,
                    help="jam operasi per hari")
    ap.add_argument("--plots", type=int, default=0, help="override jumlah plot")
    ap.add_argument("--seed", help="paksa seed tertentu (default: terbaik yang bisa dipakai)")
    ap.add_argument("--coins", type=float, help="override saldo coin (simulasi)")
    ap.add_argument("--fleet", type=int, default=10,
                    help="ukuran armada untuk mode --once (default 10)")
    ap.add_argument("--account", help="nama akun dari accounts.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    api = CryptoCrops(account=args.account)
    try:
        api.bootstrap()
    except ApiError as exc:
        print(f"gagal ambil data: {exc}", file=sys.stderr)
        return 2

    farm = api.farm
    pool = api.state.get("pool") or {}
    prog = farm.get("pool_progress") or {}
    profile = farm.get("profile") or {}

    catalog = (api.catalog().get("seeds") or [])
    info = {s.get("seed_id"): s for s in catalog}
    rates: dict[str, float] = {}
    for s in catalog:
        grow = float(s.get("grow_seconds") or 0)
        pts = float(s.get("base_points") or 0)
        if grow > 0:
            rates[s.get("seed_id")] = pts / (grow / 3600)

    own = api.seeds()
    coins = float(profile.get("farm_coins") or 0) if args.coins is None else args.coins
    usable: dict[str, float] = {}
    for sid, rate in rates.items():
        meta = info.get(sid) or {}
        price = meta.get("coin_price")
        if sid in own or (price is not None and float(price) <= coins):
            usable[sid] = rate

    if args.seed:
        seed = args.seed if args.seed in rates else None
        if seed and seed not in usable:
            print(f"! seed {seed} belum dimiliki / harga > saldo coin", file=sys.stderr)
    else:
        seed = max(usable, key=usable.get) if usable else (
            max(rates, key=rates.get) if rates else None)
    pph = rates.get(seed, 0.0)

    plots = args.plots or api.capacity() or int(profile.get("total_capacity") or 4)
    pool_hc = float(pool.get("harvestCredits") or 0)
    per_usd = float(pool.get("creditsPerUsd") or 10000) or 10000
    start = int(pool.get("startsAt") or 0)
    end = int(pool.get("endsAt") or 0)
    cycle_h = ((end - start) / 3_600_000) if end > start else 6.0

    total_points = float(prog.get("total_points") or 0)
    est_hc = float(pool.get("estimatedHarvestCredits") or 0)
    vpp = (est_hc / total_points) if (est_hc > 0 and total_points > 0) else 0.32
    pool_points = (pool_hc / vpp) if vpp > 0 else 0.0

    uptime = max(0.05, min(1.0, args.uptime))
    active_h = max(0.5, min(24.0, args.hours)) * uptime

    pts_h = pph * plots
    pts_day = pts_h * active_h
    hc_day = pts_day * vpp
    usd_day = hc_day / per_usd
    per_cycle_usd = pts_h * cycle_h * uptime * vpp / per_usd
    pool_usd_cycle = pool_hc / per_usd

    daily_target = {"day": args.target,
                    "week": args.target / 7,
                    "once": 0.0}[args.unit]
    target_cycle = daily_target * (cycle_h / max(active_h, 0.5))
    n_naive = math.ceil(daily_target / usd_day) if (usd_day > 0 and daily_target) else 0
    n_real = 0
    if target_cycle > 0 and pool_points > 0 and pts_h > 0:
        p_cycle = pts_h * cycle_h * uptime
        room = pool_usd_cycle - target_cycle
        n_real = math.ceil(target_cycle * pool_points / (p_cycle * room)) if room > 0 else -1

    if args.json:
        print(json.dumps({
            "account": api.account, "seed": seed,
            "points_per_hour_plot": round(pph, 2), "plots": plots,
            "points_per_hour_account": round(pts_h, 1),
            "points_per_day_account": round(pts_day, 1),
            "hc_per_day_account": round(hc_day, 2),
            "usd_per_day_account": round(usd_day, 4),
            "value_per_point_hc": round(vpp, 4),
            "pool_usd_cycle": round(pool_usd_cycle, 2),
            "cycle_hours": cycle_h,
            "accounts_linear": n_naive,
            "accounts_with_dilution": n_real,
        }, indent=2))
        return 0

    print(f"akun        : {api.account or 'default'} · {plots} plot · coin {hc(coins)}")
    print(f"seed        : {seed} ({pph:.0f} pts/jam/plot, "
          f"{'inventory' if seed in own else 'beli'}) · "
          f"{pts_h:.0f} pts/jam/akun")
    print(f"operasional : {active_h:.1f} jam/hari (uptime {uptime * 100:.0f}%)")
    print(f"nilai poin  : {vpp:.3f} HC/poin · pool {hc(pool_hc)} HC / "
          f"{cycle_h:.0f} jam = {usd(pool_usd_cycle)} · {hc(per_usd)} HC = $1")
    print()
    print(f"per akun    : {pts_day:,.0f} pts/hari -> {hc(hc_day)} HC -> {usd(usd_day)}/hari"
          .replace(",", "."))
    print(f"per siklus  : {usd(per_cycle_usd)} tiap {cycle_h:.0f} jam")
    print(f"per minggu  : {usd(usd_day * 7)} · per bulan {usd(usd_day * 30)}")
    print()

    if args.unit == "once":
        print(f"target {usd(args.target)} sekali")
        if usd_day > 0:
            print(f"  butuh {args.target / usd_day:.0f} akun-hari "
                  f"(1 akun x {args.target / usd_day:.0f} hari)")
            for n in (5, 10, 20, 50, args.fleet):
                if n > 0:
                    print(f"    {n:>2} akun -> {args.target / (usd_day * n):.1f} hari")
        return 0

    label = "per hari" if args.unit == "day" else "per minggu"
    print(f"target {usd(args.target)} {label}")
    if n_real == -1:
        print("  ! target melebihi seluruh pool - tidak mungkin dicapai")
    else:
        print(f"  linear    : {n_naive} akun (dilusi diabaikan)")
        print(f"  realistis : {n_real} akun (poin kamu ikut masuk pool)")
        print(f"              total {n_real * pts_h * cycle_h*uptime:,.0f} pts/siklus"
              .replace(",", "."))
    print()
    print("asumsi: bot jalan terus, seed murah/gratis tersedia, faucet + misi")
    print("        tetap diklaim supaya saldo coin cukup untuk beli seed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
