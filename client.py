#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
cryptocrops_client.py — klien API CryptoCrops
Dibangun dari bedah HAR 2026-10-20 (capture #1 baca, #2 write-path).

Auth: sesi cookie (HttpOnly). Ambil dari DevTools:
  Application -> Cookies -> https://cryptocrops.net -> salin semua "name=value"
  ke env CRYPTOCROPS_COOKIE, atau taruh cookies.txt (format simpel) di folder ini.

Kontrak yang terbukti (lihat analysis-2-write-paths.md):
  POST /api/farm/plant    {idempotency_key, seed_id, plot_index}   -> 201
  POST /api/farm/harvest  {idempotency_key, crop_id}               -> 200
  GET  /api/farm/sell-preview?seed_id=&quantity=                   -> 200
  POST /api/farm/sell     {idempotency_key, seed_id, quantity}     -> 200

Contoh:
  python client.py status
  python client.py catalog --top 20
  python client.py harvest --all
  python client.py sell --seed radish
  python client.py plant --seed radish --plot 1
  python client.py loop --seeds radish,lettuce --interval 30
  python client.py report
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import requests

BASE = "https://cryptocrops.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")

# fallback kalau /api/catalog tidak dipanggil; nilai dari bootstrap capture
SEED_CADENCE = {
    "radish":  (300, 12),
    "lettuce": (600, 24),
    "carrot":  (1800, 66),
    "wheat":   (3600, 120),
}


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: str):
        super().__init__(f"{method} {path} -> {status}: {body[:300]}")
        self.status = status
        self.body = body


def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return [v]
    return []


def _load_cookie(account: str | None = None) -> str:
    name = (account or "").strip()
    if not name:
        env = os.environ.get("CRYPTOCROPS_COOKIE", "").strip()
        if env:
            return env
        name = os.environ.get("CC_ACCOUNT", "").strip()
    if name:
        try:
            from accounts import cookie_header, get
            if get(name):
                header = cookie_header(name)
                if header:
                    return header
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            from accounts import active_name, cookie_header
            active = active_name()
            if active:
                header = cookie_header(active)
                if header:
                    return header
        except Exception:  # noqa: BLE001
            pass
    f = Path(__file__).with_name("cookies.txt")
    if f.exists():
        try:
            from cookiefile import load_first
            first = load_first(str(f))
            pairs = {k: v for k, v in (first.get("extra") or {}).items()
                     if k.startswith("cc_") and v}
            if first.get("session"):
                pairs["cc_session_v1"] = first["session"]
            if pairs:
                return "; ".join(f"{k}={v}" for k, v in pairs.items())
        except Exception:  # noqa: BLE001
            pass
    return ""


@dataclass
class Crop:
    crop_id: str
    plot: int
    seed: str
    planted_at: int
    ready_at: int
    perfect_until: int
    pre_fresh_points: int

    @classmethod
    def from_json(cls, c: dict) -> "Crop":
        return cls(
            crop_id=c["crop_id"],
            plot=int(c["plot_index"]),
            seed=c["seed_id"],
            planted_at=int(c.get("planted_at") or 0),
            ready_at=int(c.get("ready_at") or 0),
            perfect_until=int(c.get("perfect_until") or 0),
            pre_fresh_points=int(c.get("pre_fresh_points") or 0),
        )


@dataclass
class Batch:
    seed: str
    quantity: int
    points: int
    earliest_fresh_until: int


