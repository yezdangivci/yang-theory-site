#!/usr/bin/env python3
"""Offline event edit: complete sources, local portal/optics, hard match cuts.

No transition reveal fields, dissolves, noise, or temporal artwork alpha changes.
The alpha composites below are stationary object/portrait mattes, not transitions.
"""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy.ndimage import binary_erosion, label
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parents[1]
W, H, FPS = 1920, 1080, 30
EDIT_LOCK = json.loads((ROOT/'hero-edit-lock.json').read_text())
OPHELIA_SOURCE_IN = EDIT_LOCK['ophelia']['source_in_seconds']
OPHELIA_SOURCE_FIRST_FRAME = round(OPHELIA_SOURCE_IN*FPS)
SOURCES = ['zaru_3_web.mp4', 'Journey:Yez Startle video.mp4', 'seek_magic_table.png',
           'ophelia_landing_916_web.mp4', 'shila_lastvideo.mp4', 'yez_ekran_final_web.mp4']
COUNTS = [453, 152, 135, 443-OPHELIA_SOURCE_FIRST_FRAME, 176, 214]
STARTS = np.cumsum([0] + COUNTS[:-1]).tolist()
TOTAL = sum(COUNTS)
Y, X = np.mgrid[:H, :W].astype(np.float32)
IVORY = np.array([244, 233, 225], np.float32)
TABLE_IVORY = np.array([243, 233, 221], np.float32)


def ease(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def plate(color):
    return np.broadcast_to(np.asarray(color, np.float32), (H, W, 3)).copy()


def composite(a, b, alpha):
    return a + (b - a) * alpha[..., None]


def place(image, center=(960, 540), alpha=None, background=None):
    height, width = image.shape[:2]
    x, y = round(center[0] - width / 2), round(center[1] - height / 2)
    result = plate([0, 0, 0]) if background is None else background.copy()
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + width), min(H, y + height)
    tile = image[y0-y:y1-y, x0-x:x1-x].astype(np.float32)
    if alpha is None:
        result[y0:y1, x0:x1] = tile
    else:
        result[y0:y1, x0:x1] = composite(result[y0:y1, x0:x1], tile, alpha[y0-y:y1-y, x0-x:x1-x])
    return result


class Clip:
    def __init__(self, name, width, height, pad=False):
        self.name, self.width, self.height, self.pad = name, width, height, pad
        self.process, self.index, self.last = None, -1, None

    def get(self, index):
        if self.process is None:
            vf = f'fps={FPS},scale={self.width}:{self.height}:flags=lanczos'
            if self.pad:
                vf = f'fps={FPS},pad=1920:1080:1:0:black'
            self.process = subprocess.Popen(['ffmpeg', '-v', 'error', '-threads', '2',
                '-i', str(ROOT / self.name), '-an', '-vf', vf, '-pix_fmt', 'rgb24',
                '-f', 'rawvideo', 'pipe:1'], stdout=subprocess.PIPE)
        size = self.width * self.height * 3
        while self.index < index:
            data = self.process.stdout.read(size)
            if len(data) != size:
                break
            self.last = np.frombuffer(data, np.uint8).reshape(self.height, self.width, 3)
            self.index += 1
        if self.last is None:
            raise RuntimeError(f'Cannot decode {self.name}')
        return self.last

    def close(self):
        if self.process:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            self.process.stdout.close()


def optical(frame, origin, strength, color, radius=100, streak=900):
    """Few-frame additive sensor flare from a real light-bearing object.

    This adds light; it never mixes an outgoing image with an incoming image.
    Its compact core, diffraction streak and two lens ghosts have finite extent.
    """
    if strength <= 0:
        return frame
    dx, dy = X - origin[0], Y - origin[1]
    core = np.exp(-(dx*dx + dy*dy) / (2 * radius*radius))
    spike = np.exp(-(dx*dx/(streak*streak) + dy*dy/32))
    vertical = np.exp(-(dx*dx/22 + dy*dy/(radius*radius*6)))
    light = core * 230 + spike * 95 + vertical * 60
    result = frame + light[..., None] * np.asarray(color, np.float32) * strength
    # Actual optical ghosts stay local and last only as long as the flare.
    for factor, amount in [(.45, 20), (-.25, 12)]:
        gx = 960 + (origin[0] - 960) * factor
        gy = 540 + (origin[1] - 540) * factor
        ghost = np.exp(-((X-gx)**2 + (Y-gy)**2) / (radius*radius*.34))
        result += ghost[..., None] * np.asarray(color, np.float32) * amount * strength
    return result


