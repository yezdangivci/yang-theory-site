#!/usr/bin/env python3
"""Only Zaru 5 → Journey: emerald concentration, tiny lilac orb, plant contact.

The latest direction explicitly allows a tiny travelling orb, not a beam.
Its core size and fringe color are measured from the real Journey frame.
No trail, smoke, portal, inset, asset deformation or added Zaru camera move.
"""
import argparse
import hashlib
import itertools
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
DISPLAY_SCALE = 1.35  # Constant for every Zaru frame; no added animated zoom.
GREEN_START_FRAME = 390  # 13.00s, the real green material is already moving.
MATCH_EXIT_FRAMES = 45  # 1.50s native-light / native-detail resolution.
PLANT_POINT = np.array([912., 641.], np.float32)  # Native point + 1px source pad.
ORB_FORM_FRAMES = 13
ORB_TRAVEL_FRAMES = 16
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
    """Locate the active bright green region from the real source pixels."""
    records = []
    for frame in decode(SOURCE):
        region = frame[475:650, 880:1050].astype(np.float32)
        r, g, b = region.transpose(2, 0, 1)
        green = (g > r*1.5) & (g > b*1.05) & (g > 60)
        weights = (g/255)**5*green
        yy, xx = np.mgrid[475:650, 880:1050]
        if weights.sum() > .01:
            origin = [float((weights*xx).sum()/weights.sum()),
                      float((weights*yy).sum()/weights.sum())]
        else:
            origin = [985., 596.]
        records.append(origin)
    return cv2.GaussianBlur(np.asarray(records,np.float32),(1,7),0)


def display_zaru(frame):
    """One uniform display transform; only unused black margins leave the canvas."""
    sw, sh = round(W*DISPLAY_SCALE), round(H*DISPLAY_SCALE)
    larger = cv2.resize(frame, (sw,sh), interpolation=cv2.INTER_LANCZOS4)
    x, y = (sw-W)//2, (sh-H)//2
    return larger[y:y+H,x:x+W]


