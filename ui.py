#!/usr/bin/env python3
# created by Z3R0 0N3 ID | Airdrop 888
"""
ui.py - tampilan terminal: banner figlet, warna, dan dashboard.

Dashboard menggambar ulang satu frame utuh (banner + status + log terakhir),
jadi tidak ada cursor gymnastics yang gampang rusak kalau terminal scroll.
Kalau output bukan TTY (pipe/redirect), otomatis jatuh ke mode teks biasa.
"""

from __future__ import annotations

import re
import shutil
import sys
import time
from collections import deque

try:  # console lama (conhost) perlu VT diaktifkan manual
    import colorama
    colorama.just_fix_windows_console()
except Exception:  # noqa: BLE001
    pass

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"
RED = "\x1b[31m"
GRAY = "\x1b[90m"

CREDIT = "created by Z3R0 0N3 ID | Airdrop 888"

_TTY = sys.stdout.isatty()


def color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if _TTY else text


def banner(text: str = "CryptoCrops", font: str = "small") -> str:
    """ASCII art ala figlet; fallback ke teks biasa kalau pyfiglet tidak ada."""
    try:
        import pyfiglet
        art = pyfiglet.figlet_format(text, font=font).rstrip("\n")
        return "\n".join(line.rstrip() for line in art.splitlines() if line.strip())
    except Exception:  # noqa: BLE001
        return text


def clear() -> None:
    if _TTY:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()


def width(default: int = 76) -> int:
    try:
        return max(30, min(shutil.get_terminal_size().columns, 200))
    except Exception:  # noqa: BLE001
        return default


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def visible_len(text: str) -> int:
    """Panjang teks yang benar-benar tampil (escape code tidak dihitung)."""
    return len(ANSI_RE.sub("", text))


def center(text: str, size: int | None = None) -> str:
    """Tengah-kan baris di dalam lebar `size` (escape code diabaikan)."""
    size = size or width()
    pad = max(0, (size - visible_len(text)) // 2)
    return " " * pad + text


def center_block(lines: list[str], size: int) -> list[str]:
    """Tengah-kan satu blok ASCII art: semua baris digeser sama banyak,
    supaya bentuk hurufnya tidak miring (kanan tiap baris sudah di-trim)."""
    widest = max((visible_len(line) for line in lines), default=0)
    pad = " " * max(0, (size - widest) // 2)
    return [pad + line if line.strip() else line for line in lines]


def fit(text: str, size: int | None = None) -> str:
    """Potong baris supaya tidak wrap dan merusak frame.

    Escape code warna tetap dipertahankan; yang dipotong hanya karakter
    yang kelihatan - kalau dihitung mentah, garis pembatas jadi kepotong
    dan ujungnya berantakan.
    """
    size = size or width()
    if visible_len(text) <= size:
        return text
    out: list[str] = []
    vis = 0
    i = 0
    limit = max(1, size - 1)
    while i < len(text) and vis < limit:
        m = ANSI_RE.match(text, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        out.append(text[i])
        vis += 1
        i += 1
    return "".join(out) + "…" + (RESET if _TTY else "")


class Dashboard:
    def __init__(self, title: str = "CryptoCrops", subtitle: str = "",
                 maxlog: int = 7, enabled: bool | None = None,
                 align: str = "center", credit: str | None = CREDIT):
        self.title = title
        self.subtitle = subtitle
        self.enabled = _TTY if enabled is None else enabled
        self.align = align
        self.credit = credit or ""
        self.logs: deque[str] = deque(maxlen=maxlog)
        self.fields: dict[str, str] = {}
        self.stats = ""
        self.figlet = banner(title) if self.enabled else ""

    # ---------------------------------------------------------------- api ---
    def log(self, msg: str, kind: str = "") -> None:
        colors = {"ok": GREEN, "warn": YELLOW, "err": RED, "info": CYAN}
        line = color(msg, colors.get(kind, "")) if kind else msg
        if not self.enabled:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
            return
        self.logs.append(line)
        self.render()

    def set(self, key: str, value: str) -> None:
        self.fields[key] = value

    def set_stats(self, text: str) -> None:
        self.stats = text

    # ------------------------------------------------------------- render ---
    def render(self) -> None:
        if not self.enabled:
            return
        size = max(40, width() - 1)  # -1: hindari auto-wrap di kolom terakhir
        height = shutil.get_terminal_size().lines or 24
        rule = color("─" * size, GRAY)

        head: list[tuple[str, str]] = []  # mode: rule | raw | center | text
        if self.figlet:
            art = self.figlet.splitlines()
            if self.align == "center":
                head.extend(("raw", line) for line in center_block(art, size))
            else:
                head.extend(("text", line) for line in art)
            head.append(("raw", ""))
        if self.credit:
            head.append(("center" if self.align == "center" else "text",
                         color(self.credit, DIM)))
        if self.subtitle:
            head.append(("center" if self.align == "center" else "text",
                         color(self.subtitle, DIM)))
        head.append(("rule", rule))
        if self.stats:
            head.append(("text", self.stats))
            head.append(("rule", rule))
        for key, value in self.fields.items():
            head.append(("text",
                         f"  {color(f'{key.upper():<7}', BOLD)} {value}"))

        # sisakan 2 baris (rule + ruang aman) supaya frame tidak pernah
        # menyentuh baris terakhir terminal - kalau menyentuh, layar scroll
        # dan header ikut naik. Sisa ruang dipakai log.
        budget = height - 2 - len(head) - 1
        logs = list(self.logs)[-budget:] if budget > 0 else []

        def place(mode: str, line: str) -> str:
            if mode in ("rule", "raw"):
                return line
            line = fit(line, size)
            return center(line, size) if mode == "center" else line

        out = [place(mode, line) for mode, line in head]
        out.append(rule)
        for line in logs:
            out.append(place("text", "  " + line))
        if not logs and budget > 0:
            out.append(place("text", color("  menunggu aktivitas…", GRAY)))

        # tanpa newline di akhir: baris terakhir tidak pernah "mendorong" layar.
        # \x1b[K per baris: sisa teks frame lama ikut dibersihkan walau baris
        # baru lebih pendek (kalau tidak, sisa garis lama nempel di kanan).
        sys.stdout.write("\x1b[H" + "\n".join(line + "\x1b[K" for line in out)
                         + "\x1b[J")
        sys.stdout.flush()


# ------------------------------------------------------------------ one-off ---
def show_banner(title: str = "CryptoCrops", subtitle: str = "",
                align: str = "center", credit: str | None = CREDIT) -> None:
    size = max(20, width() - 1)
    art = banner(title)
    if art:
        lines = art.splitlines()
        if align == "center":
            lines = center_block(lines, size)
        for line in lines:
            print(color(line, GREEN))
    if credit:
        text = color(credit, DIM)
        print(center(text, size) if align == "center" else text)
        print()
    if subtitle:
        text = color(subtitle, DIM)
        print(center(text, size) if align == "center" else text)
    print(color("─" * size, GRAY))
