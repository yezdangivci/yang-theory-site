#!/usr/bin/env python3
"""Zaru 5, authored full frame → native-green movement → full Journey.

This renders this junction only. Zaru pixels are never scaled, cropped,
repositioned, displaced or replaced by forest pixels. The emerald's measured
motion drives a separate atmospheric field. That field conceals the scene
handoff; Journey then plays once, at full-frame native size, through its dispersal.
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
GREEN_START_FRAME = 363  # 12.10s; source framing/motion remains untouched.
FIELD_EXIT_FRAMES = 42  # 1.4s of continuing Journey motion through dispersal.
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


class EmeraldMovement:
    def __init__(self, measured, journey_start):
        self.measured = measured
        self.journey_start = journey_start
        self.size = (W//4, H//4)
        self.y, self.x = np.mgrid[:self.size[1], :self.size[0]].astype(np.float32)
        self.clarity = np.zeros((H, W, 1), np.float32)
        rng = np.random.default_rng(5005)
        self.textures = []
        for size in [9, 21, 43]:
            texture = cv2.resize(rng.random((size, size*2), dtype=np.float32),
                                (self.size[0]*2, self.size[1]*2), interpolation=cv2.INTER_CUBIC)
            self.textures.append(cv2.GaussianBlur(texture, (0, 0), 1.5))
        self.curls = [(i*2.399963, rng.uniform(.25, 1), rng.uniform(.62, 1.15),
                       rng.uniform(.7, 1.1)) for i in range(23)]
        motion = measured[:, 5:7]
        # Carry the small native material velocities into the larger volume;
        # this gain applies to atmosphere only, never the pendant or camera.
        self.drift = np.cumsum(motion*12, axis=0)
        self.turn = np.cumsum(measured[:, 8]*18)
        self.energy = np.cumsum(measured[:, 7]*.12)

    def field(self, frame_index):
        emission_length = self.journey_start-GREEN_START_FRAME
        t = (frame_index-GREEN_START_FRAME)/emission_length
        phase = max(0, frame_index-GREEN_START_FRAME)/FPS
        native_index = min(frame_index, len(self.measured)-1)
        sample = self.measured[native_index]
        ox, oy = sample[:2]/4
        dx, dy = self.drift[native_index]-self.drift[GREEN_START_FRAME]
        turn = float(self.turn[native_index]-self.turn[GREEN_START_FRAME])
        energy = float(self.energy[native_index]-self.energy[GREEN_START_FRAME])
        # Source-derived movement advects the atmosphere only. It never remaps
        # either media frame and never draws a Journey image inside the stone.
        nx = self.x+phase*12+dx+9*np.sin(self.y/40+phase*.7+turn)
        ny = self.y+phase*21+dy+7*np.sin(self.x/55-phase*.8)
        texture = np.zeros_like(self.x)
        for i, values in enumerate(self.textures):
            texture += cv2.remap(values, nx*(1+i*.03), ny*(1+i*.03),
                                cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)/(2**i)
        texture /= 1.75
        growth = float(smooth((t-.05)/.76))
        radius = 15+390*growth**1.5
        qx = self.x+18*(texture-.5)*growth+8*np.sin(self.y/34+phase+turn)*growth
        qy = self.y+8*np.sin(self.x/37-phase*.8)*growth
        density = np.zeros_like(self.x)
        for theta, travel, size, strength in self.curls:
            angle = theta+turn+phase*.11
            cx = ox+np.cos(angle)*radius*travel*.43+dx*.12
            cy = oy+np.sin(angle)*radius*travel*.40-phase*12+dy*.12
            sx = max(3, radius*size*.46)
            sy = sx*(.76+.12*np.sin(theta+phase*.6))
            density += np.exp(-.5*((qx-cx)/sx)**2-.5*((qy-cy)/sy)**2)*strength
        density *= (.3+texture*1.2)*float(smooth(t/.15))*(.8+min(.2, energy*.012))
        opacity = 1-np.exp(-density*.85)
        # Cover the whole outgoing shot before the environment clock begins.
        # This is moving green volume, with no flare, beam or portal aperture.
        coverage = float(smooth((t-.87)/.10))
        opacity += coverage*(1-opacity)
        if frame_index >= self.journey_start:
            u = (frame_index-self.journey_start)/FIELD_EXIT_FRAMES
            # Curls thin at different rates; the left forest structure becomes
            # readable first while the environment plays forward continuously.
            local = .74+texture*.38 + .12*np.sin(self.x/80+self.y/93+phase*.4)
            erosion = smooth((u-.035*texture)/np.maximum(.3, local))
            opacity *= 1-erosion
            opacity *= float(1-smooth((u-.76)/.24))
        shade = np.clip((texture-.23)*1.75, 0, 1)
        native_color = np.clip(sample[2:5], 0, 255)
        color = native_color[None, None, :]*(.38+.88*shade[..., None])
        opacity = cv2.GaussianBlur(opacity, (0, 0), 2.8)
        opacity = cv2.resize(opacity, (W, H), interpolation=cv2.INTER_CUBIC)
        color = cv2.resize(color, (W, H), interpolation=cv2.INTER_CUBIC)
        return np.clip(opacity, 0, 1)[..., None], color

    def frame(self, index, source, incoming=False):
        if index <= GREEN_START_FRAME:
            return source
        if incoming and index >= self.journey_start+FIELD_EXIT_FRAMES:
            return source
        opacity, atmosphere = self.field(index)
        source = source.astype(np.float32)
        if not incoming:
            return source*(1-opacity)+atmosphere*opacity
        visibility = smooth(1-opacity)
        self.clarity += (visibility-self.clarity)*.18
        u = (index-self.journey_start)/FIELD_EXIT_FRAMES
        recovery = float(smooth((u-.75)/.25))
        clarity = self.clarity+(1-self.clarity)*recovery
        low = cv2.resize(source, (W//8, H//8), interpolation=cv2.INTER_AREA)
        low = cv2.GaussianBlur(low, (0, 0), 6)
        low = cv2.resize(low, (W, H), interpolation=cv2.INTER_LINEAR)
        detail = visibility*clarity
        forming_environment = low*(1-detail)+source*detail
        material = atmosphere*(1-visibility*.45)+low*(visibility*.45)
        return material*(1-visibility)+forming_environment*visibility


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qa', type=Path, default=Path('/tmp/yang-zaru5-journey/qa'))
    args = parser.parse_args()
    args.qa.mkdir(parents=True, exist_ok=True)
    verify_lock()
    hashes = {p.name: sha(p) for p in [SOURCE, JOURNEY]}
    measured = analyse_emerald()
    native_frames = len(measured)
    journey_start = native_frames-12  # Begin moving forest while green is active.
    bridge = EmeraldMovement(measured, journey_start)
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
            incoming = i >= journey_start
            if incoming:
                source = next(journey)
                journey_frames += 1
            frame = bridge.frame(i, source, incoming=incoming)
            if i in [0, 240, GREEN_START_FRAME, native_frames-12, native_frames-1]:
                Image.fromarray(np.clip(frame, 0, 255).astype('uint8')).save(args.qa/f'{i:04d}.png')
            write(frame)
        assert count == native_frames
        for source in journey:
            j = journey_frames
            i = journey_start+j
            frame = bridge.frame(i, source, incoming=True)
            if j in [0, 8, 16, 25, 34, 42, 100]:
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
        'zaru_presentation': 'Authored full 1920x1080 frame; identity placement and scale.',
        'additional_zaru_scale': 1, 'additional_zaru_crop': False,
        'additional_zaru_camera_motion': False, 'source_pixel_displacement': False,
        'green_motion_start': GREEN_START_FRAME/FPS, 'journey_start': journey_start/FPS,
        'field_clear': (journey_start+FIELD_EXIT_FRAMES)/FPS,
        'source_clock_overlap_frames': 12,
        'journey_source_in': 0, 'journey_frames': journey_frames,
        'journey_padding': [1, 0, 1, 0], 'journey_clock': 'Single forward pass, no restart or duplicate sequence.',
        'bridge': 'Measured native emerald movement carries a green volume through the black negative space; the full moving Journey environment resolves through its dispersal.',
        'motion_measurements': {'mean_speed_px': float(measured[GREEN_START_FRAME:, 7].mean()),
                                'origin_at_transition': measured[GREEN_START_FRAME, :2].tolist()},
        'source_sha256': hashes, 'portal': False, 'beam': False, 'miniature_journey': False,
        'object_morphing': False, 'shot_crossfade': False,
        'locked_ophelia_shila_unchanged': True, 'other_transitions_changed': False,
        'full_hero_rendered': False}
    (OUT/'preview.json').write_text(json.dumps(meta, indent=2)+'\n')
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', '8', '-i', str(output), '-frames:v',
                    '1', '-q:v', '2', '-y', str(OUT/'poster.jpg')], check=True)
    print(json.dumps(meta, indent=2), flush=True)


if __name__ == '__main__':
    main()