@dataclass
class TickResult:
    harvested: list[dict] = field(default_factory=list)
    sold: list[dict] = field(default_factory=list)
    planted: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    missions: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class CryptoCrops:
    def __init__(self, cookie: str | None = None, timeout: float = 20.0,
                 account: str | None = None):
        self.s = requests.Session()
        self.s.headers.update({
            "user-agent": UA,
            "accept": "*/*",
            "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "origin": BASE,
            "referer": f"{BASE}/farm/",
        })
        self.account = account or os.environ.get("CC_ACCOUNT") or None
        if not self.account:
            try:
                from accounts import active_name
                self.account = active_name()
            except Exception:  # noqa: BLE001
                pass
        c = cookie if cookie is not None else _load_cookie(self.account)
        if c:
            self.s.headers["cookie"] = c
        self.timeout = timeout
        self.state: dict[str, Any] = {}
        self.server_offset = 0
        self._catalog: dict[str, dict] | None = None

    # ---------------- transport ----------------

    def _req(self, method: str, path: str, body: dict | None = None,
             allow: Iterable[int] = (200, 201), retries: int = 3) -> Any:
        url = path if path.startswith("http") else BASE + path
        last: Exception | None = None
        for attempt in range(retries):
            try:
                r = self.s.request(method, url, json=body, timeout=self.timeout)
            except requests.RequestException as exc:
                last = exc
                time.sleep(1.5 * (attempt + 1) + random.uniform(0, 1))
                continue
            if r.status_code in allow:
                if not r.content:
                    return None
                try:
                    return r.json()
                except ValueError:
                    return r.text
            body_txt = r.text[:800]
            if r.status_code in (429, 502, 503, 504):
                last = ApiError(method, path, r.status_code, body_txt)
                time.sleep(3.0 * (attempt + 1) + random.uniform(0, 2))
                continue
            raise ApiError(method, path, r.status_code, body_txt)
        raise last if last else RuntimeError("request failed")

    # ---------------- read ----------------

    def bootstrap(self) -> dict:
        st = self._req("GET", "/api/bootstrap")
        self.state = st
        now = (st.get("farm") or {}).get("server_now")
        if now:
            self.server_offset = int(now) - int(time.time() * 1000)
        return st

    def catalog(self) -> dict:
        data = self._req("GET", "/api/catalog?version=6")
        seeds = _as_list(data.get("seeds"))
        self._catalog = {s["seed_id"]: s for s in seeds if "seed_id" in s}
        return data

    def account(self) -> dict:
        return self._req("GET", "/api/auth/account")

    def pools(self) -> dict:
        return self._req("GET", "/api/pools")

    def guilds(self) -> dict:
        return self._req("GET", "/api/guilds")

    def referrals(self) -> dict:
        return self._req("GET", "/api/referrals")

    def withdrawals(self) -> dict:
        return self._req("GET", "/api/withdrawals")

    def sell_preview(self, seed_id: str, quantity: int) -> dict:
        q = f"/api/farm/sell-preview?seed_id={seed_id}&quantity={int(quantity)}"
        return self._req("GET", q)

    # ---------------- derived ----------------

    @property
    def farm(self) -> dict:
        return self.state.get("farm") or {}

    def now_ms(self) -> int:
        return int(time.time() * 1000) + self.server_offset

    def crops(self) -> list[Crop]:
        return [Crop.from_json(c) for c in _as_list(self.farm.get("crops"))]

    def seeds(self) -> dict[str, dict]:
        return {s["seed_id"]: s for s in _as_list(self.farm.get("seeds"))
                if "seed_id" in s}

    def inventory(self) -> dict[str, dict]:
        return {i["seed_id"]: i for i in _as_list(self.farm.get("inventory"))
                if "seed_id" in i}

    def capacity(self) -> int:
        return int((self.farm.get("profile") or {}).get("total_capacity") or 0)

    def free_plots(self) -> list[int]:
        used = {c.plot for c in self.crops()}
        return [i for i in range(1, self.capacity() + 1) if i not in used]

    def matured(self, include_late: bool = True) -> list[Crop]:
        n = self.now_ms()
        out = [c for c in self.crops() if c.ready_at <= n]
        if not include_late:
            out = [c for c in out if c.perfect_until >= n]
        return sorted(out, key=lambda c: c.ready_at)

    def checkpoint(self) -> dict:
        return self.farm.get("farm_checkpoint") or {}

    def checkpoint_due(self) -> bool:
        cp = self.checkpoint()
        if cp.get("required"):
            return True
        nxt = int(cp.get("next_challenge_at") or 0)
        return bool(nxt) and self.now_ms() >= nxt

    def points_per_hour(self, seed_id: str) -> float:
        if self._catalog and seed_id in self._catalog:
            s = self._catalog[seed_id]
            grow = float(s.get("grow_seconds") or 0)
            pts = float(s.get("base_points") or 0)
        else:
            grow, pts = SEED_CADENCE.get(seed_id, (0, 0))
        return (pts / (grow / 3600.0)) if grow else 0.0

    # ---------------- write ----------------

    def plant(self, seed_id: str, plot_index: int) -> dict:
        body = {"idempotency_key": str(uuid.uuid4()),
                "seed_id": seed_id, "plot_index": int(plot_index)}
        return self._req("POST", "/api/farm/plant", body)

    def harvest(self, crop: str | Crop) -> dict:
        crop_id = crop.crop_id if isinstance(crop, Crop) else crop
        body = {"idempotency_key": str(uuid.uuid4()), "crop_id": crop_id}
        return self._req("POST", "/api/farm/harvest", body)

    def sell(self, seed_id: str, quantity: int) -> dict:
        body = {"idempotency_key": str(uuid.uuid4()),
                "seed_id": seed_id, "quantity": int(quantity)}
        return self._req("POST", "/api/farm/sell", body)

    # ---------------- orders ----------------

    def orders(self) -> list[dict]:
        if not self.state:
            self.bootstrap()
        return _as_list(self.farm.get("orders"))

    def order_preview(self, order_id: str) -> dict:
        return self._req("GET", f"/api/orders/preview?order_id={order_id}")

    def fulfill_order(self, order_id: str) -> dict:
        body = {"idempotency_key": str(uuid.uuid4()), "order_id": order_id}
        return self._req("POST", "/api/orders/fulfill", body,
                         allow=(200, 201, 400, 409))

    def reroll_order(self, order_id: str) -> dict:
        body = {"idempotency_key": str(uuid.uuid4()), "order_id": order_id}
        return self._req("POST", "/api/orders/reroll", body,
                         allow=(200, 201, 400, 409))

    # ---------------- missions ----------------
    # POST /api/missions/claim {idempotency_key, mission_id} -> 200
    #   {"claimed": {mission_id, period, pass_xp_earned, harvest_pass_xp, ...}}

    def missions(self) -> list[dict]:
        if not self.state:
            self.bootstrap()
        return _as_list(self.farm.get("missions"))

    def missions_ready(self) -> list[dict]:
        """Misi yang sudah `complete` tapi belum `claimed`."""
        return [m for m in self.missions()
                if m.get("complete") and not m.get("claimed")]

    def claim_mission(self, mission_id: str) -> dict:
        body = {"idempotency_key": str(uuid.uuid4()),
                "mission_id": mission_id}
        self.s.headers["referer"] = f"{BASE}/missions/"
        try:
            data = self._req("POST", "/api/missions/claim", body,
                             allow=(200, 201, 400, 403, 409, 422, 429))
        finally:
            # balikkan referer supaya request farm berikutnya tetap sah
            self.s.headers["referer"] = f"{BASE}/farm/"
        return data if isinstance(data, dict) else {"raw": data}

    def faucet_challenge(self) -> dict:
        """POST /api/earn/faucet-challenge {} -> challenge_id + turnstile ticket."""
        data = self._req("POST", "/api/earn/faucet-challenge", {},
                         allow=(200, 201, 400, 409, 429))
        return data if isinstance(data, dict) else {"raw": data}

    def faucet_claim(self, challenge_id: str, token: str, ticket: str) -> dict:
        body = {"idempotency_key": str(uuid.uuid4()),
                "faucet_challenge": challenge_id,
                "captcha_token": token,
                "captcha_ticket": ticket}
        self.s.headers["referer"] = f"{BASE}/faucet/"
        data = self._req("POST", "/api/earn/faucet", body,
                         allow=(200, 201, 400, 403, 409, 429))
        return data if isinstance(data, dict) else {"raw": data}

    def checkpoint_challenge(self, attempt_id: str | None = None) -> dict:
        """POST /api/farm-checkpoint/challenge {attempt_id} -> number_image + ticket."""
        attempt = attempt_id or str(uuid.uuid4())
        data = self._req("POST", "/api/farm-checkpoint/challenge",
                         {"attempt_id": attempt},
                         allow=(200, 201, 400, 403, 409, 422, 429))
        data = data if isinstance(data, dict) else {"raw": data}
        data.setdefault("_attempt_id", attempt)
        return data

    def checkpoint_verify(self, attempt_id: str, required_since: int,
                          captcha_number: str, captcha_ticket: str) -> dict:
        body = {"attempt_id": attempt_id,
                "required_since": int(required_since),
                "captcha_number": str(captcha_number),
                "captcha_ticket": captcha_ticket}
        self.s.headers["referer"] = f"{BASE}/farm/"
        data = self._req("POST", "/api/farm-checkpoint/verify", body,
                         allow=(200, 201, 400, 403, 409, 422, 429))
        return data if isinstance(data, dict) else {"raw": data}

    # ---------------- automation ----------------

    def tick(self, seeds: list[str] | None = None, *,
             do_harvest: bool = True, do_sell: bool = True,
             do_plant: bool = True, perfect_only: bool = False,
             keep_for_orders: bool = False, dry_run: bool = False,
             do_orders: bool = True, reserve_orders: bool = True,
             do_missions: bool = True) -> TickResult:
        res = TickResult()
        if not self.state:
            self.bootstrap()
        if self.checkpoint_due():
            res.errors.append("farm checkpoint due — perlu interaksi manual")
            return res

        # 1) harvest
        if do_harvest:
            for c in self.matured(include_late=not perfect_only):
                if dry_run:
                    res.harvested.append({"dry": True, "plot": c.plot,
                                          "seed": c.seed, "crop_id": c.crop_id})
                    continue
                try:
                    r = (self.harvest(c) or {}).get("harvested", {})
                    res.harvested.append(r)
                except ApiError as exc:
                    res.errors.append(f"harvest p{c.plot}: {exc}")
                time.sleep(0.4 + random.uniform(0, 0.4))
            if res.harvested and not dry_run:
                self.bootstrap()

        # 2) orders siap kirim (pakai produce di barn)
        if do_orders:
            for o in self.orders():
                if o.get("status") != "active" or not o.get("ready"):
                    continue
                if dry_run:
                    res.orders.append({"dry": True, "title": o.get("title"),
                                       "coins": o.get("base_coin_reward")})
                    continue
                try:
                    r = (self.fulfill_order(o["order_id"]) or {}).get("fulfilled", {})
                    res.orders.append({**r, "title": o.get("title")})
                except ApiError as exc:
                    if "NOT_READY" in str(exc) or "ALREADY" in str(exc):
                        continue
                    res.errors.append(f"order {o.get('title')}: {exc}")
                time.sleep(0.6 + random.uniform(0, 0.4))
            if res.orders and not dry_run:
                self.bootstrap()

        # 3) sell (sisakan produce yang dibutuhkan order aktif)
        needed: dict[str, int] = {}
        if reserve_orders:
            for o in self.orders():
                if o.get("status") != "active":
                    continue
                for req in _as_list(o.get("requirements")):
                    sid = req.get("seed_id")
                    needed[sid] = needed.get(sid, 0) + int(req.get("quantity") or 0)

        if do_sell:
            skip = set()
            if keep_for_orders:
                for o in self.orders():
                    for req in _as_list(o.get("requirements")):
                        skip.add(req.get("seed_id"))
            for seed, inv in self.inventory().items():
                if seed in skip:
                    continue
                qty = int(inv.get("fresh_quantity") or 0)
                reserve = max(0, needed.get(seed, 0)
                              - int(inv.get("pantry_quantity") or 0))
                qty = max(0, qty - reserve)
                if qty <= 0:
                    continue
                if dry_run:
                    res.sold.append({"dry": True, "seed": seed, "quantity": qty,
                                     "points": inv.get("fresh_points")})
                    continue
                try:
                    prev = (self.sell_preview(seed, qty) or {}).get("preview", {})
                    r = (self.sell(seed, qty) or {}).get("sold", {})
                    res.sold.append({**r, "preview_points": prev.get("points")})
                except ApiError as exc:
                    res.errors.append(f"sell {seed}x{qty}: {exc}")
                time.sleep(0.5 + random.uniform(0, 0.5))
            if res.sold and not dry_run:
                self.bootstrap()

        # 4) plant
        if do_plant:
            base = sorted(seeds or list(self.seeds().keys()),
                          key=self.points_per_hour, reverse=True)
            exhausted: set[str] = set()
            for plot in self.free_plots():
                candidates = [s for s in base if s not in exhausted]
                if not candidates:
                    res.errors.append(f"plant p{plot}: tidak ada salinan seed tersisa")
                    continue
                if dry_run:
                    res.planted.append({"dry": True, "plot": plot,
                                        "seed": candidates[0]})
                    continue
                placed = False
                for seed in candidates:
                    try:
                        r = (self.plant(seed, plot) or {}).get("planted", {})
                        res.planted.append(r)
                        placed = True
                        break
                    except ApiError as exc:
                        if "NO_AVAILABLE_SEED_COPY" in str(exc):
                            # salinan seed ini habis -> coba seed berikutnya di plot yang sama
                            exhausted.add(seed)
                            continue
                        res.errors.append(f"plant {seed} p{plot}: {exc}")
                        break
                    finally:
                        time.sleep(0.6 + random.uniform(0, 0.5))
                if not placed and not any(s not in exhausted for s in base):
                    res.errors.append(f"plant p{plot}: semua seed habis salinan")
            if res.planted and not dry_run:
                self.bootstrap()

        # 5) claim misi yang sudah selesai (aksi di atas bisa menuntaskan misi)
        if do_missions:
            if (res.harvested or res.sold or res.orders or res.planted) \
                    and not dry_run:
                self.bootstrap()
            for m in self.missions_ready():
                mid = m.get("mission_id")
                if not mid:
                    continue
                if dry_run:
                    res.missions.append({"dry": True, "mission_id": mid,
                                         "title": m.get("title"),
                                         "pass_xp": m.get("pass_xp")})
                    continue
                try:
                    r = (self.claim_mission(mid) or {}).get("claimed", {})
                    res.missions.append({**r, "title": m.get("title")})
                except ApiError as exc:
                    if "ALREADY" in str(exc) or "CLAIMED" in str(exc):
                        continue
                    res.errors.append(f"mission {m.get('title') or mid}: {exc}")
                time.sleep(0.5 + random.uniform(0, 0.4))
            if res.missions and not dry_run:
                self.bootstrap()
        return res

    def loop(self, seeds: list[str] | None = None, interval: float = 20.0,
             max_ticks: int = 0, dry_run: bool = False,
             perfect_only: bool = False, keep_for_orders: bool = False) -> None:
        tick = 0
        while True:
            tick += 1
            try:
                self.bootstrap()
                p = self.farm.get("profile") or {}
                prog = self.farm.get("progression") or self.farm.get("farm_progression") or {}
                pool = self.farm.get("pool_progress") or {}
                print(f"[{time.strftime('%H:%M:%S')}] tick {tick} "
                      f"lvl={p.get('farm_level')} xp={prog.get('xp')} "
                      f"coin={p.get('farm_coins')} "
                      f"plots={len(self.crops())}/{self.capacity()} "
                      f"ready={len(self.matured())} "
                      f"pts={pool.get('total_points')}")
                if self.checkpoint_due():
                    print("  !! farm checkpoint due — berhenti, selesaikan di browser")
                    return
                r = self.tick(seeds, dry_run=dry_run, perfect_only=perfect_only,
                              keep_for_orders=keep_for_orders)
                for h in r.harvested:
                    print(f"  harvest p{h.get('plot_index', h.get('plot'))} "
                          f"{h.get('seed_id', h.get('seed'))} "
                          f"+{h.get('point_value', '?')}pts fresh={h.get('freshness_bps')}bps")
                for s in r.sold:
                    print(f"  sell {s.get('seed_id', s.get('seed'))}x{s.get('quantity')} "
                          f"+{s.get('points')}pts pool={s.get('pool_total_points')}")
                for pl in r.planted:
                    print(f"  plant p{pl.get('plot_index', pl.get('plot'))} "
                          f"{pl.get('seed_id', pl.get('seed'))}")
                for e in r.errors:
                    print(f"  err: {e}")
                if max_ticks and tick >= max_ticks:
                    return
            except KeyboardInterrupt:
                return
            except Exception as exc:  # noqa: BLE001
                print(f"  fatal: {exc}")
            time.sleep(interval + random.uniform(0, 3))


