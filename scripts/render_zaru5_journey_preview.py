#!/usr/bin/env python3
"""Render only Zaru 5 → emerald light → full Journey.

Zaru starts at 00:00 with a constant 1.20 display scale. No animated camera
transform is added. Native emerald movement drives a short light trace into
the plant position; a brief lens bloom conceals the edit. Journey is always
full-frame, never inset into the pendant, and advances once from 00:00.
Neither source object is warped; the original source files remain unchanged.
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
SOURCE = ROOT/'zaru5.mp4'
JOURNEY = ROOT/'Journey:Yez Startle video.mp4'
OUT = ROOT/'public/previews/zaru5-journey'
DISPLAY_SCALE = 1.20  # Constant for every Zaru frame; not an animated zoom.
GREEN_START_FRAME = 372  # 12.40s; native emerald action motivates the light.
LIGHT_EXIT_FRAMES = 19  # A short optical recovery, not a smoke interlude.
cv2.setNumThreads(2)


def smooth(t):
    t = np.clip(t, 0, 1)
    return t*t*(3-2*t)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock():
    lock = json.loads((ROOT/'hero-edit-lock.json').read_text())
    for name, expected in lock['ophelia_to_shila']['sha256'].items():
        assert sha(ROOT/name) == expected, f'Locked Ophelia/Shila file changed: {name}'


def decode(path, pad=False):
    # fps resamples time only. Both videos retain their original pixel geometry.
    filters = f'fps={FPS}' + (',pad=1920:1080:1:0:black' if pad else '')
    process = subprocess.Popen(['ffmpeg', '-v', 'error', '-threads', '2', '-i', str(path),
        '-an', '-vf', filters, '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'],
        stdout=subprocess.PIPE)
    try:
        while True:
            data = process.stdout.read(W*H*3)
            if len(data) != W*H*3:
                break
            yield np.frombuffer(data, np.uint8).reshape(H, W, 3).copy()
        assert process.wait() == 0
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait()


def analyse_emerald():
    """Read native green pixels for motion/color measurements, not display crops."""
    previous = None
    records = []
    for frame in decode(SOURCE):
        region = frame[455:680, 850:1090]
        r, g, b = region.astype(np.float32).transpose(2, 0, 1)
        green = (g > r*1.3) & (g > b*1.05) & (g > 38)
        grey = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        flow_x, flow_y, energy, curl = 0., 0., 0., 0.
        color, origin = np.array([8., 82., 43.]), np.array([966., 577.])
        if green.sum() > 60:
            yy, xx = np.where(green)
            weights = g[green]
            origin = np.array([850+np.average(xx, weights=weights),
                               455+np.average(yy, weights=weights)])
            color = np.median(region[green].astype(np.float32), axis=0)
            if previous is not None:
                flow = cv2.calcOpticalFlowFarneback(previous, grey, None, .5, 3, 19, 3, 5, 1.2, 0)
                flow_x, flow_y = np.mean(flow[green], axis=0)
                energy = np.mean(np.linalg.norm(flow[green], axis=1))
                curl_map = np.gradient(flow[..., 1], axis=1)-np.gradient(flow[..., 0], axis=0)
                curl = np.mean(curl_map[green])
        records.append([*origin, *color, flow_x, flow_y, energy, curl])
        previous = grey
    records = np.asarray(records, np.float32)
    # Optical analysis is temporally smoothed; no source image is altered.
    records = cv2.GaussianBlur(records, (1, 9), 0)
    return records


def display_zaru(frame):
    """Enlarge the complete source uniformly; only outer black margins exit canvas."""
    larger = cv2.resize(frame, (2304, 1296), interpolation=cv2.INTER_LANCZOS4)
    return larger[108:1188, 192:2112]


class EmeraldLight:
    def __init__(self, measured, journey_start):
        self.measured = measured
        self.journey_start = journey_start
        self.size = (W//2, H//2)
        self.y, self.x = np.mgrid[:self.size[1], :self.size[0]].astype(np.float32)
        self.target = np.array([650., 625.], np.float32)
        self.last_origin = (measured[-1, :2]-[W/2, H/2])*DISPLAY_SCALE+[W/2, H/2]
        self.last_color = measured[-1, 2:5]

    def light(self, index):
        time = index/FPS
        native_index = min(index, len(self.measured)-1)
        sample = self.measured[native_index]
        origin = (sample[:2]-[W/2, H/2])*DISPLAY_SCALE+[W/2, H/2]
        incoming = index >= self.journey_start
        if incoming:
            origin = self.last_origin
        progress = float(smooth((time-13.0)/1.10))
        # A single soft arc travels from real resin to the plant's luminous point.
        # The objects and footage are never remapped by the effect.
        a = origin/2
        d = self.target/2
        b = a+[-45., -34.]+sample[5:7]*14
        c = d+[45., -23.]
        tail = float(smooth((index-self.journey_start)/9)) if incoming else 0.
        segments = np.linspace(tail, progress, max(2, int((progress-tail)*80)), dtype=np.float32)
        points = np.array([(1-u)**3*a+3*(1-u)**2*u*b+3*(1-u)*u*u*c+u**3*d for u in segments])
        head = points[-1]
        activity = float(np.clip(sample[7]*1.5, 0, .20))
        attack = float(smooth((time-GREEN_START_FRAME/FPS)/.60))
        release = float(1-smooth((index-self.journey_start)/LIGHT_EXIT_FRAMES)) if incoming else 1.
        trace = np.zeros((self.size[1], self.size[0], 3), np.float32)
        native_color = self.last_color if incoming else sample[2:5]
        green = native_color/np.maximum(1, native_color.max())*.74
        violet = np.array([.48, .48, .92], np.float32)
        for n in range(1, len(points)):
            u = float(segments[n])
            hue = green*(1-u)+violet*u
            # Native velocities modulate a light reflection, not an object shape.
            strength = (.35+.35*u+activity)*attack*release
            cv2.line(trace, tuple(np.rint(points[n-1]).astype(int)),
                     tuple(np.rint(points[n]).astype(int)), tuple((hue*strength).tolist()),
                     2, cv2.LINE_AA)
        trace = cv2.GaussianBlur(trace, (0, 0), .85)
        soft = cv2.GaussianBlur(trace, (0, 0), 7)
        wide = cv2.GaussianBlur(trace, (0, 0), 25)
        trace = np.clip(trace*.25+soft*6+wide*11, 0, .80)
        # Local green activity preserves the real emerald's moving texture.
        # It follows the measured centroid, without creating an inset picture.
        stone = np.exp(-.5*((self.x-a[0])/30)**2-.5*((self.y-a[1])/29)**2)
        stone_light = stone[..., None]*green*(.12+activity)*attack*release
        if incoming:
            stone_light *= 0
        # Only a short optical event covers the edit. Two adjacent frames share
        # an exact peak; no source images are crossfaded and no fog is generated.
        seam = (self.journey_start-.5)/FPS
        distance = max(0., abs(time-seam)-.5/FPS)
        pulse = float(np.exp(-(distance/.155)**2))
        radius = 23+1080*pulse**2.2
        gaussian = np.exp(-.5*((self.x-head[0])/radius)**2-.5*((self.y-head[1])/radius)**2)
        bloom = 1-np.exp(-gaussian*(.28*attack*release+88*pulse**4))
        # Warm-green activity passes through a pale optical peak into the
        # plant's existing blue/violet emission. This colors light only.
        incoming_hue = float(smooth((index-self.journey_start)/LIGHT_EXIT_FRAMES)) if incoming else 0.
        local_hue = green*(1-incoming_hue)+violet*incoming_hue
        peak_hue = np.array([.88, .96, .94], np.float32)
        hue = local_hue*(1-pulse**1.1)+peak_hue*pulse**1.1
        bloom_light = bloom[..., None]*hue
        light = 1-(1-trace)*(1-stone_light)*(1-bloom_light)
        return cv2.resize(np.clip(light, 0, 1), (W, H), interpolation=cv2.INTER_LINEAR), pulse

    def frame(self, index, source, incoming=False):
        if index <= GREEN_START_FRAME or (incoming and index >= self.journey_start+LIGHT_EXIT_FRAMES):
            return source
        light, pulse = self.light(index)
        # Additive lens light in linear RGB, never an outgoing/incoming dissolve.
        srgb = source.astype(np.float32)/255
        linear = np.where(srgb<=.04045, srgb/12.92, ((srgb+.055)/1.055)**2.4)
        energy = np.where(light<=.04045, light/12.92, ((light+.055)/1.055)**2.4)
        result = 1-(1-linear)*(1-energy)
        result = np.where(result<=.0031308, result*12.92, 1.055*np.maximum(result,0)**(1/2.4)-.055)
        # Sensor veiling at the optical peak conceals both shots for two frames.
        # The shared light image makes the edit continuous rather than a snap.
        veiling = float(smooth((pulse-.80)/.20))
        result = result*(1-veiling)+np.array([.88,.96,.94],np.float32)*veiling
        return np.clip(result*255,0,255)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qa', type=Path, default=Path('/tmp/yang-zaru5-journey/qa'))
    args = parser.parse_args()
    args.qa.mkdir(parents=True, exist_ok=True)
    verify_lock()
    hashes = {p.name: sha(p) for p in [SOURCE, JOURNEY]}
    measured = analyse_emerald()
    native_frames = len(measured)
    journey_start = native_frames  # Journey begins once; the lens light bridges this seam.
    bridge = EmeraldLight(measured, journey_start)
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT/'preview.mp4'
    encoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-f', 'rawvideo',
        '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', 'pipe:0', '-an',
        '-vf', 'scale=w=iw:h=ih:out_color_matrix=bt709:out_range=tv,format=yuv420p',
        '-c:v', 'libx264', '-threads', '3', '-preset', 'medium', '-crf', '17',
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
        '-g', '30', '-movflags', '+faststart', '-y', str(output)], stdin=subprocess.PIPE)
    count, journey_frames = 0, 0
    def write(frame):
        nonlocal count
        encoder.stdin.write(np.clip(frame, 0, 255).astype('uint8').tobytes())
        count += 1
        if count%90 == 0:
            print(f'Rendered Zaru 5 / Journey preview {count/FPS:.1f}s', flush=True)
    journey = decode(JOURNEY, pad=True)
    try:
        for i, source in enumerate(decode(SOURCE)):
            source = display_zaru(source)
            frame = bridge.frame(i, source)
            if i in [0, 240, GREEN_START_FRAME, 390, 402, 411, 416, 419, 421, 422]:
                Image.fromarray(np.clip(frame, 0, 255).astype('uint8')).save(args.qa/f'{i:04d}.png')
            write(frame)
        assert count == native_frames
        for j, source in enumerate(journey):
            i = journey_start+j
            frame = bridge.frame(i, source, incoming=True)
            if j in [0, 1, 3, 5, 8, 12, 19, 40, 100]:
                Image.fromarray(np.clip(frame, 0, 255).astype('uint8')).save(args.qa/f'{i:04d}.png')
            write(frame)
            journey_frames += 1
    finally:
        encoder.stdin.close()
    assert encoder.wait() == 0
    verify_lock()
    assert hashes == {p.name: sha(p) for p in [SOURCE, JOURNEY]}
    meta = {'width': W, 'height': H, 'fps': FPS, 'frames': count, 'duration': count/FPS,
        'zaru_source': SOURCE.name, 'zaru_source_in': 0, 'zaru_frames': native_frames,
        'zaru_presentation': 'Whole-source 1.20 constant display enlargement, centered; substantial authored black remains. No additional animated zoom.',
        'additional_zaru_scale': DISPLAY_SCALE, 'zaru_scale_animated': False,
        'black_margin_trim_only': True, 'object_crop': False,
        'additional_zaru_camera_motion': False, 'source_pixel_displacement': False,
        'green_motion_start': GREEN_START_FRAME/FPS, 'journey_start': journey_start/FPS,
        'light_clear': (journey_start+LIGHT_EXIT_FRAMES)/FPS,
        'source_clock_overlap_frames': 0,
        'journey_source_in': 0, 'journey_frames': journey_frames,
        'journey_padding': [1, 0, 1, 0], 'journey_clock': 'Single forward pass, no restart or duplicate sequence.',
        'bridge': 'Native emerald activity → restrained light trace to the plant → brief optical lens bloom → full Journey. No fog or smoke.',
        'plant_light_target': bridge.target.tolist(), 'optical_peak_frames': [journey_start-1,journey_start],
        'motion_measurements': {'mean_speed_px': float(measured[GREEN_START_FRAME:, 7].mean()),
                                'origin_at_transition': measured[GREEN_START_FRAME, :2].tolist()},
        'source_sha256': hashes, 'portal': False, 'local_light_trace': True, 'miniature_journey': False,
        'smoke': False, 'fog': False,
        'object_morphing': False, 'shot_crossfade': False,
        'locked_ophelia_shila_unchanged': True, 'other_transitions_changed': False,
        'full_hero_rendered': False}
    (OUT/'preview.json').write_text(json.dumps(meta, indent=2)+'\n')
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', '8', '-i', str(output), '-frames:v',
                    '1', '-q:v', '2', '-y', str(OUT/'poster.jpg')], check=True)
    print(json.dumps(meta, indent=2), flush=True)


if __name__ == '__main__':
    main()
