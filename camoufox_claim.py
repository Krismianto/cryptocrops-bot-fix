#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
camoufox_claim.py — klaim faucet lewat Camoufox (Firefox stealth) di halaman asli.

Kenapa jalur ini yang dipakai:
  * Chromium (patchright / Chrome) gagal di Turnstile: "No available adapters",
    error 600010, widget tidak pernah selesai.
  * Solver pihak ketiga memang menghasilkan token, tapi server menolaknya
    (FAUCET_CAPTCHA_FAILED) karena token dibuat di luar sesi/origin situs.
  * Camoufox membuka halaman faucet yang asli dengan cookie sesi asli, jadi
    situs sendiri yang memanggil turnstile.render({cData}) dan tokennya sah.
  * Tombol klaim tertutup overlay transparan, jadi klik dilakukan lewat JS
    (b.click()), bukan klik pointer.

Dipakai sebagai modul:  from camoufox_claim import claim
Dipakai langsung:
    <venv camoufox>\\python.exe camoufox_claim.py
    ... camoufox_claim.py --headless --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from camoufox.sync_api import Camoufox  # noqa: E402

from page_solver import load_cookies  # noqa: E402

PAGE = "https://cryptocrops.net/faucet/"
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_SEL = "textarea[name='h-captcha-response'], textarea[name='cf-turnstile-response'], textarea[name='g-recaptcha-response']"
STATUS_SEL = "[data-faucet-captcha-status]"
FAUCET_STATUS_SEL = "[data-faucet-status]"
BUTTON_SEL = "[data-claim-faucet]"


def _noop(_msg: str) -> None:
    pass


def _shot(page, name: str) -> None:
    """Simpan screenshot diagnostik; folder dibuat kalau belum ada."""
    try:
        folder = os.path.join(HERE, "captures")
        os.makedirs(folder, exist_ok=True)
        page.screenshot(path=os.path.join(folder, name))
    except Exception:  # noqa: BLE001
        pass


