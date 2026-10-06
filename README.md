# Yang Theory — single-film cinematic hero

The landing page is `index.html`; `review.html` provides normal Play/Pause/Replay
and native scrubbing. Both use the same 52.433-second, 1920×1080, 30 fps edit.
The review uses the high-quality master, and the landing uses a web-optimized
copy with an IDR frame every six frames (0.2 seconds), with no B frames.

The hero pins one persistent stage with GSAP ScrollTrigger. Native document
scroll maps deterministically to one paused video. Only one seek is in flight;
new scroll input replaces its pending target. There are no wheel locks, snaps,
multiple-video seeks, WebGL rendering, or browser-created transitions.

The existing navigation, hero copy, links, lower-page markup and `editorial.css`
are preserved. Desktop displays the complete film in a pinned stage. Portrait
mobile uses a separate cinema area and readable navigation/copy outside it,
preserving every shot and product proportion instead of cropping the film.
Landscape mobile uses the wider cinematic presentation. Reduced-motion mode
uses stable moments from the same film; normal playback remains on review.html.

## Run and build

Requires Node.js 20.19+ or 22.12+.

```sh
npm ci
npm run dev
npm run build
npm run preview
```

Publish `dist/` to the existing GitHub Pages `gh-pages` branch. All asset paths
are relative and work under `/yang-theory-site/`. `.nojekyll` is copied with the
static output.

## Offline master edit

The committed movie can be watched and built without rendering dependencies.
To reproduce it, install FFmpeg and Python with NumPy, Pillow and SciPy:

```sh
python scripts/render_review_film.py
```

The edit preserves all five complete source videos from time zero and the
original transparent PNG. Zaru's full video is centered at x=960, approximately
72% of the master canvas width, with black negative space. Journey fills the
master (two missing columns padded). The table is centered by its actual alpha
bounds on `#f3e9dd`, with constant scale and alpha geometry. Ophelia's complete
portrait remains sharp and centered. Shila's entire artwork is centered on
`#f4e9e1`, at 78–82% of master height, with a restrained final push for the gaze
match. Burton's complete flight/laptop/maker shot is uninterrupted.

The previous reveal logic was removed. Each connection is a discrete event:

- A tracked physical resin interior contains the Journey world, followed by a
  few-frame local optical breakout and a cut to the forest.
- The opening plant causes a brief blue/violet optical peak and a cut to the
  fully formed table/orb composition.
- An orb specular event bridges a real cut, continuing at the jewelry area.
- Ophelia's native final pendant close-up hard-cuts to the painted object.
- A restrained 3.97% final Shila push aligns the painted eye with Burton's eye
  at master position (838,294), followed by a hard gaze cut.

Stationary PNG/clock/portrait mattes only isolate source objects and join their
own surrounding fields. They do not reveal incoming shots. Optical light is
additive and lasts only a few frames; no outgoing/incoming dissolve is used.
No source media was recolored, regenerated, distorted or destructively enlarged.
`public/film/yang-theory-film.json` records source hashes, complete source
ranges, chapter times, fixed table geometry and encoding details. Both delivery
versions have 1,573 frames. No audio was added.

## Validation

With Python Playwright and Chromium installed, start the production preview:

```sh
python scripts/check_review.py http://127.0.0.1:4173
python scripts/check_scroll_film.py http://127.0.0.1:4173
```

Checks cover uninterrupted normal playback, pause/replay/scrubbing, desktop
scroll, pixel-identical reverse seeking, idle stability, native wheel and
keyboard input, the maker CTA, mobile/landscape layout and reduced motion.
Validation screenshots stay in `/tmp`. The deployment workflow checks both live
pages, both exact movie hashes, correct video MIME types and HTTP byte ranges.

The previous HTML remains archived as `scroll-prototype.html`; its old WebGL
renderer files are retained for reference and are not imported by the landing.