class MasterEdit:
    def __init__(self):
        self.clips = [Clip(SOURCES[0], 1382, 760), Clip(SOURCES[1], W, H, pad=True),
            None, Clip(SOURCES[3], 486, 864), Clip(SOURCES[4], W, H), Clip(SOURCES[5], W, H)]
        portal = Clip(SOURCES[1], 640, 360)
        self.portal_frames = [portal.get(i).copy() for i in range(26)]
        portal.close()
        original = Image.open(ROOT / SOURCES[2]).convert('RGBA')
        bbox = original.getchannel('A').getbbox()
        self.alpha_bounds = bbox
        table = original.crop(bbox)
        scale = 780 / table.height
        table = np.asarray(table.resize((round(table.width*scale), 780), Image.Resampling.LANCZOS))
        self.table_alpha = table[..., 3].astype(np.float32) / 255
        self.table = place(table[..., :3], alpha=self.table_alpha, background=plate(TABLE_IVORY))
        # Native PNG orb coordinates transformed through fixed alpha-bound framing.
        self.orb = (960 + (1430-(bbox[0]+bbox[2])/2)*scale,
                    540 + (181-(bbox[1]+bbox[3])/2)*scale)
        self.shila_eye = np.array([868., 330.])
        self.burton_eye = np.array([838., 294.])
        self.clock_center = np.array([964., 547.])
        yy, xx = np.mgrid[:1080, :1920].astype(np.float32)
        radius = np.sqrt(((xx-964)/510)**2 + ((yy-547)/511)**2)
        self.clock_inner = 1 - ease((radius-.93)/.065)
        self.clock_outer = 1 - ease((radius-1.008)/.025)
        yy, xx = np.mgrid[:864, :486].astype(np.float32)
        # A constant portrait edge matte only joins its own ambient background.
        self.portrait_alpha = ease(xx/32)*ease((485-xx)/32)*ease(yy/30)*ease((863-yy)/34)
        self.portrait_field = (np.exp(-((X-960)/515)**4 - ((Y-540)/820)**8)
            * ease(Y/108) * ease((1080-Y)/108))

    def portal(self, small, index):
        """Replace only the tracked real resin interior. No expanding mask."""
        r, g, b = [small[..., i].astype(np.float32) for i in range(3)]
        green = (g > r*1.35) & (g > b*.88) & (g > 42)
        labels, _ = label(green)
        sizes = np.bincount(labels.ravel()); sizes[0] = 0
        region = labels == sizes.argmax()
        yy, xx = np.nonzero(region)
        if len(xx) < 40:
            raise RuntimeError('Green resin tracking failed')
        points = np.column_stack([xx, yy]); hull = ConvexHull(points)
        matte = Image.new('L', (small.shape[1], small.shape[0]))
        ImageDraw.Draw(matte).polygon([tuple(p) for p in points[hull.vertices]], fill=255)
        inside = binary_erosion(np.asarray(matte)>0, iterations=3)
        x0, x1, y0, y1 = xx.min(), xx.max()+1, yy.min(), yy.max()+1
        world = self.portal_frames[min(index, len(self.portal_frames)-1)]
        # Full-color forest miniature inhabits the physical resin, not the screen.
        texture = np.asarray(ImageOps.fit(Image.fromarray(world), (x1-x0, y1-y0),
            Image.Resampling.LANCZOS, centering=(.43,.52)))
        result = small.copy()
        local = inside[y0:y1, x0:x1]
        local &= small[y0:y1, x0:x1].max(axis=2) < 238  # preserve real glass glints
        result[y0:y1, x0:x1][local] = texture[local]
        origin = (960-small.shape[1]/2+(x0+x1)/2, 540-small.shape[0]/2+(y0+y1)/2)
        return result, origin

    def ophelia(self, frame):
        # Edge extension at the foreground's native display scale, never a second
        # enlarged portrait. Its original colors form the separate ambient field.
        ambient = np.pad(frame, ((108,108),(717,717),(0,0)), mode='edge')
        ambient = np.asarray(Image.fromarray(ambient).filter(ImageFilter.GaussianBlur(45)), dtype=np.float32)
        background = composite(plate(IVORY), ambient, self.portrait_field)
        return place(frame, alpha=self.portrait_alpha, background=background)

    def shila(self, frame, index):
        key = ease((np.linalg.norm(frame.astype(np.float32)-np.array([244,233,216],np.float32), axis=2)-7)/21)
        alpha = np.maximum(self.clock_inner, key) * self.clock_outer
        # The complete oval remains visible: 78.6% → 81.7% of master height.
        push = float(ease((index/FPS - 4.75) / 1.08))
        scale = .831 + .033*push
        target_center = self.burton_eye - (self.shila_eye-self.clock_center)*.864
        center = np.array([960.,540.]) + (target_center-np.array([960.,540.]))*push
        width, height = round(W*scale), round(H*scale)
        image = np.asarray(Image.fromarray(frame).resize((width,height), Image.Resampling.LANCZOS))
        matte = np.asarray(Image.fromarray(alpha.astype(np.float32), mode='F').resize((width,height), Image.Resampling.BILINEAR))
        # Adjust canvas placement so the artwork's true center, not video canvas,
        # owns the composition. At the final frame the chosen eyes coincide.
        canvas_center = center + (np.array([960.,540.])-self.clock_center)*scale
        return place(image, canvas_center, matte, plate(IVORY))

    def frame(self, global_index):
        scene = next((i for i in range(5,-1,-1) if global_index >= STARTS[i]), 0)
        index = global_index-STARTS[scene]
        remaining = COUNTS[scene]-index-1
        if scene == 0:
            small = self.clips[0].get(index)
            origin = (974,560)
            if remaining < 26:
                small, origin = self.portal(small, 25-remaining)
            frame = place(small)
            if remaining < 5:
                frame = optical(frame, origin, [1.8,1.45,.85,.42,.16][remaining], [.55,1,.70], radius=75+18*(4-remaining), streak=750)
            return frame
        if scene == 1:
            frame = self.clips[1].get(index).astype(np.float32)
            if index < 3:
                frame = optical(frame,(974,560),[1.1,.45,.10][index],[.55,1,.70],radius=145,streak=750)
            if remaining < 5:
                # The real opening plant supplies the optical event's position.
                frame = optical(frame,(410,863),[2.1,1.35,.7,.28,.08][remaining],[.56,.54,1.0],radius=85+20*(4-remaining),streak=1050)
                if remaining < 2:
                    # The final sensor reflection occupies the incoming orb's
                    # position, making the cut a luminous spatial match.
                    frame = optical(frame,self.orb,[1.05,.38][remaining],[.56,.54,1],radius=85,streak=550)
            return frame
        if scene == 2:
            frame = self.table.copy()  # fixed object geometry, every single frame
            if index < 3:
                frame = optical(frame,self.orb,[1.5,.55,.12][index],[.56,.54,1],radius=110,streak=1000)
            if remaining < 5:
                frame = optical(frame,self.orb,[2.8,1.65,.75,.27,.08][remaining],[.87,.93,1],radius=80+20*(4-remaining),streak=1650)
                if remaining < 2:
                    frame = optical(frame,(960,695),[1.35,.48][remaining],[.87,.93,1],radius=75,streak=1100)
            return frame
        if scene == 3:
            frame = self.ophelia(self.clips[3].get(index+OPHELIA_SOURCE_FIRST_FRAME))
            if index < 5:
                frame = optical(frame,(960,695),[1.9,.85,.38,.14,.04][index],[.87,.93,1],radius=95,streak=1300)
            return frame  # hard wearable-object → painted-object cut follows
        if scene == 4:
            return self.shila(self.clips[4].get(index),index)
        return self.clips[5].get(index).astype(np.float32)  # uninterrupted source

    def close(self):
        for clip in self.clips:
            if clip: clip.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'public/film/yang-theory-film.mp4')
    parser.add_argument('--stills',type=Path)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    edit=MasterEdit()
    encoder=subprocess.Popen(['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0',
        '-an','-c:v','libx264','-threads','3','-preset','medium','-crf','17','-pix_fmt','yuv420p','-profile:v','high','-level:v','4.1',
        '-g','60','-movflags','+faststart','-y',str(args.output)],stdin=subprocess.PIPE)
    stills = {0,45,300,TOTAL-1}
    for start in STARTS[1:]:
        stills.update(start+j for j in [-28,-8,-3,-1,0,1,4,10,45] if 0 <= start+j < TOTAL)
    try:
        for i in range(TOTAL):
            frame=np.clip(edit.frame(i),0,255).astype(np.uint8)
            if args.stills and i in stills:
                args.stills.mkdir(parents=True,exist_ok=True)
                Image.fromarray(frame).save(args.stills/f'{i:04d}-{i/FPS:.3f}.jpg',quality=95)
            encoder.stdin.write(frame.tobytes())
            if i%90 == 0: print(f'Rendered {i/FPS:.1f}/{TOTAL/FPS:.2f}s',flush=True)
    finally:
        encoder.stdin.close();edit.close()
    if encoder.wait(): raise RuntimeError('Encoder failed')
    # Encode the identical decoded master with frequent IDR frames. There is no
    # separate browser edit and no alternate source compositing during scroll.
    scrub=args.output.with_name('yang-theory-scrub.mp4')
    subprocess.run(['ffmpeg','-v','error','-i',str(args.output),'-an','-c:v','libx264','-threads','3','-preset','fast','-crf','18',
        '-g','6','-keyint_min','6','-sc_threshold','0','-bf','0','-pix_fmt','yuv420p','-movflags','+faststart','-y',str(scrub)],check=True)
    poster=args.output.with_name('poster.jpg')
    subprocess.run(['ffmpeg','-v','error','-ss','7','-i',str(args.output),'-frames:v','1','-q:v','2','-y',str(poster)],check=True)
    metadata={'width':W,'height':H,'fps':FPS,'frames':TOTAL,'duration':TOTAL/FPS,
        'starts':{name:STARTS[i]/FPS for i,name in enumerate(['Zaru','Journey','Seek Magic','Ophelia','Shila','Burton'])},
        'chapters':[{'index':i,'name':name,'start':STARTS[i]/FPS,'end':(STARTS[i]+COUNTS[i])/FPS} for i,name in enumerate(['Zaru','Journey','Seek Magic','Ophelia','Shila','Burton'])],
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES},
        'complete_source_ranges':{name:[OPHELIA_SOURCE_IN if name==SOURCES[3] else 0, float(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(ROOT/name)]))['format']['duration'])] for name in SOURCES if name.endswith('.mp4')},
        'events':['resin portal → local breakout → cut','plant reaction → short optical peak → orb cut','orb specular event → cut → jewelry glint','pendant → painted object hard cut','painted eye → aligned living eye hard cut'],
        'table':{'native_alpha_bounds':edit.alpha_bounds,'visible_center':[960,540],'fixed_height':780,'temporal_alpha_change':False},
        'gaze_match':{'eye':edit.burton_eye.tolist(),'maximum_clock_height_fraction':.817,'restrained_scale_ratio':.864/.831},
        'scrub':{'gop_frames':6,'keyframe_interval_seconds':.2,'same_edit_as_review':True}}
    args.output.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(f'Completed {TOTAL} frames. Review {args.output.stat().st_size/1e6:.1f} MB; scrub {scrub.stat().st_size/1e6:.1f} MB.',flush=True)


if __name__=='__main__': main()
