#!/usr/bin/env python3
"""Render the review edit offline. Requires FFmpeg, Pillow, NumPy and SciPy.

Original media files are read only. All foreground resampling is downsampling;
the two missing Journey columns are padded, not stretched. Transitions are
spatial compositing fields, rendered into the final H.264 movie, never browser
video seeks or flat opacity dissolves.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
W, H, FPS = 1920, 1080, 30
DURATION = 31.2
SOURCES = ["zaru_3_web.mp4", "Journey:Yez Startle video.mp4",
           "seek_magic_table.png", "ophelia_landing_916_web.mp4",
           "shila_lastvideo.mp4", "yez_ekran_final_web.mp4"]
TRANSITIONS = [(6.2, 8.0), (9.8, 11.2), (14.4, 16.0),
               (20.0, 21.6), (24.1, 25.7)]
Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
X /= W
Y /= H
CREAM = np.array([244, 233, 225], np.float32)
TABLE_CREAM = np.array([243, 233, 221], np.float32)
RNG = np.random.default_rng(8204)
small_noise = RNG.random((7, 12)).astype(np.float32)
NOISE = np.asarray(Image.fromarray(small_noise, mode='F').resize(
    (W, H), Image.Resampling.BICUBIC), dtype=np.float32)
NOISE = gaussian_filter(NOISE, 35)


def smooth(a, b, value):
    q = np.clip((value - a) / (b - a), 0, 1)
    return q * q * (3 - 2 * q)


def field(cx, cy, sx, sy):
    return np.exp(-(((X - cx) / sx) ** 2 + ((Y - cy) / sy) ** 2))


def reveal(score, progress, feather=.065):
    if progress <= 0:
        return np.zeros((H, W), np.float32)
    if progress >= 1:
        return np.ones((H, W), np.float32)
    threshold = 1.12 - 1.24 * float(smooth(0, 1, progress))
    return smooth(threshold - feather, threshold + feather, score)


def replace(a, b, mask):
    return a + (b - a) * mask[..., None]


def plate(color):
    return np.broadcast_to(np.asarray(color, np.float32), (H, W, 3)).copy()


def light(frame):
    # Blurring is confined to the matte control signal, never the artwork.
    luminance = frame[..., 0] * .2126 + frame[..., 1] * .7152 + frame[..., 2] * .0722
    low = np.asarray(Image.fromarray(luminance.astype(np.float32), mode='F').resize(
        (160, 90), Image.Resampling.BILINEAR))
    low = gaussian_filter(low, 3)
    return np.asarray(Image.fromarray(low, mode='F').resize(
        (W, H), Image.Resampling.BILINEAR), dtype=np.float32) / 255


class Clip:
    def __init__(self, name, width, height, offset=0, pad=False):
        self.name, self.width, self.height = name, width, height
        self.offset, self.pad = offset, pad
        self.process = None
        self.index, self.last = -1, None

    def get(self, time):
        if self.process is None:
            filters = f'fps={FPS},scale={self.width}:{self.height}:flags=lanczos'
            if self.pad:
                filters = f'fps={FPS},pad=1920:1080:1:0:black'
            self.process = subprocess.Popen([
                'ffmpeg', '-v', 'error', '-threads', '2', '-ss', str(self.offset),
                '-i', str(ROOT / self.name), '-an', '-vf', filters,
                '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'], stdout=subprocess.PIPE)
        target = max(0, int(time * FPS + .0001))
        size = self.width * self.height * 3
        while self.index < target:
            data = self.process.stdout.read(size)
            if len(data) != size:
                break
            self.last = np.frombuffer(data, np.uint8).reshape(self.height, self.width, 3)
            self.index += 1
        if self.last is None:
            raise RuntimeError(f'No frame decoded: {self.name}')
        return self.last

    def close(self):
        if self.process:
            # Partial clips intentionally end before their source file does.
            self.process.kill()
            self.process.wait()
            self.process.stdout.close()


def positioned(image, center, alpha=None, background=None):
    h, w = image.shape[:2]
    x, y = int(center[0] - w / 2), int(center[1] - h / 2)
    result = plate([0, 0, 0]) if background is None else background.copy()
    mask = np.zeros((H, W), np.float32)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    src = image[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = np.ones((y1 - y0, x1 - x0), np.float32) if alpha is None else alpha[y0 - y:y1 - y, x0 - x:x1 - x]
    result[y0:y1, x0:x1] = replace(result[y0:y1, x0:x1], src, a)
    mask[y0:y1, x0:x1] = a
    return result, mask


class Edit:
    def __init__(self):
        self.zaru = Clip(SOURCES[0], 1440, 792)
        self.journey = Clip(SOURCES[1], W, H, pad=True)
        self.ophelia = Clip(SOURCES[3], 432, 768, offset=.5)
        self.shila = Clip(SOURCES[4], 1280, 720)
        self.maker = Clip(SOURCES[5], W, H)
        table = np.asarray(Image.open(ROOT / SOURCES[2]).convert('RGBA').resize(
            (1600, 900), Image.Resampling.LANCZOS))
        self.table_alpha = table[..., 3].astype(np.float32) / 255
        self.table, self.table_mask = positioned(table[..., :3], (820, 562),
            self.table_alpha, plate(TABLE_CREAM))
        self.orb = field(.484, .15, .38, .55)
        self.plant = field(.245, .775, .48, .52)
        self.gaze = field(.50, .32, .38, .35)
        py, px = np.mgrid[0:768, 0:432].astype(np.float32)
        # The matte only feathers source peripheries; face and pendant stay sharp.
        self.portrait_alpha = (smooth(0, 72, px) * smooth(0, 72, 431 - px)
            * smooth(0, 90, py) * smooth(0, 120, 767 - py))
        sy, sx = np.mgrid[0:720, 0:1280].astype(np.float32)
        self.clock_radius = np.sqrt(((sx - 644) / 337) ** 2 + ((sy - 358) / 355) ** 2)

    def z(self, t):
        return positioned(self.zaru.get(t), (1030, 520))[0]

    def j(self, t):
        return self.journey.get(min(4.96, max(0, t - 6.2))).astype(np.float32)

    def o(self, t):
        source = self.ophelia.get(max(0, t - 14.4))
        # Separate, deliberately diffuse surrounding field from the real footage.
        # The foreground is always downsampled from 1080x1920 to 432x768.
        # Use the shot's real edge colors for a seamless surrounding atmosphere.
        # No enlarged duplicate of the woman's face is used behind her.
        perimeter = np.concatenate([source[:36].reshape(-1, 3), source[:, :22].reshape(-1, 3), source[:, -22:].reshape(-1, 3)])
        ambient_color = np.median(perimeter, axis=0).astype(np.float32)
        atmosphere = np.exp(-(((X - 1220 / W) / .25) ** 4 + ((Y - .48) / .82) ** 8))
        surrounding = replace(plate(CREAM), plate(ambient_color), atmosphere)
        return positioned(source, (1220, 520), self.portrait_alpha, surrounding)[0]

    def s(self, t):
        source = self.shila.get(min(5.66, max(0, t - 20)))
        # Preserve the complete painted interior, remove only source canvas.
        cream = np.array([244, 233, 216], np.float32)
        key = smooth(7, 28, np.linalg.norm(source.astype(np.float32) - cream, axis=2))
        inner = 1 - smooth(.91, .979, self.clock_radius)
        alpha = np.maximum(inner, key) * (1 - smooth(1.002, 1.027, self.clock_radius))
        return positioned(source, (960, 520), alpha, plate(CREAM))

    def b(self, t):
        # One uninterrupted native shot, including flight, laptop and maker.
        return self.maker.get(max(0, t - 24.1)).astype(np.float32)

    def frame(self, t):
        if t < 6.2:
            return self.z(t)
        if t < 8:
            p = (t - 6.2) / 1.8
            a, b = self.z(t), self.j(t)
            # Plant light travels through negative space. The woman's face is
            # deliberately late in the field so the pendant owns the first half.
            score = .64 * self.plant + .28 * np.minimum(light(b) * 2, 1) + .08 * NOISE
            return replace(a, b, reveal(score, p, .085))
        if t < 9.8:
            return self.j(t)
        if t < 11.2:
            p = (t - 9.8) / 1.4
            a = self.j(t)
            environment = reveal(.51 * X + .41 * self.orb + .08 * NOISE, min(1, p * 1.23), .095)
            result = replace(a, plate(TABLE_CREAM), environment)
            material = reveal(.66 * (1 - Y) + .26 * self.orb + .08 * NOISE, min(1, p * 1.16), .085)
            # A physical object emerges only where its environment has arrived.
            result = replace(result, self.table, self.table_mask * material * environment)
            return result
        if t < 14.4:
            return self.table
        if t < 16:
            p = (t - 14.4) / 1.6
            # Clear the tabletop to light before the right-hand face enters.
            outgoing = reveal(.53 * self.orb + .39 * (1 - Y) + .08 * NOISE, min(1, p * 1.55), .09)
            result = replace(self.table, plate(TABLE_CREAM), outgoing)
            field_change = reveal(.66 * X + .26 * self.orb + .08 * NOISE, p, .10)
            result = replace(result, plate(CREAM), field_change * (1 - self.table_mask * (1 - outgoing)))
            portrait = self.o(t)
            score = .68 * field(.635, .54, .30, .9) + .24 * (1 - Y) + .08 * NOISE
            incoming = reveal(score, max(0, (p - .15) / .85), .085)
            return replace(result, portrait, incoming)
        if t < 20:
            return self.o(t)
        if t < 21.6:
            p = (t - 20) / 1.6
            a, (b, clock_mask) = self.o(t), self.s(t)
            leave = reveal(.48 * field(.63, .35, .35, .72) + .44 * (1 - Y) + .08 * NOISE,
                           min(1, p * 1.9), .085)
            result = replace(a, plate(CREAM), leave)
            # Red painted clothing leads; the cat's face follows only after
            # Ophelia's face has gone. No transparent clock over a human face.
            arrive = reveal(.35 + .39 * Y + .08 * NOISE + .18 * light(b),
                            max(0, (p - .05) / .95), .065)
            return replace(result, b, arrive * clock_mask)
        if t < 24.1:
            return self.s(t)[0]
        if t < 25.7:
            p = (t - 24.1) / 1.6
            a, clock_mask = self.s(t)
            b = self.b(t)
            # Painted gaze gives way to real eyes and feather texture. A single
            # field replaces artwork AND cream, so no cream rectangle survives.
            score = .32 + .38 * self.gaze + .22 * np.minimum(light(b) * 2.2, 1) + .08 * NOISE
            world = reveal(score, min(1, p * 1.14), .08)
            clock_leaves = reveal(.28 + .58 * self.gaze + .14 * NOISE, min(1, p * 1.50), .075)
            environment = replace(plate(CREAM), b, world)
            return replace(environment, a, clock_mask * (1 - clock_leaves) * (1 - world))
        return self.b(t)

    def close(self):
        for clip in [self.zaru, self.journey, self.ophelia, self.shila, self.maker]:
            clip.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'public/film/yang-theory-film.mp4')
    parser.add_argument('--stills', type=Path, help='Optional local validation frames, not a deliverable')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    edit = Edit()
    encoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-threads', '3',
        '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
        '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17',
        '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-level:v', '4.1',
        '-g', '60', '-movflags', '+faststart', '-y', str(args.output)], stdin=subprocess.PIPE)
    still_times = [0, 1.5, 4, 6.2, 7.1, 8, 9.8, 10.5, 11.2, 13,
                   14.4, 15.2, 16, 18, 20, 20.8, 21.6, 23, 24.1, 24.9,
                   25.7, 27.4, 28.6, 31.0]
    still_indices = {round(t * FPS): t for t in still_times}
    try:
        for i in range(round(DURATION * FPS)):
            frame = np.clip(edit.frame(i / FPS), 0, 255).astype(np.uint8)
            if args.stills and i in still_indices:
                args.stills.mkdir(parents=True, exist_ok=True)
                Image.fromarray(frame).save(args.stills / f'{still_indices[i]:05.2f}.jpg', quality=94)
            encoder.stdin.write(frame.tobytes())
            if i % 60 == 0:
                print(f'Rendered {i / FPS:.1f} / {DURATION:.1f}s', flush=True)
    finally:
        encoder.stdin.close()
        edit.close()
    if encoder.wait() != 0:
        raise RuntimeError('Movie encoder failed')
    manifest = {'output': args.output.name, 'width': W, 'height': H, 'fps': FPS,
        'duration': DURATION, 'transitions': TRANSITIONS,
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES},
        'source_ranges': {'Zaru': [0, 8], 'Journey': [0, 5],
            'Seek Magic': 'original unchanged transparent PNG', 'Ophelia': [.5, 7.7],
            'Shila': [0, 5.7], 'Burton / maker': [0, 7.1]}}
    args.output.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Completed: {args.output} ({args.output.stat().st_size / 1e6:.1f} MB)', flush=True)


if __name__ == '__main__':
    main()
