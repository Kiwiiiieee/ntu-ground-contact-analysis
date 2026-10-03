"""
Animated GIFs for the README / portfolio. Illustrations of the
geometry, drawn from the same data as the figures:
  * GMAT state logs (results/crosscheck/gmat_reference/; rebuild with
    `uv run src/gmat_reference.py`) for the ground track,
  * GMAT's own contact reports (results/raw/) for the contact intervals.

    docs/media/anim_inclination_500km.gif   500 km: 0 deg vs 51.6 deg (RAAN 0)
    docs/media/anim_altitude_45deg.gif      45 deg: 500 km vs 800 km (RAAN 0)
    docs/media/anim_inclination_500km_short.gif   with --short: same day, coarser
                                            time step and resolution (portfolio)

Each shows the first 24 h of the analysis window: the ground track drawing
itself, the satellite, NTU's 10 deg visibility circle (brighter while in
contact), the contact segments (orange) and a running pass/contact counter.
GIF only: matplotlib's Pillow writer (ffmpeg is not required).

Example
    uv run src/make_animations.py
    uv run src/make_animations.py --short
"""

import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter

import cases as C
import make_figures as F
from run_gmat import ROOT

OUT = ROOT / "docs" / "media"
FRAME_S = 300                      # one frame per 5 min of orbit time
SHORT_FRAME_S, SHORT_DPI = 600, 72  # --short: half the frames, smaller image
FPS = 18
DPI = 90
T0 = C.WINDOW_OFFSET_H * 3600      # first 24 h of the analysis window
T1 = T0 + 24 * 3600
MASK = C.MIN_ELEVATION_BASELINE_DEG


class Panel:
    """One ground-track panel: data prepared once, artists updated per frame."""

    def __init__(self, ax, orbit: str, alt: int, label: str, title: str, summary):
        st = F.gmat_states(orbit)
        self.t = st["Sat.ElapsedSecs"].values
        self.lon_u = np.unwrap(np.radians(st["Sat.Earth.Longitude"].values))   # continuous, for interpolation
        self.lat = st["Sat.Earth.Latitude"].values
        passes = F.window_passes(f"{orbit}_el{MASK:g}")
        self.passes = passes[(passes.t1 > T0) & (passes.t0 < T1)][["t0", "t1"]].values
        clon, clat, lam = F.visibility_circle(F.row(summary, alt, label).mean_alt_km, MASK)
        self.ax = ax
        ax.set_xlim(-180, 180)
        ax.set_ylim(-75, 75)
        ax.set_xticks(range(-180, 181, 60))
        ax.set_yticks(range(-60, 61, 30))
        ax.set_ylabel("Latitude (°)")
        ax.set_aspect("equal")                 # true circle shape on the lon/lat map
        ax.set_title(title, loc="left", color=F.INK_2, fontsize=8)
        self.circle = ax.fill(clon, clat, color=F.CATEGORICAL[1], alpha=0.12, linewidth=0)[0]
        ax.plot(clon, clat, color=F.CATEGORICAL[1], linewidth=0.8)
        ax.plot(C.STATION_LON_DEG, C.STATION_LAT_DEG, marker="*", markersize=7, color=F.INK, linestyle="none")
        ax.text(C.STATION_LON_DEG + lam + 2, C.STATION_LAT_DEG - 6, "NTU", fontsize=7)
        self.track, = ax.plot([], [], color=F.CATEGORICAL[0], linewidth=0.7)
        self.contacts = [ax.plot([], [], color=F.CATEGORICAL[1], linewidth=2.8, solid_capstyle="round")[0]
                         for _ in self.passes]
        self.sat, = ax.plot([], [], marker="o", markersize=5, color=F.CATEGORICAL[0],
                            markeredgecolor="white", markeredgewidth=0.8, linestyle="none")
        self.counter = ax.text(0.995, 0.03, "", transform=ax.transAxes, ha="right", fontsize=7.5, color=F.INK,
                               bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=F.GRID, lw=0.6))

    def lonlat(self, tt):
        lon = np.degrees(np.interp(tt, self.t, self.lon_u))
        return F.track_with_breaks(lon, np.interp(tt, self.t, self.lat))

    def update(self, now: float):
        tt = np.append(self.t[(self.t >= T0) & (self.t < now)], now)
        self.track.set_data(*self.lonlat(tt))
        lo, la = self.lonlat(np.array([now]))
        self.sat.set_data(lo, la)
        in_contact, n_done, minutes = False, 0, 0.0
        for line, (a, b) in zip(self.contacts, self.passes):
            if a < now:
                end = min(b, now)
                line.set_data(*self.lonlat(np.linspace(max(a, T0), end, 40)))
                n_done += 1
                minutes += (end - max(a, T0)) / 60
                in_contact |= now <= b
        self.circle.set_alpha(0.45 if in_contact else 0.12)
        self.counter.set_text(f"passes: {n_done}   contact: {minutes:.1f} min")
        return [self.track, self.sat, self.circle, self.counter, *self.contacts]


def animate(name: str, panels_spec, headline: str, frame_s: int = FRAME_S, dpi: int = DPI) -> None:
    s = F.load_summary()
    fig, axes = plt.subplots(len(panels_spec), 1, figsize=(7.0, 2.75 * len(panels_spec)), sharex=True)
    panels = [Panel(ax, *spec, s) for ax, spec in zip(axes, panels_spec)]
    axes[-1].set_xlabel("Longitude (°)")
    clock = fig.text(0.01, 0.995, "", va="top", fontsize=8.5, color=F.INK)
    fig.text(0.99, 0.995, headline, va="top", ha="right", fontsize=7.5, color=F.INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    frames = np.arange(T0, T1 + 1, frame_s)

    def draw(now):
        hours = (now - T0) / 3600
        stamp = P_EPOCH_PLUS(now)
        clock.set_text(f"{stamp:%d %b %Y %H:%M} UTC   (+{hours:4.1f} h)")
        return [a for p in panels for a in p.update(now)] + [clock]

    anim = FuncAnimation(fig, draw, frames=frames, blit=False)
    path = OUT / f"{name}.gif"
    anim.save(path, writer=PillowWriter(fps=FPS), dpi=dpi)
    plt.close(fig)
    # The final counters must equal GMAT's reported passes in these 24 h.
    for p in panels:
        assert len(p.passes) == sum(1 for a, _ in p.passes if a < T1)
    print(f"{path.relative_to(ROOT)}: {len(frames)} frames, {path.stat().st_size / 1e6:.1f} MB; "
          f"passes in 24 h: {[len(p.passes) for p in panels]}")


def P_EPOCH_PLUS(seconds):
    from datetime import timedelta
    import parse_contacts as P
    return P.EPOCH + timedelta(seconds=float(seconds))


INCLINATION = [("h500_i0_raan0", 500, "0", "500 km, 0° (equatorial)"),
               ("h500_i51p6_raan0", 500, "51.6", "500 km, 51.6°, RAAN 0°")]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if "--short" in sys.argv[1:]:
        animate("anim_inclination_500km_short", INCLINATION,
                "GMAT state log + GMAT contact reports; 10° mask", SHORT_FRAME_S, SHORT_DPI)
        return
    animate("anim_inclination_500km", INCLINATION,
            "GMAT state log + GMAT contact reports; 10° mask")
    animate("anim_altitude_45deg",
            [("h500_i45_raan0", 500, "45", "500 km, 45°, RAAN 0°"),
             ("h800_i45_raan0", 800, "45", "800 km, 45°, RAAN 0°")],
            "GMAT state log + GMAT contact reports; 10° mask")


if __name__ == "__main__":
    sys.exit(main())