# ---------------- CLI ----------------

def _fmt_ts(ms: int) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ms / 1000)) if ms else "-"


def _dur(ms: int) -> str:
    if ms <= 0:
        return "0s"
    s = ms // 1000
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def cmd_status(api: CryptoCrops) -> None:
    st = api.bootstrap()
    a = st.get("auth") or {}
    f = st.get("farm") or {}
    p = f.get("profile") or {}
    prog = f.get("farm_progression") or {}
    pool = st.get("pool") or {}
    pp = f.get("pool_progress") or {}
    n = api.now_ms()

    print(f"user      : {a.get('display_name')} ({a.get('role')}) mode={st.get('mode')}")
    print(f"level/xp  : {p.get('farm_level')} / {prog.get('xp')} "
          f"(next {prog.get('next_level_xp')})")
    print(f"coins     : {p.get('farm_coins')}")
    print(f"capacity  : {p.get('total_capacity')} "
          f"(base {p.get('base_capacity')} + premium {p.get('premium_capacity')})")
    if pool:
        print(f"pool      : #{pool.get('cycleId')} {_fmt_ts(pool.get('startsAt'))}–"
              f"{_fmt_ts(pool.get('endsAt'))} {pool.get('harvestCredits')} HC "
              f"weather={(pool.get('weather') or {}).get('name')}")
    print(f"points    : {pp.get('total_points')} (sales {pp.get('sales_count')})")
    print(f"divisi    : {(f.get('league') or {}).get('division')}")
    cp = api.checkpoint()
    print(f"checkpoint: required={cp.get('required')} "
          f"next={_fmt_ts(int(cp.get('next_challenge_at') or 0))}")
    print(f"seeds     : " + ", ".join(
        f"{k}={v.get('quantity')}/L{v.get('level')}" for k, v in api.seeds().items()))
    inv = api.inventory()
    if inv:
        print("inventory : " + ", ".join(
            f"{k} x{v.get('fresh_quantity')} ({v.get('fresh_points')}pts)" for k, v in inv.items()))
    print("plots:")
    for c in sorted(api.crops(), key=lambda x: x.plot):
        left = c.ready_at - n
        state = "READY" if left <= 0 else _dur(left)
        pw = "in-window" if c.ready_at <= n <= c.perfect_until else ""
        print(f"  p{c.plot:>2} {c.seed:<12} {state:>8}  {pw}")
    free = api.free_plots()
    if free:
        print(f"free      : {free}")


