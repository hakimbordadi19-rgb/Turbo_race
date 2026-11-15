#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TURBO RACER - Full HD (1920x1080) top-down racing game for Python + pygame.
Made to run in Termux (Android) with Termux:X11, but works on any desktop too.

Controls
  Keyboard : Arrows / WASD to drive, R restart, T auto-gas, F fullscreen, ESC quit
  Touch    : on-screen LEFT / RIGHT / BRAKE / GAS buttons (multi-touch if available)
             tap the AUTO-GAS button for one-finger driving

Options
  --laps N        number of laps (default 3)
  --fullscreen    start fullscreen
  --touch         always show touch buttons
  --autogas       gas is pressed automatically
  --fps           show FPS counter
"""
import argparse
import math
import os
import random
import sys

import pygame

W, H = 1920, 1080          # Full HD logical resolution
SPACING = 8.0              # distance between centre-line points (px)
TRACK_W = 210              # asphalt width
HALF = TRACK_W / 2
KERB = 18                  # kerb width
NUM_CARS = 6

# Closed loop of control points (smoothed with a Catmull-Rom spline)
CONTROL = [
    (260, 560), (300, 270), (620, 170), (980, 260), (1300, 170),
    (1650, 230), (1770, 450), (1560, 630), (1260, 520), (1130, 690),
    (1330, 870), (1000, 950), (640, 910), (560, 730), (380, 810),
    (220, 740),
]

CAR_COLORS = [
    ("YOU", (230, 40, 40)),
    ("Blue", (40, 110, 235)),
    ("Yellow", (245, 200, 30)),
    ("Green", (40, 190, 90)),
    ("Purple", (160, 70, 220)),
    ("Orange", (255, 135, 20)),
]


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def fmt_time(t):
    if t is None:
        return "--:--.--"
    m = int(t // 60)
    s = t - m * 60
    return "%d:%05.2f" % (m, s)


def catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    out = []
    for k in (0, 1):
        out.append(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t
                          + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                          + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3))
    return out


# --------------------------------------------------------------------------
# Track
# --------------------------------------------------------------------------
class Track:
    def __init__(self):
        n = len(CONTROL)
        dense = []
        for i in range(n):
            p0, p1 = CONTROL[(i - 1) % n], CONTROL[i]
            p2, p3 = CONTROL[(i + 1) % n], CONTROL[(i + 2) % n]
            for k in range(80):
                dense.append(catmull(p0, p1, p2, p3, k / 80.0))
        dense.append(dense[0])
        seg = [0.0]
        for i in range(1, len(dense)):
            seg.append(seg[-1] + math.dist(dense[i - 1], dense[i]))
        total = seg[-1]
        self.N = int(total / SPACING)
        self.x, self.y = [], []
        j = 0
        for i in range(self.N):
            target = i * total / self.N
            while seg[j + 1] < target:
                j += 1
            t = (target - seg[j]) / max(1e-9, seg[j + 1] - seg[j])
            self.x.append(dense[j][0] + (dense[j + 1][0] - dense[j][0]) * t)
            self.y.append(dense[j][1] + (dense[j + 1][1] - dense[j][1]) * t)
        N = self.N
        self.ang = [math.atan2(self.y[(i + 1) % N] - self.y[i - 1],
                               self.x[(i + 1) % N] - self.x[i - 1]) for i in range(N)]
        self.nx = [-math.sin(a) for a in self.ang]   # right-hand normal (screen coords)
        self.ny = [math.cos(a) for a in self.ang]

    def min_clearance(self):
        """Smallest distance between far-apart parts of the centre line."""
        N = self.N
        best = 1e9
        for i in range(0, N, 3):
            for j in range(i + N // 8, N, 3):
                if min(j - i, N - (j - i)) < N // 8:
                    continue
                d = math.hypot(self.x[i] - self.x[j], self.y[i] - self.y[j])
                best = min(best, d)
        return best

    def render(self):
        N = self.N
        surf = pygame.Surface((W, H)).convert()
        rng = random.Random(7)
        surf.fill((44, 128, 58))
        for y in range(0, H, 72):
            if (y // 72) % 2:
                pygame.draw.rect(surf, (40, 120, 54), (0, y, W, 72))
        for _ in range(2500):
            x, y = rng.randrange(W), rng.randrange(H)
            c = rng.choice([(36, 112, 50), (52, 140, 64), (48, 132, 60)])
            pygame.draw.circle(surf, c, (x, y), rng.randint(2, 5))

        # kerbs (red / white blocks) on both edges
        for i in range(N):
            j = (i + 1) % N
            col = (215, 35, 35) if (i // 5) % 2 else (240, 240, 240)
            for side in (-1, 1):
                a_in, a_out = side * (HALF - 3), side * (HALF + KERB)
                poly = [
                    (self.x[i] + self.nx[i] * a_in, self.y[i] + self.ny[i] * a_in),
                    (self.x[i] + self.nx[i] * a_out, self.y[i] + self.ny[i] * a_out),
                    (self.x[j] + self.nx[j] * a_out, self.y[j] + self.ny[j] * a_out),
                    (self.x[j] + self.nx[j] * a_in, self.y[j] + self.ny[j] * a_in),
                ]
                pygame.draw.polygon(surf, col, poly)

        # asphalt
        for i in range(N):
            pygame.draw.circle(surf, (62, 64, 70), (int(self.x[i]), int(self.y[i])), int(HALF))
        # worn racing-line band
        for i in range(N):
            if i % 2 == 0:
                pygame.draw.circle(surf, (70, 72, 79), (int(self.x[i]), int(self.y[i])), int(HALF * 0.55))
        # dashed centre line
        for i in range(N):
            if (i // 6) % 2 == 0:
                j = (i + 1) % N
                pygame.draw.line(surf, (225, 225, 140), (self.x[i], self.y[i]),
                                 (self.x[j], self.y[j]), 4)

        # start / finish line (checkered)
        f = (math.cos(self.ang[0]), math.sin(self.ang[0]))
        r = (self.nx[0], self.ny[0])
        sq = 15
        count = int(TRACK_W // sq)
        for c in range(count):
            off = -HALF + c * sq + sq / 2
            for row in range(2):
                al = (row - 1) * sq + sq / 2
                cx = self.x[0] + r[0] * off + f[0] * al
                cy = self.y[0] + r[1] * off + f[1] * al
                h = sq / 2
                poly = [(cx - f[0] * h - r[0] * h, cy - f[1] * h - r[1] * h),
                        (cx + f[0] * h - r[0] * h, cy + f[1] * h - r[1] * h),
                        (cx + f[0] * h + r[0] * h, cy + f[1] * h + r[1] * h),
                        (cx - f[0] * h + r[0] * h, cy - f[1] * h + r[1] * h)]
                pygame.draw.polygon(surf, (250, 250, 250) if (c + row) % 2 == 0 else (15, 15, 15), poly)

        # trees on the grass, away from the track
        clear = HALF + KERB + 70
        placed = 0
        tries = 0
        while placed < 140 and tries < 4000:
            tries += 1
            x, y = rng.randrange(30, W - 30), rng.randrange(30, H - 30)
            ok = True
            for i in range(0, N, 2):
                if (x - self.x[i]) ** 2 + (y - self.y[i]) ** 2 < clear * clear:
                    ok = False
                    break
            if not ok:
                continue
            placed += 1
            s = rng.randint(18, 30)
            pygame.draw.circle(surf, (24, 80, 36), (x + 6, y + 8), s)
            pygame.draw.circle(surf, (30, 105, 45), (x, y), s)
            pygame.draw.circle(surf, (46, 140, 62), (x - s // 4, y - s // 4), int(s * 0.62))

        # drivable mask (asphalt + a bit of kerb)
        ms = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(N):
            pygame.draw.circle(ms, (255, 255, 255, 255), (int(self.x[i]), int(self.y[i])), int(HALF + 6))
        mask = pygame.mask.from_surface(ms)
        return surf, mask


# --------------------------------------------------------------------------
# Cars
# --------------------------------------------------------------------------
def make_car_sprite(color):
    s = pygame.Surface((84, 46), pygame.SRCALPHA)
    dark = tuple(int(c * 0.55) for c in color)
    light = tuple(min(255, int(c * 1.25) + 20) for c in color)
    pygame.draw.rect(s, (0, 0, 0, 80), (7, 10, 72, 32), border_radius=12)       # shadow
    for wx in (14, 54):
        for wy in (3, 35):
            pygame.draw.rect(s, (18, 18, 18), (wx, wy, 17, 8), border_radius=3)  # wheels
    pygame.draw.rect(s, color, (6, 8, 72, 30), border_radius=13)                 # body
    pygame.draw.rect(s, dark, (6, 8, 72, 30), width=3, border_radius=13)
    pygame.draw.rect(s, light, (50, 20, 26, 6), border_radius=3)                 # hood stripe
    pygame.draw.rect(s, (30, 40, 60), (32, 12, 22, 22), border_radius=6)         # cabin
    pygame.draw.rect(s, (110, 150, 200), (45, 14, 8, 18), border_radius=3)       # windshield
    pygame.draw.rect(s, (255, 245, 170), (74, 12, 4, 6), border_radius=2)        # headlights
    pygame.draw.rect(s, (255, 245, 170), (74, 28, 4, 6), border_radius=2)
    pygame.draw.rect(s, (200, 20, 20), (6, 12, 3, 6))                            # tail lights
    pygame.draw.rect(s, (200, 20, 20), (6, 28, 3, 6))
    pygame.draw.rect(s, dark, (2, 10, 6, 26), border_radius=2)                   # rear wing
    return s


class Car:
    def __init__(self, name, color, is_player, top, skill, lane):
        self.name, self.color, self.is_player = name, color, is_player
        self.top, self.skill, self.lane = top, skill, lane
        self.sprite = make_car_sprite(color)
        self.cache = {}
        self.reset(0, 0, 0, 0)

    def reset(self, x, y, angle, idx):
        self.x, self.y, self.angle = x, y, angle
        self.vx = self.vy = 0.0
        self.vf = self.vr = 0.0
        self.idx = idx
        self.progress = 0
        self.cur_lap = 0
        self.lap_start = 0.0
        self.last_lap = None
        self.best_lap = None
        self.finish_time = None
        self.on_track = True
        self.slip = 0.0
        self.wrong = 0.0

    @property
    def finished(self):
        return self.finish_time is not None

    def physics(self, dt, throttle, brake, steer, on_track):
        c, s = math.cos(self.angle), math.sin(self.angle)
        vf = self.vx * c + self.vy * s
        vr = -self.vx * s + self.vy * c
        top = self.top * (1.0 if on_track else 0.45)
        if throttle > 0:
            vf += 430.0 * throttle * max(0.0, 1.0 - vf / top) * dt
        if brake > 0:
            if vf > 8:
                vf = max(0.0, vf - 760.0 * dt)
            else:
                vf = max(-120.0, vf - 260.0 * dt)
        vf *= math.exp(-(0.22 if on_track else 1.5) * dt)
        if vf > top:
            vf -= (vf - top) * 3.0 * dt
        grip = 5.8 if on_track else 3.2
        if brake > 0 and vf > 160:
            grip *= 0.5
        vr *= math.exp(-grip * dt)
        self.vf, self.vr = vf, vr
        self.vx = c * vf - s * vr
        self.vy = s * vf + c * vr
        speed_factor = clamp(abs(vf) / 170.0, 0.0, 1.0)
        turn = 2.9 / (1.0 + abs(vf) / 600.0)
        self.angle = wrap(self.angle + steer * turn * speed_factor * (1 if vf >= -1 else -1) * dt)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.slip = abs(vr)

    def circles(self):
        c, s = math.cos(self.angle), math.sin(self.angle)
        return [(self.x + c * 19, self.y + s * 19), (self.x - c * 19, self.y - s * 19)]

    def draw(self, screen):
        deg = int(-math.degrees(self.angle)) // 2 * 2
        img = self.cache.get(deg)
        if img is None:
            img = pygame.transform.rotate(self.sprite, deg)
            self.cache[deg] = img
        screen.blit(img, img.get_rect(center=(int(self.x), int(self.y))))


def collide(a, b):
    for ax, ay in a.circles():
        for bx, by in b.circles():
            dx, dy = bx - ax, by - ay
            d = math.hypot(dx, dy)
            md = 38.0
            if 0.001 < d < md:
                nx, ny = dx / d, dy / d
                pen = (md - d) / 2
                a.x -= nx * pen
                a.y -= ny * pen
                b.x += nx * pen
                b.y += ny * pen
                rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
                if rel < 0:
                    imp = -rel * 0.6
                    a.vx -= imp * nx
                    a.vy -= imp * ny
                    b.vx += imp * nx
                    b.vy += imp * ny


# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------
class Game:
    def __init__(self, args):
        self.args = args
        pygame.display.init()
        pygame.font.init()
        flags = pygame.SCALED | (pygame.FULLSCREEN if args.fullscreen else 0)
        try:
            self.screen = pygame.display.set_mode((W, H), flags)
        except pygame.error:
            self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Turbo Racer")
        self.clock = pygame.time.Clock()
        self.f_s = pygame.font.Font(None, 40)
        self.f_m = pygame.font.Font(None, 64)
        self.f_l = pygame.font.Font(None, 130)
        self.f_xl = pygame.font.Font(None, 240)

        self.laps = max(1, args.laps)
        self.track = Track()
        self.base, self.mask = self.track.render()
        self.surface = self.base.copy()
        self.skid_sprite = pygame.Surface((7, 7), pygame.SRCALPHA)
        pygame.draw.circle(self.skid_sprite, (10, 10, 10, 70), (3, 3), 3)

        skills = [1.0, 0.94, 0.97, 0.91, 0.95]
        self.cars = []
        for i, (name, col) in enumerate(CAR_COLORS):
            if i == 0:
                self.cars.append(Car(name, col, True, 505.0, 1.0, 0.0))
            else:
                lane = random.choice([-0.8, -0.4, 0.0, 0.4, 0.8])
                self.cars.append(Car(name, col, False, 480.0, skills[i - 1], lane))
        self.player = self.cars[0]

        self.particles = []
        self.smoke_cache = {}
        self.panel_cache = {}
        self.pointers = {}
        self.touch_mode = args.touch
        self.autogas = args.autogas
        self.show_fps = args.fps
        self.autopilot = args.demo
        self.build_buttons()
        self.state = "menu"
        self.cd = 0.0
        self.race_t = 0.0
        self.finish_timer = 0.0
        self.dim = pygame.Surface((W, H), pygame.SRCALPHA)
        self.dim.fill((0, 0, 0, 150))
        self.restart()
        if args.demo:
            self.start_countdown()

    # ---- setup ----------------------------------------------------------
    def restart(self):
        self.surface = self.base.copy()
        self.particles = []
        tr = self.track
        N = tr.N
        order = [2, 0, 1, 3, 4, 5]          # slot of each car in the grid
        slots = [None] * NUM_CARS
        for car_i, slot in enumerate(order):
            slots[car_i] = slot
        for car, slot in zip(self.cars, slots):
            row, col = slot // 2, slot % 2
            back = 70 + row * 90 + (col * 40)
            idx = (N - int(back / SPACING)) % N
            side = -48 if col == 0 else 48
            x = tr.x[idx] + tr.nx[idx] * side
            y = tr.y[idx] + tr.ny[idx] * side
            car.reset(x, y, tr.ang[idx], idx)
            car.progress = idx - N
            car.cur_lap = 0
        self.race_t = 0.0
        self.finish_timer = 0.0
        if self.args.demo:
            self.start_countdown()
        else:
            self.state = "menu"

    def start_countdown(self):
        self.state = "countdown"
        self.cd = 3.99

    # ---- touch buttons --------------------------------------------------
    def build_buttons(self):
        self.btn_rects = {
            "left": pygame.Rect(0, 0, 210, 210),
            "right": pygame.Rect(0, 0, 210, 210),
            "brake": pygame.Rect(0, 0, 210, 210),
            "gas": pygame.Rect(0, 0, 210, 210),
        }
        self.btn_rects["left"].center = (170, 900)
        self.btn_rects["right"].center = (420, 900)
        self.btn_rects["brake"].center = (1500, 900)
        self.btn_rects["gas"].center = (1750, 900)
        self.toggle_rect = pygame.Rect(0, 0, 430, 90)
        self.toggle_rect.center = (W // 2, 1000)
        self.btn_imgs = {}
        for name in self.btn_rects:
            for pressed in (False, True):
                s = pygame.Surface((210, 210), pygame.SRCALPHA)
                pygame.draw.rect(s, (255, 255, 255, 130 if pressed else 55), (0, 0, 210, 210), border_radius=36)
                pygame.draw.rect(s, (255, 255, 255, 190), (0, 0, 210, 210), width=5, border_radius=36)
                if name in ("left", "right"):
                    d = -1 if name == "left" else 1
                    pts = [(105 + d * 45, 105), (105 - d * 35, 55), (105 - d * 35, 155)]
                    pygame.draw.polygon(s, (255, 255, 255, 230), pts)
                else:
                    label = self.f_m.render("GAS" if name == "gas" else "BRAKE", True, (255, 255, 255))
                    s.blit(label, label.get_rect(center=(105, 105)))
                self.btn_imgs[(name, pressed)] = s

    def pressed_buttons(self):
        res = set()
        for pos in self.pointers.values():
            for name, rect in self.btn_rects.items():
                if rect.inflate(60, 60).collidepoint(pos):
                    res.add(name)
        return res

    def pointer_down(self, pos):
        self.touch_mode = True
        if self.toggle_rect.collidepoint(pos):
            self.autogas = not self.autogas
            return
        if self.state == "menu":
            self.start_countdown()
        elif self.state == "finish":
            self.restart()

    @staticmethod
    def finger_pos(e):
        return (e.x * W, e.y * H)

    # ---- events ---------------------------------------------------------
    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    return False
                if e.key == pygame.K_r:
                    self.restart()
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    if self.state == "menu":
                        self.start_countdown()
                    elif self.state == "finish":
                        self.restart()
                elif e.key == pygame.K_t:
                    self.autogas = not self.autogas
                elif e.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                elif e.key == pygame.K_F3:
                    self.show_fps = not self.show_fps
            elif e.type == pygame.FINGERDOWN:
                p = self.finger_pos(e)
                self.pointers[("f", e.finger_id)] = p
                self.pointer_down(p)
            elif e.type == pygame.FINGERMOTION:
                self.pointers[("f", e.finger_id)] = self.finger_pos(e)
            elif e.type == pygame.FINGERUP:
                self.pointers.pop(("f", e.finger_id), None)
            elif e.type == pygame.MOUSEBUTTONDOWN and not getattr(e, "touch", False):
                if e.button == 1:
                    self.pointers["m"] = e.pos
                    self.pointer_down(e.pos)
            elif e.type == pygame.MOUSEMOTION and not getattr(e, "touch", False):
                if "m" in self.pointers:
                    self.pointers["m"] = e.pos
            elif e.type == pygame.MOUSEBUTTONUP and not getattr(e, "touch", False):
                self.pointers.pop("m", None)
        return True

    def read_input(self):
        k = pygame.key.get_pressed()
        btn = self.pressed_buttons()
        left = k[pygame.K_LEFT] or k[pygame.K_a] or "left" in btn
        right = k[pygame.K_RIGHT] or k[pygame.K_d] or "right" in btn
        brake = k[pygame.K_DOWN] or k[pygame.K_s] or "brake" in btn
        gas = k[pygame.K_UP] or k[pygame.K_w] or "gas" in btn
        if self.autogas and not brake:
            gas = True
        steer = (1 if right else 0) - (1 if left else 0)
        return (1.0 if gas else 0.0), (1.0 if brake else 0.0), float(steer)

    # ---- AI -------------------------------------------------------------
    def ai_control(self, car, boost=1.0):
        tr = self.track
        N = tr.N
        look = int(11 + abs(car.vf) / 20.0)
        ti = (car.idx + look) % N
        off = car.lane * HALF * 0.5
        tx = tr.x[ti] + tr.nx[ti] * off
        ty = tr.y[ti] + tr.ny[ti] * off
        desired = math.atan2(ty - car.y, tx - car.x)
        diff = wrap(desired - car.angle)
        steer = clamp(diff * 2.2, -1.0, 1.0)
        a1 = tr.ang[(car.idx + 6) % N]
        a2 = tr.ang[(car.idx + 6 + 38) % N]
        curv = abs(wrap(a2 - a1))
        target = car.top * car.skill * boost * (1.0 - clamp(curv * 0.62, 0.0, 0.55))
        if car.finished:
            target = min(target, 260.0)
        throttle = 1.0 if car.vf < target else 0.0
        brake = 1.0 if car.vf > target * 1.1 else 0.0
        return throttle, brake, steer

    # ---- progress -------------------------------------------------------
    def update_progress(self, car):
        tr = self.track
        N = tr.N
        best, bd = 0, 1e18
        for d in range(-6, 34):
            j = (car.idx + d) % N
            dx, dy = car.x - tr.x[j], car.y - tr.y[j]
            dd = dx * dx + dy * dy
            if dd < bd:
                bd, best = dd, d
        car.idx = (car.idx + best) % N
        car.progress += best
        car.wrong = car.wrong + 1 if best < 0 else 0
        lap = int(math.floor(car.progress / N)) + 1
        while car.cur_lap < lap:
            car.cur_lap += 1
            if car.cur_lap == 1:
                car.lap_start = self.race_t
            elif car.cur_lap <= self.laps + 1:
                lt = self.race_t - car.lap_start
                car.last_lap = lt
                if car.best_lap is None or lt < car.best_lap:
                    car.best_lap = lt
                car.lap_start = self.race_t
            if car.cur_lap == self.laps + 1 and car.finish_time is None:
                car.finish_time = self.race_t

    def ranking(self):
        return sorted(self.cars, key=lambda c: (0, c.finish_time) if c.finished else (1, -c.progress))

    # ---- effects --------------------------------------------------------
    def smoke(self, x, y, kind):
        if len(self.particles) < 160:
            self.particles.append([x, y, random.uniform(-25, 25), random.uniform(-25, 25),
                                   0.7, 0.7, kind])

    def smoke_surf(self, size_b, alpha_b, kind):
        key = (size_b, alpha_b, kind)
        s = self.smoke_cache.get(key)
        if s is None:
            r = 9 + size_b * 5
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            col = (225, 225, 225) if kind == 0 else (150, 115, 70)
            pygame.draw.circle(s, col + (alpha_b * 22 + 10,), (r, r), r)
            self.smoke_cache[key] = s
        return s

    def car_effects(self, car, brake):
        c, s = math.cos(car.angle), math.sin(car.angle)
        sliding = car.slip > 95 or (brake > 0 and car.vf > 220)
        if sliding or (not car.on_track and car.vf > 120):
            for side in (-13, 13):
                wx = car.x - c * 24 - s * side
                wy = car.y - s * 24 + c * side
                if car.on_track or sliding:
                    self.surface.blit(self.skid_sprite, (wx - 3, wy - 3))
                if random.random() < 0.5:
                    self.smoke(wx, wy, 0 if car.on_track else 1)

    def update_particles(self, dt):
        alive = []
        for p in self.particles:
            p[4] -= dt
            if p[4] > 0:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                alive.append(p)
        self.particles = alive

    # ---- update ---------------------------------------------------------
    def update(self, dt):
        if self.state == "countdown":
            self.cd -= dt
            if self.cd <= 0:
                self.state = "race"
                self.race_t = 0.0
        elif self.state in ("race", "finish"):
            self.race_t += dt

        racing = self.state in ("race", "finish")
        player_input = self.read_input() if (self.state == "race" and not self.autopilot) else None

        for car in self.cars:
            if not racing:
                continue
            if car.is_player and not car.finished and not self.autopilot:
                th, br, st = player_input if player_input else (0.0, 0.0, 0.0)
            else:
                boost = 1.0
                if not car.is_player:
                    d = car.progress - self.player.progress
                    if d > self.track.N * 0.12:
                        boost = 0.9
                    elif d < -self.track.N * 0.12:
                        boost = 1.07
                th, br, st = self.ai_control(car, boost)
            x, y = int(car.x), int(car.y)
            car.on_track = 0 <= x < W and 0 <= y < H and bool(self.mask.get_at((x, y)))
            car.physics(dt, th, br, st, car.on_track)
            self.car_effects(car, br)

        for i in range(NUM_CARS):
            for j in range(i + 1, NUM_CARS):
                collide(self.cars[i], self.cars[j])
        for car in self.cars:
            if car.x < 40:
                car.x, car.vx = 40, abs(car.vx) * 0.3
            elif car.x > W - 40:
                car.x, car.vx = W - 40, -abs(car.vx) * 0.3
            if car.y < 40:
                car.y, car.vy = 40, abs(car.vy) * 0.3
            elif car.y > H - 40:
                car.y, car.vy = H - 40, -abs(car.vy) * 0.3
            if racing:
                self.update_progress(car)

        self.update_particles(dt)
        if self.state == "race" and self.player.finished:
            self.finish_timer += dt
            if self.finish_timer > 2.0 or self.autopilot and self.finish_timer > 0.5:
                self.state = "finish"

    # ---- drawing --------------------------------------------------------
    def text(self, s, font, color, pos, anchor="topleft", shadow=True):
        img = font.render(s, True, color)
        r = img.get_rect(**{anchor: pos})
        if shadow:
            self.screen.blit(font.render(s, True, (0, 0, 0)), r.move(3, 3))
        self.screen.blit(img, r)

    def panel(self, rect, alpha=140):
        key = (rect[2], rect[3], alpha)
        s = self.panel_cache.get(key)
        if s is None:
            s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
            pygame.draw.rect(s, (0, 0, 0, alpha), (0, 0, rect[2], rect[3]), border_radius=18)
            self.panel_cache[key] = s
        self.screen.blit(s, (rect[0], rect[1]))

    def draw_hud(self):
        p = self.player
        order = self.ranking()
        pos = order.index(p) + 1
        lap = clamp(p.cur_lap, 1, self.laps)

        self.panel((30, 30, 330, 190))
        self.text("LAP %d/%d" % (lap, self.laps), self.f_m, (255, 255, 255), (52, 44))
        self.text("POS %d/%d" % (pos, NUM_CARS), self.f_m, (255, 220, 80), (52, 100))
        kmh = int(abs(p.vf) * 0.62)
        self.text("%d km/h" % kmh, self.f_m, (140, 230, 255), (52, 156))

        self.panel((W // 2 - 260, 30, 520, 140))
        cur = (self.race_t - p.lap_start) if p.cur_lap >= 1 and not p.finished else (p.last_lap or 0)
        self.text(fmt_time(self.race_t), self.f_m, (255, 255, 255), (W // 2, 40), "midtop")
        self.text("LAP " + fmt_time(cur), self.f_s, (200, 200, 200), (W // 2, 98), "midtop")
        self.text("BEST " + fmt_time(p.best_lap), self.f_s, (120, 255, 150), (W // 2, 130), "midtop")

        self.panel((W - 360, 30, 330, 40 + NUM_CARS * 42))
        for i, c in enumerate(order):
            y = 46 + i * 42
            pygame.draw.rect(self.screen, c.color, (W - 340, y + 4, 26, 26), border_radius=6)
            col = (255, 255, 255) if c.is_player else (210, 210, 210)
            self.text("%d  %s" % (i + 1, c.name), self.f_s, col, (W - 300, y + 3), shadow=False)
            if c.finished:
                self.text("FIN", self.f_s, (120, 255, 150), (W - 45, y + 3), "topright", shadow=False)

        if p.wrong > 40 and abs(p.vf) > 60 and self.state == "race":
            self.text("WRONG WAY!", self.f_l, (255, 70, 70), (W // 2, 330), "center")

        if self.touch_mode or self.state == "menu":
            btn = self.pressed_buttons()
            for name, rect in self.btn_rects.items():
                if self.touch_mode:
                    self.screen.blit(self.btn_imgs[(name, name in btn)], rect)
            self.panel(tuple(self.toggle_rect), 150)
            self.text("AUTO-GAS: " + ("ON" if self.autogas else "OFF"), self.f_m,
                      (120, 255, 150) if self.autogas else (230, 230, 230),
                      self.toggle_rect.center, "center", shadow=False)

    def draw_overlay(self):
        if self.state == "menu":
            self.screen.blit(self.dim, (0, 0))
            self.text("TURBO RACER", self.f_xl, (255, 255, 255), (W // 2, 250), "center")
            self.text("%d laps  -  beat 5 rivals" % self.laps, self.f_m, (255, 220, 80), (W // 2, 390), "center")
            self.text("TAP or press ENTER to start", self.f_l, (140, 230, 255), (W // 2, 560), "center")
            self.text("Arrows / WASD to drive      T = auto-gas      F = fullscreen      ESC = quit",
                      self.f_s, (230, 230, 230), (W // 2, 690), "center")
        elif self.state == "countdown":
            n = int(self.cd) if self.cd >= 1 else 0
            self.text(str(n) if n > 0 else "GO!", self.f_xl, (255, 235, 80) if n else (120, 255, 150),
                      (W // 2, H // 2), "center")
        elif self.state == "race" and self.race_t < 1.2:
            self.text("GO!", self.f_xl, (120, 255, 150), (W // 2, H // 2), "center")
        elif self.state == "finish":
            self.screen.blit(self.dim, (0, 0))
            order = self.ranking()
            pos = order.index(self.player) + 1
            self.text("RACE FINISHED", self.f_l, (255, 255, 255), (W // 2, 150), "center")
            self.text("You finished P%d" % pos, self.f_m, (255, 220, 80), (W // 2, 250), "center")
            self.text("Best lap " + fmt_time(self.player.best_lap), self.f_m, (120, 255, 150),
                      (W // 2, 320), "center")
            for i, c in enumerate(order):
                y = 410 + i * 70
                pygame.draw.rect(self.screen, c.color, (W // 2 - 330, y, 40, 40), border_radius=8)
                col = (255, 255, 255) if c.is_player else (210, 210, 210)
                self.text("%d. %s" % (i + 1, c.name), self.f_m, col, (W // 2 - 270, y - 6))
                self.text(fmt_time(c.finish_time) if c.finished else "racing...", self.f_m, col,
                          (W // 2 + 330, y - 6), "topright")
            self.text("TAP or press ENTER / R to race again", self.f_m, (140, 230, 255),
                      (W // 2, 930), "center")

    def draw(self):
        self.screen.blit(self.surface, (0, 0))
        order = self.ranking()
        for car in reversed(order):
            car.draw(self.screen)
        for p in self.particles:
            f = p[4] / p[5]
            surf = self.smoke_surf(int(4 * (1 - f)), int(clamp(f, 0, 0.999) * 6), p[6])
            self.screen.blit(surf, surf.get_rect(center=(int(p[0]), int(p[1]))))
        if self.state != "finish":
            self.draw_hud()
        self.draw_overlay()
        if self.show_fps:
            self.text("%d FPS" % self.clock.get_fps(), self.f_s, (255, 255, 0), (40, H - 50))
        pygame.display.flip()

    # ---- main loop ------------------------------------------------------
    def run(self):
        frames = 0
        while True:
            if not self.handle_events():
                break
            dt = min(self.clock.tick(self.args.maxfps) / 1000.0, 1 / 30.0)
            if self.args.frames:
                dt = 1 / 60.0
            self.update(dt)
            self.draw()
            frames += 1
            if self.args.frames and frames >= self.args.frames:
                break
        if self.args.screenshot:
            pygame.image.save(self.screen, self.args.screenshot)
        return self


def main():
    ap = argparse.ArgumentParser(description="Turbo Racer - Full HD racing game")
    ap.add_argument("--laps", type=int, default=3)
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--touch", action="store_true", help="always show touch buttons")
    ap.add_argument("--autogas", action="store_true", help="automatic throttle")
    ap.add_argument("--fps", action="store_true", help="show FPS")
    ap.add_argument("--maxfps", type=int, default=60)
    ap.add_argument("--demo", action="store_true", help="AI drives your car (attract mode)")
    ap.add_argument("--frames", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--screenshot", default="", help=argparse.SUPPRESS)
    args = ap.parse_args()

    game = Game(args)
    game.run()
    if args.frames:
        for i, c in enumerate(game.ranking()):
            print(i + 1, c.name, fmt_time(c.finish_time), "best", fmt_time(c.best_lap),
                  "lap", c.cur_lap, "progress", c.progress)
    pygame.quit()


if __name__ == "__main__":
    main()