class EmeraldPlantMatch:
    def __init__(self, measured, journey_start, plant_reference):
        self.journey_start = journey_start
        self.anchor = (measured[-8:].mean(axis=0)-[W/2,H/2])*DISPLAY_SCALE+[W/2,H/2]
        self.y,self.x = np.mgrid[:H,:W].astype(np.float32)
        r,g,b = plant_reference.astype(np.float32).transpose(2,0,1)
        yellow = ((r>170)&(g>140)&(b<g*.8)&(r>g*.95)).astype(np.uint8)
        _,_,stats,centers = cv2.connectedComponentsWithStats(yellow,8)
        cores = [s for s,p in zip(stats[1:],centers[1:])
                 if 4<s[4]<250 and 400<p[0]<1100]
        self.core_diameter = float(np.median([np.sqrt(s[2]*s[3]) for s in cores]))
        distance = np.hypot(self.x-PLANT_POINT[0],self.y-PLANT_POINT[1])
        fringe = (distance>2)&(distance<6)&(b>r*1.08)&(b>g*1.08)
        sample = np.median(plant_reference[fringe],axis=0).astype(np.float32)
        self.lilac = sample/sample.max()
        self.travel_start = journey_start-ORB_TRAVEL_FRAMES

    def orb(self,point,amount=1.,color=None):
        """A firefly-size point only: no line, trail, streak or large flare."""
        field = np.zeros((H,W,3),np.float32)
        # Limit the entire optical footprint to 36×36 pixels (0.063% canvas).
        x0,y0 = np.floor(point-18).astype(int)
        x1,y1 = x0+36,y0+36
        distance2 = (self.x[y0:y1,x0:x1]-point[0])**2+(self.y[y0:y1,x0:x1]-point[1])**2
        sigma = self.core_diameter/2.355
        core = np.exp(-distance2/(2*sigma*sigma))
        halo = np.exp(-distance2/(2*5.5**2))*.09
        fringe = self.lilac if color is None else np.asarray(color)
        center = fringe*.24+np.array([.77,.79,.84],np.float32)
        field[y0:y1,x0:x1] = (core[...,None]*center*.88+halo[...,None]*fringe)*amount
        return np.clip(field,0,1)

    def zaru_frame(self,index,source):
        if index < GREEN_START_FRAME:
            return source
        formed = float(smooth((index-GREEN_START_FRAME)/ORB_FORM_FRAMES))
        color_mix = float(smooth((index-GREEN_START_FRAME-3)/9))
        # Green only during concentration inside the stone; blue/lilac before
        # release, sampled from the native plant fringe, not a green projectile.
        color = np.array([.12,.92,.42])*(1-color_mix)+self.lilac*color_mix
        travel = float(smooth((index-self.travel_start)/(ORB_TRAVEL_FRAMES-1)))
        point = self.anchor*(1-travel)+PLANT_POINT*travel
        point[1] -= 3*np.sin(travel*np.pi)  # A tiny elegant arc, never a tail.
        rgb = source.astype(np.float32)/255
        # Concentrate within the stone, leaving the pendant's geometry intact.
        local = np.exp(-((self.x-self.anchor[0])**2+(self.y-self.anchor[1])**2)/(2*12**2))
        rgb = 1-(1-rgb)*(1-local[...,None]*color*formed*.055)
        # The original object is photographed normally, then leaves through a
        # brief focus/exposure falloff while the tiny orb travels. No deformation
        # and no incoming image inside or behind the pendant.
        if travel > 0:
            focused = cv2.GaussianBlur(rgb,(0,0),.1+travel*2.5)
            rgb = focused*(1-travel)
        light = self.orb(point,formed,color)
        return np.clip((1-(1-rgb)*(1-light))*255,0,255)

    def journey_frame(self,j,source):
        if j >= MATCH_EXIT_FRAMES:
            return source
        p = float(np.clip(j/MATCH_EXIT_FRAMES,0,1))
        rgb = source.astype(np.float32)/255
        luminance = rgb[...,0]*.2126+rgb[...,1]*.7152+rgb[...,2]*.0722
        proximity = np.exp(-.5*((self.x-PLANT_POINT[0])/145)**2
                           -.5*((self.y-PLANT_POINT[1])/145)**2)
        # Actual luminous stems/leaves resolve before their midtone environment.
        # This is a native-image luminance key, not an expanding geometric wipe.
        score = np.clip(luminance*.72+proximity*.28,0,1)
        # A continuous, luminance-dependent exposure curve retains photographic
        # midtones instead of clipping the scene into isolated bright outlines.
        opening = float(np.sin(p*np.pi/2)**.65)
        visibility = opening**(1.80-score*.90)
        clarity = visibility**1.4
        low = cv2.GaussianBlur(rgb,(0,0),7*(1-p)+.10)
        resolved = (low*(1-clarity[...,None])+rgb*clarity[...,None])*visibility[...,None]
        # Arrival is the first possible incoming frame. The same tiny point
        # becomes the real plant light as its surrounding native texture opens.
        # Contact has no flash, bloom expansion or second travelling effect.
        carry = self.orb(PLANT_POINT,1-smooth(p/.50))
        return np.clip((1-(1-resolved)*(1-carry))*255,0,255)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qa', type=Path, default=Path('/tmp/yang-zaru5-journey/qa'))
    args = parser.parse_args()
    args.qa.mkdir(parents=True, exist_ok=True)
    verify_lock()
    hashes = {p.name: sha(p) for p in [SOURCE, JOURNEY]}
    measured = analyse_emerald()
    native_frames = len(measured)
    journey_start = native_frames  # Journey begins once, only after orb arrival.
    journey = decode(JOURNEY, pad=True)
    first_journey = next(journey)
    bridge = EmeraldPlantMatch(measured, journey_start, first_journey)
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
    try:
        for i, source in enumerate(decode(SOURCE)):
            source = display_zaru(source)
            frame = bridge.zaru_frame(i, source)
            if i in [0, 240, GREEN_START_FRAME, 410, 413, 416, 419, 421, 422]:
                Image.fromarray(np.clip(frame, 0, 255).astype('uint8')).save(args.qa/f'{i:04d}.png')
            write(frame)
        assert count == native_frames
        for j, source in enumerate(itertools.chain([first_journey],journey)):
            i = journey_start+j
            frame = bridge.journey_frame(j, source)
            if j in [0, 1, 3, 8, 12, 19, 25, 34, 44, 45, 100]:
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
        'zaru_presentation': 'Whole-source constant 1.35 display size, centered, original motion and black negative space preserved.',
        'additional_zaru_scale': DISPLAY_SCALE, 'zaru_scale_animated': False,
        'black_margin_trim_only': True, 'object_crop': False,
        'additional_zaru_camera_motion': False, 'source_pixel_displacement': False,
        'green_motion_start': GREEN_START_FRAME/FPS, 'journey_start': journey_start/FPS,
        'match_clear': (journey_start+MATCH_EXIT_FRAMES)/FPS,
        'source_clock_overlap_frames': 0,
        'journey_source_in': 0, 'journey_frames': journey_frames,
        'journey_padding': [1, 0, 1, 0], 'journey_clock': 'Single forward pass, no restart or duplicate sequence.',
        'bridge': 'Emerald energy concentrates → tiny blue/lilac orb → short clean travel → plant contact → native luminance/detail resolution of Journey.',
        'match_anchor': bridge.anchor.tolist(), 'native_plant_point': PLANT_POINT.tolist(),
        'orb_formation_start': GREEN_START_FRAME/FPS,
        'orb_formation_end': (GREEN_START_FRAME+ORB_FORM_FRAMES)/FPS,
        'orb_travel_start': bridge.travel_start/FPS,
        'orb_arrival': (journey_start-1)/FPS,
        'orb_core_diameter': bridge.core_diameter,
        'orb_lilac_fringe_rgb': (bridge.lilac*255).round(3).tolist(),
        'orb_travel_distance_pixels': float(np.linalg.norm(bridge.anchor-PLANT_POINT)),
        'orb_tail': False, 'orb_flash': False,
        'journey_initial_offset': [0,0], 'journey_additional_scale': 1,
        'journey_recenter_frames': 0,
        'source_sha256': hashes, 'portal': False, 'miniature_journey': False,
        'beam': False, 'streak': False, 'travelling_light': 'Tiny blue/lilac orb only, explicitly requested.', 'flat_color_wash': False,
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
