# Yang Theory

The working landing page is `index.html`. The original V9 prototype and all six source media files are retained unchanged.

## Run

Requires Node.js 20.19+ or 22.12+.

```sh
npm ci
npm run dev
```

Open the address printed by Vite. Scroll normally, use the scrollbar, or use the browser's keyboard navigation. The hero pins one stage; its real video frames and selective WebGL composites follow document scroll in both directions. Native media proportions and a device-pixel-aware size cap protect foreground quality. There are no wheel interception, gesture locks, automatic chapter jumps, or primary opacity crossfades.

```sh
npm run build
npm run preview
```

`dist/` is the production site and can be served by any static web host. Asset URLs are relative, so subdirectory hosting is supported. Live playback requires HTTP(S), rather than opening the module-based HTML with `file://`.

## Media and edit

- Zaru → Journey → Seek Magic → Ophelia → Shila → Burton / Behind the world.
- `cinematic.js` owns the scroll edit, source time ranges, and copy cues.
- `film-renderer.js` owns proportional framing, native-pixel limits, and texture uploads.
- `film-shaders.js` owns the selective light/gradient transitions. The portrait foreground is never blurred; only luminance control signals are averaged. Shila's exterior background is matted, preserving its painted interior.
- Burton's flight and laptop/maker reveal remain one source video with no added internal transition.
- `editorial.css` and the lower-page markup retain V9's existing presentation. Images in `assets/original-editorial-*` are decoded copies of V9's embedded originals, without re-encoding.
- Reduced-motion mode uses static source moments and chapter cuts while preserving native scroll access to all six works.

## Browser validation

With Python Playwright and Chromium installed, start the production preview, then run:

```sh
python scripts/check_hero.py http://127.0.0.1:4173
```

The check visits all six beats and five transition midpoints, verifies frame seeking and reverse-scroll pixel determinism, checks mobile/reduced-motion behavior and the CTA handoff, and fails on browser errors or missing resources. Outputs stay outside the repository in `/tmp/yang-hero-checks`.
