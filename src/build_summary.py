"""
Collect every GMAT run into two tidy CSV tables:

results/contact_runs.csv     one row per orbit x RAAN x elevation mask
                             (the individual runs; keeps the spread auditable)
results/contact_summary.csv  one row per nominal altitude x inclination x mask,
                             aggregated over the RAAN samples:
                               mean_<metric>  mean over RAAN (representative value)
                               min_<metric>   minimum over RAAN
                               max_<metric>   maximum over RAAN
                             Equatorial orbits have a single RAAN (n_raan = 1),
                             so mean = min = max for them.

Altitude columns describe the propagated trajectory, not the case label:
    nominal_altitude_km   case label; sets the initial osculating SMA = R_eq + h
    mean/min/max_alt_km   geocentric radius minus the equatorial radius
                          R_eq = 6378.1363 km, sampled at every 60 s step
                          inside the 7-day analysis window. In the summary:
                          mean over RAAN of the per-run mean, and the overall
                          min/max over all RAAN runs.

Example
    uv run src/build_summary.py
"""

import pandas as pd

import cases as C
import parse_contacts as P
from run_gmat import RAW, ROOT, report_path, state_path

METRICS = ["passes_per_day", "contact_min_per_day", "mean_pass_min", "max_pass_min", "longest_gap_h"]
KEYS = ["nominal_altitude_km", "inclination_deg", "orbit_label", "elevation_mask_deg"]
RUN_COLUMNS = [
    "case_id", *KEYS, "raan_deg",
    "mean_alt_km", "min_alt_km", "max_alt_km",
    *METRICS, "min_pass_min", "n_passes_under_1min", "n_boundary_passes", "n_state_samples",
]


def altitude_stats(orbit: C.Orbit) -> dict:
    """Min/mean/max of (|r| - R_eq) inside the analysis window."""
    state = pd.read_csv(state_path(orbit), sep=r"\s+")
    t_h = state["Sat.ElapsedSecs"] / 3600.0
    in_window = (t_h >= C.WINDOW_OFFSET_H) & (t_h <= C.WINDOW_OFFSET_H + 24.0 * C.DURATION_DAYS)
    alt = state.loc[in_window, "Sat.Earth.RMAG"] - C.R_EQ_KM
    return dict(mean_alt_km=alt.mean(), min_alt_km=alt.min(), max_alt_km=alt.max(),
                n_state_samples=int(in_window.sum()))


def run_rows() -> pd.DataFrame:
    rows = []
    for orbit in C.all_orbits():
        alt = altitude_stats(orbit)
        for mask in C.MASKS_DEG:
            passes = P.read_report(report_path(orbit, mask, RAW))
            rows.append(dict(
                case_id=orbit.report_name(mask),
                nominal_altitude_km=orbit.alt_km,
                inclination_deg=round(orbit.inc_deg, 3),
                orbit_label=orbit.inc_label,
                elevation_mask_deg=mask,
                raan_deg=orbit.raan_deg,
                **alt,
                **P.summarise(passes),
            ))
    return pd.DataFrame(rows)[RUN_COLUMNS]


def aggregate(runs: pd.DataFrame) -> pd.DataFrame:
    g = runs.groupby(KEYS, sort=False)
    out = g.agg(
        n_raan=("raan_deg", "count"),
        mean_alt_km=("mean_alt_km", "mean"),
        min_alt_km=("min_alt_km", "min"),
        max_alt_km=("max_alt_km", "max"),
    )
    for m in METRICS:
        out[f"mean_{m}"] = g[m].mean()
        out[f"min_{m}"] = g[m].min()
        out[f"max_{m}"] = g[m].max()
    out["total_passes_under_1min"] = g["n_passes_under_1min"].sum()
    out["total_boundary_passes"] = g["n_boundary_passes"].sum()
    return out.reset_index()


def main() -> None:
    runs = run_rows()
    runs.to_csv(ROOT / "results" / "contact_runs.csv", index=False, float_format="%.4f")
    summary = aggregate(runs)
    summary.to_csv(ROOT / "results" / "contact_summary.csv", index=False, float_format="%.4f")
    print(f"results/contact_runs.csv: {len(runs)} rows; results/contact_summary.csv: {len(summary)} rows")


if __name__ == "__main__":
    main()