def cmd_catalog(api: CryptoCrops, top: int) -> None:
    seeds = _as_list(api.catalog().get("seeds"))
    rows = []
    for s in seeds:
        grow = float(s.get("grow_seconds") or 0)
        pts = float(s.get("base_points") or 0)
        pph = (pts / (grow / 3600)) if grow else 0
        rows.append((pph, s.get("seed_id"), s.get("rarity"), grow / 3600, pts,
                     s.get("coin_price")))
    rows.sort(reverse=True)
    print(f"{'seed':<22}{'rarity':<12}{'grow_h':>7}{'pts':>7}{'pts/h':>8}{'coin':>8}")
    for pph, sid, rar, hrs, pts, coin in rows[:top]:
        print(f"{str(sid):<22}{str(rar):<12}{hrs:>7.2f}{pts:>7.0f}{pph:>8.0f}"
              f"{(coin or 0):>8}")


def cmd_sell(api: CryptoCrops, seed: str, quantity: int | None, dry: bool) -> None:
    api.bootstrap()
    inv = api.inventory().get(seed)
    if not inv:
        print(f"tidak ada {seed} di inventory")
        return
    qty = int(quantity or inv.get("fresh_quantity") or 0)
    prev = (api.sell_preview(seed, qty) or {}).get("preview", {})
    print("preview:", json.dumps(prev, indent=2))
    if dry:
        return
    sold = (api.sell(seed, qty) or {}).get("sold", {})
    print("sold   :", json.dumps(sold, indent=2))


