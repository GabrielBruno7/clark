#!/usr/bin/env python3
"""CLARK — launcher retrô em pixel art para rodar vários agentes Claude Code ao mesmo tempo."""
import json
import math
import os
import random
import re
import shutil
import signal
import sys
import threading
import time
import unicodedata
import urllib.request
import uuid
from glob import glob
from string import Template

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
gi.require_version("PangoCairo", "1.0")
import cairo
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo, Vte

VERSION = "0.1.0"
CONFIG_PATH = os.path.join(GLib.get_user_config_dir(), "clark", "config.json")
CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_REFRESH_S = 300


# ───────────────────────── paleta ─────────────────────────
def hexc(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


WHITE = (1.0, 1.0, 1.0)
BLACK = (0.0, 0.0, 0.0)
EYE = hexc("#0a0807")

# ORANGE é a cor de destaque do tema (no MAGICK ela é roxa); o nome ficou por compatibilidade.
THEMES = {
    "dark": dict(
        label="DARK", dark=True,
        bg="#14100e", bg2="#1f1915", bg3="#2a221d", bg4="#3a2f28", bg5="#4a3c33", shadow="#0a0807",
        ink="#f0e6d6", dim="#8a7d6e", accent="#d97757", accent_hi="#e88a6a", accent_lo="#b85c3e",
        on_accent="#14100e", yellow="#f2c14e", green="#7fc86a", red="#e05a4f",
        agents=["#d97757", "#5fb3b3", "#9b7bd8", "#7fc86a", "#f2c14e", "#e07aa8", "#5e9be0", "#e05a4f"],
        term=["#1a1410", "#e05a4f", "#7fc86a", "#f2c14e", "#5e9be0", "#b48ead", "#5fb3b3", "#d9cbb8",
              "#6b5f53", "#ff7a6b", "#a4e08f", "#ffd97a", "#8bb8f0", "#d7a8e0", "#8fd6d6", "#fff6e8"]),
    "white": dict(
        label="WHITE", dark=False,
        bg="#f4ecdf", bg2="#e9dcc8", bg3="#ddcdb4", bg4="#d1bea0", bg5="#c3ad8e", shadow="#b19c7e",
        ink="#2b211b", dim="#8a7560", accent="#c8603f", accent_hi="#d7714f", accent_lo="#a94d30",
        on_accent="#fff8ee", yellow="#c99a1e", green="#4f9a3c", red="#c4443a",
        agents=["#c8603f", "#2f8f8f", "#7a5cc0", "#4f9a3c", "#c99a1e", "#c45a8c", "#3f7cc4", "#c4443a"],
        term=["#2b211b", "#c4443a", "#4f9a3c", "#a87d10", "#3f7cc4", "#8e5aa8", "#2f8f8f", "#d8c9b2",
              "#6b5a4b", "#e05a4f", "#5fae4a", "#c99a1e", "#5e9be0", "#a874c4", "#3fa5a5", "#fffaf2"]),
    "magick": dict(
        label="MAGICK", dark=True,
        bg="#140f1f", bg2="#1d1630", bg3="#2a2042", bg4="#3a2d5a", bg5="#4a3a70", shadow="#08050f",
        ink="#ece4ff", dim="#8b7fb0", accent="#b07cff", accent_hi="#c49bff", accent_lo="#8e57e6",
        on_accent="#140f1f", yellow="#ffd36e", green="#6fe0b0", red="#ff6b9a",
        agents=["#b07cff", "#5fd4e0", "#ff7ad9", "#6fe0b0", "#ffd36e", "#ff9a6b", "#7aa2ff", "#ff6b9a"],
        term=["#1d1630", "#ff6b9a", "#6fe0b0", "#ffd36e", "#7aa2ff", "#c49bff", "#5fd4e0", "#d9d0f0",
              "#5a4d7a", "#ff8fb3", "#93f0c8", "#ffe08f", "#9fbcff", "#dcbfff", "#8fe6ee", "#fbf8ff"]),
}
THEME = THEMES["dark"]
AGENT_COLORS, TERM_PALETTE = [], []


def apply_theme(name):
    """Troca a paleta global; quem desenha lê essas variáveis a cada frame."""
    global THEME, BG, BG2, BG3, SHADOW, INK, DIM, ORANGE, YELLOW, GREEN, RED
    THEME = THEMES.get(name) or THEMES["dark"]
    BG, BG2, BG3, SHADOW = (hexc(THEME[k]) for k in ("bg", "bg2", "bg3", "shadow"))
    INK, DIM, ORANGE = hexc(THEME["ink"]), hexc(THEME["dim"]), hexc(THEME["accent"])
    YELLOW, GREEN, RED = hexc(THEME["yellow"]), hexc(THEME["green"]), hexc(THEME["red"])
    AGENT_COLORS[:] = [hexc(h) for h in THEME["agents"]]
    TERM_PALETTE[:] = THEME["term"]


apply_theme("dark")


# ───────────────────────── fonte bitmap 5x7 ─────────────────────────
_FONT_SRC = {
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01111", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "01110 00100 00100 00100 00100 00100 01110", "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 10001 11001 10101 10011 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 10101 01010", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "3": "11111 00010 00100 00010 00001 10001 01110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
    " ": "00000 00000 00000 00000 00000 00000 00000", ".": "00000 00000 00000 00000 00000 01100 01100",
    ":": "00000 01100 01100 00000 01100 01100 00000", "-": "00000 00000 00000 11111 00000 00000 00000",
    "!": "00100 00100 00100 00100 00100 00000 00100", "?": "01110 10001 00001 00010 00100 00000 00100",
    "/": "00001 00001 00010 00100 01000 10000 10000", "+": "00000 00100 00100 11111 00100 00100 00000",
    ">": "01000 00100 00010 00001 00010 00100 01000", "<": "00010 00100 01000 10000 01000 00100 00010",
    "_": "00000 00000 00000 00000 00000 00000 11111", "%": "11001 11001 00010 00100 01000 10011 10011",
    "'": "00100 00100 01000 00000 00000 00000 00000", "(": "00010 00100 01000 01000 01000 00100 00010",
    ")": "01000 00100 00010 00010 00010 00100 01000", "[": "01110 01000 01000 01000 01000 01000 01110",
    "]": "01110 00010 00010 00010 00010 00010 01110", "#": "01010 01010 11111 01010 11111 01010 01010",
    "*": "00000 00100 10101 01110 10101 00100 00000", "=": "00000 00000 11111 00000 11111 00000 00000",
    ",": "00000 00000 00000 00000 01100 00100 01000",
}
FONT = {k: v.split() for k, v in _FONT_SRC.items()}


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


def text_w(s, sc):
    return max(0, len(norm(s)) * 6 * sc - sc)


def fit_text(s, sc, width):
    """Corta o texto (com ...) para caber em `width` pixels na fonte pixelada."""
    s = norm(s)
    if text_w(s, sc) <= width:
        return s
    n = max(0, (width + sc) // (6 * sc) - 3)
    return s[:n].rstrip() + "..."


def text_rects(cr, s, x, y, sc):
    x, y = int(x), int(y)
    for i, ch in enumerate(norm(s)):
        g = FONT.get(ch) or FONT["?"]
        ox = x + i * 6 * sc
        for r, row in enumerate(g):
            for c, b in enumerate(row):
                if b == "1":
                    cr.rectangle(ox + c * sc, y + r * sc, sc, sc)


def draw_text(cr, s, x, y, sc, color, alpha=1.0, shadow=None):
    if shadow is not None:
        cr.set_source_rgba(*shadow, alpha)
        text_rects(cr, s, x + sc, y + sc, sc)
        cr.fill()
    cr.set_source_rgba(*color, alpha)
    text_rects(cr, s, x, y, sc)
    cr.fill()


# ───────────────────────── sprite do mascote ─────────────────────────
# Dragãozinho de perfil, olhando pra direita. O=corpo H=barriga/topo D=asa/chifres K=olho F/Y=fogo
_DRAGON_TOP = {  # linhas 0-6: chifres, cabeça e asa (abaixada / levantada)
    False: ["..........D..D..",
            ".........HHHHHH.",
            "..D......OOOOKOO",
            ".DD......OOOOOOO",
            ".DDD.....OOOOOD.",
            ".DDDD...OOOOO...",
            "..DDDDOOOOOO...."],
    True: ["D.........D..D..",
           "DD.......HHHHHH.",
           ".DD......OOOOKOO",
           ".DDD.....OOOOOOO",
           "..DDD....OOOOOD.",
           "...DDD..OOOOO...",
           "....DDOOOOOO...."],
}
_DRAGON_BODY = ["...DDOHHHHOO....",
                "OO..OOHHHHOO....",
                ".OOOOOOOOOOO...."]
_LEGS = [["....DD...DD.....", "....DD...DD....."],
         ["...DD.....DD....", "....DD...DD....."]]
_FIRE = [(".Y..", "F", "YYFY", ".FY."),
         ("..Y.", "Y", "FYYF", "Y..F")]
SPRITE_W, SPRITE_H = 16, 12
HEAT_W = 280


def mascot_rows(step=0, blink=False, sleep=False, arms_up=False, fire=0):
    rows = list(_DRAGON_TOP[bool(arms_up)])
    if sleep:
        rows[2] = rows[2][:12] + "KKOO"
    elif blink:
        rows[2] = rows[2][:13] + "OO"
    if fire and not sleep:
        a, mouth, b, c = _FIRE[(fire - 1) % 2]
        rows[3] += a
        rows[4] = rows[4][:15] + mouth + b
        rows[5] += c
    return rows + _DRAGON_BODY + _LEGS[step % 2]


def sprite_pal(base):
    return {"O": base, "H": mix(base, WHITE, 0.3), "D": mix(base, BLACK, 0.3), "K": EYE,
            "F": hexc("#ff6b35"), "Y": YELLOW}


def draw_sprite(cr, rows, x, y, p, pal, alpha=1.0):
    x, y = int(x), int(y)
    buckets = {}
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in pal:
                buckets.setdefault(ch, []).append((c, r))
    for ch, cells in buckets.items():
        cr.set_source_rgba(*pal[ch], alpha)
        for c, r in cells:
            cr.rectangle(x + c * p, y + r * p, p, p)
        cr.fill()


def _rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def make_icon_surface(size):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(s)
    m = size * 0.06  # margem pra sombra da placa
    w = size - 2 * m
    rad = w * 0.22

    # sombra da placa
    for i in range(6, 0, -1):
        _rounded_rect(cr, m, m + size * 0.012 * i / 2, w, w, rad)
        cr.set_source_rgba(0, 0, 0, 0.06)
        cr.fill()

    # placa com gradiente quente + brilho laranja atrás do mascote
    _rounded_rect(cr, m, m, w, w, rad)
    cr.save()
    cr.clip()
    g = cairo.LinearGradient(0, m, 0, m + w)
    g.add_color_stop_rgb(0, *mix(BG3, ORANGE, 0.12))
    g.add_color_stop_rgb(1, *SHADOW)
    cr.set_source(g)
    cr.paint()
    glow = cairo.RadialGradient(size / 2, size * 0.5, 0, size / 2, size * 0.5, w * 0.55)
    glow.add_color_stop_rgba(0, *ORANGE, 0.38)
    glow.add_color_stop_rgba(1, *ORANGE, 0.0)
    cr.set_source(glow)
    cr.paint()
    if size >= 64:  # scanlines CRT
        cr.set_source_rgba(0, 0, 0, 0.13)
        step = max(2, size // 64)
        for yy in range(int(m), int(m + w), step * 2):
            cr.rectangle(m, yy, w, step)
        cr.fill()
    cr.restore()

    # bordas: contorno escuro + filete de luz no topo
    lw = max(1.0, size / 96)
    _rounded_rect(cr, m + lw / 2, m + lw / 2, w - lw, w - lw, rad - lw / 2)
    cr.set_line_width(lw)
    cr.set_source_rgba(*mix(ORANGE, WHITE, 0.2), 0.35)
    cr.stroke()
    _rounded_rect(cr, m + lw * 1.5, m + lw * 1.5, w - lw * 3, w - lw * 3, rad - lw * 1.5)
    cr.set_source_rgba(*SHADOW, 0.6)
    cr.stroke()

    # mascote em pixel art: asas pra cima, cuspindo fogo, com contorno
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    rows = mascot_rows(arms_up=True, fire=1)
    cols = max(len(r) for r in rows)
    rows = [r.ljust(cols, ".") for r in rows]
    pal = sprite_pal(ORANGE)
    filled = {(c, r) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch in pal}
    outline = {(c + dc, r + dr) for c, r in filled for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))} - filled
    p = max(1, int(w / (cols + 4)))
    sx = int((size - cols * p) / 2)
    sy = int((size - len(rows) * p) / 2 + p * 0.5)

    # sombra no chão
    cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
    cr.save()
    cr.translate(sx + 7.5 * p, sy + len(rows) * p + p * 0.6)
    cr.scale(6.5 * p, 1.1 * p)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()
    cr.set_source_rgba(0, 0, 0, 0.35)
    cr.fill()
    cr.set_antialias(cairo.ANTIALIAS_NONE)

    if p >= 2:
        cr.set_source_rgb(*SHADOW)
        for c, r in outline:
            cr.rectangle(sx + c * p, sy + r * p, p, p)
        cr.fill()
    draw_sprite(cr, rows, sx, sy, p, pal)
    # brilho no olho
    if p >= 4:
        er = next(r for r, row in enumerate(rows) if "K" in row)
        ec = rows[er].index("K")
        cr.set_source_rgb(*WHITE)
        q = max(1, p // 3)
        cr.rectangle(sx + ec * p, sy + er * p, q, q)
        cr.fill()

    # faíscas
    if size >= 48:
        for fx, fy, k, col in ((0.22, 0.24, 1.0, YELLOW), (0.80, 0.22, 0.7, INK), (0.16, 0.70, 0.6, ORANGE)):
            q = max(1, int(p * 0.6 * k))
            x0, y0 = int(size * fx), int(size * fy)
            cr.set_source_rgba(*col, 0.9)
            cr.rectangle(x0, y0 - q, q, q * 3)
            cr.rectangle(x0 - q, y0, q * 3, q)
            cr.fill()
    return s


# ───────────────────────── easing ─────────────────────────
def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_out_bounce(t):
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


# ───────────────────────── tela de loading ─────────────────────────
class Splash(Gtk.DrawingArea):
    DURATION = 2.9
    WIPE = 0.5

    def __init__(self, on_done):
        super().__init__()
        self.on_done = on_done
        self.t = 0.0
        self.t0 = None
        self.wipe_t0 = None
        self.done = False
        self.claude_status = None  # (texto, ok)
        rnd = random.Random(7)
        self.stars = [(rnd.random(), rnd.random() * 0.58, rnd.choice((1, 1, 2, 3)), rnd.random() * 6.28)
                      for _ in range(150)]
        self.set_can_focus(True)
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("draw", self._draw)
        self.connect("key-press-event", self._skip)
        self.connect("button-press-event", self._skip)
        self.add_tick_callback(self._tick)

    def set_claude_status(self, text, ok):
        self.claude_status = (text, ok)

    def _skip(self, *_):
        if self.wipe_t0 is None:
            self.wipe_t0 = self.t
        return True

    def _tick(self, _w, clock):
        now = clock.get_frame_time() / 1e6
        if self.t0 is None:
            self.t0 = now
        self.t = now - self.t0
        if self.wipe_t0 is None and self.t >= self.DURATION and self.claude_status:
            self.wipe_t0 = self.t
        self.queue_draw()
        if self.wipe_t0 is not None and self.t - self.wipe_t0 >= self.WIPE and not self.done:
            self.done = True
            self.on_done()
            return False
        return True

    def _progress(self):
        p = ease_out_cubic(clamp((self.t - 0.2) / (self.DURATION - 0.5)))
        if self.claude_status is None:
            p = min(p, 0.85)
        if self.wipe_t0 is not None:
            p = 1.0
        return p

    def _draw(self, _w, cr):
        W, H, t = self.get_allocated_width(), self.get_allocated_height(), self.t
        P = max(3, min(W, H) // 120)
        L = P * 2                       # escala do logo
        M = max(3, int(P * 1.5))        # escala do mascote
        sc = max(2, P // 3)             # texto pequeno
        sc2 = max(2, P // 2)            # texto médio
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.set_source_rgb(*BG)
        cr.paint()

        # estrelas em parallax
        for sx, sy, layer, ph in self.stars:
            x = int(((sx - t * 0.018 * layer) % 1.0) * W)
            y = int(sy * H)
            a = (0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 3 + ph))) * (0.3 + 0.23 * layer)
            cr.set_source_rgba(*INK, min(1.0, a))
            cr.rectangle(x - x % P, y - y % P, P, P)
            cr.fill()

        gy = int(H * 0.62) // P * P

        # chão
        cr.set_source_rgb(*BG3)
        cr.rectangle(0, gy, W, P)
        cr.fill()
        cr.set_source_rgba(*BG3, 0.6)
        for row, off in ((2, 0), (4, 2), (7, 1)):
            for x in range(off * P * 2, W, P * 6):
                cr.rectangle(x, gy + row * P, P, P)
        cr.fill()

        # logo caindo letra por letra
        word = "CLARK"
        logo_w = text_w(word, L)
        x0 = (W - logo_w) // 2
        ly = int(H * 0.15)
        shade = mix(ORANGE, BLACK, 0.5)
        for i, ch in enumerate(word):
            k = clamp((t - (0.5 + i * 0.11)) / 0.6)
            if k <= 0:
                continue
            dy = int((1 - ease_out_bounce(k)) * -(ly + 7 * L + 40))
            lx = x0 + i * 6 * L
            cr.set_source_rgb(*SHADOW)
            text_rects(cr, ch, lx + L, ly + dy + L, L)
            cr.fill()
            cr.set_source_rgb(*shade)
            for d in range(1, L // 2 + 1, max(1, P // 2)):
                text_rects(cr, ch, lx + d, ly + dy + d, L)
            cr.fill()
            cr.set_source_rgb(*ORANGE)
            text_rects(cr, ch, lx, ly + dy, L)
            cr.fill()

        # brilho passando no logo
        sk = (t - 1.75) / 0.55
        if 0 <= sk <= 1:
            cr.save()
            text_rects(cr, word, x0, ly, L)
            cr.clip()
            bx = x0 - 6 * L + (logo_w + 12 * L) * sk
            cr.set_source_rgba(*WHITE, 0.55)
            cr.move_to(bx, ly)
            cr.line_to(bx + 3 * L, ly)
            cr.line_to(bx + L, ly + 7 * L)
            cr.line_to(bx - 2 * L, ly + 7 * L)
            cr.close_path()
            cr.fill()
            cr.restore()

        sub = "MULTI-AGENT CLAUDE LAUNCHER"
        sa = clamp((t - 1.35) / 0.4)
        if sa > 0:
            draw_text(cr, sub, (W - text_w(sub, sc)) // 2, ly + 7 * L + 4 * P, sc, DIM, sa)

        # mascote andando, pulando e comemorando
        prog = self._progress()
        ready = prog >= 1.0
        cx = W // 2 - SPRITE_W * M // 2
        wk = clamp(t / 1.1)
        mx = int(-SPRITE_W * M + (cx + SPRITE_W * M) * ease_out_cubic(wk))
        step = int(t * 10) % 2 if wk < 1 else 0
        jy, arms = 0, False
        jk = (t - 1.55) / 0.4
        if 0 <= jk <= 1:
            jy = -int(math.sin(math.pi * jk) * M * 5)
            arms = True
        elif ready:
            arms = int(t * 6) % 2 == 0
        blink = (t % 2.2) < 0.12
        sw = int(10 * M * (1 - 0.5 * (-jy) / (M * 5 + 1)))
        cr.set_source_rgba(*SHADOW, 0.7)
        cr.rectangle(mx + (SPRITE_W * M - sw) // 2, gy - P, sw, P)
        cr.fill()
        fire = int(t * 10) % 2 + 1 if (arms or ready) else 0
        flap = arms or (wk < 1 and step == 1)
        draw_sprite(cr, mascot_rows(step, blink, arms_up=flap, fire=fire), mx, gy - SPRITE_H * M + jy, M,
                    sprite_pal(ORANGE))

        # barra de progresso em blocos
        bw = int(min(W * 0.5, P * 80)) // P * P
        bx, by, bh = (W - bw) // 2, gy + 7 * P, 4 * P
        cr.set_source_rgb(*SHADOW)
        cr.rectangle(bx + P, by + P, bw, bh)
        cr.fill()
        cr.set_source_rgb(*DIM)
        cr.rectangle(bx, by, bw, bh)
        cr.fill()
        cr.set_source_rgb(*BG)
        cr.rectangle(bx + P // 2 + 1, by + P // 2 + 1, bw - P - 2, bh - P - 2)
        cr.fill()
        seg = 3 * P
        nseg = (bw - 2 * P) // seg
        filled = int(prog * nseg)
        for i in range(filled):
            cr.set_source_rgb(*mix(ORANGE, YELLOW, i / max(1, nseg - 1)))
            cr.rectangle(bx + P + i * seg, by + P, seg - P // 2 - 1, bh - 2 * P)
            cr.fill()
        if not ready and int(t * 8) % 2 and filled < nseg:
            cr.set_source_rgba(*INK, 0.5)
            cr.rectangle(bx + P + filled * seg, by + P, seg - P // 2 - 1, bh - 2 * P)
            cr.fill()

        steps = ["INICIANDO MOTOR DE PIXELS", "CARREGANDO SPRITES", "PROCURANDO CLAUDE CLI",
                 "AQUECENDO OS NEURONIOS", "INVOCANDO AGENTES"]
        msg = "PRONTO!" if ready else steps[min(4, int(prog * 5))] + "." * (int(t * 4) % 4)
        my = by + bh + 4 * P
        draw_text(cr, msg, bx, my, sc2, YELLOW if ready else INK, shadow=SHADOW)
        pct = f"{int(prog * 100):03d}%"
        draw_text(cr, pct, bx + bw - text_w(pct, sc2), my, sc2, ORANGE, shadow=SHADOW)
        if self.claude_status and prog > 0.45:
            txt, ok = self.claude_status
            draw_text(cr, ("> " if ok else "! ") + txt, bx, my + 7 * sc2 + 3 * P, sc, GREEN if ok else RED)

        hint = "PRESS ANY KEY"
        if int(t * 2) % 2 == 0:
            draw_text(cr, hint, (W - text_w(hint, sc)) // 2, H - 6 * P, sc, DIM)
        draw_text(cr, "V" + VERSION, 3 * P, H - 6 * P, sc, BG3)
        cpy = "(C) 2026 CLARK"
        draw_text(cr, cpy, W - 3 * P - text_w(cpy, sc), H - 6 * P, sc, BG3)

        # efeito CRT: scanlines + vinheta
        cr.set_source_rgba(0, 0, 0, 0.18)
        for y in range(0, H, 3):
            cr.rectangle(0, y, W, 1)
        cr.fill()
        g = cairo.RadialGradient(W / 2, H / 2, min(W, H) * 0.3, W / 2, H / 2, max(W, H) * 0.75)
        g.add_color_stop_rgba(0, 0, 0, 0, 0)
        g.add_color_stop_rgba(1, 0, 0, 0, 0.6)
        cr.set_source(g)
        cr.paint()

        # transição em mosaico
        if self.wipe_t0 is not None:
            wt = (t - self.wipe_t0) / self.WIPE
            T = P * 8
            cols, rows = W // T + 1, H // T + 1
            cr.set_source_rgb(*BG)
            for j in range(rows):
                for i in range(cols):
                    k = clamp((wt - (i + j) / (cols + rows) * 0.6) / 0.4)
                    if k > 0:
                        s = int(T * k) + 1
                        cr.rectangle(i * T + (T - s) // 2, j * T + (T - s) // 2, s, s)
            cr.fill()


# ───────────────────────── painel de um agente ─────────────────────────
SESSION_FLAGS = ("-c", "--continue", "-r", "--resume", "--session-id")
# variáveis que uma sessão do Claude Code passa aos processos filhos: se o CLARK for aberto de dentro
# de uma, cada agente se acharia uma subsessão (e não salvaria o histórico da conversa). Configurações
# do usuário (ex.: CLAUDE_CODE_USE_BEDROCK) ficam de fora desta lista e continuam chegando aos agentes.
PARENT_SESSION_VARS = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID",
                       "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH",
                       "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN")


AUTO_NAME = re.compile(r"AGENT \d+$")
TASK_NAME_MAX = 40  # nome de agente vindo de uma tarefa do TODO
# diálogo de confiança do Claude Code (na pasta home ele nunca fica salvo).
# Comparado sem espaços/quebras: no painel estreito a frase quebra em várias linhas.
TRUST_PROMPT = re.compile(r"Yes,Itrustthisfolder|Doyoutrustthefilesinthisfolder")
TRUST_YES_SELECTED = re.compile(r"❯\d*\.?Yes,Itrust")


def trust_folder(path):
    """Marca a pasta como confiável no ~/.claude.json, para o claude abrir sem o diálogo de confiança.
    A home fica de fora: confiar nela vale para tudo abaixo dela (aí sobra o aceite pela tela)."""
    path = os.path.realpath(path)
    if path == os.path.realpath(os.path.expanduser("~")):
        return
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~")
    cfg = os.path.join(base, ".claude.json")
    try:
        with open(cfg) as f:
            data = json.load(f)
        proj = data.setdefault("projects", {}).setdefault(path, {})
        if proj.get("hasTrustDialogAccepted"):
            return
        proj["hasTrustDialogAccepted"] = True
        tmp = f"{cfg}.clark-{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, cfg)  # troca atômica: o claude nunca lê um arquivo pela metade
    except (OSError, ValueError, AttributeError):
        pass


def claude_session_exists(sid):
    """A conversa só existe (e pode ser retomada) depois que o claude grava o .jsonl dela."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return bool(glob(os.path.join(base, "projects", "*", f"{sid}.jsonl")))


class AgentPane(Gtk.Box):
    def __init__(self, app, idx, cwd, color, name=None, session_id=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app, self.cwd, self.color = app, cwd, color
        self.color_idx = AGENT_COLORS.index(color) if color in AGENT_COLORS else 0
        self.name = name or f"AGENT {idx}"
        self.session_id = session_id or str(uuid.uuid4())
        self.state = "BOOT"  # BOOT, WORKING, IDLE, DONE, EXITED
        self.pid = None
        self.last_change = 0.0
        self.last_input = 0.0
        self.mute_until = 0.0
        self.work_start = None
        self.has_input = False
        self.spawn_time = time.monotonic()
        self.get_style_context().add_class("pane")

        head = Gtk.Box()
        head.get_style_context().add_class("pane-head")
        self.head_area = Gtk.DrawingArea()
        self.head_area.set_size_request(-1, 30)
        self.head_area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.head_area.connect("draw", self._draw_head)
        self.head_area.connect("button-press-event", self._head_click)
        head.pack_start(self.head_area, True, True, 0)
        for label, tip, cb, extra in (("[ ]", "Zoom (Ctrl+Shift+Enter)", lambda *_: app.toggle_zoom(self), None),
                                      ("X", "Fechar (Ctrl+Shift+W)", lambda *_: app.close_agent(self), "close")):
            b = Gtk.Button(label=label)
            b.set_tooltip_text(tip)
            b.set_can_focus(False)
            b.get_style_context().add_class("mini")
            if extra:
                b.get_style_context().add_class(extra)
            b.connect("clicked", cb)
            head.pack_start(b, False, False, 0)

        self.term = t = Vte.Terminal()
        t.set_font(Pango.FontDescription(app.config.get("font", "Monospace 11")))
        t.set_font_scale(app.font_scale)
        self.apply_theme()
        t.set_scrollback_lines(20000)
        t.set_cursor_shape(Vte.CursorShape.BLOCK)
        t.set_mouse_autohide(True)
        t.set_allow_hyperlink(True)
        t.set_hexpand(True)
        t.set_vexpand(True)
        t.connect("contents-changed", self._on_contents)
        t.connect("commit", self._on_commit)
        t.connect("child-exited", self._on_exit)
        t.connect("focus-in-event", self._on_focus)
        # clique no terminal sempre traz o foco de volta (ex.: vindo do campo do TODO)
        t.connect("button-press-event", lambda *_: (t.has_focus() or t.grab_focus()) and False)
        t.connect("key-press-event", self._on_key)
        t.connect("bell", lambda *_: self._attention())
        t.connect("size-allocate", lambda *_: self.mute(0.5))

        body = Gtk.Box()
        body.pack_start(t, True, True, 0)
        body.pack_start(Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL, adjustment=t.get_vadjustment()),
                        False, False, 0)
        self.pack_start(head, False, False, 0)
        self.pack_start(body, True, True, 0)
        self.show_all()
        self.preview, self.preview_at = [], 0.0
        self.card = AgentCard(app, self)
        self.spawn()

    def apply_theme(self):
        def rgba(h):
            c = Gdk.RGBA()
            c.parse(h)
            return c
        self.color = AGENT_COLORS[self.color_idx % len(AGENT_COLORS)]
        self.term.set_colors(rgba(THEME["ink"]), rgba(THEME["bg"]), [rgba(h) for h in TERM_PALETTE])
        self.term.set_color_cursor(rgba(THEME["accent"]))
        self.term.set_color_cursor_foreground(rgba(THEME["bg"]))

    # ── processo ──
    def spawn(self):
        self.state = "BOOT"
        self.spawn_time = time.monotonic()
        self.has_input = False
        self.auto_trust = False
        self._set_class("exited", False)
        if self.app.claude:
            argv = [self.app.claude] + self.app.claude_args
            if not any(a.split("=")[0] in SESSION_FLAGS for a in self.app.claude_args):
                resume = claude_session_exists(self.session_id)
                argv += ["--resume" if resume else "--session-id", self.session_id]
            # opcional ("auto_trust" no config): a pasta foi escolhida no próprio CLARK, então já marca
            # como confiável e, se o diálogo aparecer mesmo assim (ex.: home), aceita pela tela
            if self.app.config.get("auto_trust", False):
                trust_folder(self.cwd)
                self.auto_trust = True
        else:
            self.term.feed(b"\r\n\x1b[1;31m  claude nao encontrado no PATH.\x1b[0m"
                           b" Instale o Claude Code e reabra o CLARK.\r\n\r\n")
            argv = [os.environ.get("SHELL", "/bin/bash")]
        env = [f"{k}={v}" for k, v in os.environ.items() if k not in ("TERM", "COLORTERM")]
        env += ["TERM=xterm-256color", "COLORTERM=truecolor", f"CLARK_AGENT={self.name}"]
        cwd = self.cwd if os.path.isdir(self.cwd) else os.path.expanduser("~")
        self.term.spawn_async(Vte.PtyFlags.DEFAULT, cwd, argv, env, GLib.SpawnFlags.DEFAULT,
                              None, None, -1, None, self._spawned)

    def _spawned(self, _term, pid, error, *_):
        if error:
            self.term.feed(f"\r\n\x1b[31mfalha ao iniciar: {error}\x1b[0m\r\n".encode())
            self.state = "EXITED"
        else:
            self.pid = pid

    def kill(self):
        if self.pid and self.state != "EXITED":
            try:
                os.kill(self.pid, signal.SIGHUP)
            except OSError:
                pass

    def _on_exit(self, _term, _status):
        self.state = "EXITED"
        self.pid = None
        self._set_class("exited", True)
        self._set_class("done", False)
        self.term.feed(b"\r\n\r\n\x1b[1;41;97m  GAME OVER  \x1b[0m  \x1b[2mENTER = continue?  "
                       b"CTRL+SHIFT+W = sair\x1b[0m\r\n")
        self.head_area.queue_draw()

    def _on_key(self, _term, ev):
        if self.state == "EXITED" and ev.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.term.reset(True, True)
            self.spawn()
            return True
        return False

    # ── detecção de atividade ──
    def mute(self, secs):
        self.mute_until = max(self.mute_until, time.monotonic() + secs)

    def _on_commit(self, *_):
        self.last_input = time.monotonic()
        self.has_input = True
        if self.state == "DONE":
            self.state = "IDLE"
            self._set_class("done", False)

    def _on_contents(self, _term):
        now = time.monotonic()
        if self.auto_trust:
            self._maybe_accept_trust(now)
        if now < self.mute_until or now - self.last_input < 0.3:
            return
        self.last_change = now

    def _maybe_accept_trust(self, now):
        if now - self.spawn_time > 60 or self.has_input:
            self.auto_trust = False
            return
        t = self.term
        try:
            row = t.get_cursor_position()[1]  # tela atual, mesmo com histórico longo acima
            text = t.get_text_range(max(0, row - t.get_row_count()), 0, row + t.get_row_count(),
                                    t.get_column_count() - 1, None, None)[0] or ""
        except (TypeError, GLib.Error):
            return
        flat = re.sub(r"\s+", "", text)
        if TRUST_PROMPT.search(flat):
            self.auto_trust = False
            # o padrão selecionado é "No, exit": desce para "Yes, I trust this folder" antes do Enter
            if TRUST_YES_SELECTED.search(flat):
                GLib.timeout_add(150, self._send_keys, b"\r")
            else:
                GLib.timeout_add(150, self._send_keys, b"\x1b[B")
                GLib.timeout_add(450, self._send_keys, b"\r")

    def _send_keys(self, data):
        try:
            self.term.feed_child(data)
        except TypeError:
            self.term.feed_child(data.decode(), len(data))
        return False

    def refresh_preview(self, now):
        """Últimas linhas úteis do terminal, para o card da lista lateral."""
        self.preview_at = now
        t = self.term
        # lê pelas linhas acima do cursor: terminal oculto não atualiza a viewport,
        # e no Claude Code isso pula a caixa de input
        try:
            row = t.get_cursor_position()[1]
            text = t.get_text_range(max(0, row - t.get_row_count()), 0, max(0, row - 1),
                                    t.get_column_count() - 1, None, None)[0]
        except (TypeError, GLib.Error):
            return
        lines = []
        for ln in (text or "").splitlines():
            ln = ln.strip().strip("│┃|").strip()
            if not ln or all(c in "─━═╭╮╰╯┌┐└┘│┃>❯·•* " for c in ln):
                continue
            lines.append(ln)
        self.preview = lines[-2:]

    def update(self, now):
        if self.state == "EXITED":
            return
        if now - self.last_change < 1.0:
            if self.state != "WORKING":
                self.state = "WORKING"
                self.work_start = now
                self._set_class("done", False)
        elif self.state == "WORKING":
            worked = now - (self.work_start or now)
            if self.has_input and worked > 2.5 and not self.app.is_watching(self):
                self._attention()
            else:
                self.state = "IDLE"
            self.work_start = None
        elif self.state == "BOOT" and now - self.spawn_time > 2.0:
            self.state = "IDLE"

    def _attention(self):
        if self.app.is_watching(self) or self.state == "EXITED":
            if self.state == "WORKING":
                self.state = "IDLE"
            return
        self.state = "DONE"
        self._set_class("done", True)
        self.app.notify_done(self)

    def _on_focus(self, *_):
        self.mute(0.3)
        self.app.set_focused(self)
        if self.state == "DONE":
            self.state = "IDLE"
            self._set_class("done", False)
        return False

    def _set_class(self, cls, on):
        ctx = self.get_style_context()
        (ctx.add_class if on else ctx.remove_class)(cls)

    # ── cabeçalho ──
    def _head_click(self, _w, ev):
        if ev.type == Gdk.EventType._2BUTTON_PRESS:
            self._rename()
        else:
            self.term.grab_focus()
        return True

    def _rename(self):
        pop = Gtk.Popover(relative_to=self.head_area)
        entry = Gtk.Entry(text=self.name)
        entry.set_max_length(20)

        def done(_e):
            self.name = norm(entry.get_text().strip()) or self.name
            self.app.save_config()
            pop.popdown()
            self.head_area.queue_draw()
            self.term.grab_focus()
        entry.connect("activate", done)
        pop.add(entry)
        pop.show_all()
        entry.grab_focus()

    def _draw_head(self, w, cr):
        W, H, t = w.get_allocated_width(), w.get_allocated_height(), self.app.t
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.set_source_rgb(*BG2)
        cr.paint()
        st = self.state
        working = st in ("WORKING", "BOOT")
        f = int(t * 8) % 2
        rows = mascot_rows(step=f if working else 0,
                           blink=st == "IDLE" and (t % 3.1) < 0.15,
                           sleep=st == "EXITED",
                           arms_up=(working and f) or (st == "DONE" and int(t * 4) % 2 == 0),
                           fire=f + 1 if st == "WORKING" else 0)
        p = 2
        draw_sprite(cr, rows, 8, (H - SPRITE_H * p) // 2 - (1 if working and f else 0), p, sprite_pal(self.color))
        x = 8 + (SPRITE_W + 4) * p + 8
        name = fit_text(self.name, 2, max(60, W - x - 200))
        draw_text(cr, name, x, (H - 14) // 2, 2, INK, shadow=SHADOW)
        x += text_w(name, 2) + 14

        label, col = {
            "BOOT": ("BOOT" + "." * (int(t * 4) % 4), YELLOW),
            "WORKING": ("WORKING" + "." * (int(t * 4) % 4), GREEN),
            "IDLE": ("IDLE", DIM),
            "DONE": ("DONE!", YELLOW),
            "EXITED": ("GAME OVER", RED),
        }[st]
        pw = text_w("WORKING...", 1 if W < 300 else 2) + 16
        sc = 1 if W < 300 else 2
        px, py, ph = W - pw - 6, (H - 20) // 2, 20
        if st == "DONE" and int(t * 3) % 2 == 0:
            cr.set_source_rgb(*col)
            cr.rectangle(px, py, pw, ph)
            cr.fill()
            tc = BG
        else:
            cr.set_source_rgba(*col, 0.15)
            cr.rectangle(px, py, pw, ph)
            cr.fill()
            cr.set_source_rgb(*col)
            for r in ((px, py, pw, 2), (px, py + ph - 2, pw, 2), (px, py, 2, ph), (px + pw - 2, py, 2, ph)):
                cr.rectangle(*r)
            cr.fill()
            tc = col
        draw_text(cr, label, px + 8, py + (ph - 7 * sc) // 2, sc, tc)

        room = px - x - 10
        if room > 60:
            cr.save()
            cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
            lay = PangoCairo.create_layout(cr)
            lay.set_font_description(Pango.FontDescription("Monospace 8"))
            lay.set_text(self.app.short_path(self.cwd), -1)
            lay.set_width(room * Pango.SCALE)
            lay.set_ellipsize(Pango.EllipsizeMode.START)
            _, lh = lay.get_pixel_size()
            cr.move_to(x, (H - lh) // 2)
            cr.set_source_rgb(*DIM)
            PangoCairo.show_layout(cr, lay)
            cr.restore()


STATE_LABELS = {
    "BOOT": ("BOOT", YELLOW), "WORKING": ("WORKING", GREEN), "IDLE": ("IDLE", DIM),
    "DONE": ("DONE!", YELLOW), "EXITED": ("GAME OVER", RED),
}


class AgentCard(Gtk.DrawingArea):
    """Card compacto de um agente na lista lateral do modo foco."""
    H = 86

    def __init__(self, app, pane):
        super().__init__()
        self.app, self.pane, self.hover = app, pane, False
        self.set_size_request(-1, self.H)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._click)
        self.connect("enter-notify-event", lambda *_: self._set_hover(True))
        self.connect("leave-notify-event", lambda *_: self._set_hover(False))
        self.set_tooltip_text("Clique: abrir no painel principal · X ou botão do meio: fechar")

    def _set_hover(self, on):
        self.hover = on
        self.queue_draw()

    def _close_rect(self):
        W = self.get_allocated_width()
        return W - 26, 4, 22, 20

    def _click(self, _w, ev):
        cx, cy, cw, ch = self._close_rect()
        if ev.button == 1 and cx <= ev.x <= cx + cw and cy <= ev.y <= cy + ch:
            self.app.close_agent(self.pane)
        elif ev.button == 2:
            self.app.close_agent(self.pane)
        elif ev.button == 1:
            self.app.select(self.pane)
        return True

    def _draw(self, w, cr):
        W, H, t, p = w.get_allocated_width(), w.get_allocated_height(), self.app.t, self.pane
        st = p.state
        active = p is self.app.main_pane
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        bg = BG3 if self.hover else BG2
        cr.set_source_rgb(*(mix(bg, ORANGE, 0.18) if active else bg))
        cr.paint()
        border = {"DONE": YELLOW, "EXITED": RED}.get(st)
        if active:
            border, bw = ORANGE, 3
        else:
            bw = 2
            if st == "DONE" and int(t * 3) % 2:
                border = None
        if border:
            cr.set_source_rgb(*border)
            for r in ((0, 0, W, bw), (0, H - bw, W, bw), (W - bw, 0, bw, H)):
                cr.rectangle(*r)
            cr.fill()
        cr.set_source_rgb(*p.color)
        cr.rectangle(0, 0, 6 if active else 4, H)
        cr.fill()

        working = st in ("WORKING", "BOOT")
        f = int(t * 8) % 2
        rows = mascot_rows(step=f if working else 0, blink=st == "IDLE" and (t % 3.1) < 0.15,
                           sleep=st == "EXITED", arms_up=(working and f) or (st == "DONE" and int(t * 4) % 2 == 0),
                           fire=f + 1 if st == "WORKING" else 0)
        draw_sprite(cr, rows, 12, 10 - (1 if working and f else 0), 2, sprite_pal(p.color))
        x = 12 + (SPRITE_W + 2) * 2 + 6
        idx = self.app.panes.index(p) + 1 if p in self.app.panes else 0
        if self.hover:
            cx, cy, cw, ch = self._close_rect()
            cr.set_source_rgb(*RED)
            cr.rectangle(cx, cy, cw, ch)
            cr.fill()
            draw_text(cr, "X", cx + (cw - 5) // 2, cy + (ch - 7) // 2, 1, BG)
        elif active:
            tag = "EM FOCO"
            tw = text_w(tag, 1)
            cr.set_source_rgb(*ORANGE)
            cr.rectangle(W - tw - 14, 6, tw + 8, 13)
            cr.fill()
            draw_text(cr, tag, W - tw - 10, 9, 1, BG)
        elif idx <= 9:
            draw_text(cr, str(idx), W - 16, 10, 1, DIM)
        name_w = W - x - (text_w("EM FOCO", 1) + 20 if active else 24)
        draw_text(cr, fit_text(p.name, 2, name_w), x, 10, 2, ORANGE if active else INK, shadow=SHADOW)

        label, col = STATE_LABELS[st]
        if working:
            label += "." * (int(t * 4) % 4)
        cr.set_source_rgb(*col)
        cr.rectangle(x, 31, 5, 5)
        cr.fill()
        draw_text(cr, label, x + 9, 30, 1, col)

        cr.save()
        cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
        lay = PangoCairo.create_layout(cr)
        lay.set_font_description(Pango.FontDescription("Monospace 8"))
        lay.set_ellipsize(Pango.EllipsizeMode.START)
        lay.set_text(self.app.short_path(p.cwd), -1)
        px = x + 9 + text_w("WORKING...", 1) + 10
        lay.set_width(max(1, W - px - 22) * Pango.SCALE)
        cr.move_to(px, 27)
        cr.set_source_rgb(*mix(DIM, BG, 0.3))
        PangoCairo.show_layout(cr, lay)
        lay.set_width(max(1, W - 24) * Pango.SCALE)
        lay.set_ellipsize(Pango.EllipsizeMode.END)
        y = 46
        for ln in p.preview or ["…"]:
            lay.set_text(ln, -1)
            cr.move_to(12, y)
            cr.set_source_rgb(*(INK if active else DIM))
            PangoCairo.show_layout(cr, lay)
            y += 16
        cr.restore()


# ───────────────────────── dragões voando pela tela ─────────────────────────
class DragonSky(Gtk.Overlay):
    """Overlay em volta dos agentes com um dragão voando para cada agente.

    Cada dragão é um DrawingArea pequeno, do tamanho do sprite, que se move por cima dos terminais
    (uma camada do tamanho da tela inteira engolia todos os cliques no GTK 3). Só o próprio dragão
    pega o clique, e clicar nele traz o agente dele. É semitransparente para não esconder o texto.
    O voo segue o estado do agente: trabalhando voa rápido cuspindo fogo, ocioso plana devagar com
    pausas, DONE dá pulinhos, GAME OVER pousa e dorme.
    """
    P = 3
    ALPHA = 0.55
    MARGIN = 12

    def __init__(self, app, child):
        super().__init__()
        self.app = app
        self.on = True
        self.dragons = {}
        self.last = time.monotonic()
        self.add(child)
        self.connect("get-child-position", self._child_pos)
        GLib.timeout_add(40, self._step)

    def set_on(self, on):
        self.on = on
        for d in self.dragons.values():
            d["w"].set_visible(on)

    def _child_pos(self, _o, widget, rect):
        d = next((d for d in self.dragons.values() if d["w"] is widget), None)
        if not d or not d["box"]:
            return False
        rect.x, rect.y, rect.width, rect.height = d["box"]
        return True

    def _size(self):
        return SPRITE_W * self.P, SPRITE_H * self.P

    def _bounds(self):
        W, H = self.get_allocated_width(), self.get_allocated_height()
        w, h = self._size()
        m = self.MARGIN
        return m, max(m + 1, W - w - m), m, max(m + 1, H - h - m)

    def _new_target(self, d):
        x0, x1, y0, y1 = self._bounds()
        d["tx"], d["ty"] = random.uniform(x0, x1), random.uniform(y0, y1)

    def _dragon(self, key):
        d = self.dragons.get(key)
        if d is None:
            x0, x1, y0, y1 = self._bounds()
            x, y = random.uniform(x0, x1), random.uniform(y0, y1)
            w = Gtk.DrawingArea()
            w.set_can_focus(False)
            w.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            w.set_tooltip_text(key.name if key != "wild" else None)
            w.connect("draw", self._draw, key)
            w.connect("button-press-event", lambda *_: (key != "wild" and self.app.select(key)) or True)
            d = self.dragons[key] = dict(x=x, y=y, tx=x, ty=y, face=random.choice((1, -1)), pause=0.0,
                                         hop=0.0, vy=0.0, anim=random.random() * 10, box=None, w=w)
            d["box"] = self._box(d)
            self.add_overlay(w)
            w.set_visible(self.on)
        return d

    def _box(self, d):
        """Retângulo ocupado pelo dragão (com folga para fogo, pulo e Zzz)."""
        w, h = self._size()
        x = int(d["x"]) - 6 * self.P
        y = int(d["y"] - d["hop"]) - 4 * self.P
        return x, y, w + 12 * self.P, h + 6 * self.P

    def _step(self):
        now = time.monotonic()
        dt, self.last = min(0.1, now - self.last), now
        if not self.get_mapped() or not self.on:
            return True
        keys = self.app.panes or ["wild"]
        for k in list(self.dragons):
            if k not in keys:
                self.dragons.pop(k)["w"].destroy()
        x0, x1, y0, y1 = self._bounds()
        moved = False
        for k in keys:
            d = self._dragon(k)
            st = k.state if k != "wild" else "IDLE"
            d["anim"] += dt
            fast = st in ("WORKING", "BOOT")
            if st == "EXITED":  # pousa no chão e dorme
                d["tx"], d["ty"] = d["x"], y1
            elif st == "DONE":
                d["tx"], d["ty"] = d["x"], d["y"]
                if d["hop"] <= 0 and d["vy"] <= 0:
                    d["vy"] = 110.0
            dx, dy = d["tx"] - d["x"], d["ty"] - d["y"]
            dist = math.hypot(dx, dy)
            if dist < 3:
                if st not in ("EXITED", "DONE") and (fast or now > d["pause"]):
                    self._new_target(d)
                    if not fast:
                        d["pause"] = now + random.uniform(1.0, 4.0)
            elif now > d["pause"] or fast or st == "EXITED":
                speed = 150.0 if fast else 45.0
                step = min(speed * dt, dist)
                d["x"] = clamp(d["x"] + dx / dist * step, x0, x1)
                d["y"] = clamp(d["y"] + dy / dist * step, y0, y1)
                if abs(dx) > 1:
                    d["face"] = 1 if dx > 0 else -1
            if d["vy"] or d["hop"] > 0:  # pulinho com gravidade
                d["hop"] += d["vy"] * dt
                d["vy"] -= 600.0 * dt
                if d["hop"] <= 0:
                    d["hop"], d["vy"] = 0.0, 0.0
            box = self._box(d)
            if box != d["box"]:
                d["box"] = box
                moved = True
            d["w"].queue_draw()
        if moved:
            self.queue_allocate()  # só reposiciona os dragões; os terminais mantêm o tamanho
        return True

    def _draw(self, w, cr, k):
        d = self.dragons.get(k)
        if not d or not d["box"]:
            return False
        P = self.P
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.translate(-d["box"][0], -d["box"][1])  # desenha em coordenadas do overlay
        st = k.state if k != "wild" else "IDLE"
        color = k.color if k != "wild" else ORANGE
        fast = st in ("WORKING", "BOOT")
        flap = int(d["anim"] * (9 if fast else 4)) % 2 if st != "EXITED" else 0
        fire = (int(d["anim"] * 8) % 2 + 1) if st == "WORKING" and int(d["anim"] * 1.5) % 3 == 0 else 0
        rows = mascot_rows(step=0, blink=(d["anim"] % 3.3) < 0.15, sleep=st == "EXITED",
                           arms_up=bool(flap), fire=fire)
        cols = max(len(r) for r in rows)
        rows = [r.ljust(cols, ".") for r in rows]
        x = d["x"]
        if d["face"] < 0:
            rows = [r[::-1] for r in rows]
            x -= (cols - SPRITE_W) * P
        bob = 0 if st == "EXITED" else math.sin(d["anim"] * 3.0) * 3
        y = int(d["y"] - d["hop"] + bob)
        draw_sprite(cr, rows, int(x), y, P, sprite_pal(color), alpha=self.ALPHA)
        if st == "EXITED":
            k_ = (d["anim"] * 0.6) % 1.0
            draw_text(cr, "Z", int(d["x"]) + SPRITE_W * P + int(k_ * 8), y - int(k_ * 10) + 2, 2, INK,
                      alpha=(1 - k_) * self.ALPHA)
        return False


# ───────────────────────── janela principal ─────────────────────────
CSS = """
.sidebar { background-color: $bg; border-left: 3px solid $shadow; }
.sidebar-list { padding: 3px 0 3px 3px; }
window.clark { background-color: $bg; }
.topbar { background-color: $bg2; border-bottom: 3px solid $shadow; padding: 6px 10px; }
button.px {
  font-family: monospace; font-weight: 800; font-size: 11px; color: $ink;
  background-image: none; background-color: $bg3; border: 2px solid $shadow; border-radius: 0;
  box-shadow: 3px 3px 0 0 $shadow; padding: 4px 12px; text-shadow: none; min-height: 0;
  transition: background-color 120ms, box-shadow 80ms;
}
button.px:hover { background-color: $bg4; }
button.px:active { box-shadow: 0 0 0 0 $shadow; background-color: $bg5; }
button.px.primary { background-color: $accent; color: $on_accent; }
button.px.primary:hover { background-color: $accent_hi; }
button.px.primary:active { background-color: $accent_lo; }
button.mini {
  font-family: monospace; font-weight: 800; font-size: 10px; color: $dim;
  background-image: none; background-color: $bg2; border: none; box-shadow: none;
  border-radius: 0; padding: 0 9px; min-height: 0; min-width: 0; text-shadow: none;
}
button.mini:hover { color: $ink; background-color: $bg3; }
button.mini.close:hover { color: $on_accent; background-color: $red; }
.pane { border: 3px solid $bg3; background-color: $bg; transition: border-color 180ms ease-out; }
.pane.focused { border-color: $accent; }
.pane.done { border-color: $yellow; }
.pane.exited { border-color: $red; }
.side-head { background-color: $bg2; }
.pane-head { background-color: $bg2; border-bottom: 2px solid $shadow; }
vte-terminal { padding: 4px 6px; }
scrollbar, scrollbar trough { background-color: $bg; border: none; }
scrollbar slider { background-color: $bg4; border-radius: 0; min-width: 6px; border: none; }
scrollbar slider:hover { background-color: $accent; }
popover { background-color: $bg2; border: 2px solid $accent; border-radius: 0; box-shadow: 4px 4px 0 $shadow; }
popover label { color: $ink; font-family: monospace; }
popover entry { font-family: monospace; background-color: $bg; color: $ink; border-radius: 0;
  border: 2px solid $bg4; box-shadow: none; }
.todo-panel { background-color: $bg; border-left: 3px solid $shadow; }
.todo-panel label { color: $ink; font-family: monospace; }
.todo-panel entry { font-family: monospace; background-color: $bg; color: $ink; border-radius: 0;
  border: 2px solid $bg4; box-shadow: none; }
.todo-panel entry.todo-text { background-color: transparent; border: 2px solid transparent; padding: 2px 4px; }
.todo-panel entry.todo-text:focus { background-color: $bg2; border-color: $accent; }
.todo-panel entry.todo-text.done { color: $dim; text-decoration-line: line-through; }
.todo-row:hover { background-color: $bg3; }
label.todo-dim { color: $dim; font-size: 10px; }
button.mini.agent { color: $accent; }
button.mini.agent:hover { color: $on_accent; background-color: $accent; }
.todo-panel check { background-image: none; background-color: $bg; border: 2px solid $bg4; border-radius: 0;
  color: $on_accent; min-width: 12px; min-height: 12px; }
.todo-panel check:checked { background-color: $green; border-color: $green; }
button.px.theme-opt { padding: 4px 10px; }
popover button.px.primary label { color: $on_accent; }
"""


def theme_css():
    return Template(CSS).substitute({k: v for k, v in THEME.items() if isinstance(v, str)}).encode()


GEAR = ["....#....",
        ".#.###.#.",
        "..#####..",
        ".##...##.",
        "###...###",
        ".##...##.",
        "..#####..",
        ".#.###.#.",
        "....#...."]

HELP = """\
 CTRL+SHIFT+N        novo agente
 CTRL+SHIFT+W        fechar agente
 CTRL+SHIFT+ENTER    zoom no agente
 CTRL+SHIFT+L        alternar layout foco / grade
 CTRL+SHIFT+← / →    agente anterior/próximo
 ALT+1..9            pular para o agente N
 CTRL+SHIFT+D        trocar pasta
 CTRL+SHIFT+T        mostrar/esconder TODO
 CTRL+SHIFT+C / V    copiar / colar
 CTRL+SHIFT+ + / -   fonte maior / menor
 duplo clique        renomear agente
 ENTER (game over)   reiniciar agente
"""


class TodoList(Gtk.Box):
    """Listinha de tarefas: Enter adiciona, clique no texto edita, > abre um agente, [x] remove."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.app = app
        self.items = [dict(text=str(t.get("text", "")), done=bool(t.get("done")))
                      for t in app.config.get("todos", []) if isinstance(t, dict)]
        for m in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{m}")(8)
        self.entry = Gtk.Entry(placeholder_text="nova tarefa + ENTER")
        self.entry.connect("activate", self._on_add)
        self.pack_start(self.entry, False, False, 0)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll.add(self.rows)
        self.pack_start(scroll, True, True, 0)
        foot = Gtk.Box(spacing=6)
        self.footer = Gtk.Label(xalign=0)
        self.footer.get_style_context().add_class("todo-dim")
        foot.pack_start(self.footer, True, True, 0)
        self.clear_btn = Gtk.Button(label="LIMPAR FEITAS")
        self.clear_btn.set_can_focus(False)
        self.clear_btn.get_style_context().add_class("mini")
        self.clear_btn.connect("clicked", lambda *_: self.clear_done())
        foot.pack_start(self.clear_btn, False, False, 0)
        self.pack_start(foot, False, False, 0)
        self._rebuild()

    def pending(self):
        return sum(not t["done"] for t in self.items)

    def _changed(self):
        self.app.config["todos"] = self.items
        self.app.save_config()
        self.app.update_todo_badge()
        done = sum(t["done"] for t in self.items)
        self.footer.set_text(f"{done}/{len(self.items)} feitas" if self.items else "nenhuma tarefa ainda")
        self.clear_btn.set_visible(bool(done))
        self.clear_btn.set_no_show_all(True)

    def _rebuild(self):
        for c in self.rows.get_children():
            c.destroy()
        for item in self.items:
            self.rows.pack_start(self._row(item), False, False, 0)
        self.rows.show_all()
        self._changed()

    def _row(self, item):
        row = Gtk.Box(spacing=4)
        row.get_style_context().add_class("todo-row")
        chk = Gtk.CheckButton(active=item["done"])
        chk.set_can_focus(False)
        ent = Gtk.Entry(text=item["text"], has_frame=False, hexpand=True)
        ent.get_style_context().add_class("todo-text")
        if item["done"]:
            ent.get_style_context().add_class("done")

        def toggle(b):
            item["done"] = b.get_active()
            (ent.get_style_context().add_class if item["done"] else ent.get_style_context().remove_class)("done")
            self._changed()

        def commit(*_):
            txt = ent.get_text().strip()
            if not txt:
                self._remove(item)
            elif txt != item["text"]:
                item["text"] = txt
                self._changed()
            return False

        chk.connect("toggled", toggle)
        ent.connect("activate", lambda *_: (commit(), self.entry.grab_focus()))
        ent.connect("focus-out-event", commit)
        go = Gtk.Button(label="ABRIR AGENTE")
        go.set_can_focus(False)
        go.set_tooltip_text("Abrir um agente Claude com o nome desta tarefa")
        go.get_style_context().add_class("mini")
        go.get_style_context().add_class("agent")
        go.connect("clicked", lambda *_: (commit(), self.app.open_task_agent(item["text"])))
        rm = Gtk.Button(label="x")
        rm.set_can_focus(False)
        rm.set_tooltip_text("Remover tarefa")
        rm.get_style_context().add_class("mini")
        rm.get_style_context().add_class("close")
        rm.connect("clicked", lambda *_: self._remove(item))
        row.pack_start(chk, False, False, 0)
        row.pack_start(ent, True, True, 0)
        row.pack_start(go, False, False, 0)
        row.pack_start(rm, False, False, 0)
        return row

    def _on_add(self, e):
        txt = e.get_text().strip()
        if txt:
            self.items.append(dict(text=txt, done=False))
            e.set_text("")
            self._rebuild()

    def _remove(self, item):
        if item in self.items:
            self.items.remove(item)
            GLib.idle_add(lambda: self._rebuild() and False)

    def clear_done(self):
        self.items = [t for t in self.items if not t["done"]]
        self._rebuild()


class Clark(Gtk.Window):
    def __init__(self, opts):
        super().__init__(title="CLARK")
        self.config = self._load_config()
        self.claude = find_claude()
        self.claude_args = opts["claude_args"]
        self.cwd = opts["dir"] or self.config.get("cwd") or os.path.expanduser("~")
        self.font_scale = float(self.config.get("font_scale", 1.0))
        self.initial = opts["n"]
        self.panes, self.focused, self.zoomed = [], None, None
        self.main_pane = None
        self.restored = False  # só grava a lista de agentes depois de restaurar a sessão anterior
        self.fresh = opts["fresh"]
        self.layout_mode = self.config.get("layout", "focus")
        self.dragons_on = bool(self.config.get("dragons", True))
        self.todo_visible = bool(self.config.get("todo_visible", True))
        self.t_start = time.monotonic()
        self.t = 0.0
        self.week_pct = None  # uso semanal real (0-100), None até a primeira leitura
        self.week_reset = ""
        self.heat = 0.0       # valor animado que o caldeirão mostra

        self.get_style_context().add_class("clark")
        self.set_default_size(1360, 840)
        self.set_size_request(760, 520)
        self.set_icon_list([Gdk.pixbuf_get_from_surface(make_icon_surface(n), 0, 0, n, n)
                            for n in (32, 48, 64, 128, 256)])  # antes do tema: o ícone é sempre o mesmo
        self.theme = self.config.get("theme", "dark") if self.config.get("theme") in THEMES else "dark"
        apply_theme(self.theme)
        self.css = Gtk.CssProvider()
        self.css.load_from_data(theme_css())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.css,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", THEME["dark"])

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=350)
        self.splash = None
        self.stack.add_named(self._build_main(), "main")
        if not opts["no_splash"]:
            self.splash = Splash(self._enter_main)
            self.stack.add_named(self.splash, "splash")
        self.add(self.stack)

        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", self._on_delete)
        self.connect("focus-in-event", lambda *_: self.set_urgency_hint(False))
        GLib.timeout_add(100, self._tick)
        self._fetch_usage()
        GLib.timeout_add_seconds(USAGE_REFRESH_S, self._fetch_usage)
        self._check_claude()

        self.show_all()
        self.set_dragons(self.dragons_on)
        if self.splash:
            self.stack.set_visible_child_name("splash")
            self.splash.grab_focus()
        else:
            GLib.idle_add(self._enter_main)

    # ── config ──
    def _load_config(self):
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_config(self):
        self.config.update(cwd=self.cwd, font_scale=self.font_scale, layout=self.layout_mode, theme=self.theme,
                           dragons=self.dragons_on, todo_visible=self.todo_visible)
        if self.restored:
            self.config["agents"] = [dict(name=p.name, cwd=p.cwd, session_id=p.session_id,
                                          color=p.color_idx)
                                     for p in self.panes]
            self.config["main_agent"] = self.panes.index(self.main_pane) if self.main_pane in self.panes else 0
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f, indent=2)
        except OSError:
            pass

    def _check_claude(self):
        def status(txt, ok):
            if self.splash:
                self.splash.set_claude_status(txt, ok)
        if not self.claude:
            status("CLAUDE CLI NAO ENCONTRADO", False)
            return
        GLib.timeout_add(2500, lambda: (self.splash and not self.splash.claude_status
                                        and status("CLAUDE CLI ENCONTRADO", True)) and False)
        try:
            proc = Gio.Subprocess.new([self.claude, "--version"],
                                      Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error:
            status("CLAUDE CLI ENCONTRADO", True)
            return

        def done(p, res):
            try:
                _, out, _ = p.communicate_utf8_finish(res)
                ver = (out or "").split()[0] if (out or "").split() else ""
            except GLib.Error:
                ver = ""
            status(f"CLAUDE CLI V{ver} ENCONTRADO" if ver else "CLAUDE CLI ENCONTRADO", True)
        proc.communicate_utf8_async(None, None, done)

    # ── layout ──
    def _build_main(self):
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top = Gtk.Box(spacing=10)
        top.get_style_context().add_class("topbar")
        logo = Gtk.DrawingArea()
        logo.set_size_request(text_w("CLARK", 3) + 4, 34)
        logo.connect("draw", self._draw_logo)
        top.pack_start(logo, False, False, 0)
        self.stats = Gtk.DrawingArea()
        self.stats.connect("draw", self._draw_stats)
        top.pack_start(self.stats, False, False, 0)
        self.heat_area = Gtk.DrawingArea()
        self.heat_area.set_size_request(HEAT_W, 34)
        self.heat_area.connect("draw", self._draw_heat)
        top.pack_start(self.heat_area, True, True, 0)

        self.layout_btn = self._button("", lambda *_: self.toggle_layout(),
                                       tip="Alternar layout foco / grade (Ctrl+Shift+L)")
        self._update_layout_label()
        top.pack_start(self.layout_btn, False, False, 0)
        top.pack_start(self._button("+ AGENT", lambda *_: self.add_agents(1), primary=True,
                                    tip="Novo agente (Ctrl+Shift+N)"), False, False, 0)
        self.todo_btn = self._button("TODO", lambda *_: self.set_todo_visible(not self.todo_visible),
                                     tip="Mostrar/esconder TODO (Ctrl+Shift+T)")
        top.pack_start(self.todo_btn, False, False, 0)
        top.pack_start(self._build_config(), False, False, 0)
        help_btn = self._button("?", None, tip="Atalhos")
        pop = Gtk.Popover(relative_to=help_btn)
        lbl = Gtk.Label(label=HELP)
        lbl.set_margin_top(8)
        lbl.set_margin_bottom(8)
        lbl.set_margin_start(8)
        lbl.set_margin_end(8)
        pop.add(lbl)
        lbl.show()
        help_btn.connect("clicked", lambda *_: pop.popup())
        top.pack_start(help_btn, False, False, 0)
        v.pack_start(top, False, False, 0)

        self.content = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=200)
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.empty_area = Gtk.DrawingArea()
        self.empty_area.connect("draw", self._draw_empty)
        empty.pack_start(self.empty_area, True, True, 0)
        row = Gtk.Box(spacing=14, halign=Gtk.Align.CENTER)
        row.set_margin_bottom(90)
        for n in (1, 2, 4, 6):
            row.pack_start(self._button(f"{n} AGENTE" + ("S" if n > 1 else ""),
                                        lambda _b, n=n: self.add_agents(n), primary=n == 1), False, False, 0)
        empty.pack_start(row, False, False, 0)
        self.content.add_named(empty, "empty")

        self.grid = Gtk.Grid(row_spacing=6, column_spacing=6, row_homogeneous=True, column_homogeneous=True)
        for m in ("top", "bottom", "start", "end"):
            getattr(self.grid, f"set_margin_{m}")(6)
        self.content.add_named(self.grid, "grid")

        # modo foco: agente principal grande à esquerda, demais em lista à direita
        focus = Gtk.Box()
        self.main_slot = Gtk.Stack()  # todos os terminais ficam aqui; só o principal é visível
        for m in ("top", "bottom", "start", "end"):
            getattr(self.main_slot, f"set_margin_{m}")(6)
        focus.pack_start(self.main_slot, True, True, 0)
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.get_style_context().add_class("sidebar")
        self.sidebar.set_size_request(310, -1)
        head = Gtk.Box()
        head.get_style_context().add_class("side-head")
        side_head = Gtk.DrawingArea()
        side_head.set_size_request(-1, 30)
        side_head.connect("draw", self._draw_side_head)
        head.pack_start(side_head, True, True, 0)
        close_all = Gtk.Button(label="FECHAR TODOS")
        close_all.set_can_focus(False)
        close_all.set_tooltip_text("Fechar os outros agentes (ou todos)")
        close_all.get_style_context().add_class("mini")
        close_all.get_style_context().add_class("close")
        close_all.connect("clicked", lambda *_: self.close_all())
        head.pack_start(close_all, False, False, 0)
        self.sidebar.pack_start(head, False, False, 0)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.card_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.card_list.get_style_context().add_class("sidebar-list")
        scroll.add(self.card_list)
        self.sidebar.pack_start(scroll, True, True, 0)
        focus.pack_start(self.sidebar, False, False, 0)
        self.content.add_named(focus, "focus")
        # dragões voam por cima dos agentes (pintados depois deles; cliques passam direto)
        self.sky = sky = DragonSky(self, self.content)
        body = Gtk.Box()
        body.pack_start(sky, True, True, 0)
        body.pack_start(self._build_todo_panel(), False, False, 0)
        v.pack_start(body, True, True, 0)
        return v

    # ── TODO na página principal ──
    def _build_todo_panel(self):
        self.todo_panel = panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.get_style_context().add_class("todo-panel")
        panel.set_size_request(380, -1)
        head = Gtk.Box()
        head.get_style_context().add_class("side-head")
        self.todo_title = Gtk.Label(xalign=0)
        self.todo_title.set_margin_start(10)
        head.pack_start(self.todo_title, True, True, 0)
        hide = Gtk.Button(label="ESCONDER")
        hide.set_can_focus(False)
        hide.set_tooltip_text("Esconder TODO (Ctrl+Shift+T)")
        hide.get_style_context().add_class("mini")
        hide.connect("clicked", lambda *_: self.set_todo_visible(False))
        head.pack_start(hide, False, False, 0)
        head.set_size_request(-1, 30)
        panel.pack_start(head, False, False, 0)
        self.todo = TodoList(self)
        panel.pack_start(self.todo, True, True, 0)
        panel.set_no_show_all(True)  # visibilidade controlada por set_todo_visible
        for c in panel.get_children():
            c.show_all()
        panel.set_visible(self.todo_visible)
        self.update_todo_badge()
        return panel

    def set_todo_visible(self, on):
        self.todo_visible = on
        self.todo_panel.set_visible(on)
        self.update_todo_badge()
        self.save_config()
        if on:
            self.todo.entry.grab_focus()
        elif self.focused in self.panes:
            self.focused.term.grab_focus()

    def update_todo_badge(self):
        if not hasattr(self, "todo") or not hasattr(self, "todo_btn"):
            return
        n = self.todo.pending()
        self.todo_title.set_markup(f"<b>TODO</b>  <small>{n} pendente{'s' if n != 1 else ''}</small>")
        self.todo_btn.set_label(f"TODO {n}" if n else "TODO")
        (self.todo_btn.get_style_context().add_class if self.todo_visible
         else self.todo_btn.get_style_context().remove_class)("primary")

    def open_task_agent(self, text):
        """Abre (ou traz de volta) um agente Claude cujo nome é o texto da tarefa."""
        name = norm(" ".join(text.split()))
        if len(name) > TASK_NAME_MAX:
            name = name[:TASK_NAME_MAX - 3].rstrip() + "..."
        if not name:
            return
        pane = next((p for p in self.panes if p.name == name), None)
        if pane:
            self.zoomed = None
            self.select(pane)
            return
        pane = AgentPane(self, 0, self.cwd, AGENT_COLORS[self._free_color()], name=name)
        self.panes.append(pane)
        self.zoomed = None
        self.main_pane = pane
        self.relayout()
        self.save_config()
        GLib.idle_add(lambda: pane.term.grab_focus() and False)

    # ── engrenagem: ajustes (tema, fonte, dragões) ──
    def _build_config(self):
        self.cfg_btn = self._button("", None, tip="Ajustes")
        gear = Gtk.DrawingArea()
        gear.set_size_request(18, 18)
        gear.connect("draw", self._draw_gear)
        self.cfg_btn.remove(self.cfg_btn.get_child())
        self.cfg_btn.add(gear)
        self.cfg_pop = Gtk.Popover(relative_to=self.cfg_btn)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(8)

        adj = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        adj.set_size_request(320, -1)
        adj.pack_start(self._section("TEMA"), False, False, 0)
        self.theme_opts = {}
        for key, th in THEMES.items():
            b = self._button("", lambda _b, k=key: self.set_theme(k))
            b.get_style_context().add_class("theme-opt")
            row = Gtk.Box(spacing=8)
            sw = Gtk.DrawingArea()
            sw.set_size_request(30, 12)
            sw.connect("draw", self._draw_swatch, th)
            row.pack_start(sw, False, False, 0)
            row.pack_start(Gtk.Label(label=th["label"], xalign=0), True, True, 0)
            b.remove(b.get_child())
            b.add(row)
            adj.pack_start(b, False, False, 0)
            self.theme_opts[key] = b
        self._mark_theme()

        adj.pack_start(self._section("FONTE DOS TERMINAIS"), False, False, 0)
        frow = Gtk.Box(spacing=8)
        frow.pack_start(self._button("A-", lambda *_: self.set_font_scale(self.font_scale - 0.1),
                                     tip="Ctrl+Shift+-"), False, False, 0)
        self.font_lbl = Gtk.Label()
        frow.pack_start(self.font_lbl, True, True, 0)
        frow.pack_start(self._button("A+", lambda *_: self.set_font_scale(self.font_scale + 0.1),
                                     tip="Ctrl+Shift++"), False, False, 0)
        frow.pack_start(self._button("100%", lambda *_: self.set_font_scale(1.0), tip="Ctrl+Shift+0"),
                        False, False, 0)
        adj.pack_start(frow, False, False, 0)
        self._update_font_label()

        adj.pack_start(self._section("DRAGÕES VOANDO"), False, False, 0)
        self.dragon_btn = self._button("", lambda *_: self.set_dragons(not self.dragons_on))
        adj.pack_start(self.dragon_btn, False, False, 0)
        box.pack_start(adj, True, True, 0)
        self.cfg_pop.add(box)
        box.show_all()
        self.cfg_btn.connect("clicked", lambda *_: self.toggle_config())
        return self.cfg_btn

    @staticmethod
    def _section(text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.get_style_context().add_class("todo-dim")
        return lbl

    def _draw_gear(self, w, cr):
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        rows = GEAR
        p = max(1, min(w.get_allocated_width(), w.get_allocated_height()) // len(rows))
        ox = (w.get_allocated_width() - len(rows[0]) * p) // 2
        oy = (w.get_allocated_height() - len(rows) * p) // 2
        cr.set_source_rgb(*INK)
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch == "#":
                    cr.rectangle(ox + c * p, oy + r * p, p, p)
        cr.fill()

    def toggle_config(self):
        if self.cfg_pop.get_visible():
            self.cfg_pop.popdown()
        else:
            self.cfg_pop.popup()

    def _update_font_label(self):
        self.font_lbl.set_text(f"{round(self.font_scale * 100)}%")

    def set_dragons(self, on):
        self.dragons_on = on
        self.sky.set_on(on)
        self.dragon_btn.set_label("LIGADOS  -  CLIQUE PARA ESCONDER" if on else "DESLIGADOS  -  CLIQUE PARA MOSTRAR")
        self.save_config()

    # ── tema ──
    @staticmethod
    def _draw_swatch(_w, cr, th):
        cr.set_source_rgb(*hexc(th["shadow"]))
        cr.rectangle(0, 0, 30, 12)
        cr.fill()
        for i, k in enumerate(("bg", "ink", "accent")):
            cr.set_source_rgb(*hexc(th[k]))
            cr.rectangle(1 + i * 10, 1, 9, 10)
            cr.fill()

    def _mark_theme(self):
        for k, b in self.theme_opts.items():
            (b.get_style_context().add_class if k == self.theme else b.get_style_context().remove_class)("primary")

    def set_theme(self, name):
        if name not in THEMES:
            return
        self.theme = name
        apply_theme(name)
        self.css.load_from_data(theme_css())
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", THEME["dark"])
        for p in self.panes:
            p.apply_theme()
        self._mark_theme()
        self.queue_draw()
        self.save_config()

    def _button(self, label, cb, primary=False, tip=None):
        b = Gtk.Button(label=label)
        b.set_can_focus(False)
        b.get_style_context().add_class("px")
        if primary:
            b.get_style_context().add_class("primary")
        if tip:
            b.set_tooltip_text(tip)
        if cb:
            b.connect("clicked", cb)
        return b

    def _enter_main(self):
        self.stack.set_visible_child_name("main")
        if self.splash:
            s, self.splash = self.splash, None
            GLib.timeout_add(600, lambda: s.destroy() and False)
        self.restore_agents()
        if self.initial:
            self.add_agents(self.initial)
        else:
            self.relayout()
        return False

    def relayout(self):
        for p in self.panes:
            for w in (p, p.card):
                if w.get_parent():
                    w.get_parent().remove(w)
        if not self.panes:
            self.content.set_visible_child_name("empty")
            self._update_title()
            return
        if self.main_pane not in self.panes:
            self.main_pane = self.focused if self.focused in self.panes else self.panes[0]
        if self.layout_mode == "focus":
            self._layout_focus()
        else:
            self._layout_grid()
        self._update_title()

    def _layout_focus(self):
        main = self.zoomed or self.main_pane
        for p in self.panes:
            self.main_slot.add(p)
        others = [p for p in self.panes if p is not main]
        for p in self.panes:
            self.card_list.pack_start(p.card, False, False, 0)
        self.content.get_child_by_name("focus").show_all()
        self.sidebar.set_visible(bool(others) and not self.zoomed)
        self.content.set_visible_child_name("focus")
        self.main_slot.set_visible_child(main)
        main.mute(0.8)
        now = time.monotonic()
        for p in self.panes:
            p.term.realize()  # terminal oculto precisa estar realizado para o preview funcionar
            p.refresh_preview(now)

    def _switch_focus_main(self, main):
        """Troca o agente principal sem reconstruir o layout (a lista já tem todos; só redesenha)."""
        now = time.monotonic()
        for p in self.panes:
            p.refresh_preview(now)
            p.card.queue_draw()
        self.main_slot.set_visible_child(main)
        main.mute(0.8)

    def _layout_grid(self):
        panes = [self.zoomed] if self.zoomed else self.panes
        n = len(panes)
        W, H = self.get_size()
        if n <= 3 and W / max(1, H) > 1.5:
            cols = n
        else:
            cols = math.ceil(math.sqrt(n))
        for i, p in enumerate(panes):
            r, c = divmod(i, cols)
            span = cols - c if i == n - 1 else 1
            self.grid.attach(p, c, r, span, 1)
            p.mute(0.8)
        self.grid.show_all()
        self.content.set_visible_child_name("grid")

    def toggle_layout(self):
        self.layout_mode = "grid" if self.layout_mode == "focus" else "focus"
        self.zoomed = None
        self._update_layout_label()
        self.save_config()
        self.relayout()
        target = self.main_pane if self.main_pane in self.panes else None
        if target:
            GLib.idle_add(lambda: target.term.grab_focus() and False)

    def _update_layout_label(self):
        self.layout_btn.set_label("FOCO" if self.layout_mode == "focus" else "GRADE")

    def select(self, pane):
        """Traz o agente para o painel principal (modo foco/zoom) e foca o terminal."""
        if pane not in self.panes:
            return
        self.main_pane = pane
        if self.zoomed:
            self.zoomed = pane
        if self.layout_mode == "focus" and not self.zoomed and pane.get_parent() is self.main_slot:
            self._switch_focus_main(pane)
        elif self.zoomed or self.layout_mode == "focus":
            self.relayout()
        GLib.idle_add(lambda: pane.term.grab_focus() and False)

    # ── agentes ──
    def restore_agents(self):
        """Reabre os agentes da última execução, retomando a conversa de cada um."""
        if self.restored:
            return
        saved = [] if self.fresh else [a for a in self.config.get("agents", []) if isinstance(a, dict)]
        self.restored = True
        for a in saved:
            name = a.get("name")
            if not name or AUTO_NAME.match(name):  # nome automático: renumera sem buracos
                name = f"AGENT {self._free_number()}"
            color = AGENT_COLORS[int(a.get("color", len(self.panes))) % len(AGENT_COLORS)]
            self.panes.append(AgentPane(self, 0, a.get("cwd") or self.cwd, color,
                                        name=name, session_id=a.get("session_id")))
        if self.panes:
            self.main_pane = self.panes[min(int(self.config.get("main_agent", 0)), len(self.panes) - 1)]
            self.relayout()
            GLib.idle_add(lambda: self.main_pane.term.grab_focus() and False)
        self.save_config()

    def add_agents(self, n):
        new = []
        for _ in range(n):
            p = AgentPane(self, self._free_number(), self.cwd, AGENT_COLORS[self._free_color()])
            self.panes.append(p)
            new.append(p)
        self.zoomed = None
        if new:
            self.main_pane = new[0]
        self.relayout()
        self.save_config()
        if new:
            GLib.idle_add(lambda: new[0].term.grab_focus() and False)

    def _free_number(self):
        """Menor número livre: fechou o AGENT 2, o próximo volta a ser AGENT 2."""
        used = {int(p.name.split()[1]) for p in self.panes if AUTO_NAME.match(p.name)}
        n = 1
        while n in used:
            n += 1
        return n

    def _free_color(self):
        used = {p.color_idx for p in self.panes}
        return next((i for i in range(len(AGENT_COLORS)) if i not in used), len(self.panes) % len(AGENT_COLORS))

    def close_agent(self, pane):
        if pane not in self.panes:
            return
        i = self.panes.index(pane)
        pane.kill()
        self.panes.remove(pane)
        if self.zoomed is pane:
            self.zoomed = None
        if self.focused is pane:
            self.focused = None
        if self.panes and self.main_pane is pane:
            self.main_pane = self.panes[min(i, len(self.panes) - 1)]
        self.relayout()
        pane.card.destroy()
        pane.destroy()
        self.save_config()
        if self.panes:
            self.main_pane.term.grab_focus()

    def close_all(self):
        others = [p for p in self.panes if p is not self.main_pane]
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                text="Fechar agentes?")
        dlg.format_secondary_text("As conversas continuam salvas no Claude (claude --resume), "
                                  "mas os agentes fechados não voltam ao reabrir o CLARK.")
        dlg.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        if others:
            dlg.add_button(f"Só os outros ({len(others)})", 1)
        dlg.add_button(f"Todos ({len(self.panes)})", 2)
        dlg.set_default_response(Gtk.ResponseType.CANCEL)
        r = dlg.run()
        dlg.destroy()
        if r in (1, 2):
            for p in (others if r == 1 else list(self.panes)):
                self.close_agent(p)

    def toggle_zoom(self, pane):
        self.zoomed = None if self.zoomed is pane else pane
        self.relayout()
        GLib.idle_add(lambda: pane.term.grab_focus() and False)

    def set_focused(self, pane):
        for p in self.panes:
            p.get_style_context().remove_class("focused")
        pane.get_style_context().add_class("focused")
        self.focused = pane
        if self.layout_mode == "grid":
            self.main_pane = pane

    def is_watching(self, pane):
        return pane is self.focused and self.is_active()

    def notify_done(self, pane):
        self._update_title()
        if not self.is_active():
            self.set_urgency_hint(True)
            if shutil.which("notify-send"):
                try:
                    Gio.Subprocess.new(["notify-send", "-a", "Clark", "-i", "clark",
                                        f"CLARK · {pane.name}", "Terminou e está te esperando."],
                                       Gio.SubprocessFlags.NONE)
                except GLib.Error:
                    pass

    def focus_offset(self, d):
        if not self.panes:
            return
        i = self.panes.index(self.focused) if self.focused in self.panes else 0
        self.select(self.panes[(i + d) % len(self.panes)])

    def set_font_scale(self, s):
        self.font_scale = clamp(s, 0.6, 2.5)
        for p in self.panes:
            p.term.set_font_scale(self.font_scale)
        self._update_font_label()
        self.save_config()

    def choose_folder(self, *_):
        dlg = Gtk.FileChooserNative.new("Pasta dos agentes", self, Gtk.FileChooserAction.SELECT_FOLDER, None, None)
        dlg.set_current_folder(self.cwd)
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            self.cwd = dlg.get_filename()
            self.save_config()

    def short_path(self, path):
        home = os.path.expanduser("~")
        return "~" + path[len(home):] if path.startswith(home) else path

    def _update_title(self):
        done = sum(p.state == "DONE" for p in self.panes)
        self.set_title((f"({done}) " if done else "") + f"CLARK — {len(self.panes)} agentes")

    # ── eventos ──
    def _on_key(self, _w, ev):
        if self.stack.get_visible_child_name() != "main":
            return False
        mods = ev.state & Gtk.accelerator_get_default_mod_mask()
        k = Gdk.keyval_to_lower(ev.keyval)
        cs = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        f = self.focused if self.focused in self.panes else None
        if mods == cs:
            if k == Gdk.KEY_n:
                self.add_agents(1)
            elif k == Gdk.KEY_w and f:
                self.close_agent(f)
            elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and f:
                self.toggle_zoom(f)
            elif k == Gdk.KEY_c and f:
                f.term.copy_clipboard_format(Vte.Format.TEXT)
            elif k == Gdk.KEY_v and f:
                f.term.paste_clipboard()
            elif k == Gdk.KEY_d:
                self.choose_folder()
            elif k == Gdk.KEY_l:
                self.toggle_layout()
            elif k == Gdk.KEY_t:
                self.set_todo_visible(not self.todo_visible)
            elif k in (Gdk.KEY_Right, Gdk.KEY_Down):
                self.focus_offset(1)
            elif k in (Gdk.KEY_Left, Gdk.KEY_Up):
                self.focus_offset(-1)
            elif k in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
                self.set_font_scale(self.font_scale + 0.1)
            elif k in (Gdk.KEY_minus, Gdk.KEY_underscore, Gdk.KEY_KP_Subtract):
                self.set_font_scale(self.font_scale - 0.1)
            elif k in (Gdk.KEY_0, Gdk.KEY_parenright):
                self.set_font_scale(1.0)
            else:
                return False
            return True
        if mods == Gdk.ModifierType.MOD1_MASK and Gdk.KEY_1 <= k <= Gdk.KEY_9:
            i = k - Gdk.KEY_1
            if i < len(self.panes):
                self.select(self.panes[i])
                return True
        return False

    def _on_delete(self, *_):
        alive = [p for p in self.panes if p.state != "EXITED"]
        if alive:
            dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                    buttons=Gtk.ButtonsType.OK_CANCEL, text="Sair do CLARK?")
            dlg.format_secondary_text(f"{len(alive)} agente(s) ativo(s) serão encerrados e reabertos "
                                      "com a mesma conversa na próxima vez (use --fresh para começar do zero).")
            ok = dlg.run() == Gtk.ResponseType.OK
            dlg.destroy()
            if not ok:
                return True
        for p in self.panes:
            p.kill()
        self.save_config()
        Gtk.main_quit()
        return False

    def _tick(self):
        now = time.monotonic()
        self.t = now - self.t_start
        changed = False
        for p in self.panes:
            before = p.state
            p.update(now)
            changed |= before != p.state
            p.head_area.queue_draw()
            if p.card.get_mapped():
                if now - p.preview_at > (0.5 if p.last_change > p.preview_at else 2.0):
                    p.refresh_preview(now)
                p.card.queue_draw()
        stats_w = 16 + sum(text_w(f"{label} {n}", 2) + 34 for label, n, _ in self._stats_items())
        if stats_w != self.stats.get_size_request()[0]:
            self.stats.set_size_request(stats_w, -1)
        self.stats.queue_draw()
        if self.week_pct is not None:
            self.heat += (self.week_pct - self.heat) * 0.08
        self.heat_area.queue_draw()
        if self.content.get_visible_child_name() == "empty":
            self.empty_area.queue_draw()
        if changed:
            self._update_title()
        return True

    # ── limite semanal ──
    def _fetch_usage(self):
        def work():
            pct = reset = None
            try:
                with open(CREDENTIALS_PATH) as f:
                    token = json.load(f)["claudeAiOauth"]["accessToken"]
                req = urllib.request.Request(USAGE_URL, headers={"Authorization": f"Bearer {token}",
                                                                 "anthropic-beta": "oauth-2025-04-20"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    week = json.load(r)["seven_day"]
                pct, reset = float(week["utilization"]), week.get("resets_at") or ""
            except (OSError, ValueError, KeyError, TypeError):
                pass
            if pct is not None:
                GLib.idle_add(self._set_usage, pct, reset)
        threading.Thread(target=work, daemon=True).start()
        return True

    def _set_usage(self, pct, reset):
        first = self.week_pct is None
        self.week_pct, self.week_reset = clamp(pct, 0, 100), reset
        if first:
            self.heat = self.week_pct
        self.heat_area.set_tooltip_text(f"Limite semanal: {pct:.0f}% usado" +
                                        (f"\nRenova em {self._reset_label()}" if reset else ""))
        return False

    def _reset_label(self):
        try:
            from datetime import datetime
            left = datetime.fromisoformat(self.week_reset).timestamp() - time.time()
        except ValueError:
            return self.week_reset
        d, h = int(left // 86400), int(left % 86400 // 3600)
        return f"{d}d {h}h" if d > 0 else f"{h}h {int(left % 3600 // 60)}min"

    def _draw_heat(self, w, cr):
        W, H, t = HEAT_W, w.get_allocated_height(), self.t
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.translate((w.get_allocated_width() - W) // 2, 0)
        f = clamp(self.heat / 100)
        P = 2
        # dragão à esquerda, fora da barra, soprando mais forte quanto mais quente
        step = int(t * 3) % 2
        fire = int(t * (4 + f * 10)) % 2 + 1
        draw_sprite(cr, mascot_rows(step, arms_up=bool(int(t * 2) % 2), fire=fire),
                    0, (H - SPRITE_H * P) // 2, P, sprite_pal(ORANGE))
        # barra
        bx, bw, bh = (SPRITE_W + 4) * P + 4, W - (SPRITE_W + 4) * P - 8 - text_w("100%", 2) - 8, 18
        by = (H - bh) // 2
        cr.set_source_rgb(*SHADOW)
        cr.rectangle(bx - 3, by - 3, bw + 6, bh + 6)
        cr.fill()
        cr.set_source_rgb(*BG)
        cr.rectangle(bx, by, bw, bh)
        cr.fill()
        # líquido: verde no começo, laranja no meio, vermelho perto do fim
        stops = [(0.0, GREEN), (0.3, GREEN), (0.5, ORANGE), (0.75, ORANGE), (0.9, RED), (1.0, RED)]
        col = stops[-1][1]
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if f <= b:
                col = mix(ca, cb, (f - a) / (b - a))
                break
        fw = int(bw * f)
        if fw > 0:
            cr.save()
            cr.rectangle(bx, by, bw, bh)
            cr.clip()
            amp = 1 + f * 2
            # degradê: escuro onde o dragão sopra (esquerda), claro lá longe (ponta)
            grad = cairo.LinearGradient(bx, 0, bx + fw, 0)
            grad.add_color_stop_rgb(0, *mix(col, BLACK, 0.5))
            grad.add_color_stop_rgb(1, *mix(col, WHITE, 0.3))
            for y in range(bh):  # ponta ondulada, mais agitada quando quente
                edge = fw + int(math.sin(t * (3 + f * 6) + y * 0.9) * amp)
                cr.set_source(grad)
                cr.rectangle(bx, by + y, max(0, edge), 1)
                cr.fill()
            cr.set_source_rgba(*mix(col, BLACK, 0.3), 0.6)
            cr.rectangle(bx, by + bh - 4, fw, 4)
            cr.fill()
            # bolhas: mais numerosas e rápidas conforme esquenta
            for i in range(int(2 + f * 16)):
                ph = (t * (0.3 + f * 1.2) + i * 0.37) % 1.0
                x = bx + int(((i * 0.618) % 1.0) * max(1, fw - 4))
                sz = 2 if i % 3 else 4
                cr.set_source_rgba(*mix(col, WHITE, 0.6), 0.9 - ph * 0.6)
                cr.rectangle(x, by + bh - 2 - int(ph * (bh - 2)), sz, sz)
                cr.fill()
            cr.restore()
        # reflexo de vidro no canto inferior direito da barra
        cr.save()
        cr.rectangle(bx, by, bw, bh)
        cr.clip()
        glass = cairo.RadialGradient(bx + bw, by + bh, 0, bx + bw, by + bh, bh * 2.2)
        glass.add_color_stop_rgba(0, 1, 1, 1, 0.45)
        glass.add_color_stop_rgba(1, 1, 1, 1, 0.0)
        cr.set_source(glass)
        cr.paint()
        cr.set_source_rgba(1, 1, 1, 0.6)
        cr.rectangle(bx + bw - 14, by + bh - 2, 14, 1)  # brilho na borda de baixo
        cr.rectangle(bx + bw - 2, by + bh - 9, 1, 8)    # e na borda da direita
        cr.fill()
        cr.restore()
        # vapor quando passa de 75%
        if f > 0.75:
            for i in range(3):
                ph = (t * 0.8 + i / 3) % 1.0
                cr.set_source_rgba(*INK, (1 - ph) * 0.5)
                cr.rectangle(bx + int(fw * (0.3 + 0.25 * i)) + int(math.sin(t * 4 + i) * 2), by - 3 - int(ph * 6), 2, 2)
                cr.fill()
        # brasas do sopro do dragão chegando na barra
        for i in range(int(2 + f * 6)):
            ph = (t * 2 + i * 0.29) % 1.0
            cr.set_source_rgba(*(YELLOW if i % 2 else ORANGE), 1 - ph)
            cr.rectangle(SPRITE_W * P + int(ph * 12), H // 2 - 2 + int(math.sin(i * 2.3 + t * 6) * 5 * ph), 2, 2)
            cr.fill()
        label = "--" if self.week_pct is None else f"{self.week_pct:.0f}%"
        draw_text(cr, label, W - text_w(label, 2), (H - 14) // 2, 2, col if self.week_pct is not None else DIM)

    # ── desenhos da barra / estado vazio ──
    def _draw_logo(self, w, cr):
        H = w.get_allocated_height()
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        y = (H - 21) // 2
        draw_text(cr, "CLARK", 2, y + 2, 3, mix(ORANGE, BLACK, 0.5))
        draw_text(cr, "CLARK", 0, y, 3, ORANGE)

    def _draw_side_head(self, w, cr):
        H = w.get_allocated_height()
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.set_source_rgb(*BG2)
        cr.paint()
        draw_text(cr, f"AGENTES {len(self.panes)}", 12, (H - 7) // 2, 1, DIM)

    def _stats_items(self):
        counts = {s: sum(p.state == s for p in self.panes) for s in ("WORKING", "IDLE", "DONE", "EXITED")}
        items = [("AGENTS", len(self.panes), INK), ("WORKING", counts["WORKING"], GREEN),
                 ("DONE", counts["DONE"], YELLOW), ("IDLE", counts["IDLE"], DIM)]
        if counts["EXITED"]:
            items.append(("GAME OVER", counts["EXITED"], RED))
        return items

    def _draw_stats(self, w, cr):
        H = w.get_allocated_height()
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        x, y = 16, (H - 14) // 2
        for label, n, col in self._stats_items():
            s = f"{label} {n}"
            cr.set_source_rgb(*col)
            cr.rectangle(x, y + 4, 6, 6)
            cr.fill()
            draw_text(cr, s, x + 12, y, 2, col if n else DIM)
            x += text_w(s, 2) + 34

    def _draw_empty(self, w, cr):
        W, H, t = w.get_allocated_width(), w.get_allocated_height(), self.t
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        P = max(4, min(W, H) // 70)
        mx, my = (W - SPRITE_W * P) // 2, int(H * 0.42)
        cr.set_source_rgba(*SHADOW, 0.8)
        cr.rectangle(mx + 3 * P, my + SPRITE_H * P, 9 * P, P)
        cr.fill()
        breath = int(math.sin(t * 2) > 0.6)
        draw_sprite(cr, mascot_rows(sleep=True), mx, my + breath * (P // 2), P, sprite_pal(ORANGE))
        for i in range(3):
            k = ((t * 0.5) + i / 3) % 1.0
            zs = max(2, P // 2 + i)
            draw_text(cr, "Z", mx + SPRITE_W * P + int(k * 4 * P) + i * P, my - int(k * 7 * P),
                      zs, INK, alpha=1 - k)
        msg = "NENHUM AGENTE ONLINE"
        sc = max(2, P // 2)
        draw_text(cr, msg, (W - text_w(msg, sc)) // 2, my + SPRITE_H * P + 4 * P, sc, INK, shadow=SHADOW)
        sub = "PRESS START  -  CTRL+SHIFT+N"
        if int(t * 2) % 2 == 0:
            draw_text(cr, sub, (W - text_w(sub, 2)) // 2, my + SPRITE_H * P + 4 * P + 7 * sc + 3 * P, 2, ORANGE)


def find_claude():
    p = shutil.which("claude")
    if p:
        return p
    for c in ("~/.local/bin/claude", "~/.claude/local/claude", "/usr/local/bin/claude"):
        c = os.path.expanduser(c)
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def parse_args(argv):
    claude_args = []
    if "--" in argv:
        i = argv.index("--")
        argv, claude_args = argv[:i], argv[i + 1:]
    opts = {"dir": None, "n": 0, "no_splash": False, "claude_args": claude_args, "export_icon": None, "fresh": False,
            "icon_size": 256}
    it = iter(argv)
    for a in it:
        if a in ("-h", "--help"):
            print("uso: clark [PASTA] [-n N] [--no-splash] [--fresh] [-- argumentos extras do claude]")
            sys.exit(0)
        elif a == "-n":
            opts["n"] = max(0, min(16, int(next(it, "1"))))
        elif a == "--fresh":
            opts["fresh"] = True
        elif a == "--no-splash":
            opts["no_splash"] = True
        elif a == "--export-icon":
            opts["export_icon"] = next(it)
        elif a == "--icon-size":
            opts["icon_size"] = int(next(it, "256"))
        elif a == "--version":
            print(f"clark {VERSION}")
            sys.exit(0)
        elif not a.startswith("-"):
            opts["dir"] = os.path.abspath(os.path.expanduser(a))
    return opts


def forget_parent_session():
    # sai do próprio ambiente: o VTE soma o env do spawn ao do processo, então filtrar lá não basta
    for k in PARENT_SESSION_VARS:
        os.environ.pop(k, None)


def main():
    opts = parse_args(sys.argv[1:])
    forget_parent_session()
    if opts["export_icon"]:
        make_icon_surface(opts["icon_size"]).write_to_png(opts["export_icon"])
        return
    GLib.set_prgname("clark")
    GLib.set_application_name("Clark")
    win = Clark(opts)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: win._on_delete() or True)
    Gtk.main()


if __name__ == "__main__":
    main()
