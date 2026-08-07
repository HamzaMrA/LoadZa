# LoadZa viewer

React + three.js. Three tabs:

- **New job** — pick a vehicle, add cargo lines from the catalogue, set delivery
  stops, choose solver settings, hit solve. Live gauges show how the cargo
  compares to the vehicle's volume and payload before you commit.
- **Jobs** — every job stored, and every plan under it side by side, so turning
  a constraint off and solving again gives you a comparison rather than a
  replacement.
- **Plan** — the load in 3D: colour by delivery stop, a slider that replays the
  loading order, click a box for its details, and the centre of gravity marked
  against the tolerance it has to stay inside.

```bash
npm install
npm run dev        # http://localhost:5173, proxies to the API on :8000
npm run build      # static bundle in dist/
```

The service has to be running for the first two tabs:

```bash
uvicorn app.api:app        # from the repository root
```

## Where the plan comes from

1. **New job** — built in the browser, solved by the service.
2. `?plan=<plan_id>` — fetched from `GET /plans/{id}`.
3. No service reachable — the bundled `public/sample-plan.json` loads instead
   and the page says so. The built bundle is therefore a working demo on a
   static host, which is what makes GitHub Pages enough for a shareable link.
4. **Open plan…** — any plan JSON off disk, including benchmark output the
   service never saw.

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