def cmd_report(api: CryptoCrops) -> None:
    st = api.bootstrap()
    f = st.get("farm") or {}
    p = f.get("profile") or {}
    pool = st.get("pool") or {}
    pp = f.get("pool_progress") or {}
    prog = f.get("farm_progression") or {}
    cap = int(p.get("total_capacity") or 0)
    best = max(api.points_per_hour(s) for s in SEED_CADENCE) if not api._catalog else \
        max((api.points_per_hour(k) for k in api._catalog), default=0)
    per_h = best * cap
    print(f"capacity      : {cap} plot")
    print(f"best pts/h    : {best:.0f}/plot -> {per_h:.0f}/jam -> {per_h * 6:.0f}/siklus")
    print(f"points skrg   : {pp.get('total_points')}")
    print(f"pool          : {pool.get('harvestCredits')} HC / 6 jam "
          f"({pool.get('creditsPerUsd')} HC per USD)")
    est = pool.get("estimatedHarvestCredits")
    if est and pp.get("total_points"):
        per_pt = est / pp["total_points"]
        print(f"nilai/poin    : {per_pt:.3f} HC  (dari estimasi server)")
        print(f"proyeksi 6 jam: {per_h * 6 * per_pt:.0f} HC "
              f"= ${per_h * 6 * per_pt / (pool.get('creditsPerUsd') or 10000):.4f}")
    print(f"level         : {p.get('farm_level')} xp={prog.get('xp')} "
          f"next={prog.get('next_level_xp')}")


