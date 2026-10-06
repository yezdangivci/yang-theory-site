# Yang Theory — film review

`review.html` and the site root open the normal-playback review page. A single
offline-rendered MP4 contains the complete edit; the page does not use WebGL,
ScrollTrigger, multiple video elements, or scroll seeking.

Use **PLAY FILM**, the native video controls, Pause/Resume, Replay and the native
scrub bar. The movie is 31.2 seconds, 1920×1080 at 30 fps, H.264 High Profile,
CRF 17, with a fast-start MP4 header. No audio was added.

## Development and static build

Requires Node.js 20.19+ or 22.12+.

```sh
npm ci
npm run dev
npm run build
```

Serve the generated `dist/` directory. Both `index.html` and `review.html` are
built entries. `public/film/` is copied into `dist/film/`; all links are relative
and support the repository's GitHub Pages subdirectory.

## Render the film

The movie is committed, so building and watching require no rendering tools.
To reproduce it, install FFmpeg and Python with NumPy, Pillow and SciPy:

```sh
python scripts/render_review_film.py
```

The renderer reads the repository's original videos and unchanged transparent
PNG. It downsamples foreground media, preserves their proportions and colors,
and composites transition masks offline. Journey fills the 1080p environment;
Ophelia has a sharp 432×768 foreground and a separate surrounding field sampled
from its own background; Shila is matted out of its source canvas and shown at
a smaller size on `#f4e9e1`. Seek Magic uses `#f3e9dd`. Zaru starts at source
time zero in black, framed with substantial negative space.

`public/film/yang-theory-film.json` records original asset SHA-256 hashes,
source ranges and transition intervals. The last source plays continuously from
its beginning through Burton's flight, the laptop and the maker. No internal
transition was added.

The former scroll prototype remains archived as `scroll-prototype.html`, with
its renderer files and source assets unchanged. It is not the review player.
