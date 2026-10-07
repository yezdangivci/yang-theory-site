#!/usr/bin/env python3
"""Short Ophelia / original-PNG zoom-out / moving-hands review, not a hero render.

Requires numpy, Pillow and opencv-python-headless, plus ffmpeg.
The ruby-to-garment bridge is a correspondence / material morph. The approved
Shila zoom-out follows it unchanged. Shila colors are not corrected: the user
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
from red_material_bridge import RedMaterialBridge
cv2.setNumThreads(2)

ROOT = Path(__file__).resolve().parents[1]
W, H, FPS = 1920, 1080, 30
IVORY = np.array([244, 233, 225], np.float32)
OPHELIA_IN = 11.6
OPHELIA_FRAMES = 95
ZOOM_FRAMES = 84
BRIDGE_FRAMES = 27
SHILA_FRAMES = 176
HANDOFF_FRAME = OPHELIA_FRAMES + BRIDGE_FRAMES + ZOOM_FRAMES
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
        # Freeze the approved uniform registration and zoom path. A color-only
        # replacement source must not subtly reframe the artwork via a new fit.
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
        progress = float(ease(t))
        final_scale = np.hypot(self.end[0, 0], self.end[1, 0])
        initial_scale = .58  # < 1 native pixel per canvas pixel: no enlargement.
        scale = np.exp(np.log(initial_scale)*(1-progress)+np.log(final_scale)*progress)
        # Select existing red clothing only; no new object or reframing of Ophelia.
        red_reference = np.array([937., 758., 1.])
        red_native = (np.linalg.inv(self.homogeneous(self.registration)) @ red_reference)[:2]
        start = np.array([[initial_scale, 0, 960-initial_scale*red_native[0]],
                          [0, initial_scale, 717-initial_scale*red_native[1]]])
        matrix = self.end.copy()
        angle = np.arctan2(self.end[1, 0], self.end[0, 0])*progress
        matrix[:, :2] = [[scale*np.cos(angle), -scale*np.sin(angle)],
                        [scale*np.sin(angle), scale*np.cos(angle)]]
        # Red detail starts in the pendant's screen region; the completed artwork
        # ends precisely centered. This positioning belongs to the requested reveal.
        red_position = np.array([960., 717.])*(1-progress)+(self.end @ np.r_[red_native, 1])*progress
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
    outgoing = ophelia(tail[-1])
    incoming = match.png_frame(0)
    native_tail = list(decode('ophelia_landing_916_web.mp4', 14.65, (1080, 1920)))
    bridge = RedMaterialBridge(outgoing, incoming, native_tail[-1], match.png, match.png_matrix(0)[0])
    assert np.array_equal(bridge.frame(0), outgoing)
    assert np.array_equal(bridge.frame(1), incoming)
    try:
        for i in range(OPHELIA_FRAMES):
            write(ophelia(tail[min(i, len(tail)-1)]))
        for i in range(BRIDGE_FRAMES):
            material = bridge.frame(i/(BRIDGE_FRAMES-1))
            if i in [6, 13, 20]:
                Image.fromarray(material.astype('uint8')).save(args.qa/f'red-bridge-{i}.png')
            write(material)
        for i in range(ZOOM_FRAMES):
            write(match.png_frame(i))
        for i in range(SHILA_FRAMES):
            write(match.video_frame(i))
    finally:
        encoder.stdin.close()
    assert encoder.wait() == 0
    assert count == OPHELIA_FRAMES+BRIDGE_FRAMES+ZOOM_FRAMES+SHILA_FRAMES
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in hashes.items())
    metadata = {'width': W, 'height': H, 'fps': FPS, 'frames': count, 'duration': count/FPS,
        'ophelia_source_in': OPHELIA_IN, 'red_bridge_start': OPHELIA_FRAMES/FPS,
        'red_bridge_duration': BRIDGE_FRAMES/FPS, 'png_start': (OPHELIA_FRAMES+BRIDGE_FRAMES)/FPS,
        'video_handoff': HANDOFF_FRAME/FPS, 'video_source_in': 0, 'complete_shila_video': True,
        'original_files_sha256': hashes, 'handoff_metrics': metrics,
        'treatment': 'Red-fold / brush-stroke correspondence material morph; approved original-PNG zoom-out; uncorrected shila_final.mp4 from frame zero.',
        'shila_color_correction': False, 'approved_zoom_frames': ZOOM_FRAMES,
        'full_hero_rendered': False}
    args.output.with_suffix('.json').write_text(json.dumps(metadata, indent=2)+'\n')
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', '4.7', '-i', str(args.output), '-frames:v', '1',
                    '-q:v', '2', '-y', str(args.output.with_name('poster.jpg'))], check=True)
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == '__main__':
    main()
