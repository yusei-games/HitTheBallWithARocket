import os
import random
import pyxel
import math
from collections import deque

SAVE_FILE = "save.dat"
SCREEN_W = 256
SCREEN_H = 256
FIELD_L = 8
FIELD_T = 20
FIELD_R = 248
FIELD_B = 248
BALL_R = 7
PLAYER_R = 5
HOLE_R = 17
FRICTION_B = 0.992
STOP_SPD = 0.12
PLAYER_SPD = 2.2
PLAYER_ACCEL = 0.25
FRICTION_P = 0.88
FRICTION_CRASH = 0.96
CRASH_SPIN = 0.18
TURN_RATE = 0.1
PLAYER_FRONT = 7
PLAYER_BACK = 3
PLAYER_SIDE = 4
TRAIL_LEN = 40
BUMPER_R = 12
BUMPER_PUSH = 5.0
BUMPER_MAX_SPD = 12.0
BIG_BALL_R = 18
SMALL_BALL_R = 4
FRICTION_SMALL = FRICTION_B
BALL_MASS = 1.0
BIG_BALL_MASS = 4.0
SMALL_BALL_MASS = 0.125
PLAYER_MASS = 1.0
CHASE_ACCEL = 0.025
CHASE_MAX_SPD = 3.5
REPULSION_R = 40
REPULSION_STR = 0.27
TURRET_R = 10
TURRET_SHOT_SPD = 4.5
TURRET_COOLDOWN = 25
HIT_LEVEL_MAX = 15
HIT_LEVEL_TIMEOUT = 60  # 1秒（60fps）

_GAMEPAD_WATCH = (
    pyxel.GAMEPAD1_BUTTON_DPAD_UP, pyxel.GAMEPAD1_BUTTON_DPAD_DOWN,
    pyxel.GAMEPAD1_BUTTON_DPAD_LEFT, pyxel.GAMEPAD1_BUTTON_DPAD_RIGHT,
    pyxel.GAMEPAD1_BUTTON_A, pyxel.GAMEPAD1_BUTTON_START,
)
_KEYBOARD_WATCH = (
    pyxel.KEY_UP, pyxel.KEY_DOWN, pyxel.KEY_LEFT, pyxel.KEY_RIGHT,
    pyxel.KEY_W, pyxel.KEY_A, pyxel.KEY_S, pyxel.KEY_D,
    pyxel.KEY_SPACE, pyxel.KEY_RETURN, pyxel.KEY_ESCAPE,
)


class Ball:
    def __init__(self, n, x, y, r=BALL_R, can_fall=True, friction=FRICTION_B, is_chase=False, ttl=0):
        self.num = n
        self.x = float(x)
        self.y = float(y)
        self.vx = self.vy = 0.0
        self.active = True
        self.r = r
        self.can_fall = can_fall
        self.friction = friction
        self.is_chase = is_chase
        self.ttl = ttl
        self.is_cannonball = False
        if r == BIG_BALL_R:
            self.mass = BIG_BALL_MASS
        elif r == SMALL_BALL_R:
            self.mass = SMALL_BALL_MASS
        else:
            self.mass = BALL_MASS

    def update(self, fl, ft, fr, fb):
        if self.ttl > 0:
            self.ttl -= 1
            if self.ttl == 0:
                self.active = False
                return
        self.vx *= self.friction
        self.vy *= self.friction
        if not self.is_chase and math.hypot(self.vx, self.vy) < STOP_SPD:
            self.vx = self.vy = 0.0
        self.x += self.vx
        self.y += self.vy
        if self.x - self.r < fl:
            self.x = fl + self.r
            self.vx = abs(self.vx)
        elif self.x + self.r > fr:
            self.x = fr - self.r
            self.vx = -abs(self.vx)
        if self.y - self.r < ft:
            self.y = ft + self.r
            self.vy = abs(self.vy)
        elif self.y + self.r > fb:
            self.y = fb - self.r
            self.vy = -abs(self.vy)


class RectWall:
    def __init__(self, x, y, w, h):
        self.x = float(x)
        self.y = float(y)
        self.w = float(w)
        self.h = float(h)

    def _resolve(self, cx, cy, r):
        qx = max(self.x, min(cx, self.x + self.w))
        qy = max(self.y, min(cy, self.y + self.h))
        dx = cx - qx
        dy = cy - qy
        d = math.hypot(dx, dy)
        if 0 < d < r:
            return dx / d, dy / d, r - d
        elif d == 0:
            dl = cx - self.x
            dr = (self.x + self.w) - cx
            dt = cy - self.y
            db = (self.y + self.h) - cy
            m = min(dl, dr, dt, db)
            if m == dl:
                return -1.0, 0.0, r + dl
            elif m == dr:
                return 1.0, 0.0, r + dr
            elif m == dt:
                return 0.0, -1.0, r + dt
            else:
                return 0.0, 1.0, r + db
        return None

    def reflect_ball(self, b):
        res = self._resolve(b.x, b.y, b.r)
        if res:
            nx, ny, ov = res
            b.x += nx * ov
            b.y += ny * ov
            dot = b.vx * nx + b.vy * ny
            if dot < 0:
                b.vx -= 2 * dot * nx
                b.vy -= 2 * dot * ny

    def reflect_player(self, p):
        res = self._resolve(p.x, p.y, PLAYER_R)
        if res:
            nx, ny, ov = res
            p.x += nx * ov
            p.y += ny * ov
            vx = math.cos(p.angle) * p.spd
            vy = math.sin(p.angle) * p.spd
            dot = vx * nx + vy * ny
            if dot < 0:
                rvx = vx - 2 * dot * nx
                rvy = vy - 2 * dot * ny
                p.angle = math.atan2(rvy, rvx)

    def draw(self):
        pyxel.rect(int(self.x), int(self.y), int(self.w), int(self.h), 5)
        pyxel.rectb(int(self.x), int(self.y), int(self.w), int(self.h), 7)


