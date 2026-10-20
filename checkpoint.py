#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
checkpoint.py — solver farm checkpoint CryptoCrops (captcha angka / number_image).

Alur (dari HAR + probe live):

  1. POST /api/farm-checkpoint/challenge  {"attempt_id": "<uuid4>"}
       - kalau checkpoint tidak diperlukan:
           {"verified": true, "checkpoint": {required:false, next_challenge_at, ...}}
       - kalau diperlukan: berisi gambar angka + ticket
  2. OCR gambar -> captcha_number (contoh "059")
  3. POST /api/farm-checkpoint/verify
       {"attempt_id", "required_since", "captcha_number", "captcha_ticket"}
     -> {"verified": true, "checkpoint": {required:false, next_challenge_at, ...}}

ticket = base64(payload) + "." + cdata, payload:
  ["farm-number-v1", player_id, required_since, attempt_id, host, issued_at, nonce]

Pemakaian:
  python checkpoint.py --status
  python checkpoint.py --once
  python checkpoint.py --watch            # pantau, selesaikan tiap kali due
  python checkpoint.py --once --number 059   # skip OCR, isi manual
  python checkpoint.py --dump             # simpan response mentah ke captures/
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import CryptoCrops, ApiError

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURES = os.path.join(HERE, "captures")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
SVG_HINT = b"<svg"


# --------------------------------------------------------------------------- #
# image extraction
# --------------------------------------------------------------------------- #

def _decode_blob(value: str) -> bytes | None:
    """Coba decode string jadi binary gambar."""
    if value.startswith("data:image"):
        value = value.split(",", 1)[-1]
    value = value.strip()
    if not value:
        return None
    if value.lstrip().startswith("<svg") or value.lstrip().startswith("<?xml"):
        return value.encode("utf-8")
    if len(value) < 32 or len(value) % 4:
        return None
    try:
        raw = base64.b64decode(value, validate=False)
    except Exception:  # noqa: BLE001
        return None
    if raw[:8] == PNG_MAGIC or raw[:3] == JPEG_MAGIC or SVG_HINT in raw[:64]:
        return raw
    return None


def find_image(node, path="") -> tuple[bytes, str] | None:
    """Telusuri JSON, ambil blob gambar pertama yang valid."""
    if isinstance(node, dict):
        for key, val in node.items():
            hit = find_image(val, f"{path}/{key}")
            if hit:
                return hit
    elif isinstance(node, list):
        for i, val in enumerate(node):
            hit = find_image(val, f"{path}/{i}")
            if hit:
                return hit
    elif isinstance(node, str):
        if "image" not in path.lower() and len(node) < 200:
            return None
        blob = _decode_blob(node)
        if blob:
            return blob, path or "?"
    return None


def find_key(node, names: tuple[str, ...], path=""):
    """Cari key pertama (rekursif) yang namanya cocok."""
    if isinstance(node, dict):
        for key, val in node.items():
            if key in names and isinstance(val, (str, int)):
                return val, f"{path}/{key}"
            hit = find_key(val, names, f"{path}/{key}")
            if hit:
                return hit
    elif isinstance(node, list):
        for i, val in enumerate(node):
            hit = find_key(val, names, f"{path}/{i}")
            if hit:
                return hit
    return None


def decode_ticket(ticket: str) -> list | None:
    try:
        payload = ticket.split(".")[0]
        return json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# OCR
# --------------------------------------------------------------------------- #

class Ocr:
    def __init__(self, debug: bool = False):
        self.debug = debug
        self._engine = None
        self._backend = "none"
        self._init()

    def _init(self) -> None:
        try:
            import ddddocr  # type: ignore
            self._engine = ddddocr.DdddOcr(show_ad=False)
            self._backend = "ddddocr"
        except Exception:  # noqa: BLE001
            try:
                import pytesseract  # type: ignore
                from PIL import Image  # noqa: F401
                self._engine = pytesseract
                self._backend = "tesseract"
            except Exception:  # noqa: BLE001
                self._backend = "none"

    @property
    def backend(self) -> str:
        return self._backend

    def read(self, blob: bytes) -> str:
        if self._backend == "ddddocr":
            return self._engine.classification(blob)
        if self._backend == "tesseract":
            from PIL import Image
            img = Image.open(io.BytesIO(blob))
            cfg = "--psm 8 -c tessedit_char_whitelist=0123456789"
            return self._engine.image_to_string(img, config=cfg)
        raise RuntimeError("tidak ada backend OCR (pip install ddddocr)")


def clean_number(raw: str, width: int = 0) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if width and len(digits) < width:
        digits = digits.zfill(width)
    return digits


# --------------------------------------------------------------------------- #
# solve
# --------------------------------------------------------------------------- #

