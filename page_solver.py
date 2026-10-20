#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
page_solver.py — ambil token Turnstile dari halaman faucet asli (bukan halaman sintetis).

Kenapa: situs memasang widget lewat `turnstile.render(el, {sitekey, action, cData})`
di /turnstile-check.js. Halaman sintetis generik memakai implicit render + `data-cdata`,
yang tokennya tidak membawa cdata yang benar → server menjawab FAUCET_CAPTCHA_FAILED.

Dengan memuat halaman asli (cookie sesi ikut), widget dipasang oleh kode situs sendiri,
jadi `action` dan `cdata` dijamin cocok dengan ticket yang diterbitkan pada request
`/api/earn/faucet-challenge` yang ditangkap dari network.

Pemakaian:
    python page_solver.py --json
    python page_solver.py --headed --debug
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from patchright.sync_api import sync_playwright

PAGE = "https://cryptocrops.net/faucet/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")


def load_cookies(path: str = "cookies.txt",
                 account: str | None = None) -> list[dict]:
    """Baca cookies.txt format simpel (atau Netscape) -> cookie Playwright."""
    try:
        import cookiefile
    except ImportError:  # dijalankan dari folder lain
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        import cookiefile

    items = cookiefile.load(path)
    if not items:
        return []
    item = items[0]
    if account:
        low = account.lower()
        for cand in items:
            if (cand.get("name") or "").lower() == low:
                item = cand
                break

    pairs = {k: v for k, v in (item.get("extra") or {}).items()
             if k.startswith("cc_") and v}
    if item.get("session"):
        pairs[cookiefile.SESSION] = item["session"]

    expires = int(time.time()) + 30 * 24 * 3600
    return [{"name": name, "value": value, "domain": ".cryptocrops.net",
             "path": "/", "secure": True, "httpOnly": False,
             "expires": expires}
            for name, value in pairs.items()]


def harvest(headed: bool = False, timeout: float = 90.0, debug: bool = False,
            cookie_path: str = "cookies.txt") -> dict:
    challenge: dict = {}
    token = ""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not headed,
            channel=None if headed else "chromium",
            args=["--disable-blink-features=AutomationControlled",
                  "--enable-unsafe-swiftshader"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  user_agent=UA, locale="id-ID",
                                  timezone_id="Asia/Jakarta")
        cookies = load_cookies(cookie_path)
        if cookies:
            ctx.add_cookies(cookies)

        page = ctx.new_page()
        if debug:
            page.on("console", lambda m: print(f"  console[{m.type}] {m.text[:160]}",
                                               file=sys.stderr))

        def on_response(resp):
            if "/api/earn/faucet-challenge" in resp.url:
                try:
                    challenge.update(resp.json())
                    if debug:
                        print("  challenge:", json.dumps(challenge)[:300], file=sys.stderr)
                except Exception:  # noqa: BLE001
                    pass

        page.on("response", on_response)
        page.goto(PAGE, wait_until="domcontentloaded", timeout=60000)

        deadline = time.time() + timeout
        clicked = False
        while time.time() < deadline:
            try:
                token = page.evaluate(
                    "() => (document.querySelector('input[name=\"cf-turnstile-response\"]')||{}).value || ''")
            except Exception:  # noqa: BLE001
                token = ""
            if token:
                break
            if not clicked:
                try:
                    frame = page.frame_locator("[data-faucet-turnstile] iframe")
                    frame.locator("body").click(timeout=2000)
                    clicked = True
                except Exception:  # noqa: BLE001
                    try:
                        page.locator("[data-faucet-turnstile]").click(timeout=1500, force=True)
                    except Exception:  # noqa: BLE001
                        pass
            page.wait_for_timeout(700)

        if debug:
            shot = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "captures", "page_solver.png")
            os.makedirs(os.path.dirname(shot), exist_ok=True)
            try:
                page.screenshot(path=shot)
                print("  screenshot:", shot, file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass

        ctx.close()
        browser.close()

    if not token:
        raise RuntimeError("token kosong")
    ver = challenge.get("verification") or {}
    return {"token": token,
            "challenge_id": (challenge.get("challenge") or {}).get("challenge_id"),
            "ticket": ver.get("ticket"),
            "cdata": ver.get("cdata"),
            "action": ver.get("action"),
            "site_key": ver.get("site_key")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--cookies", default="cookies.txt")
    args = ap.parse_args()

    try:
        res = harvest(headed=args.headed, timeout=args.timeout, debug=args.debug,
                      cookie_path=args.cookies)
    except Exception as exc:  # noqa: BLE001
        print(f"gagal: {exc}", file=sys.stderr)
        return 1

    if args.json:
        out = dict(res)
        out["token"] = out["token"][:18] + "…"
        print(json.dumps(out, indent=2))
    else:
        print(res["token"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