def claim(headed: bool = True, timeout: float = 120.0, cookie_path: str = "cookies.txt",
          dry_run: bool = False, log=_noop) -> dict:
    """Buka /faucet/, tunggu widget selesai, klik klaim. Return dict response."""
    result: dict = {}

    with Camoufox(headless=not headed, humanize=True, locale="id-ID",
                  os="windows", geoip=False) as browser:
        page = browser.new_page()

        def on_resp(resp):
            try:
                if resp.request.method != "POST":
                    return
            except Exception:  # noqa: BLE001
                pass
            path = resp.url.split("?")[0].rstrip("/")
            if path.endswith("/api/earn/faucet"):
                try:
                    result.update(resp.json())
                except Exception:  # noqa: BLE001
                    pass

        page.on("response", on_resp)

        ck = load_cookies(cookie_path)
        if ck:
            page.context.add_cookies(ck)
            log(f"  cookie: {len(ck)} entri")

        page.goto(PAGE, wait_until="domcontentloaded", timeout=90000)
        log("  halaman /faucet/ dibuka")

        def app_rendered(wait_s: float = 45.0) -> bool:
            end_s = time.time() + wait_s
            while time.time() < end_s:
                try:
                    if page.query_selector(BUTTON_SEL):
                        return True
                except Exception:  # noqa: BLE001
                    pass
                try:
                    page.wait_for_timeout(500)
                except Exception:  # noqa: BLE001
                    return False
            return False

        if not app_rendered():
            log("  app belum render (kemungkinan interstitial) — reload")
            try:
                page.reload(wait_until="domcontentloaded", timeout=90000)
            except Exception as exc:  # noqa: BLE001
                log(f"  reload gagal: {exc}")
            if not app_rendered(30):
                try:
                    ttl = page.title()
                    body = page.evaluate("() => document.body.innerText.slice(0,200)")
                except Exception:  # noqa: BLE001
                    ttl, body = "", ""
                try:
                    _shot(page, "claim_page_error.png")
                except Exception:  # noqa: BLE001
                    pass
                log(f"  halaman tidak merender app · title={ttl!r}")
                return {"status": "page_error", "detail": (ttl + " | " + body)[:300]}

        deadline = time.time() + timeout
        token = ""
        clicks = 0
        ready = False
        cstatus = ""
        label = ""
        fstatus = ""
        last_dbg = -10.0

        while time.time() < deadline:
            elapsed = timeout - (deadline - time.time())
            token = ""
            try:
                st = page.evaluate("""() => {
                    const b = document.querySelector('[data-claim-faucet]');
                    const cs = document.querySelector('[data-faucet-captcha-status]');
                    const fs = document.querySelector('[data-faucet-status]');
                    const vals = [...document.querySelectorAll(
                        'input[name=cf-turnstile-response]')]
                        .map(i => i.value).filter(v => v && v.length > 40);
                    return {
                        btn: b ? b.textContent.trim() : null,
                        dis: b ? b.hasAttribute('disabled') : null,
                        cap: cs ? cs.textContent.trim() : '',
                        fs: fs ? fs.textContent.trim() : '',
                        tok: vals.length ? vals[vals.length - 1] : '',
                    };
                }""")
                token = st.get("tok") or ""
                ready = (st.get("dis") is False)
                label = st.get("btn") or ""
                cstatus = st.get("cap") or ""
                fstatus = st.get("fs") or ""
            except Exception as exc:  # noqa: BLE001
                log(f"  baca state gagal: {exc}")

            if elapsed - last_dbg >= 6:
                last_dbg = elapsed
                log(f"  [{int(elapsed):3d}s] tombol={label[:26]!r} "
                    f"aktif={ready} captcha={cstatus[:40]!r} token={len(token)}")

            if label.lower().startswith("refill"):
                log(f"  masih cooldown: {label}")
                return {"status": "cooldown", "detail": label}

            if token or ready or "verified" in cstatus.lower():
                break

            # Turnstile managed mode butuh klik kotak centang.
            if clicks < 3 and elapsed > 4 + clicks * 7:
                try:
                    box = page.evaluate("""() => {
                        const s = document.querySelector('[data-faucet-turnstile]');
                        if (!s) return null;
                        s.scrollIntoView({block: 'center', behavior: 'instant'});
                        const r = s.getBoundingClientRect();
                        return {x: r.x, y: r.y, w: r.width, h: r.height};
                    }""")
                    if box:
                        page.mouse.move(box["x"] - 90, box["y"] + 130, steps=12)
                        page.wait_for_timeout(220)
                        page.mouse.move(box["x"] + 24,
                                        box["y"] + box["h"] / 2, steps=9)
                        page.wait_for_timeout(150)
                        page.mouse.click(box["x"] + 24, box["y"] + box["h"] / 2)
                        clicks += 1
                        log(f"  klik kotak captcha #{clicks}"
                            f" @({int(box['x'] + 24)},{int(box['y'] + box['h'] / 2)})")
                except Exception as exc:  # noqa: BLE001
                    log(f"  klik kotak gagal: {exc}")
            try:
                page.wait_for_timeout(700)
            except Exception:  # noqa: BLE001
                break

        if not token and not ready and "verified" not in cstatus.lower():
            detail = fstatus or cstatus
            log(f"  widget tidak selesai · status={detail!r}")
            _shot(page, "claim_not_ready.png")
            return {"status": "not_ready", "detail": detail}

        log(f"  siap klaim · token={len(token)} chars · tombol aktif={ready}")
        if dry_run:
            return {"status": "dry_run", "token_len": len(token)}

        clicked = False
        try:
            how = page.evaluate("""() => {
                const b = document.querySelector('[data-claim-faucet]');
                if (!b) return 'no-button';
                if (b.disabled) return 'disabled';
                b.click();
                return 'js-click';
            }""")
            clicked = how == "js-click"
            log(f"  klaim: {how}")
        except Exception as exc:  # noqa: BLE001
            log(f"  klik klaim gagal: {exc}")

        # tunggu response klaim yang asli (bukan challenge)
        end = time.time() + 45
        while time.time() < end:
            if result.get("claim_id") or result.get("error"):
                break
            try:
                page.wait_for_timeout(400)
            except Exception:  # noqa: BLE001
                log("  halaman tertutup saat menunggu response")
                break

    if not result:
        return {"status": "clicked" if clicked else "no_response"}
    body = result.get("claimed")
    if isinstance(body, dict):
        return {"status": "claimed", **body}
    return {"status": "response", **result}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--cookies", default="cookies.txt")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    log = _noop if args.quiet else (lambda m: print(m, file=sys.stderr, flush=True))
    res = claim(headed=not args.headless, timeout=args.timeout,
                cookie_path=args.cookies, dry_run=args.dry_run, log=log)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res.get("status") in ("claimed", "dry_run") else 1


if __name__ == "__main__":
    sys.exit(main())
