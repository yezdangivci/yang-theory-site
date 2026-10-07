#!/usr/bin/env python3
"""Short Ophelia / original-PNG zoom-out / moving-hands review, not a hero render.

Requires numpy, Pillow and opencv-python-headless, plus ffmpeg.
The ruby smoke dispersal and Shila camera move overlap on one timeline. The
full-clock framing is retained. Shila colors are not corrected: the user
supplied the corrected shila_final.mp4. Existing clock hands play uninterrupted.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from red_smoke_bridge import RedSmokeBridge
cv2.setNumThreads(2)

ROOT = Path(__file__).resolve().parents[1]
W, H, FPS = 1920, 1080, 30
IVORY = np.array([244, 233, 225], np.float32)
OPHELIA_IN = 11.6
OPHELIA_FRAMES = 42  # 11.6–13.0s: emit from the original red stone at 13s.
ZOOM_FRAMES = 84
BRIDGE_FRAMES = 48
ZOOM_START = 16  # Begin camera motion under expanding smoke, not after it.
ZOOM_OVERLAP = BRIDGE_FRAMES-ZOOM_START
SHILA_FRAMES = 176
HANDOFF_FRAME = OPHELIA_FRAMES + ZOOM_START + ZOOM_FRAMES
SCALE = .831


def ease(t):
    t = np.clip(t, 0, 1)
    return t*t*(3-2*t)


def decode(name, start=0, size=(W, H)):
    path = ROOT/name
    args = ['ffmpeg', '-v', 'error', '-threads', '2', '-ss', str(start), '-i', str(path),
            '-an', '-vf', f'fps={FPS},scale={size[0]}:{size[1]}:flags=lanczos',
            '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1']
    process = subprocess.Popen(args, stdout=subprocess.PIPE)
    try:
        while True:
            data = process.stdout.read(size[0]*size[1]*3)
            if len(data) != size[0]*size[1]*3:
                break
            yield np.frombuffer(data, np.uint8).reshape(size[1], size[0], 3).copy()
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()
        process.wait()


class Handoff:
    def __init__(self):
        self.png = np.array(Image.open(ROOT/'shila_original.png').convert('RGBA'))
        self.video = list(decode('shila_final.mp4'))
        assert len(self.video) == SHILA_FRAMES
        # Retain the approved full-clock registration; only the requested
        # starting crop and continuous camera path change.
        self.registration = np.array([[.26562231405493836, -.000051125836463486105, 409.560024194332],
                                      [.000051125836463486105, .26562231405493836, -174.92425049722073]])
        self.registration_error = .7612966299057007
        rgba = cv2.warpAffine(self.png, self.registration, (W, H), flags=cv2.INTER_LANCZOS4)
        self.alpha = np.clip(rgba[..., 3].astype(np.float32)/255, 0, 1)
        self.registered = rgba[..., :3].astype(np.float32)
        yy, xx = np.where(self.alpha > .98)
        self.art_center = np.array([(xx.min()+xx.max())/2, (yy.min()+yy.max())/2])
        self.full = np.array([[SCALE, 0, 960-SCALE*self.art_center[0]],
                              [0, SCALE, 540-SCALE*self.art_center[1]]], np.float64)
        self.end = (self.homogeneous(self.full) @ self.homogeneous(self.registration))[:2]
        self.match_mask = self.alpha > .99
        self.sigma = 1.0  # Approved final optical softness; no color matching.

    @staticmethod
    def homogeneous(matrix):
        return np.vstack([matrix, [0, 0, 1]])

    def png_frame(self, index):
        matrix, scale, t = self.png_matrix(index)
        rgba = cv2.warpAffine(self.png, matrix, (W, H), flags=cv2.INTER_LANCZOS4,
                              borderValue=tuple(int(v) for v in (*IVORY, 0)))
        rgb = rgba[..., :3].astype(np.float32)
        alpha = np.clip(rgba[..., 3:4].astype(np.float32)/255, 0, 1)
        strength = float(ease((t-.66)/.34))
        if strength > 0:
            # Preserve the approved softness envelope only. Original PNG colors.
            rgb = cv2.GaussianBlur(rgb, (0, 0), max(.01, self.sigma*strength*scale/.26562))
        return IVORY*(1-alpha)+rgb*alpha

    def png_matrix(self, index):
        t = index/(ZOOM_FRAMES-1)
        # Nonzero starting velocity: the emerging garment is already moving.
        # Decelerate smoothly into the unchanged full-clock composition.
        progress = float(t+t*t-t*t*t)
        final_scale = np.hypot(self.end[0, 0], self.end[1, 0])
        initial_scale = .90  # Tighter detail, still downsampled from native PNG.
        scale = np.exp(np.log(initial_scale)*(1-progress)+np.log(final_scale)*progress)
        # Select existing red clothing only; no new object or reframing of Ophelia.
        red_native = np.array([1980., 3790.])  # Painted bodice below mechanism.
        matrix = self.end.copy()
        angle = np.arctan2(self.end[1, 0], self.end[0, 0])*progress
        matrix[:, :2] = [[scale*np.cos(angle), -scale*np.sin(angle)],
                        [scale*np.sin(angle), scale*np.cos(angle)]]
        # Raise the tighter bodice detail; scale and placement travel together
        # along one camera path into the unchanged centered full clock.
        red_position = np.array([947., 580.])*(1-progress)+(self.end @ np.r_[red_native, 1])*progress
        matrix[:, 2] = red_position-matrix[:, :2] @ red_native
        return matrix, scale, t

    def video_frame(self, index):
        rgb = self.video[index].astype(np.float32)
        # Both representations use the very same stationary artwork-edge matte.
        premultiplied = rgb*self.alpha[..., None]
        foreground = cv2.warpAffine(premultiplied, self.full, (W, H), flags=cv2.INTER_LANCZOS4)
        alpha = cv2.warpAffine(self.alpha, self.full, (W, H), flags=cv2.INTER_LANCZOS4)
        alpha = np.clip(alpha, 0, 1)
        return foreground+IVORY*(1-alpha[..., None])


def ophelia(frame):
    # The same sharp centered portrait presentation as the current landing hero.
    yy, xx = np.mgrid[:864, :486].astype(np.float32)
    alpha = ease(xx/32)*ease((485-xx)/32)*ease(yy/30)*ease((863-yy)/34)
    ambient = np.pad(frame, ((108, 108), (717, 717), (0, 0)), mode='edge')
    ambient = cv2.GaussianBlur(ambient.astype(np.float32), (0, 0), 45)
    y, x = np.mgrid[:H, :W].astype(np.float32)
    field = np.exp(-((x-960)/515)**4-((y-540)/820)**8)*ease(y/108)*ease((1080-y)/108)
    canvas = IVORY+field[..., None]*(ambient-IVORY)
    area = canvas[108:972, 717:1203]
    canvas[108:972, 717:1203] = area+alpha[..., None]*(frame.astype(np.float32)-area)
    return canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'public/previews/shila-handoff/preview.mp4')
    parser.add_argument('--qa', type=Path, default=Path('/tmp/yang-shila-preview-qa'))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.qa.mkdir(parents=True, exist_ok=True)
    hashes = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
              for name in ['shila_original.png', 'shila_final.mp4', 'ophelia_landing_916_web.mp4']}
    match = Handoff()
    last_png, first_video = match.png_frame(ZOOM_FRAMES-1), match.video_frame(0)
    opaque = cv2.warpAffine(match.match_mask.astype('uint8'), match.full, (W, H)).astype(bool)
    error = np.abs(last_png-first_video)[opaque]
    metrics = {'mean_rgb_absolute_error': np.mean(error, axis=0).tolist(),
               'median_rgb_absolute_error': np.median(error, axis=0).tolist(),
               'registration_median_error_px': match.registration_error}
    for name, frame in [('png-before-switch', last_png), ('video-after-switch', first_video),
                        ('original-red-detail', match.png_frame(0))]:
        Image.fromarray(np.clip(frame, 0, 255).astype('uint8')).save(args.qa/f'{name}.png')
    encoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
        '-s', f'{W}x{H}', '-r', str(FPS), '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-threads', '3',
        '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-g', '30', '-movflags', '+faststart',
        '-y', str(args.output)], stdin=subprocess.PIPE)
    count = 0
    def write(frame):
        nonlocal count
        encoder.stdin.write(np.clip(frame, 0, 255).astype('uint8').tobytes())
        count += 1
        if count % 30 == 0:
            print(f'Rendered section preview {count/FPS:.1f}s', flush=True)
    tail = list(decode('ophelia_landing_916_web.mp4', OPHELIA_IN, (486, 864)))
    incoming = match.png_frame(0)
    bridge = RedSmokeBridge(origin=(947, 760))
    assert np.array_equal(bridge.frame(0, ophelia(tail[OPHELIA_FRAMES]), incoming), ophelia(tail[OPHELIA_FRAMES]))
    assert np.array_equal(bridge.frame(1, ophelia(tail[-1]), incoming), incoming)
    try:
        for i in range(OPHELIA_FRAMES):
            write(ophelia(tail[min(i, len(tail)-1)]))
        for i in range(BRIDGE_FRAMES):
            # The single camera advances every frame under the same cloud.
            # Continue the same indices after the cloud; never restart at zero.
            moving_shila = match.png_frame(max(0, i-ZOOM_START))
            progress = i/(BRIDGE_FRAMES-1)
            outgoing = ophelia(tail[min(OPHELIA_FRAMES+i, len(tail)-1)]) if progress < .38 else moving_shila
            material = bridge.frame(progress, outgoing, moving_shila)
            if i in [6, 14, 18, 23, 28, 32, 38, 40, 47]:
                Image.fromarray(material.astype('uint8')).save(args.qa/f'red-smoke-{i}.png')
            write(material)
        for i in range(ZOOM_OVERLAP, ZOOM_FRAMES):
            write(match.png_frame(i))
        for i in range(SHILA_FRAMES):
            write(match.video_frame(i))
    finally:
        encoder.stdin.close()
    assert encoder.wait() == 0
    assert count == HANDOFF_FRAME+SHILA_FRAMES
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in hashes.items())
    metadata = {'width': W, 'height': H, 'fps': FPS, 'frames': count, 'duration': count/FPS,
        'ophelia_source_in': OPHELIA_IN, 'red_bridge_start': OPHELIA_FRAMES/FPS,
        'red_bridge_duration': BRIDGE_FRAMES/FPS, 'png_start': (OPHELIA_FRAMES+ZOOM_START)/FPS,
        'zoom_starts_under_smoke': True, 'zoom_overlap_frames': ZOOM_OVERLAP,
        'smoke_clear_frame': OPHELIA_FRAMES+30,
        'initial_native_scale': .90, 'initial_garment_native_point': [1980, 3790],
        'initial_garment_screen_point': [947, 580],
        'video_handoff': HANDOFF_FRAME/FPS, 'video_source_in': 0, 'complete_shila_video': True,
        'original_files_sha256': hashes, 'handoff_metrics': metrics,
        'treatment': 'Original Ophelia at 13s; soft ruby smoke and tighter garment camera move overlap continuously; same final full-clock framing and uncorrected shila_final.mp4.',
        'ophelia_smoke_source_time': OPHELIA_IN+OPHELIA_FRAMES/FPS,
        'source_deformation': False, 'shot_crossfade': False,
        'shila_color_correction': False, 'zoom_frames': ZOOM_FRAMES,
        'full_hero_rendered': False}
    args.output.with_suffix('.json').write_text(json.dumps(metadata, indent=2)+'\n')
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', '1.5', '-i', str(args.output), '-frames:v', '1',
                    '-q:v', '2', '-y', str(args.output.with_name('poster.jpg'))], check=True)
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == '__main__':
    main()
