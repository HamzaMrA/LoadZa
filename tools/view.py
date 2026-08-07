"""Draw a plan as a side elevation and a top plan view.

    python -m tools.view data/demo/job.json data/plans/plan.json
    python -m tools.view <job> <plan> --out docs/plan.png --label sku

This is the eyeball check that comes before the 3D viewer in F7: a validator
says a load is legal, a picture says whether it is sane. Requires the optional
plotting extra:  pip install -e ".[viz]"

Colour encodes the **delivery stop**, not the SKU. Two reasons. Operationally
the stop is what a loader needs to see at a glance. Technically, boxes in a
load touch at arbitrary pairings, so every pair of fills has to be
distinguishable -- and only three hues clear that bar. Past three stops the
hues repeat with a hatch, and every box carries a text label, so identity never
rests on colour alone.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.io import load_job, load_plan
from core.models import Job, Plan
from core.validator import validate

# Validated categorical slots 1-3 (light surface #fcfcfb, all-pairs clean).
STOP_COLOURS = ("#2a78d6", "#eb6834", "#1baf7a")
#: Composite encoding for stop 4 and beyond: the same hues, hatched.
HATCHES = ("", "///", "...", "xxx")

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
BASELINE = "#c3c2b7"


def stop_style(stop: int) -> tuple[str, str]:
    """(fill, hatch) for a delivery stop, 1-based."""
    index = max(stop - 1, 0)
    colour = STOP_COLOURS[index % len(STOP_COLOURS)]
    hatch = HATCHES[min(index // len(STOP_COLOURS), len(HATCHES) - 1)]
    return colour, hatch


def _draw_panel(ax, job: Job, plan: Plan, horizontal: str, vertical: str, label: str):
    """Render one orthographic projection.

    ``horizontal``/``vertical`` name the placement axes mapped to the screen, so
    the same routine draws the side elevation (x/z) and the top view (x/y).
    """
    from matplotlib.patches import Rectangle

    inner = job.vehicle.inner
    extent = {"x": inner.l, "y": inner.w, "z": inner.h}
    axis_attr = {"x": "l", "y": "w", "z": "h"}
    span_h, span_v = extent[horizontal], extent[vertical]
    hidden = ({"x", "y", "z"} - {horizontal, vertical}).pop()

    # The camera sits beside the trailer for the side view (near = small y) and
    # above it for the top view (near = large z). Draw far to near so the
    # nearest box wins the pixel, as it would in reality.
    reverse = hidden == "y"
    order = sorted(
        plan.placements, key=lambda p: getattr(p.pos, hidden), reverse=reverse
    )

    rects = []
    for placement in order:
        h0 = getattr(placement.pos, horizontal)
        v0 = getattr(placement.pos, vertical)
        hw = getattr(placement.dims, axis_attr[horizontal])
        vh = getattr(placement.dims, axis_attr[vertical])
        colour, hatch = stop_style(placement.stop)

        ax.add_patch(
            Rectangle(
                (h0, v0), hw, vh,
                facecolor=colour,
                hatch=hatch or None,
                edgecolor=SURFACE,      # a surface-coloured rim is the 2px gap
                linewidth=1.6,
                zorder=2,
            )
        )
        text = placement.sku if label == "sku" else str(placement.seq)
        rects.append((h0, v0, h0 + hw, v0 + vh, text))

    if label == "none":
        return

    # Label from the nearest box outwards, skipping any whose centre a nearer
    # box already covers. Without this every hidden box writes its name through
    # the one in front of it and the drawing turns to soup.
    covered: list[tuple[float, float, float, float]] = []
    for h0, v0, h1, v1, text in reversed(rects):
        cx, cy = (h0 + h1) / 2, (v0 + v1) / 2
        occluded = any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in covered)
        covered.append((h0, v0, h1, v1))
        if occluded:
            continue
        # Only label boxes with room for it; clipped text reads worse than none.
        if h1 - h0 > span_h * 0.035 and v1 - v0 > span_v * 0.075:
            ax.text(
                cx, cy, text,
                ha="center", va="center", fontsize=5.5,
                color="#ffffff", zorder=3,
            )

    ax.add_patch(
        Rectangle((0, 0), span_h, span_v, fill=False,
                  edgecolor=BASELINE, linewidth=1.2, zorder=4)
    )
    ax.set_xlim(-span_h * 0.02, span_h * 1.02)
    ax.set_ylim(-span_v * 0.05, span_v * 1.05)
    ax.set_aspect("equal")
    ax.set_facecolor(SURFACE)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=INK_MUTED, labelsize=7, length=3)
    ax.set_xlabel("mm from the closed end  →  doors", color=INK_MUTED, fontsize=7)
    ax.set_ylabel({"y": "width (mm)", "z": "height (mm)"}[vertical],
                  color=INK_MUTED, fontsize=7)


def _draw_cog(ax, job: Job, plan: Plan, vertical: str) -> None:
    """Mark the centre of gravity and the tolerance it has to stay inside."""
    from matplotlib.patches import Rectangle

    if plan.metrics is None or not plan.placements:
        return
    inner = job.vehicle.inner
    cog_x = inner.l / 2 + plan.metrics.cog_longitudinal_mm
    long_tol = job.vehicle.cog_long_tol_ratio * inner.l

    if vertical == "y":
        cog_v = inner.w / 2 + plan.metrics.cog_lateral_mm
        tol_v = job.vehicle.cog_lateral_tol_mm
        ax.add_patch(
            Rectangle(
                (inner.l / 2 - long_tol, inner.w / 2 - tol_v),
                2 * long_tol, 2 * tol_v,
                fill=False, edgecolor=INK_MUTED, linewidth=0.8,
                linestyle=(0, (4, 3)), zorder=5,
            )
        )
    else:
        # Below the floor line, clear of the load, where it stays readable.
        cog_v = -inner.h * 0.025
        ax.axvline(inner.l / 2 - long_tol, color=INK_MUTED, lw=0.8,
                   ls=(0, (4, 3)), zorder=5)
        ax.axvline(inner.l / 2 + long_tol, color=INK_MUTED, lw=0.8,
                   ls=(0, (4, 3)), zorder=5)

    ax.plot([cog_x], [cog_v], marker="+", markersize=9, markeredgewidth=1.6,
            color=INK_PRIMARY, zorder=6)
    ax.annotate(
        "centre of gravity", (cog_x, cog_v),
        textcoords="offset points", xytext=(8, -2),
        fontsize=6.5, color=INK_SECONDARY, zorder=6,
        bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.5, "alpha": 0.85},
    )


def render(job: Job, plan: Plan, out: Path, label: str = "sku") -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    matplotlib.rcParams["font.family"] = ["DejaVu Sans"]

    report = validate(job, plan)
    inner = job.vehicle.inner
    ratio = (inner.h + inner.w) / inner.l

    fig, (side, top) = plt.subplots(
        2, 1, figsize=(11, 3 + 11 * ratio), facecolor=SURFACE,
        gridspec_kw={"height_ratios": [inner.h, inner.w], "hspace": 0.35},
    )

    _draw_panel(side, job, plan, "x", "z", label)
    _draw_panel(top, job, plan, "x", "y", label)
    _draw_cog(side, job, plan, "z")
    _draw_cog(top, job, plan, "y")

    side.set_title("side elevation", color=INK_SECONDARY, fontsize=8, loc="left")
    top.set_title("top view", color=INK_SECONDARY, fontsize=8, loc="left")

    metrics = plan.metrics
    headline = f"{plan.job_id} — {job.vehicle.name}"
    detail = f"{len(plan.placements)} of {len(job.items)} items placed"
    if metrics is not None:
        detail += (f"   ·   {metrics.volume_utilization:.1%} volume"
                   f"   ·   {metrics.weight_utilization:.1%} payload")
    detail += f"   ·   {report.summary()}"

    fig.suptitle(headline, color=INK_PRIMARY, fontsize=11, x=0.02, ha="left", y=0.985)
    fig.text(0.02, 0.955, detail, color=INK_SECONDARY, fontsize=8, ha="left")
    fig.text(0.02, 0.02, f"{plan.algorithm}   ·   doors at x = {inner.l} mm",
             color=INK_MUTED, fontsize=7, ha="left")

    stops = sorted({p.stop for p in plan.placements})
    if len(stops) > 1:
        handles = []
        for stop in stops:
            colour, hatch = stop_style(stop)
            handles.append(
                Patch(facecolor=colour, hatch=hatch or None,
                      edgecolor=SURFACE, label=f"stop {stop}")
            )
        side.legend(handles=handles, loc="upper right", frameon=False,
                    fontsize=7, labelcolor=INK_SECONDARY, ncols=len(stops))

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw a LoadZa plan")
    parser.add_argument("job", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--label", default="sku", choices=["sku", "seq", "none"])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    job = load_job(args.job)
    plan = load_plan(args.plan)
    out = args.out or Path("docs") / f"{plan.plan_id}.png"
    print(f"written to {render(job, plan, out, args.label)}")


if __name__ == "__main__":
    main()
