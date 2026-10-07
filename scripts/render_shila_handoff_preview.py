#!/usr/bin/env python3
"""Short Ophelia / original-PNG zoom-out / moving-hands review, not a hero render.

Requires numpy, Pillow, scipy and opencv-python-headless, plus ffmpeg.
The only animated image transform is the explicitly requested Shila zoom-out.
The technical match changes color coefficients and optical softness on the SAME
PNG pixels. There is no opacity transition to a video frame. At the handoff the
source switches once, directly to video frame zero, then plays it uninterrupted.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
W, H, FPS = 1920, 1080, 30
IVORY = np.array([244, 233, 225], np.float32)
OPHELIA_IN = 11.6
OPHELIA_FRAMES = 95
ZOOM_FRAMES = 84
SHILA_FRAMES = 176
HANDOFF_FRAME = OPHELIA_FRAMES + ZOOM_FRAMES
SCALE = .831
TERMS = [(i, j, k) for i in range(4) for j in range(4-i) for k in range(4-i-j)]


def ease(t):
    t = np.clip(t, 0, 1)
    return t*t*(3-2*t)


def basis(rgb):
    r, g, b = rgb.T
    return np.stack([r**i*g**j*b**k for i, j, k in TERMS], axis=-1)


def grade(rgb, coefficients):
    output = np.empty_like(rgb, np.float32)
    for y in range(0, rgb.shape[0], 64):
        tile = rgb[y:y+64]
        output[y:y+64] = (basis(tile.reshape(-1, 3)/255) @ coefficients).reshape(tile.shape)*255
    return output


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
        self.video = list(decode('shila_lastvideo.mp4'))
        assert len(self.video) == SHILA_FRAMES
        reference = self.video[0]
        self.registration = self.register(reference)
        rgba = cv2.warpAffine(self.png, self.registration, (W, H), flags=cv2.INTER_LANCZOS4)
        self.alpha = np.clip(rgba[..., 3].astype(np.float32)/255, 0, 1)
        self.registered = rgba[..., :3].astype(np.float32)
        yy, xx = np.where(self.alpha > .98)
        self.art_center = np.array([(xx.min()+xx.max())/2, (yy.min()+yy.max())/2])
        self.full = np.array([[SCALE, 0, 960-SCALE*self.art_center[0]],
                              [0, SCALE, 540-SCALE*self.art_center[1]]], np.float64)
        self.end = (self.homogeneous(self.full) @ self.homogeneous(self.registration))[:2]
        self.fit_technical_match(reference)

    @staticmethod
    def homogeneous(matrix):
        return np.vstack([matrix, [0, 0, 1]])

    def register(self, reference):
        # A uniform similarity alignment, never perspective or product warping.
        bbox = Image.fromarray(self.png[..., 3]).getbbox()
        x0, y0, x1, y1 = bbox
        crop = self.png[y0:y1, x0:x1]
        small = cv2.resize(crop, (round(crop.shape[1]/4), round(crop.shape[0]/4)), interpolation=cv2.INTER_AREA)
        sift = cv2.SIFT_create(nfeatures=6000)
        k1, d1 = sift.detectAndCompute(cv2.cvtColor(small[..., :3], cv2.COLOR_RGB2GRAY), small[..., 3])
        k2, d2 = sift.detectAndCompute(cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY), None)
        matches = [m for m, n in cv2.BFMatcher().knnMatch(d1, d2, k=2) if m.distance < .72*n.distance]
        p1 = np.float32([k1[m.queryIdx].pt for m in matches])
        p2 = np.float32([k2[m.trainIdx].pt for m in matches])
        matrix, inliers = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=2, maxIters=10000)
        predicted = cv2.transform(p1[:, None], matrix).squeeze(1)
        residual = np.linalg.norm(predicted-p2, axis=1)[inliers.ravel().astype(bool)]
        self.registration_error = float(np.median(residual))
        matrix[:, :2] *= .25
        matrix[:, 2] -= matrix[:, :2] @ np.array([x0, y0])
        return matrix

    def fit_technical_match(self, reference):
        mask = cv2.erode((self.alpha > .99).astype('uint8'), np.ones((17, 17), 'uint8')).astype(bool)
        # Do not derive a color correction from the different moving-hand pixels.
        stack = np.stack(self.video[::30]).astype(np.float32)
        stable = np.max(np.ptp(stack, axis=0), axis=2) < 13
        mask &= stable
        mask &= (self.registered.min(axis=2) > 12) & (reference.min(axis=2) > 12)
        yy, xx = np.where(mask)
        chosen = np.random.default_rng(8).choice(len(yy), min(70000, len(yy)), replace=False)
        yy, xx = yy[chosen], xx[chosen]
        # Match the video's optical softness, measured at its native 1080p scale.
        # 1 px reproduces the measured reference's high-frequency detail energy;
        # a larger blur lowers pixel error but visibly over-softens the artwork.
        self.sigma = 1.0
        blurred = cv2.GaussianBlur(self.registered, (0, 0), self.sigma)
        A = basis(blurred[yy, xx]/255)
        B = reference[yy, xx].astype(np.float32)/255
        self.coefficients = np.linalg.solve(A.T @ A + np.eye(len(TERMS))*.025, A.T @ B)
        corrected = grade(blurred, self.coefficients)
        # A smooth, source-registered color/illumination calibration field removes
        # spatial lighting differences left after the global color/contrast fit.
        # It contains no transferred paint texture or clock-hand animation.
        weight = mask.astype(np.float32)
        denominator = cv2.GaussianBlur(weight, (0, 0), 8)
        difference = (reference.astype(np.float32)-corrected)*weight[..., None]
        self.field = cv2.GaussianBlur(difference, (0, 0), 8)/np.maximum(denominator[..., None], .001)
        self.field *= (denominator > .01)[..., None]
        self.match_mask = mask
        self.reference = reference

    def png_frame(self, index):
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
        rgba = cv2.warpAffine(self.png, matrix, (W, H), flags=cv2.INTER_LANCZOS4,
                              borderValue=tuple(int(v) for v in (*IVORY, 0)))
        rgb = rgba[..., :3].astype(np.float32)
        alpha = np.clip(rgba[..., 3:4].astype(np.float32)/255, 0, 1)
        strength = float(ease((t-.66)/.34))
        if strength > 0:
            # Parameter matching on one PNG, not an image-opacity handoff.
            rgb = cv2.GaussianBlur(rgb, (0, 0), max(.01, self.sigma*strength*scale/.26562))
            curve_delta = grade(rgb, self.coefficients)-rgb
            reference_to_canvas = (self.homogeneous(matrix) @ np.linalg.inv(self.homogeneous(self.registration)))[:2]
            field = cv2.warpAffine(self.field, reference_to_canvas, (W, H), flags=cv2.INTER_LINEAR)
            rgb += strength*(curve_delta+field)
        return IVORY*(1-alpha)+rgb*alpha

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
              for name in ['shila_original.png', 'shila_lastvideo.mp4', 'ophelia_landing_916_web.mp4']}
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
    try:
        for i in range(OPHELIA_FRAMES):
            write(ophelia(tail[min(i, len(tail)-1)]))
        for i in range(ZOOM_FRAMES):
            write(match.png_frame(i))
        for i in range(SHILA_FRAMES):
            write(match.video_frame(i))
    finally:
        encoder.stdin.close()
    assert encoder.wait() == 0
    assert count == OPHELIA_FRAMES+ZOOM_FRAMES+SHILA_FRAMES
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in hashes.items())
    metadata = {'width': W, 'height': H, 'fps': FPS, 'frames': count, 'duration': count/FPS,
        'ophelia_source_in': OPHELIA_IN, 'png_start': OPHELIA_FRAMES/FPS,
        'technical_match_start': (OPHELIA_FRAMES+.66*(ZOOM_FRAMES-1))/FPS,
        'video_handoff': HANDOFF_FRAME/FPS, 'video_source_in': 0, 'complete_shila_video': True,
        'original_files_sha256': hashes, 'handoff_metrics': metrics,
        'treatment': 'Same PNG: reference-calibrated RGB tone/color coefficients, smooth local illumination compensation, optical softness; then a direct frame-zero video switch.',
        'full_hero_rendered': False}
    args.output.with_suffix('.json').write_text(json.dumps(metadata, indent=2)+'\n')
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', '4.7', '-i', str(args.output), '-frames:v', '1',
                    '-q:v', '2', '-y', str(args.output.with_name('poster.jpg'))], check=True)
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == '__main__':
    main()
