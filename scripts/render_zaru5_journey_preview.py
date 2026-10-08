#!/usr/bin/env python3
"""Only Zaru 5 → Journey: green release, depth passage, live plant contact.

The latest direction explicitly allows a tiny travelling orb, not a beam.
Its core size and fringe color are measured from the real Journey frame.
No trail, smoke, portal, inset or asset deformation. The only added source
camera move is the newly requested slight exit pullback, never a push-in.
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
DISPLAY_SCALE = 1.40  # Slightly larger static display, never an animated zoom.
GREEN_START_FRAME = 390  # 13.00s, the real green material is already moving.
MATCH_EXIT_FRAMES = 33  # Live Journey resolves before plant arrival.
PLANT_POINT = np.array([651., 625.], np.float32)  # Plant under the reaching hand, +1px pad.
ORB_FORM_FRAMES = 15  # 0.50s green concentration, readable before release.
OUTWARD_FRAMES = 18  # 0.60s approach, Zaru pullback/fade, then black.
BLACK_PASSAGE_FRAMES = 9  # 0.30s continuous foreground passage over black.
REENTRY_FRAMES = 42  # 1.40s curved recession into the live Journey world.
ZARU_EXIT_PULLBACK = .08  # Latest request: slight zoom OUT only.
CONTACT_FRAMES = 9
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


def analyse_plant():
    """Track the actual moving luminous plant tip; not an unrelated firefly."""
    point = PLANT_POINT.copy()
    points = []
    for source in decode(JOURNEY,pad=True):
        x,y = np.rint(point).astype(int)
        x0,y0 = x-30,y-28
        patch = source[y0:y+29,x0:x+31].astype(np.float32)
        r,g,b = patch.transpose(2,0,1)
        yy,xx = np.mgrid[y0:y+29,x0:x+31]
        luminous = (b>150)&(g>130)&(b>r*.95)&(b>g*.96)
        proximity = np.exp(-((xx-point[0])**2+(yy-point[1])**2)/(2*16**2))
        weights = ((r*.2126+g*.7152+b*.0722)/255)**8*luminous*proximity
        if weights.sum()>.01:
            point = np.array([(weights*xx).sum()/weights.sum(),
                              (weights*yy).sum()/weights.sum()],np.float32)
        points.append(point.copy())
    return cv2.GaussianBlur(np.asarray(points,np.float32),(1,7),0)


class EmeraldPlantMatch:
    def __init__(self, measured, journey_start, plant_reference, plant_points):
        self.journey_start = journey_start
        self.travel_start = GREEN_START_FRAME+ORB_FORM_FRAMES
        self.near_camera = self.travel_start+OUTWARD_FRAMES
        self.arrival = journey_start+REENTRY_FRAMES
        self.origins = (measured-[W/2,H/2])*DISPLAY_SCALE+[W/2,H/2]
        self.anchor = self.origins[self.travel_start].copy()
        self.plant_points = plant_points
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

    def orb(self,point,amount=1.,color=None,scale=1.):
        """A firefly-size point only: no line, trail, streak or large flare."""
        field = np.zeros((H,W,3),np.float32)
        # Small colored core; modest growth at the lens, no streak or trail.
        radius = int(np.ceil(18*scale))
        x0,y0 = np.floor(point-radius).astype(int)
        x1,y1 = x0+radius*2,y0+radius*2
        distance2 = (self.x[y0:y1,x0:x1]-point[0])**2+(self.y[y0:y1,x0:x1]-point[1])**2
        sigma = self.core_diameter/2.355*scale
        core = np.exp(-distance2/(2*sigma*sigma))
        halo = np.exp(-distance2/(2*(5.5*scale)**2))*.09
        fringe = self.lilac if color is None else np.asarray(color)
        # Colored core, not the old white dot with only a colored fringe.
        center = fringe*.80+np.array([.10,.10,.10],np.float32)
        field[y0:y1,x0:x1] = (core[...,None]*center+halo[...,None]*fringe)*amount
        return np.clip(field,0,1)

    def zaru_frame(self,index,source):
        if source is None:
            return np.zeros((H,W,3),np.float32)
        rgb = source.astype(np.float32)/255
        if index < GREEN_START_FRAME:
            return rgb
        formed = float(smooth((index-GREEN_START_FRAME)/ORB_FORM_FRAMES))
        origin = self.origins[min(index,len(self.origins)-1)]
        local = np.exp(-((self.x-origin[0])**2+(self.y-origin[1])**2)/(2*10**2))
        rgb = 1-(1-rgb)*(1-local[...,None]*np.array([.10,.95,.32])*formed*.16)
        # The newly requested exit-only pullback creates an independent depth
        # cue: photographed Zaru recedes while its emitted green light advances.
        # The source's own movement continues; no added push-in or deformation.
        exposure = float(smooth((index-self.travel_start)/(len(self.origins)-1-self.travel_start)))
        if exposure > 0:
            matrix = cv2.getRotationMatrix2D((W/2,H/2),0,1-ZARU_EXIT_PULLBACK*exposure)
            rgb = cv2.warpAffine(rgb,matrix,(W,H),flags=cv2.INTER_LANCZOS4,
                                 borderMode=cv2.BORDER_CONSTANT,borderValue=0)
            rgb = cv2.GaussianBlur(rgb,(0,0),.1+exposure*1.7)*(1-exposure)
        return rgb

    def journey_frame(self,j,source):
        if source is None:
            return np.zeros((H,W,3),np.float32)
        if j >= MATCH_EXIT_FRAMES:
            return source.astype(np.float32)/255
        p = float(np.clip(j/MATCH_EXIT_FRAMES,0,1))
        rgb = source.astype(np.float32)/255
        luminance = rgb[...,0]*.2126+rgb[...,1]*.7152+rgb[...,2]*.0722
        point = self.plant_points[j]
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
        return resolved

    @staticmethod
    def camera_point(screen,distance):
        """Unproject screen coordinates onto a positive camera-distance plane."""
        return np.array([(screen[0]-W/2)*distance,
                         (screen[1]-H/2)*distance,distance],np.float64)

    @staticmethod
    def bezier(points,t):
        return ((1-t)**3*points[0]+3*(1-t)**2*t*points[1]
                +3*(1-t)*t*t*points[2]+t**3*points[3])

    def orb_state(self,index):
        formed = float(smooth((index-GREEN_START_FRAME)/ORB_FORM_FRAMES))
        color = np.array([.10,.95,.32])
        j = int(np.clip(index-self.journey_start,0,len(self.plant_points)-1))
        target = self.plant_points[j]
        lens = np.array([self.anchor[0]+8.,self.anchor[1]-51.])
        entry = np.array([945.,552.])
        if index < self.travel_start:
            point = self.origins[min(index,len(self.origins)-1)].copy()
            size = .55+.45*formed
            brightness = .84
        else:
            # Three camera-space trajectories, not an anchor-to-plant tween.
            # First come forward on the emerald's own ray (no sideways flight).
            # Then traverse the lens plane over BLACK. Finally recede along a
            # separate 3D arc into Journey, following its actual moving plant.
            if index < self.near_camera:
                t = float(smooth((index-self.travel_start)/OUTWARD_FRAMES))
                controls = [self.camera_point(self.anchor,2.),
                    self.camera_point(self.anchor+[0,-8],1.80),
                    self.camera_point(lens+[0,10],1.18),
                    self.camera_point(lens,1.08)]
            elif index < self.journey_start:
                t = float(smooth((index-self.near_camera)/BLACK_PASSAGE_FRAMES))
                controls = [self.camera_point(lens,1.08),
                    self.camera_point(lens+[-6,-3],1.08),
                    self.camera_point(entry+[8,6],1.10),
                    self.camera_point(entry,1.16)]
            else:
                t = float(smooth((index-self.journey_start)/REENTRY_FRAMES))
                controls = [self.camera_point(entry,1.16),
                    self.camera_point([930.,460.],1.30),
                    self.camera_point(target+[-45.,-90.],1.72),
                    self.camera_point(target,2.)]
                color_mix = float(smooth((t-.06)/.58))
                color = color*(1-color_mix)+self.lilac*color_mix
            position = self.bezier(controls,t)
            point = np.array([W/2,H/2])+position[:2]/position[2]
            size = 2/position[2]
            brightness = .84+.16*smooth((size-1)/(.85))
        amount = formed*brightness*(1-float(smooth((index-self.arrival)/CONTACT_FRAMES)))
        return point,color,size,amount

    def frame(self,index,zaru,journey):
        outgoing = self.zaru_frame(index,zaru)
        incoming = self.journey_frame(index-self.journey_start,journey)
        # Outgoing and incoming scenes never overlap: a true black lens passage
        # separates them while the same continuous green orb stays foreground.
        rgb = 1-(1-outgoing)*(1-incoming)
        if GREEN_START_FRAME <= index < self.arrival+CONTACT_FRAMES:
            point,color,size,amount = self.orb_state(index)
            rgb = 1-(1-rgb)*(1-self.orb(point,amount,color,size))
        return np.clip(rgb*255,0,255)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qa', type=Path, default=Path('/tmp/yang-zaru5-journey/qa'))
    args = parser.parse_args()
    args.qa.mkdir(parents=True, exist_ok=True)
    verify_lock()
    hashes = {p.name: sha(p) for p in [SOURCE, JOURNEY]}
    measured = analyse_emerald()
    native_frames = len(measured)
    plant_points = analyse_plant()
    journey_start = GREEN_START_FRAME+ORB_FORM_FRAMES+OUTWARD_FRAMES+BLACK_PASSAGE_FRAMES
    journey = decode(JOURNEY, pad=True)
    first_journey = next(journey)
    bridge = EmeraldPlantMatch(measured, journey_start, first_journey,plant_points)
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT/'preview.mp4'
    encoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-f', 'rawvideo',
        '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', 'pipe:0', '-an',
        '-vf', 'scale=w=iw:h=ih:out_color_matrix=bt709:out_range=tv,format=yuv420p',
        '-c:v', 'libx264', '-threads', '3', '-preset', 'medium', '-crf', '17',
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
        '-g', '30', '-movflags', '+faststart', '-y', str(output)], stdin=subprocess.PIPE)
    count, journey_frames, zaru_frames = 0, 0, 0
    def write(frame):
        nonlocal count
        encoder.stdin.write(np.clip(frame, 0, 255).astype('uint8').tobytes())
        count += 1
        if count%90 == 0:
            print(f'Rendered Zaru 5 / Journey preview {count/FPS:.1f}s', flush=True)
    try:
        zaru_stream = decode(SOURCE)
        journey_stream = itertools.chain([first_journey],journey)
        for i in range(journey_start+len(plant_points)):
            zaru = journey_source = None
            if i < native_frames:
                zaru = display_zaru(next(zaru_stream))
                zaru_frames += 1
            if i >= journey_start:
                journey_source = next(journey_stream)
                journey_frames += 1
            frame = bridge.frame(i,zaru,journey_source)
            if i in [0,240,390,402,405,410,416,421,422,423,427,431,432,438,447,456,465,473,474,479,483,532,581]:
                Image.fromarray(np.clip(frame, 0, 255).astype('uint8')).save(args.qa/f'{i:04d}.png')
            write(frame)
        assert zaru_frames == native_frames
        assert next(zaru_stream,None) is None
        assert next(journey_stream,None) is None
    finally:
        encoder.stdin.close()
    assert encoder.wait() == 0
    verify_lock()
    assert hashes == {p.name: sha(p) for p in [SOURCE, JOURNEY]}
    meta = {'width': W, 'height': H, 'fps': FPS, 'frames': count, 'duration': count/FPS,
        'zaru_source': SOURCE.name, 'zaru_source_in': 0, 'zaru_frames': native_frames,
        'zaru_presentation': 'Whole source from 00:00 at 1.40 display size, centered on black; latest requested 8% exit-only pullback as green orb approaches camera.',
        'additional_zaru_scale': DISPLAY_SCALE, 'zaru_scale_animated': 'Exit-only 8% pullback, explicitly requested; never an added push-in.',
        'zaru_added_zoom_in': False, 'zaru_exit_pullback': ZARU_EXIT_PULLBACK,
        'black_margin_trim_only': True, 'object_crop': False,
        'additional_zaru_camera_motion': 'Exit-only pullback', 'source_pixel_displacement': False,
        'green_motion_start': GREEN_START_FRAME/FPS, 'journey_start': journey_start/FPS,
        'match_clear': (bridge.arrival+CONTACT_FRAMES)/FPS,
        'journey_resolution_clear': (journey_start+MATCH_EXIT_FRAMES)/FPS,
        'source_clock_overlap_frames': max(0,native_frames-journey_start),
        'outward_passage_start': bridge.travel_start/FPS,
        'near_camera': bridge.near_camera/FPS,
        'black_passage_start': native_frames/FPS,
        'black_passage_frames': journey_start-native_frames,
        'journey_source_in': 0, 'journey_frames': journey_frames,
        'journey_padding': [1, 0, 1, 0], 'journey_clock': 'Single forward pass, no restart or duplicate sequence.',
        'bridge': 'Green glow → green orb approaches camera while Zaru pulls back into black → continuous black lens passage → green-to-blue curved recession into live Journey → moving plant contact.',
        'match_anchor': bridge.anchor.tolist(), 'native_plant_point': PLANT_POINT.tolist(),
        'orb_formation_start': GREEN_START_FRAME/FPS,
        'orb_formation_end': (GREEN_START_FRAME+ORB_FORM_FRAMES)/FPS,
        'orb_travel_start': bridge.travel_start/FPS,
        'orb_arrival': bridge.arrival/FPS,
        'transformation_duration': (bridge.arrival-GREEN_START_FRAME)/FPS,
        'orb_release_color': [25.5,242.25,81.6],
        'orb_max_core_diameter': bridge.core_diameter*2/1.08,
        'orb_depth_projection': 'Three camera-space cubic curves: outbound distance 2→1.08; black foreground passage 1.08→1.16; curved Journey entry 1.16→2. Perspective projection, depth-driven core/halo size and brightness.',
        'orb_core_diameter': bridge.core_diameter,
        'orb_lilac_fringe_rgb': (bridge.lilac*255).round(3).tolist(),
        'orb_travel_distance_pixels': float(np.linalg.norm(bridge.anchor-plant_points[bridge.arrival-journey_start])),
        'plant_arrival_point': plant_points[bridge.arrival-journey_start].tolist(),
        'plant_point_tracking': 'Actual luminous plant beneath the reaching hand; native source motion, not a floating background particle.',
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
