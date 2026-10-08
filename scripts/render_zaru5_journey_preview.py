#!/usr/bin/env python3
"""Render only the screen-space emerald / Journey plant-light match.

Zaru 5 starts at 00:00, at a constant 1.35 display size. The native green
light supplies a local optical match; the actual plant tip occupies the same
screen position. Journey resolves through native luminance and local detail,
then returns gently to its original framing. No travelling effect, emitted
ray, fog, wash, inset scene, portal or object deformation is generated.
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
DISPLAY_SCALE = 1.35  # Constant for every Zaru frame; no added animated zoom.
GREEN_START_FRAME = 390  # 13.00s, the real green material is already moving.
MATCH_EXIT_FRAMES = 45  # 1.50s native-light / native-detail resolution.
PLANT_POINT = np.array([911., 641.], np.float32)
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
    def __init__(self, measured, journey_start):
        self.journey_start = journey_start
        self.anchor = (measured[-8:].mean(axis=0)-[W/2,H/2])*DISPLAY_SCALE+[W/2,H/2]
        self.offset = self.anchor-PLANT_POINT
        self.y,self.x = np.mgrid[:H,:W].astype(np.float32)
        self.last_emission = None

    def emission(self, source):
        """Diffuse actual emerald light only; no synthetic field or object warp."""
        rgb = source.astype(np.float32)/255
        r,g,b = rgb.transpose(2,0,1)
        # The source is the only green material in this black composition.
        select = smooth((g-r*1.35)/.13)*smooth((g-b*1.02)/.09)
        select *= np.exp(-.5*((self.x-self.anchor[0])/35)**2
                         -.5*((self.y-self.anchor[1])/35)**2)
        actual = rgb*select[...,None]
        # Sampling light rather than cutting out a diamond avoids an object
        # silhouette in the optical handoff. Its RGB and texture are source data.
        near = cv2.GaussianBlur(actual,(0,0),14)
        halo = cv2.GaussianBlur(actual,(0,0),34)
        return np.clip(near*1.50+halo*.60,0,1)

    def zaru_frame(self,index,source):
        if index < GREEN_START_FRAME:
            return source
        native_light = self.emission(source)
        self.last_emission = native_light
        # A short local focus/exposure pass leaves a co-located light image.
        # No Journey pixel is displayed while the pendant form is visible.
        u = float(smooth((index-(self.journey_start-13))/12))
        if u <= 0:
            return source
        sigma = 1+u*6
        softly_focused = cv2.GaussianBlur(source.astype(np.float32)/255,(0,0),sigma)
        detail = softly_focused*(1-u)
        optical_light = native_light*u
        return np.clip((1-(1-detail)*(1-optical_light))*255,0,255)

    def reframe_journey(self,source,j):
        p = j/MATCH_EXIT_FRAMES
        # Hold the aligned point while it registers, then return by less than
        # 5% of the canvas width. The source is never enlarged or distorted.
        remaining = float(1-smooth((p-.28)/.72))
        offset = self.offset*remaining
        matrix = np.array([[1,0,offset[0]],[0,1,offset[1]]],np.float32)
        # Replicate the two missing source columns before the tiny framing move,
        # so padding cannot produce an internal one-pixel rectangular boundary.
        source = source.copy()
        source[:,0] = source[:,1]
        source[:,-1] = source[:,-2]
        shifted = cv2.warpAffine(source,matrix,(W,H),flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REFLECT_101)
        # Keep the exposed peripheral margin atmospheric, without recognizable
        # reflected leaves, black bars, a rectangle edge or enlarged footage.
        left = smooth((max(0.,offset[0])+24-self.x)/48)
        bottom = smooth((self.y-(H-max(0.,-offset[1])-24))/48)
        margin = np.maximum(left,bottom)*remaining
        ambient = cv2.GaussianBlur(shifted,(0,0),26)
        shifted = shifted*(1-margin[...,None])+ambient*margin[...,None]
        return shifted,offset

    def journey_frame(self,j,source):
        if j >= MATCH_EXIT_FRAMES:
            return source
        reframed,offset = self.reframe_journey(source,j)
        p = float(np.clip(j/MATCH_EXIT_FRAMES,0,1))
        rgb = reframed.astype(np.float32)/255
        luminance = rgb[...,0]*.2126+rgb[...,1]*.7152+rgb[...,2]*.0722
        point = PLANT_POINT+offset
        proximity = np.exp(-.5*((self.x-point[0])/145)**2
                           -.5*((self.y-point[1])/145)**2)
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
        # The last native emerald light image bridges the exact shot boundary.
        # No complete outgoing shot, stone or miniature forest sits underneath.
        carry = self.last_emission*(1-smooth(p/.65))
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
    journey_start = native_frames  # Journey begins once at the matched-light handoff.
    bridge = EmeraldPlantMatch(measured, journey_start)
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
            frame = bridge.zaru_frame(i, source)
            if i in [0, 240, GREEN_START_FRAME, 410, 413, 416, 419, 421, 422]:
                Image.fromarray(np.clip(frame, 0, 255).astype('uint8')).save(args.qa/f'{i:04d}.png')
            write(frame)
        assert count == native_frames
        for j, source in enumerate(journey):
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
        'bridge': 'Moving emerald → coincident native plant light → luminance/detail resolution of the full Journey environment.',
        'match_anchor': bridge.anchor.tolist(), 'native_plant_point': PLANT_POINT.tolist(),
        'journey_initial_offset': bridge.offset.tolist(), 'journey_additional_scale': 1,
        'journey_recenter_frames': MATCH_EXIT_FRAMES,
        'source_sha256': hashes, 'portal': False, 'miniature_journey': False,
        'beam': False, 'streak': False, 'travelling_light': False, 'flat_color_wash': False,
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
