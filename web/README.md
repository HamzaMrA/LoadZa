# LoadZa viewer

React + three.js. Shows a solved load in 3D: colour by delivery stop, a slider
that replays the loading order, click a box for its details, and the centre of
gravity marked against the tolerance it has to stay inside.

```bash
npm install
npm run dev        # http://localhost:5173, proxies /plans to the API on :8000
npm run build      # static bundle in dist/
```

## Where the plan comes from

1. `?plan=<plan_id>` — fetched from `GET /plans/{id}` on the same origin.
2. Nothing in the query string — the bundled `public/sample-plan.json` loads
   instead, so the built page is a working demo with no service behind it.
   That is what makes a static host (GitHub Pages) enough for a shareable link.
3. **Open plan…** — pick any plan JSON off disk. Useful for benchmark output
   and for plans this service never saw.

## Two things the viewer is careful about

**An unchecked plan is not a valid plan.** The solver leaves the violation map
empty because it is not entitled to grade itself. The badge reads `unchecked`
for an empty map and never green — a tick over an unaudited load would undo the
point of having a separate validator at all.

**Colour is by stop, not by SKU.** Boxes in a load touch at arbitrary pairings,
so every pair of fills has to be separable, and only three hues clear that bar
(validated: worst all-pairs CVD ΔE 9.2). Past three stops the hues repeat a
shade darker, and identity is carried by the legend and the detail panel rather
than by hue alone.

## Notes

The bundle is ~350 kB gzipped, nearly all of it three.js. Code-splitting it
would trade a smaller first paint for a blank canvas while the 3D chunk loads,
which is the wrong trade for a page whose entire purpose is the canvas.