class JetBumper:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.hit_timer = 0

    def _overlap(self, ox, oy, r):
        dx = ox - self.x
        dy = oy - self.y
        d = math.hypot(dx, dy)
        total = BUMPER_R + r
        if d < total:
            if d < 0.01:
                return 1.0, 0.0, total
            return dx / d, dy / d, total - d
        return None

    def check_ball(self, b):
        res = self._overlap(b.x, b.y, b.r)
        if res:
            nx, ny, ov = res
            b.x += nx * ov
            b.y += ny * ov
            spd = max(math.hypot(b.vx, b.vy), 1.0)
            new_spd = min(max(spd * 1.8, BUMPER_PUSH), BUMPER_MAX_SPD)
            b.vx = nx * new_spd
            b.vy = ny * new_spd
            self.hit_timer = 6

    def check_player(self, p):
        res = self._overlap(p.x, p.y, PLAYER_R)
        if res:
            nx, ny, ov = res
            p.x += nx * ov
            p.y += ny * ov
            new_spd = min(max(p.spd * 1.8, BUMPER_PUSH), BUMPER_MAX_SPD)
            p.angle = math.atan2(ny, nx)
            p.spd = new_spd
            p.vx = nx * new_spd
            p.vy = ny * new_spd
            self.hit_timer = 6

    def update(self):
        if self.hit_timer > 0:
            self.hit_timer -= 1

    def draw(self):
        col = 10 if self.hit_timer > 0 else 6
        pyxel.circ(int(self.x), int(self.y), BUMPER_R, col)
        pyxel.circb(int(self.x), int(self.y), BUMPER_R, 7)
        x, y = int(self.x), int(self.y)
        pyxel.line(x - 5, y, x + 5, y, 7)
        pyxel.line(x, y - 5, x, y + 5, 7)


class Turret:
    def __init__(self, x, y, n_shots=1):
        self.x = float(x)
        self.y = float(y)
        self.hit_timer = 0
        self.cooldown = 0
        self.n_shots = n_shots

    def _overlap(self, ox, oy, r):
        dx = ox - self.x
        dy = oy - self.y
        d = math.hypot(dx, dy)
        total = TURRET_R + r
        if d < total:
            if d < 0.01:
                return 1.0, 0.0, total
            return dx / d, dy / d, total - d
        return None

    def _fire(self, hx, hy, balls):
        if self.cooldown > 0:
            return
        dx = self.x - hx
        dy = self.y - hy
        d = math.hypot(dx, dy)
        if d < 0.01:
            dx, dy = 1.0, 0.0
        else:
            dx /= d
            dy /= d
        base_angle = math.atan2(dy, dx)
        spread = math.radians(10)
        offsets = [0.0] if self.n_shots == 1 else [-spread + spread * 2 * i / (self.n_shots - 1) for i in range(self.n_shots)]
        for da in offsets:
            a = base_angle + da
            fdx, fdy = math.cos(a), math.sin(a)
            sx = self.x + fdx * (TURRET_R + SMALL_BALL_R + 1)
            sy = self.y + fdy * (TURRET_R + SMALL_BALL_R + 1)
            cb = Ball(0, sx, sy, r=SMALL_BALL_R, can_fall=True, friction=FRICTION_SMALL, ttl=60)
            cb.is_cannonball = True
            cb.mass = BALL_MASS
            cb.vx = fdx * TURRET_SHOT_SPD
            cb.vy = fdy * TURRET_SHOT_SPD
            balls.append(cb)
        self.hit_timer = 8
        self.cooldown = TURRET_COOLDOWN

    def check_ball(self, b, balls):
        res = self._overlap(b.x, b.y, b.r)
        if res:
            nx, ny, ov = res
            orig_x, orig_y = b.x, b.y
            b.x += nx * ov
            b.y += ny * ov
            dot = b.vx * nx + b.vy * ny
            if dot < 0:
                b.vx -= 2 * dot * nx
                b.vy -= 2 * dot * ny
            self._fire(orig_x, orig_y, balls)

    def check_player(self, p, balls):
        res = self._overlap(p.x, p.y, PLAYER_R)
        if res:
            nx, ny, ov = res
            orig_x, orig_y = p.x, p.y
            p.x += nx * ov
            p.y += ny * ov
            vx_old = math.cos(p.angle) * p.spd
            vy_old = math.sin(p.angle) * p.spd
            dot = vx_old * nx + vy_old * ny
            if dot < 0:
                rvx = vx_old - 2 * dot * nx
                rvy = vy_old - 2 * dot * ny
                p.angle = math.atan2(rvy, rvx)
            self._fire(orig_x, orig_y, balls)

    def update(self):
        if self.hit_timer > 0:
            self.hit_timer -= 1
        if self.cooldown > 0:
            self.cooldown -= 1

    def draw(self):
        col = 8 if self.hit_timer > 0 else 4
        x, y = int(self.x), int(self.y)
        pyxel.circ(x, y, TURRET_R, col)
        pyxel.circb(x, y, TURRET_R, 7)
        pyxel.line(x - 5, y, x + 5, y, 7)
        pyxel.line(x, y - 5, x, y + 5, 7)


class RepulsionZone:
    def __init__(self, x, y, r=REPULSION_R, strength=REPULSION_STR):
        self.x = float(x)
        self.y = float(y)
        self.r = float(r)
        self.strength = strength

    def apply_to_ball(self, b):
        dx = b.x - self.x
        dy = b.y - self.y
        d = math.hypot(dx, dy)
        if 0 < d < self.r:
            f = self.strength * (1.0 - d / self.r)
            b.vx += (dx / d) * f
            b.vy += (dy / d) * f

    def apply_to_player(self, p):
        dx = p.x - self.x
        dy = p.y - self.y
        d = math.hypot(dx, dy)
        if 0 < d < self.r:
            f = self.strength * (1.0 - d / self.r)
            p.x += (dx / d) * f
            p.y += (dy / d) * f

    def draw(self):
        x, y = int(self.x), int(self.y)
        r = int(self.r)
        pyxel.circb(x, y, r, 9)
        for ang in (0.0, math.pi * 0.5, math.pi, math.pi * 1.5):
            cos_a, sin_a = math.cos(ang), math.sin(ang)
            ix = x + int(cos_a * (HOLE_R + 2))
            iy = y + int(sin_a * (HOLE_R + 2))
            ox = x + int(cos_a * (r - 5))
            oy = y + int(sin_a * (r - 5))
            pyxel.line(ix, iy, ox, oy, 9)