def _save(name: str, data: bytes) -> str:
    os.makedirs(CAPTURES, exist_ok=True)
    path = os.path.join(CAPTURES, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def solve_once(api: CryptoCrops, ocr: Ocr, *, manual: str | None = None,
               dump: bool = False, verbose: bool = True,
               max_attempts: int = 4) -> dict:
    for attempt in range(1, max_attempts + 1):
        attempt_id = str(uuid.uuid4())
        res = api.checkpoint_challenge(attempt_id)

        if dump:
            _save("checkpoint_challenge.json",
                  json.dumps(res, indent=2).encode("utf-8"))

        cp = res.get("checkpoint") or {}
        if res.get("verified") and not cp.get("required"):
            return {"status": "not_required", "checkpoint": cp,
                    "next_challenge_at": cp.get("next_challenge_at")}

        found = find_image(res)
        if not found:
            if verbose:
                print(f"  [{attempt}] challenge tanpa gambar: {json.dumps(res)[:220]}")
            time.sleep(3)
            continue
        blob, where = found
        if dump or verbose:
            ext = "png" if blob[:8] == PNG_MAGIC else "jpg" if blob[:3] == JPEG_MAGIC else "img"
            print("  image:", _save(f"checkpoint_{int(time.time())}.{ext}", blob),
                  f"{len(blob)}B via {where}")

        ticket, _ = find_key(res, ("captcha_ticket", "ticket", "checkpoint_ticket")) or (None, None)
        required_since, _ = find_key(res, ("required_since",)) or (None, None)
        width_hint, _ = find_key(res, ("length", "digits", "captcha_length")) or (0, None)
        width = int(width_hint) if isinstance(width_hint, int) and 1 <= int(width_hint) <= 8 else 0

        if not ticket:
            return {"status": "error", "reason": "ticket tidak ditemukan",
                    "raw": json.dumps(res)[:400]}
        if required_since is None:
            required_since = (decode_ticket(ticket) or [None, None, 0])[2]

        payload = decode_ticket(ticket)
        if payload and not width:
            width = len("".join(ch for ch in str(manual or "") if ch.isdigit())) or 0

        number = manual
        if not number:
            if ocr.backend == "none":
                return {"status": "error", "reason": "OCR tidak tersedia",
                        "image": where}
            raw = ocr.read(blob)
            number = clean_number(raw, width)
            if verbose:
                print(f"  ocr[{ocr.backend}] raw={raw!r} -> {number!r} width={width}")

        if not number:
            if verbose:
                print(f"  [{attempt}] OCR gagal, ulangi dengan challenge baru")
            continue

        try:
            ver = api.checkpoint_verify(str(attempt_id), int(required_since),
                                        number, ticket)
        except ApiError as exc:
            if verbose:
                print(f"  [{attempt}] verify ditolak: {exc}")
            if exc.status in (401, 403):
                raise
            continue

        if dump:
            _save("checkpoint_verify.json",
                  json.dumps(ver, indent=2).encode("utf-8"))
        if ver.get("verified"):
            return {"status": "verified", "number": number,
                    "checkpoint": ver.get("checkpoint") or {}}
        if verbose:
            print(f"  [{attempt}] belum verified: {json.dumps(ver)[:220]}")
    return {"status": "error", "reason": "habis percobaan"}


def status(api: CryptoCrops) -> dict:
    api.bootstrap()
    cp = api.checkpoint()
    return {"required": cp.get("required"),
            "next_challenge_at": cp.get("next_challenge_at"),
            "last_verified_at": cp.get("last_verified_at"),
            "wait_s": max(0, (int(cp.get("next_challenge_at") or 0) - api.now_ms()) // 1000)}


def main() -> int:
    ap = argparse.ArgumentParser(description="CryptoCrops farm checkpoint solver")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--number", help="isi angka manual, skip OCR")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--interval", type=int, default=30, help="detik antar polling watch")
    args = ap.parse_args()
    if not (args.status or args.once or args.watch):
        args.status = True

    api = CryptoCrops()
    ocr = Ocr()

    if args.status:
        st = status(api)
        print(json.dumps(st, indent=2))

    if args.once:
        api.bootstrap()
        res = solve_once(api, ocr, manual=args.number, dump=args.dump)
        print(json.dumps(res, indent=2))
        return 0

    if args.watch:
        print(f"watch aktif · ocr={ocr.backend} · interval={args.interval}s")
        while True:
            try:
                st = status(api)
                due = bool(st["required"]) or st["wait_s"] == 0
                if due:
                    print(f"[{time.strftime('%H:%M:%S')}] checkpoint due — solve")
                    res = solve_once(api, ocr, manual=args.number, dump=args.dump)
                    print("  ->", json.dumps(res))
                    if res.get("status") == "error":
                        time.sleep(15)
                    continue
                print(f"\r  berikutnya {st['wait_s'] // 60}m{st['wait_s'] % 60:02d}s ",
                      end="", flush=True)
            except KeyboardInterrupt:
                return 0
            except ApiError as exc:
                print(f"\n  API error: {exc}")
            time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