def cmd_missions(api: CryptoCrops, claim: bool = False) -> None:
    api.bootstrap()
    ms = api.missions()
    if not ms:
        print("tidak ada misi di response bootstrap")
        return
    ready = [m for m in ms if m.get("complete") and not m.get("claimed")]
    print(f"{'mission_id':<34}{'period':<8}{'progress':>10}  status")
    for m in ms:
        if m.get("claimed"):
            state = "claimed"
        elif m.get("complete"):
            state = "READY"
        else:
            state = "progress"
        print(f"{str(m.get('mission_id')):<34}{str(m.get('period')):<8}"
              f"{str(m.get('progress')) + '/' + str(m.get('target')):>10}  {state}")
    if not ready:
        print(f"\ntidak ada misi siap diklaim ({len(ms)} misi dipantau)")
        return
    print(f"\n{len(ready)} misi siap diklaim")
    if not claim:
        print("jalankan: python client.py missions --claim")
        return
    for m in ready:
        mid = m.get("mission_id")
        try:
            r = (api.claim_mission(mid) or {}).get("claimed", {})
            fert = (f" +{r.get('fertilizer_rarity')}x{r.get('fertilizer_quantity')}"
                    if r.get("fertilizer_rarity") else "")
            print(f"  claimed {mid} +{r.get('pass_xp_earned')} pass xp{fert}")
        except ApiError as exc:
            print(f"  gagal {mid}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="CryptoCrops API client")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    sub.add_parser("report")
    pc = sub.add_parser("catalog")
    pc.add_argument("--top", type=int, default=20)

    pp = sub.add_parser("plant")
    pp.add_argument("--seed", required=True)
    pp.add_argument("--plot", type=int, required=True)

    ph = sub.add_parser("harvest")
    ph.add_argument("--all", action="store_true", help="panen semua yang siap")
    ph.add_argument("--crop-id")

    ps = sub.add_parser("sell")
    ps.add_argument("--seed", required=True)
    ps.add_argument("--quantity", type=int)
    ps.add_argument("--dry-run", action="store_true")

    pl = sub.add_parser("loop")
    pl.add_argument("--seeds", default="")
    pl.add_argument("--interval", type=float, default=30.0)
    pl.add_argument("--ticks", type=int, default=0)
    pl.add_argument("--dry-run", action="store_true")
    pl.add_argument("--perfect-only", action="store_true",
                    help="hanya panen di dalam perfect window")
    pl.add_argument("--keep-orders", action="store_true",
                    help="jangan jual produce yang dibutuhkan order aktif")

    sub.add_parser("account")
    sub.add_parser("pools")
    sub.add_parser("guilds")

    pm = sub.add_parser("missions")
    pm.add_argument("--claim", action="store_true",
                    help="klaim semua misi yang sudah selesai")

    args = ap.parse_args()
    api = CryptoCrops()

    try:
        if args.cmd == "status":
            cmd_status(api)
        elif args.cmd == "report":
            cmd_report(api)
        elif args.cmd == "catalog":
            cmd_catalog(api, args.top)
        elif args.cmd == "plant":
            print(json.dumps(api.plant(args.seed, args.plot), indent=2))
        elif args.cmd == "harvest":
            api.bootstrap()
            targets = [args.crop_id] if args.crop_id else (
                [c.crop_id for c in api.matured()] if args.all else [])
            if not targets:
                print("tidak ada target (pakai --all atau --crop-id)")
                return 1
            for cid in targets:
                print(json.dumps((api.harvest(cid) or {}).get("harvested"), indent=2))
        elif args.cmd == "sell":
            cmd_sell(api, args.seed, args.quantity, args.dry_run)
        elif args.cmd == "account":
            print(json.dumps(api.account(), indent=2))
        elif args.cmd == "pools":
            print(json.dumps(api.pools(), indent=2))
        elif args.cmd == "guilds":
            print(json.dumps(api.guilds(), indent=2)[:4000])
        elif args.cmd == "missions":
            cmd_missions(api, claim=args.claim)
        elif args.cmd == "loop":
            seeds = [s.strip() for s in args.seeds.split(",") if s.strip()] or None
            api.loop(seeds, interval=args.interval, max_ticks=args.ticks,
                     dry_run=args.dry_run, perfect_only=args.perfect_only,
                     keep_for_orders=args.keep_orders)
    except ApiError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