class Player:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.angle = -math.pi / 2
        self.spd = PLAYER_SPD
        self.vx = 0.0
        self.vy = -PLAYER_SPD
        self.trail = deque(maxlen=TRAIL_LEN)
        self.crash = False
        self.spin_angle = 0.0
        self.mass = PLAYER_MASS

    def update(self):
        if self.crash:
            self.spd *= FRICTION_CRASH
            if self.spd < STOP_SPD:
                self.spd = 0.0
                self.crash = False
            self.spin_angle += CRASH_SPIN
            self.vx = math.cos(self.angle) * self.spd
            self.vy = math.sin(self.angle) * self.spd
            self.x += self.vx
            self.y += self.vy
            return

        tx, ty = 0.0, 0.0
        if pyxel.btn(pyxel.KEY_LEFT) or pyxel.btn(pyxel.KEY_A) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_LEFT):
            tx -= 1.0
        if pyxel.btn(pyxel.KEY_RIGHT) or pyxel.btn(pyxel.KEY_D) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_RIGHT):
            tx += 1.0
        if pyxel.btn(pyxel.KEY_UP) or pyxel.btn(pyxel.KEY_W) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_UP):
            ty -= 1.0
        if pyxel.btn(pyxel.KEY_DOWN) or pyxel.btn(pyxel.KEY_S) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_DOWN):
            ty += 1.0

        if tx != 0.0 or ty != 0.0:
            target_angle = math.atan2(ty, tx)
            diff = (target_angle - self.angle + math.pi) % (2 * math.pi) - math.pi
            if abs(diff) <= TURN_RATE:
                self.angle = target_angle
            else:
                self.angle += TURN_RATE * (1 if diff > 0 else -1)
            max_spd = PLAYER_SPD if abs(diff) <= TURN_RATE else PLAYER_SPD / 2
            if self.spd > max_spd:
                self.spd *= FRICTION_P
            else:
                self.spd = min(self.spd + PLAYER_ACCEL, max_spd)
        else:
            self.spd *= FRICTION_P
            if self.spd < STOP_SPD:
                self.spd = 0.0

        self.vx = math.cos(self.angle) * self.spd
        self.vy = math.sin(self.angle) * self.spd
        self.x += self.vx
        self.y += self.vy


class BgParticle:
    _COLS = [5, 6, 13]

    def __init__(self, delay=0):
        self._randomize()
        self.alive = delay == 0
        self.timer = delay

    def _randomize(self):
        self.x = random.uniform(0, SCREEN_W)
        self.y = random.uniform(0, SCREEN_H)
        spd = random.uniform(0.08, 0.25)
        angle = random.uniform(0, math.pi * 2)
        self.vx = math.cos(angle) * spd
        self.vy = math.sin(angle) * spd
        self.col = random.choice(self._COLS)
        self.life = random.randint(120, 360)

    def update(self):
        if self.alive:
            self.x = (self.x + self.vx) % SCREEN_W
            self.y = (self.y + self.vy) % SCREEN_H
            self.timer += 1
            if self.timer >= self.life:
                self.alive = False
                self.timer = random.randint(60, 200)
        else:
            self.timer -= 1
            if self.timer <= 0:
                self._randomize()
                self.alive = True
                self.timer = 0

    def draw(self):
        if self.alive:
            pyxel.pset(int(self.x), int(self.y), self.col)


