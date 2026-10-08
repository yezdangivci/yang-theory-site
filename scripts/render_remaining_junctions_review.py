#!/usr/bin/env python3
"""Extract four existing junctions for review; never render a full hero.

Three clips are excerpted directly from the stored master. The fourth preserves
the Seek Magic frames and existing Ophelia composition/optical timings, with the
sole authorized source in-point change: Ophelia starts at 9s. No new edit effects.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from render_review_film import MasterEdit, OPHELIA_SOURCE_IN, STARTS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'public/previews/remaining-junctions'
MASTER = ROOT/'public/film/yang-theory-film.mp4'
FPS, W, H = 30, 1920, 1080


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock(lock):
    for name, expected in lock['ophelia_to_shila']['sha256'].items():
        assert sha(ROOT/name) == expected, f'Approved implementation changed: {name}'


def encode_args(output):
    return ['-an', '-c:v', 'libx264', '-threads', '3', '-preset', 'medium',
            '-crf', '17', '-pix_fmt', 'yuv420p', '-g', '30', '-movflags',
            '+faststart', '-y', str(output)]


def extract(start, frames, output):
    subprocess.run(['ffmpeg', '-v', 'error', '-threads', '2', '-ss', str(start/FPS),
        '-i', str(MASTER), '-frames:v', str(frames), *encode_args(output)], check=True)


def raw_excerpt(start, frames):
    process = subprocess.Popen(['ffmpeg', '-v', 'error', '-threads', '2', '-ss',
        str(start/FPS), '-i', str(MASTER), '-frames:v', str(frames), '-an',
        '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'], stdout=subprocess.PIPE)
    try:
        for _ in range(frames):
            data = process.stdout.read(W*H*3)
            assert len(data) == W*H*3
            yield data
        assert process.wait() == 0
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait()


def ophelia_entry(start, before, after, output):
    # Call the current edit's exact scene function, including its existing
    # five-frame jewelry glint. Only its source offset is different.
    edit = MasterEdit()
    encoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-f', 'rawvideo',
        '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', 'pipe:0',
        *encode_args(output)], stdin=subprocess.PIPE)
    try:
        for frame in raw_excerpt(start, before):
            encoder.stdin.write(frame)
        for i in range(after):
            frame = np.clip(edit.frame(STARTS[3]+i), 0, 255).astype('uint8')
            encoder.stdin.write(frame.tobytes())
    finally:
        encoder.stdin.close()
        edit.close()
    assert encoder.wait() == 0


def main():
    lock = json.loads((ROOT/'hero-edit-lock.json').read_text())
    verify_lock(lock)
    assert OPHELIA_SOURCE_IN == 9
    OUT.mkdir(parents=True, exist_ok=True)
    snapshot = json.loads((MASTER.with_suffix('.json')).read_text())
    snapshot_hashes = {name: sha(ROOT/'public/film'/name) for name in
        ['yang-theory-film.mp4', 'yang-theory-film.json', 'yang-theory-scrub.mp4', 'poster.jpg']}
    windows = [
        ('zaru-journey', 'Zaru → Journey', 'Journey', 90, 90),
        ('journey-seek-magic', 'Journey → Seek Magic', 'Seek Magic', 120, 90),
        ('seek-magic-ophelia', 'Seek Magic → Ophelia', 'Ophelia', 90, 105),
        ('shila-burton', 'Shila → Burton', 'Burton', 90, 120),
    ]
    clips = []
    for slug, title, chapter, before, after in windows:
        cut = round(snapshot['starts'][chapter]*FPS)
        first = cut-before
        path = OUT/f'{slug}.mp4'
        print(f'Preparing existing junction: {title}', flush=True)
        if chapter == 'Ophelia':
            ophelia_entry(first, before, after, path)
        else:
            extract(first, before+after, path)
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(max(0, before/FPS-1.0)),
            '-i', str(path), '-frames:v', '1', '-q:v', '2', '-y',
            str(OUT/f'{slug}.jpg')], check=True)
        info = {'slug': slug, 'title': title, 'frames': before+after,
                'duration': (before+after)/FPS, 'junction_time': before/FPS,
                'context_before': before/FPS, 'context_after': after/FPS,
                'stored_master_context': [first/FPS, (cut+after)/FPS],
                'provenance': 'Existing stored master excerpt; no transition changes.',
                'sha256': sha(path)}
        if chapter == 'Ophelia':
            info.update(provenance='Existing Seek Magic frames and current Ophelia composition/optical event; only Ophelia source in-point changes to 9s.',
                        incoming_source='ophelia_landing_916_web.mp4',
                        incoming_source_range=[9, 9+after/FPS])
        clips.append(info)
    verify_lock(lock)
    assert all(sha(ROOT/'public/film'/name) == expected
               for name, expected in snapshot_hashes.items())
    manifest = {'width': W, 'height': H, 'fps': FPS,
                'snapshot_commit': '26ad392b12ecf279fa61383762ba9c80080c6a18',
                'stored_master_sha256': snapshot_hashes['yang-theory-film.mp4'],
                'full_hero_rendered': False, 'remaining_transitions_redesigned': False,
                'approved_ophelia_shila_unchanged': True, 'ophelia_source_in': 9,
                'known_zaru_mismatch': 'The stored master still contains the older stone inset/light breakout. It is shown unchanged; the intended emerald-movement edit remains the requirement.',
                'shila_burton_intent': lock['remaining_junctions']['shila_to_burton_intent'],
                'burton_maker_unchanged': True, 'clips': clips}
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('Four junction clips prepared; locked preview and full master unchanged.', flush=True)


if __name__ == '__main__':
    main()