class App:
    def __init__(self):
        pyxel.init(SCREEN_W, SCREEN_H, title="POCKET THE 9", fps=60, quit_key=pyxel.KEY_NONE)
        try:
            self.use_gamepad = pyxel.gamepad_count() > 0
        except AttributeError:
            self.use_gamepad = False
        self._setup_sounds()
        self.unlocked = self._load_save()
        self.selected_stage = 1
        self.menu_cursor = 1
        self.gameover_cursor = 0
        self.pause_cursor = 0
        self.scene = "title"
        self.stage = 1
        self.sfx_ch_idx = 0
        self.bg_particles = [BgParticle(delay=random.randint(0, 240)) for _ in range(20)]
        pyxel.run(self.update, self.draw)

    def _setup_sounds(self):
        pyxel.sounds[0].mml("T200 @0 V90 O4 L16 CEG>C4")        # ステージ開始ジングル（C-E-G-Cの上昇アルペジオ）
        pyxel.sounds[1].mml("T180 @0 V100 O4 L16 CEGCE>C4.")    # ステージクリアジングル（C-E-G-C-E-Cの長めアルペジオ）
        pyxel.sounds[2].mml("T90 @1 V90 O5 L8 C<BAGF2")         # ゲームオーバージングル（C-B-A-G-Fの下降メロディ）
        pyxel.sounds[3].mml("@env1{90,5,10,30,0} o6a64")               # カーソル移動音（高音の短い一音）
        pyxel.sounds[4].mml("T150 @0 @GLI1{1000,70} @ENV1{100,64,50} o5c2")     # ボールポケットイン音（速い下降スケール）
        pyxel.sounds[5].mml("T180 @3 V100 O5 L16 CC")            # 残機減少音（低めの2音）
        # 反射音16段階：低音（O2A）→高音（O5A）、1秒以内に重なるごとに音程が上がる
        _hit_notes = [
            "@env1{90,5,10,30,0} o5c4",  # 0
            "@env1{90,5,10,30,0} o5d4",  # 1
            "@env1{90,5,10,30,0} o5e4",  # 2
            "@env1{90,5,10,30,0} o5f4",  # 3
            "@env1{90,5,10,30,0} o5g4",  # 4
            "@env1{90,5,10,30,0} o5a4",  # 5
            "@env1{90,5,10,30,0} o5b4",  # 6
            "@env1{90,5,10,30,0} o6c4",  # 7
            "@env1{90,5,10,30,0} o6d4",  # 8
            "@env1{90,5,10,30,0} o6e4",  # 9
            "@env1{90,5,10,30,0} o6f4",  # 10
            "@env1{90,5,10,30,0} o6g4",  # 11
            "@env1{90,5,10,30,0} o6a4",  # 12
            "@env1{90,5,10,30,0} o6b4",  # 13
            "@env1{90,5,10,30,0} o7c4",  # 14
            "@env1{90,5,10,30,0} o7d4",  # 15
        ]
        for i, note in enumerate(_hit_notes):
            pyxel.sounds[6 + i].mml(f"@env1{{90,5,0}} {note}")
        pyxel.sounds[22].mml("T150 @0 @GLI1{1000,70} @ENV1{100,64,50} o5c2")  # 落下音（2オクターブ下降）

    def _update_input_device(self):
        if any(pyxel.btnp(b) for b in _GAMEPAD_WATCH):
            self.use_gamepad = True
        elif any(pyxel.btnp(k) for k in _KEYBOARD_WATCH):
            self.use_gamepad = False

    def _load_save(self):
        try:
            with open(SAVE_FILE) as f:
                return max(1, min(20, int(f.read().strip())))
        except Exception:
            return 1

    def _save_progress(self):
        with open(SAVE_FILE, "w") as f:
            f.write(str(self.unlocked))

    def _trigger_clear(self):
        self.state = "clear"
        pyxel.play(0, 1)
        next_st = self.stage + 1
        if next_st <= 20 and next_st > self.unlocked:
            self.unlocked = next_st
            self._save_progress()

    def _stage_bounds(self):
        if self.stage == 1:
            return FIELD_L + 20, FIELD_T, FIELD_R - 20, FIELD_B
        return FIELD_L, FIELD_T, FIELD_R, FIELD_B

    def _init_stage(self):
        self.fl, self.ft, self.fr, self.fb = self._stage_bounds()
        cx = (self.fl + self.fr) / 2.0
        start_y = self.ft + (self.fb - self.ft) * 2 // 3
        self.p = Player(cx - 1, start_y)
        self.tnum = 1
        self.state = "play"
        self.lives = 3
        self.hole_x, self.hole_y = self._place_hole()
        self._place_balls()
        self._setup_stage_objects()
        self.death_timer = 0
        self.hole_fall_timer = 0
        self.hole_fall_scale = 1.0
        self.hole_fall_start_x = 0.0
        self.hole_fall_start_y = 0.0
        self.gameover_from_hole = False
        self.hit_cooldown = 0
        self.hit_level = 0
        self.hit_level_timer = 0
        self.sfx_ch_idx = 0
        pyxel.play(0, 0)

    def _place_hole(self):
        cx = (self.fl + self.fr) / 2.0
        return cx, float(self.fb - 45)

    def _place_balls(self):
        cx = (self.fl + self.fr) / 2.0
        top_y = float(self.ft + 30)
        rh = BALL_R * math.sqrt(3)
        positions = [
            (8, cx,              top_y),
            (6, cx - BALL_R,     top_y + rh),
            (7, cx + BALL_R,     top_y + rh),
            (4, cx - BALL_R * 2, top_y + rh * 2),
            (9, cx,              top_y + rh * 2),
            (5, cx + BALL_R * 2, top_y + rh * 2),
            (2, cx - BALL_R,     top_y + rh * 3),
            (3, cx + BALL_R,     top_y + rh * 3),
            (1, cx,              top_y + rh * 4),
        ]
        if self.stage == 3:
            positions += [
                (0, cx - 65, top_y + rh * 5 + 32),
                (0, cx + 65, top_y + rh * 5 + 32),
            ]
        elif self.stage == 4:
            positions += [
                (0, cx - 45, top_y + rh * 5 + 28),
                (0, cx + 45, top_y + rh * 5 + 28),
            ]
        self.balls = [Ball(n, x, y) for n, x, y in positions]
        if self.stage == 7:
            self.balls.append(Ball(0, self.hole_x, self.hole_y, r=BIG_BALL_R, can_fall=False))
        elif self.stage == 8:
            self.balls.append(Ball(0, self.hole_x, self.hole_y, r=BIG_BALL_R, can_fall=False))
        elif self.stage == 9:
            self.balls.append(Ball(0, self.fl + 20, self.fb - 40, can_fall=True, is_chase=True))
        elif self.stage == 10:
            self.balls.append(Ball(0, self.fl + 20, self.fb - 40, can_fall=True, is_chase=True))
            self.balls.append(Ball(0, self.fr - 20, self.ft + 40, can_fall=True, is_chase=True))
        elif self.stage == 11:
            for sx, sy in [(cx - 70, self.ft + 55), (cx + 70, self.ft + 55),
                           (cx - 70, self.fb - 70)]:
                self.balls.append(Ball(0, sx, sy, r=SMALL_BALL_R, can_fall=True, friction=FRICTION_SMALL))
        elif self.stage == 12:
            mid_y = (self.ft + self.fb) / 2.0
            for sx, sy in [(self.fl + 45, self.ft + 110), (self.fr - 45, self.ft + 90),
                           (self.fl + 55, self.fb - 75)]:
                self.balls.append(Ball(0, sx, sy, r=SMALL_BALL_R, can_fall=True, friction=FRICTION_SMALL))
        elif self.stage == 14:
            self.balls.append(Ball(0, cx - 60, self.fb - 65, can_fall=True))
            self.balls.append(Ball(0, cx + 60, self.fb - 65, can_fall=True))
        elif self.stage == 15:
            cx = (self.fl + self.fr) / 2.0
            self.balls.append(Ball(0, cx - 60, self.fb - 65, can_fall=True))
            self.balls.append(Ball(0, cx - 90, self.fb - 65, can_fall=True))
        elif self.stage == 17:
            self.balls.append(Ball(0, self.fl + 30, self.fb - 50, r=BIG_BALL_R, can_fall=False))
            self.balls.append(Ball(0, cx + 70, self.fb - 70, r=SMALL_BALL_R, can_fall=True, friction=FRICTION_SMALL))
            self.balls.append(Ball(0, cx - 40, self.fb - 55, r=SMALL_BALL_R, can_fall=True, friction=FRICTION_SMALL))
            self.balls.append(Ball(0, self.fr - 20, self.fb - 40, can_fall=True, is_chase=True))
        elif self.stage == 18:
            self.balls.append(Ball(0, self.fl + 20, self.fb - 40, can_fall=True, is_chase=True))
        elif self.stage == 20:
            self.balls.append(Ball(0, cx + 65, self.fb - 80, r=SMALL_BALL_R, can_fall=True, friction=FRICTION_SMALL))
            self.balls.append(Ball(0, cx - 65, self.fb - 80, r=SMALL_BALL_R, can_fall=True, friction=FRICTION_SMALL))

    def _setup_stage_objects(self):
        self.walls = []
        self.bumpers = []
        self.repulsion_zones = []
        self.turrets = []
        if self.stage == 2:
            mid_y = (self.ft + self.fb) / 2.0
            h = 100
            self.walls = [
                RectWall(55, mid_y - h / 2, 16, h),
                RectWall(185, mid_y - h / 2, 16, h),
            ]
        elif self.stage == 4:
            mid_y = (self.ft + self.fb) / 2.0
            h = 100
            self.walls = [
                RectWall(55, mid_y - h / 2, 16, h),
                RectWall(185, mid_y - h / 2, 16, h),
            ]
        elif self.stage == 5:
            self.bumpers = [
                JetBumper(85, 105),
                JetBumper(171, 155),
            ]
        elif self.stage == 6:
            self.bumpers = [
                JetBumper(175, 170),
                JetBumper(85, 120),
                JetBumper(185, 55),
            ]
        elif self.stage == 8:
            self.bumpers = [
                JetBumper(60, 195),
                JetBumper(196, 195),
            ]
        elif self.stage == 9:
            mid_y = (self.ft + self.fb) / 2.0
            h = 100
            self.walls = [
                RectWall(185, mid_y - h / 2, 16, h),
            ]
        elif self.stage == 12:
            cx = (self.fl + self.fr) / 2.0
            mid_y = (self.ft + self.fb) / 2.0
            self.bumpers = [
                JetBumper(cx + 50, mid_y),
            ]
        elif self.stage in (13, 14):
            self.repulsion_zones = [RepulsionZone(self.hole_x, self.hole_y)]
        elif self.stage == 16:
            self.turrets = [
                Turret(55, 180, n_shots=2),
                Turret(200, 180, n_shots=2),
            ]
        elif self.stage == 15:
            self.turrets = [
                Turret(200, 180, n_shots=2),
            ]
        elif self.stage == 18:
            self.repulsion_zones = [RepulsionZone(self.hole_x, self.hole_y)]
        elif self.stage == 19:
            self.bumpers = [
                JetBumper(73, 183),
                JetBumper(183, 183),
            ]
            self.turrets = [
                Turret(self.fl + 40, 115, n_shots=2),
            ]
        elif self.stage == 20:
            self.bumpers = [JetBumper(48, 195)]
            self.repulsion_zones = [RepulsionZone(self.hole_x, self.hole_y)]
            self.turrets = [
                Turret(self.fl + 40, 115, n_shots=2),
                Turret(self.fr - 40, 115, n_shots=2),
            ]

    def update(self):
        self._update_input_device()
        for p in self.bg_particles:
            p.update()
        if self.scene == "title":
            min_cursor = 0 if self.unlocked > 1 else 1
            old_cursor = self.menu_cursor
            old_stage = self.selected_stage
            if pyxel.btnp(pyxel.KEY_UP) or pyxel.btnp(pyxel.KEY_W) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_UP):
                self.menu_cursor = max(min_cursor, self.menu_cursor - 1)
            if pyxel.btnp(pyxel.KEY_DOWN) or pyxel.btnp(pyxel.KEY_S) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_DOWN):
                self.menu_cursor = min(1, self.menu_cursor + 1)
            if self.menu_cursor == 0:
                if pyxel.btnp(pyxel.KEY_LEFT, 20, 6) or pyxel.btnp(pyxel.KEY_A, 20, 6) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_LEFT, 20, 6):
                    self.selected_stage = max(1, self.selected_stage - 1)
                if pyxel.btnp(pyxel.KEY_RIGHT, 20, 6) or pyxel.btnp(pyxel.KEY_D, 20, 6) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_RIGHT, 20, 6):
                    self.selected_stage = min(self.unlocked, self.selected_stage + 1)
            if self.menu_cursor != old_cursor or self.selected_stage != old_stage:
                pyxel.play(self._next_sfx_ch(), 3)
            if self.menu_cursor == 1 and (pyxel.btnp(pyxel.KEY_SPACE) or pyxel.btnp(pyxel.KEY_RETURN) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A)):
                self.stage = self.selected_stage
                self.scene = "game"
                self._init_stage()
            return

        if self.state != "play":
            if self.state == "dying":
                self.death_timer -= 1
                self.p.update()
                self._update_ball_physics()
                if self.death_timer <= 0:
                    self.state = "gameover"
                    pyxel.play(0, 2)
                return
            if self.state == "hole_fall":
                self.hole_fall_timer -= 1
                if self.hole_fall_timer > 0:
                    progress = 1.0 - self.hole_fall_timer / 60.0
                    self.p.x = self.hole_fall_start_x + (self.hole_x - self.hole_fall_start_x) * progress
                    self.p.y = self.hole_fall_start_y + (self.hole_y - self.hole_fall_start_y) * progress
                    self.hole_fall_scale = self.hole_fall_timer / 60.0
                    self.p.spin_angle += 0.15 + progress * 0.3
                else:
                    self.gameover_from_hole = True
                    self.state = "gameover"
                    pyxel.play(0, 2)
                return
            if self.state == "gameover":
                old_cursor = self.gameover_cursor
                if pyxel.btnp(pyxel.KEY_UP) or pyxel.btnp(pyxel.KEY_W) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_UP):
                    self.gameover_cursor = max(0, self.gameover_cursor - 1)
                if pyxel.btnp(pyxel.KEY_DOWN) or pyxel.btnp(pyxel.KEY_S) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_DOWN):
                    self.gameover_cursor = min(1, self.gameover_cursor + 1)
                if self.gameover_cursor != old_cursor:
                    pyxel.play(self._next_sfx_ch(), 3)
                if pyxel.btnp(pyxel.KEY_SPACE) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A):
                    if self.gameover_cursor == 0:
                        self._init_stage()
                    else:
                        self.stage = 1
                        self.menu_cursor = 1
                        self.scene = "title"
            elif self.state == "clear":
                if pyxel.btnp(pyxel.KEY_SPACE) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A):
                    if self.stage < 20:
                        self.stage += 1
                        self._init_stage()
                    else:
                        self.stage = 1
                        self.menu_cursor = 1
                        self.scene = "title"
            elif self.state == "pause_confirm":
                if pyxel.btnp(pyxel.KEY_ESCAPE):
                    self.state = "play"
                    return
                old_cursor = self.pause_cursor
                if pyxel.btnp(pyxel.KEY_UP) or pyxel.btnp(pyxel.KEY_W) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_UP):
                    self.pause_cursor = max(0, self.pause_cursor - 1)
                if pyxel.btnp(pyxel.KEY_DOWN) or pyxel.btnp(pyxel.KEY_S) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_DOWN):
                    self.pause_cursor = min(1, self.pause_cursor + 1)
                if self.pause_cursor != old_cursor:
                    pyxel.play(self._next_sfx_ch(), 3)
                if pyxel.btnp(pyxel.KEY_SPACE) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A):
                    if self.pause_cursor == 0:
                        self.stage = 1
                        self.menu_cursor = 1
                        self.scene = "title"
                    else:
                        self.state = "play"
            return

        if pyxel.btnp(pyxel.KEY_ESCAPE) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_START):
            self.state = "pause_confirm"
            self.pause_cursor = 0
            return

        self.hit_cooldown = max(0, self.hit_cooldown - 1)
        if self.hit_level_timer > 0:
            self.hit_level_timer -= 1
            if self.hit_level_timer == 0:
                self.hit_level = 0
        self.p.update()

        if self.p.x - PLAYER_R < self.fl:
            self.p.x = self.fl + PLAYER_R
            self.p.angle = math.pi - self.p.angle
        elif self.p.x + PLAYER_R > self.fr:
            self.p.x = self.fr - PLAYER_R
            self.p.angle = math.pi - self.p.angle
        if self.p.y - PLAYER_R < self.ft:
            self.p.y = self.ft + PLAYER_R
            self.p.angle = -self.p.angle
        elif self.p.y + PLAYER_R > self.fb:
            self.p.y = self.fb - PLAYER_R
            self.p.angle = -self.p.angle

        for w in self.walls:
            w.reflect_player(self.p)

        for bmp in self.bumpers:
            bmp.update()
            bmp.check_player(self.p)
            if bmp.hit_timer == 6 and self.hit_cooldown <= 0:
                self._play_hit_sound()
                self.hit_cooldown = 8

        for t in self.turrets:
            t.update()
            t.check_player(self.p, self.balls)

        for rz in self.repulsion_zones:
            rz.apply_to_player(self.p)

        px, py = self.p.x, self.p.y
        self.p.trail.append((px, py))

        if math.hypot(px - self.hole_x, py - self.hole_y) < HOLE_R:
            self.state = "hole_fall"
            self.hole_fall_timer = 60
            self.hole_fall_scale = 1.0
            self.hole_fall_start_x = self.p.x
            self.hole_fall_start_y = self.p.y
            self.p.crash = False
            self.p.spin_angle = 0.0
            self.gameover_cursor = 0
            pyxel.play(0, 22)
            return

        active = [b for b in self.balls if b.active]
        for b in active:
            b.update(self.fl, self.ft, self.fr, self.fb)
            if b.is_chase:
                dx = px - b.x
                dy = py - b.y
                d = math.hypot(dx, dy)
                if d > 0.1:
                    b.vx += (dx / d) * CHASE_ACCEL
                    b.vy += (dy / d) * CHASE_ACCEL
                    spd = math.hypot(b.vx, b.vy)
                    if spd > CHASE_MAX_SPD:
                        b.vx = b.vx / spd * CHASE_MAX_SPD
                        b.vy = b.vy / spd * CHASE_MAX_SPD

        for w in self.walls:
            for b in active:
                w.reflect_ball(b)

        for bmp in self.bumpers:
            for b in active:
                prev = bmp.hit_timer
                bmp.check_ball(b)
                if prev < 6 and bmp.hit_timer == 6 and self.hit_cooldown <= 0:
                    self._play_hit_sound()
                    self.hit_cooldown = 8

        for t in self.turrets:
            for b in active:
                t.check_ball(b, self.balls)

        for rz in self.repulsion_zones:
            for b in active:
                rz.apply_to_ball(b)

        active = [b for b in self.balls if b.active]

        for b in active:
            if b.can_fall and math.hypot(b.x - self.hole_x, b.y - self.hole_y) < HOLE_R:
                b.active = False
                if b.num != 9:
                    pyxel.play(self._next_sfx_ch(), 4)
        active = [b for b in self.balls if b.active]

        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                b1, b2 = active[i], active[j]
                dx = b2.x - b1.x
                dy = b2.y - b1.y
                d = math.hypot(dx, dy)
                if 0 < d < b1.r + b2.r:
                    nx, ny = dx / d, dy / d
                    rv = (b1.vx - b2.vx) * nx + (b1.vy - b2.vy) * ny
                    if rv > 0:
                        f = 2.0 / (b1.mass + b2.mass)
                        b1.vx -= f * b2.mass * rv * nx
                        b1.vy -= f * b2.mass * rv * ny
                        b2.vx += f * b1.mass * rv * nx
                        b2.vy += f * b1.mass * rv * ny
                        if self.hit_cooldown <= 0:
                            self._play_hit_sound()
                            self.hit_cooldown = 8
                    ov = b1.r + b2.r - d
                    r1 = b2.mass / (b1.mass + b2.mass)
                    r2 = b1.mass / (b1.mass + b2.mass)
                    b1.x -= nx * ov * r1
                    b1.y -= ny * ov * r1
                    b2.x += nx * ov * r2
                    b2.y += ny * ov * r2

        for b in active:
            d = math.hypot(px - b.x, py - b.y)
            if d < PLAYER_R + b.r:
                if self.p.crash:
                    self._strike(b)
                    continue
                if b.num == self.tnum:
                    self._strike(b)
                    self._play_hit_sound()
                else:
                    self._strike(b)
                    self.p.spin_angle = 0.0
                    self.p.crash = True
                    self._lose_life()
                    if self.state == "dying":
                        return

        tb = next((b for b in self.balls if b.num == self.tnum), None)
        if tb is None or not tb.active:
            self.tnum += 1
            if self.tnum > 9:
                self._trigger_clear()

        nine = next((b for b in self.balls if b.num == 9), None)
        if nine is not None and not nine.active:
            self._trigger_clear()

    def _update_ball_physics(self):
        px, py = self.p.x, self.p.y
        active = [b for b in self.balls if b.active]
        for b in active:
            b.update(self.fl, self.ft, self.fr, self.fb)
            if b.is_chase:
                dx = px - b.x
                dy = py - b.y
                d = math.hypot(dx, dy)
                if d > 0.1:
                    b.vx += (dx / d) * CHASE_ACCEL
                    b.vy += (dy / d) * CHASE_ACCEL
                    spd = math.hypot(b.vx, b.vy)
                    if spd > CHASE_MAX_SPD:
                        b.vx = b.vx / spd * CHASE_MAX_SPD
                        b.vy = b.vy / spd * CHASE_MAX_SPD
        for w in self.walls:
            for b in active:
                w.reflect_ball(b)
        for bmp in self.bumpers:
            bmp.update()
            for b in active:
                bmp.check_ball(b)
        for t in self.turrets:
            t.update()
            for b in active:
                t.check_ball(b, self.balls)
        for rz in self.repulsion_zones:
            for b in active:
                rz.apply_to_ball(b)
        active = [b for b in self.balls if b.active]
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                b1, b2 = active[i], active[j]
                dx = b2.x - b1.x
                dy = b2.y - b1.y
                d = math.hypot(dx, dy)
                if 0 < d < b1.r + b2.r:
                    nx, ny = dx / d, dy / d
                    rv = (b1.vx - b2.vx) * nx + (b1.vy - b2.vy) * ny
                    if rv > 0:
                        f = 2.0 / (b1.mass + b2.mass)
                        b1.vx -= f * b2.mass * rv * nx
                        b1.vy -= f * b2.mass * rv * ny
                        b2.vx += f * b1.mass * rv * nx
                        b2.vy += f * b1.mass * rv * ny
                    ov = b1.r + b2.r - d
                    r1 = b2.mass / (b1.mass + b2.mass)
                    r2 = b1.mass / (b1.mass + b2.mass)
                    b1.x -= nx * ov * r1
                    b1.y -= ny * ov * r1
                    b2.x += nx * ov * r2
                    b2.y += ny * ov * r2

    def _next_sfx_ch(self):
        ch = 1 + self.sfx_ch_idx
        self.sfx_ch_idx = (self.sfx_ch_idx + 1) % 3
        return ch

    def _play_hit_sound(self):
        pyxel.play(self._next_sfx_ch(), 6 + self.hit_level)
        self.hit_level = min(self.hit_level + 1, HIT_LEVEL_MAX)
        self.hit_level_timer = HIT_LEVEL_TIMEOUT

    def _lose_life(self):
        self.lives -= 1
        pyxel.play(self._next_sfx_ch(), 5)
        if self.lives <= 0:
            self.state = "dying"
            self.death_timer = 30
            self.gameover_cursor = 0

    def _strike(self, ball):
        px, py = self.p.x, self.p.y
        d = math.hypot(px - ball.x, py - ball.y)
        if d < 0.01:
            nx, ny = 1.0, 0.0
            d = 0.01
        else:
            nx = (ball.x - px) / d
            ny = (ball.y - py) / d

        mp = self.p.mass
        mb = ball.mass
        mass_f = 2.0 * mp / (mp + mb)

        imp = self.p.vx * nx + self.p.vy * ny
        ball_imp = ball.vx * nx + ball.vy * ny
        push = max(imp * 4.0 * mass_f, 3.5 * mass_f)
        ball.vx += nx * push
        ball.vy += ny * push
        if imp > 0:
            rvx = self.p.vx - 2 * imp * nx
            rvy = self.p.vy - 2 * imp * ny
            self.p.angle = math.atan2(rvy, rvx)
        elif ball_imp < 0:
            knock_spd = min(-ball_imp * mb / (mp + mb) * 2, PLAYER_SPD)
            if knock_spd > STOP_SPD:
                self.p.angle = math.atan2(-ny, -nx)
                self.p.spd = knock_spd

        ov = PLAYER_R + ball.r - d
        if ov > 0:
            rb = mb / (mp + mb)
            rp = mp / (mp + mb)
            self.p.x -= nx * ov * rb
            self.p.y -= ny * ov * rb
            ball.x += nx * ov * rp
            ball.y += ny * ov * rp

    def _draw_title(self):
        pyxel.cls(1)
        for p in self.bg_particles:
            p.draw()

        # タイトル文字
        title = "POCKET THE 9"
        tx = (SCREEN_W - len(title) * 4) // 2
        pyxel.text(tx + 1, 55, title, 0)
        pyxel.text(tx, 54, title, 10)

        # ボール装飾
        ball_y = 95
        total_w = 9 * (BALL_R * 2 + 4) - 4
        start_x = (SCREEN_W - total_w) // 2 + BALL_R
        for i in range(9):
            bx = start_x + i * (BALL_R * 2 + 4)
            if i == 8:
                pyxel.circ(bx, ball_y, BALL_R, 10)
                pyxel.circ(bx, ball_y, BALL_R - 3, 7)
                pyxel.circb(bx, ball_y, BALL_R, 10)
            else:
                col = 7 if i == 0 else 6
                pyxel.circ(bx, ball_y, BALL_R, col)
                pyxel.circb(bx, ball_y, BALL_R, 7)
            pyxel.text(bx - 2, ball_y - 3, str(i + 1), 0)

        # メニュー
        cursor_x = 88
        text_x = 100
        item_y = [148, 168]

        # 三角カーソル（右向き）
        cy = item_y[self.menu_cursor]
        pyxel.tri(cursor_x, cy - 4, cursor_x, cy + 4, cursor_x + 6, cy, 10)

        # STAGE項目（複数ステージ解放済みのときのみ表示）
        if self.unlocked > 1:
            on_stage = self.menu_cursor == 0
            stage_col = 7 if on_stage else 5
            if on_stage and self.selected_stage > 1:
                pyxel.text(text_x, item_y[0], "<", 7)
            stage_str = f"STAGE {self.selected_stage}"
            pyxel.text(text_x + 8, item_y[0], stage_str, stage_col)
            if on_stage and self.selected_stage < self.unlocked:
                pyxel.text(text_x + 8 + len(stage_str) * 4 + 2, item_y[0], ">", 7)

        # START項目
        start_col = 7 if self.menu_cursor == 1 else 5
        pyxel.text(text_x + 8, item_y[1], "START", start_col)

        hint = "DPAD:SELECT  A:DECIDE" if self.use_gamepad else "UP/DOWN:SELECT  SPACE:DECIDE"
        pyxel.text((SCREEN_W - len(hint) * 4) // 2, SCREEN_H - 14, hint, 5)

    def draw(self):
        if self.scene == "title":
            self._draw_title()
            return

        pyxel.cls(1)
        for p in self.bg_particles:
            p.draw()

        fw = self.fr - self.fl
        fh = self.fb - self.ft
        pyxel.rectb(self.fl, self.ft, fw, fh, 7)

        if self.stage == 1 and self.state not in ("gameover", "clear"):
            line1 = "Hit the target ball"
            line2 = "Pocket the 9-ball"
            cx = (self.fl + self.fr) // 2
            pyxel.text(cx - len(line1) * 2, 118, line1, 5)
            pyxel.text(cx - len(line2) * 2, 130, line2, 5)

        ctrl = "DPAD:MOVE  START:TITLE" if self.use_gamepad else "ARROWS:MOVE  ESC:TITLE"
        pyxel.text((SCREEN_W - len(ctrl) * 4) // 2, self.fb + 2, ctrl, 5)

        for w in self.walls:
            w.draw()
        for bmp in self.bumpers:
            bmp.draw()
        for t in self.turrets:
            t.draw()

        for rz in self.repulsion_zones:
            rz.draw()

        pyxel.circ(int(self.hole_x), int(self.hole_y), HOLE_R, 0)
        pyxel.circb(int(self.hole_x), int(self.hole_y), HOLE_R, 5)

        for b in self.balls:
            if not b.active:
                continue
            if b.is_chase:
                bx, by = int(b.x), int(b.y)
                pyxel.circ(bx, by, b.r, 8)
                pyxel.circb(bx, by, b.r, 9)
                pyxel.text(bx - 2, by - 3, "C", 7)
            elif b.num == 0 and b.r < BALL_R:
                if b.is_cannonball:
                    pyxel.circ(int(b.x), int(b.y), b.r, 9)
                    pyxel.circb(int(b.x), int(b.y), b.r, 8)
                else:
                    pyxel.circ(int(b.x), int(b.y), b.r, 12)
                    pyxel.circb(int(b.x), int(b.y), b.r, 7)
            elif b.num == 0:
                pyxel.circ(int(b.x), int(b.y), b.r, 13)
                pyxel.circb(int(b.x), int(b.y), b.r, 7)
            else:
                bx, by = int(b.x), int(b.y)
                if b.num == 9:
                    pyxel.circ(bx, by, b.r, 10)
                    pyxel.circ(bx, by, b.r - 3, 7)
                    pyxel.circb(bx, by, b.r, 7 if self.tnum == 9 else 10)
                else:
                    col = 7 if b.num == self.tnum else 6
                    pyxel.circ(bx, by, b.r, col)
                    pyxel.circb(bx, by, b.r, 7)
                pyxel.text(bx - 2, by - 3, str(b.num), 0)

        if self.p.crash:
            p_col, trail_hi, trail_mid = 8, 8, 2
        elif self.lives >= 3:
            p_col, trail_hi, trail_mid = 11, 11, 3
        elif self.lives == 2:
            p_col, trail_hi, trail_mid = 10, 10, 4
        else:
            p_col, trail_hi, trail_mid = 8, 8, 2

        if self.state not in ("dying", "hole_fall", "gameover"):
            trail = self.p.trail
            n = len(trail)
            for i, (tx, ty) in enumerate(trail):
                ratio = i / max(n - 1, 1)
                col = trail_hi if ratio > 0.65 else (trail_mid if ratio > 0.3 else 1)
                pyxel.pset(int(tx), int(ty), col)

        if not (self.state == "gameover" and self.gameover_from_hole):
            px, py = self.p.x, self.p.y
            ang = self.p.angle + (self.p.spin_angle if (self.p.crash or self.state == "hole_fall") else 0.0)
            fa = math.cos(ang)
            fb_s = math.sin(ang)
            ra = math.sin(ang)
            rb_s = -math.cos(ang)

            pscale = self.hole_fall_scale if self.state == "hole_fall" else 1.0
            pf = PLAYER_FRONT * pscale
            pb = PLAYER_BACK * pscale
            ps = PLAYER_SIDE * pscale

            x0 = int(px + fa * pf + ra * ps)
            y0 = int(py + fb_s * pf + rb_s * ps)
            x1 = int(px + fa * pf - ra * ps)
            y1 = int(py + fb_s * pf - rb_s * ps)
            x2 = int(px - fa * pb - ra * ps)
            y2 = int(py - fb_s * pb - rb_s * ps)
            x3 = int(px - fa * pb + ra * ps)
            y3 = int(py - fb_s * pb + rb_s * ps)

            pyxel.tri(x0, y0, x1, y1, x2, y2, p_col)
            pyxel.tri(x0, y0, x2, y2, x3, y3, p_col)
            pyxel.line(x0, y0, x1, y1, 7)
            pyxel.line(x1, y1, x2, y2, 7)
            pyxel.line(x2, y2, x3, y3, 7)
            pyxel.line(x3, y3, x0, y0, 7)

        hx = FIELD_L + 2
        hy = 5
        text_y = hy + 3
        stage_str = f"STAGE:{self.stage}"
        pyxel.text(hx, text_y, stage_str, 7)
        hx += (len(stage_str) + 2) * 4
        if self.tnum <= 9:
            pyxel.text(hx, text_y, "TARGET:", 7)
            hx += 32
            cx, cy = hx + 5, hy + 5
            if self.tnum == 9:
                pyxel.circ(cx, cy, 5, 10)
                pyxel.circ(cx, cy, 2, 7)
                pyxel.circb(cx, cy, 5, 10)
            else:
                pyxel.circ(cx, cy, 5, 7)
                pyxel.circb(cx, cy, 5, 7)
            pyxel.text(cx - 2, cy - 2, str(self.tnum), 0)
            hx += 16
        pyxel.text(hx, text_y, "LIFE:", 7)
        hx += 20
        for i in range(self.lives):
            pyxel.rect(hx + i * 7, text_y, 5, 5, 8)

        if self.state == "gameover":
            s = "GAME OVER"
            pyxel.text((SCREEN_W - len(s) * 4) // 2, SCREEN_H // 2 - 20, s, 8)
            items = ["CONTINUE", "TITLE"]
            for i, item in enumerate(items):
                col = 7 if i == self.gameover_cursor else 5
                iy = SCREEN_H // 2 + i * 14
                ix = (SCREEN_W - len(item) * 4) // 2
                pyxel.text(ix, iy, item, col)
            cy = SCREEN_H // 2 + self.gameover_cursor * 14
            cx = (SCREEN_W - len(items[0]) * 4) // 2 - 10
            pyxel.tri(cx, cy - 3, cx, cy + 3, cx + 5, cy, 10)
        elif self.state == "clear":
            if self.stage < 20:
                s = "STAGE CLEAR!"
                s2 = "PRESS SPACE FOR NEXT STAGE"
            else:
                s = "ALL CLEAR!"
                s2 = "PRESS SPACE FOR TITLE"
            pyxel.text((SCREEN_W - len(s) * 4) // 2, SCREEN_H // 2 - 4, s, 10)
            pyxel.text((SCREEN_W - len(s2) * 4) // 2, SCREEN_H // 2 + 8, s2, 7)
        elif self.state == "pause_confirm":
            bx, by, bw, bh = 72, 96, 112, 64
            pyxel.rect(bx, by, bw, bh, 0)
            pyxel.rectb(bx, by, bw, bh, 7)
            q = "RETURN TO TITLE?"
            pyxel.text((SCREEN_W - len(q) * 4) // 2, by + 10, q, 7)
            items = ["YES", "NO"]
            for i, item in enumerate(items):
                col = 10 if i == self.pause_cursor else 5
                iy = by + 28 + i * 14
                ix = (SCREEN_W - len(item) * 4) // 2
                pyxel.text(ix, iy, item, col)
            cy = by + 28 + self.pause_cursor * 14
            cx = (SCREEN_W - len(items[0]) * 4) // 2 - 10
            pyxel.tri(cx, cy - 3, cx, cy + 3, cx + 5, cy, 10)


App()
