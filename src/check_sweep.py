"""
Automated sanity checks on the RAAN sweep. This script only FLAGS problems;
it never edits, drops or replaces results.
Outputs: results/sanity_report.md, results/raan_comparison.csv

Checks
  Completeness   every altitude x inclination x mask x RAAN run exists
                 exactly once; no stray report files
  Run integrity  GMAT log says the run completed; state log has the expected
                 number of samples; every contact report is complete and
                 self-consistent (see parse_contacts.integrity_problems)
  Anomaly flags  (per run unless stated; thresholds next to each rule)
    A1 zero passes in the window
    A2 boundary passes (cut by the window edges): listed, handled by the
       rules in parse_contacts.py
    A3 longest pass longer than the physical upper bound (zenith pass)
    A4 complete passes shorter than 1 min: counted, listed for the write-up
    A5 for the same orbit and RAAN, the 5 deg mask must not give fewer
       contact minutes, fewer passes or a longer gap than the 10 deg mask
    A6 the RAAN-mean pass duration and contact minutes should grow with
       altitude at fixed inclination and mask; any decrease is flagged
    A7 longest gap > 2x the median of all runs with the same inclination
       and mask
    A8 altitude spread (max - min) > 1.5x the median of the same inclination,
       or > 2x the median over all runs
  RAAN sampling  mean over the 4-value subset (0/90/180/270) vs the 8-value
                 mean, for every inclined case
  Comparison     single-RAAN (RAAN = 0) value vs the RAAN mean; and the
                 preliminary single-RAAN sweep vs the main-sweep RAAN = 0 runs (effect of the
                 window offset and boundary rules)

Example
    uv run src/check_sweep.py
"""

import math
import sys

import numpy as np
import pandas as pd

import cases as C
import parse_contacts as P
from build_summary import KEYS, METRICS
from run_gmat import RAW, ROOT, log_path, report_path

OMEGA_EARTH = 7.2921159e-5      # Earth rotation rate [rad/s]
EXPECTED_SAMPLES = int(C.DURATION_DAYS * 86400 / C.MAX_STEP_S) + 1
SUBSET_4 = [0.0, 90.0, 180.0, 270.0]


def zenith_pass_bound_min(r_km: float, min_el_deg: float) -> float:
    """Upper bound on pass duration [min] for a circular orbit of radius r.

    A pass straight overhead covers an Earth-central angle of 2*lambda, with
    lambda = acos(R cos(el) / r) - el. The slowest possible relative motion
    is a prograde equatorial orbit, where the station moves with the
    satellite at the Earth rotation rate, so the rate is n - omega_E.
    """
    el = math.radians(min_el_deg)
    lam = math.acos(C.R_EQ_KM * math.cos(el) / r_km) - el
    n = math.sqrt(C.MU_KM3_S2 / r_km**3)
    return 2 * lam / (n - OMEGA_EARTH) / 60.0


def md_table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> list[str]:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        cells = [floatfmt.format(v) if isinstance(v, float) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def main() -> int:
    runs = pd.read_csv(ROOT / "results" / "contact_runs.csv")
    summ = pd.read_csv(ROOT / "results" / "contact_summary.csv")
    runs["orbit_label"] = runs["orbit_label"].astype(str)
    summ["orbit_label"] = summ["orbit_label"].astype(str)
    flags, info, integrity_fail = [], [], False

    def flag(rule, case, metric, value, why):
        flags.append(f"| {rule} | `{case}` | {metric} | {value} | {why} |")

    # ---------------------------------------------------------------- completeness
    orbits = C.all_orbits()
    expected = {(o.alt_km, o.inc_label, m, o.raan_deg) for o in orbits for m in C.MASKS_DEG}
    keys = list(zip(runs.nominal_altitude_km, runs.orbit_label, runs.elevation_mask_deg, runs.raan_deg))
    counts = pd.Series(keys).value_counts()
    dupes = sorted(counts[counts > 1].index)
    missing = sorted(expected - set(keys))
    extra = sorted(set(keys) - expected)
    expected_files = {report_path(o, m, RAW).name for o in orbits for m in C.MASKS_DEG}
    on_disk = {f.name for f in RAW.glob("*.txt")}
    n_raan_bad = summ[(summ.n_raan != np.where(summ.inclination_deg == 0, 1, len(C.RAAN_SAMPLES_DEG)))]
    completeness = [
        f"- GMAT runs: {len(orbits)} orbits "
        f"(5 equatorial x 1 RAAN + 25 inclined x {len(C.RAAN_SAMPLES_DEG)} RAAN), both masks per run",
        f"- Per-run rows: expected {len(expected)}, found {len(runs)}; per mask: "
        f"{runs.groupby('elevation_mask_deg').size().to_dict()}",
        f"- Duplicates: {dupes or 'none'}; missing: {missing or 'none'}; unexpected: {extra or 'none'}",
        f"- Report files: expected {len(expected_files)}, on disk {len(on_disk)}; "
        f"missing {sorted(expected_files - on_disk) or 'none'}; stray {sorted(on_disk - expected_files) or 'none'}",
        f"- Summary rows: {len(summ)} (expected 60); rows with wrong RAAN count: "
        f"{n_raan_bad[KEYS].values.tolist() or 'none'}",
    ]
    integrity_fail |= bool(dupes or missing or extra or (expected_files ^ on_disk) or len(n_raan_bad) or len(summ) != 60)

    # ---------------------------------------------------------------- run integrity
    integrity = []
    for o in orbits:
        log = log_path(o).read_text() if log_path(o).exists() else ""
        if "Mission run completed" not in log:
            integrity.append(f"- `{o.name}`: GMAT log does not report a completed run")
        for m in C.MASKS_DEG:
            for p in P.integrity_problems(report_path(o, m, RAW)):
                integrity.append(f"- `{o.report_name(m)}`: {p}")
    for row in runs[runs.n_state_samples != EXPECTED_SAMPLES].itertuples():
        integrity.append(f"- `{row.case_id}`: {row.n_state_samples} state samples, expected {EXPECTED_SAMPLES}")
    integrity_fail |= bool(integrity)

    # ---------------------------------------------------------------- per-run flags
    for row in runs.itertuples():
        if row.passes_per_day == 0:
            flag("A1", row.case_id, "passes_per_day", 0, "no contact in the 7-day window")
        bound = zenith_pass_bound_min(C.R_EQ_KM + row.max_alt_km, row.elevation_mask_deg)
        if row.max_pass_min > bound:
            flag("A3", row.case_id, "max_pass_min", f"{row.max_pass_min:.2f}",
                 f"exceeds zenith-pass upper bound {bound:.2f} min")
        if row.n_boundary_passes > 0 or row.n_passes_under_1min > 0:
            info.append((row.case_id, row.n_boundary_passes, row.n_passes_under_1min,
                         round(row.min_pass_min * 60, 1)))

    # A5: 5 deg vs 10 deg for the same orbit and RAAN
    orbit_key = ["nominal_altitude_km", "orbit_label", "raan_deg"]
    pair = runs[runs.elevation_mask_deg == 10].merge(runs[runs.elevation_mask_deg == 5], on=orbit_key, suffixes=("", "_5"))
    for r in pair.itertuples():
        if r.contact_min_per_day_5 < r.contact_min_per_day:
            flag("A5", r.case_id, "contact_min_per_day", f"{r.contact_min_per_day_5:.2f} (5°) < {r.contact_min_per_day:.2f} (10°)", "lower mask must see at least as much")
        if r.passes_per_day_5 < r.passes_per_day:
            flag("A5", r.case_id, "passes_per_day", f"{r.passes_per_day_5:.3f} (5°) < {r.passes_per_day:.3f} (10°)", "lower mask must see at least as many passes")
        if r.longest_gap_h_5 > r.longest_gap_h + 1e-6:
            flag("A5", r.case_id, "longest_gap_h", f"{r.longest_gap_h_5:.2f} (5°) > {r.longest_gap_h:.2f} (10°)", "lower mask must not have a longer gap")

    # A6: RAAN-mean trends with altitude
    for (label, mask), g in summ.groupby(["orbit_label", "elevation_mask_deg"]):
        g = g.sort_values("nominal_altitude_km").reset_index(drop=True)
        for m in ["mean_mean_pass_min", "mean_contact_min_per_day"]:
            for i in range(1, len(g)):
                if g.loc[i, m] < g.loc[i - 1, m]:
                    flag("A6", f"h{g.loc[i, 'nominal_altitude_km']:g}_i{label}_el{mask:g} (RAAN mean)", m,
                         f"{g.loc[i, m]:.2f} < {g.loc[i - 1, m]:.2f} at {g.loc[i - 1, 'nominal_altitude_km']:g} km",
                         "decreases with altitude")

    # A7: gap outliers within the same inclination and mask
    for (label, mask), g in runs.groupby(["orbit_label", "elevation_mask_deg"]):
        med = g.longest_gap_h.median()
        for r in g[g.longest_gap_h > 2 * med].itertuples():
            flag("A7", r.case_id, "longest_gap_h", f"{r.longest_gap_h:.2f}", f"> 2x median {med:.2f} h (i={label}, mask {mask:g}°)")

    # A8: altitude spread (one row per orbit: use the 10 deg rows)
    sp = runs[runs.elevation_mask_deg == 10].assign(spread=lambda d: d.max_alt_km - d.min_alt_km)
    all_med = sp.spread.median()
    for label, g in sp.groupby("orbit_label"):
        med = g.spread.median()
        for r in g[(g.spread > 1.5 * med) | (g.spread > 2 * all_med)].itertuples():
            flag("A8", r.case_id.replace("_el10", ""), "max_alt_km - min_alt_km", f"{r.spread:.2f} km",
                 f"group median {med:.2f} km, all-run median {all_med:.2f} km")

    # ---------------------------------------------------------------- RAAN sampling: 4 vs 8
    incl = runs[runs.inclination_deg != 0]
    comp = []
    for key, g in incl.groupby(KEYS, sort=False):
        row = dict(zip(KEYS, key))
        g4 = g[g.raan_deg.isin(SUBSET_4)]
        r0 = g[g.raan_deg == 0.0].iloc[0]
        for m in METRICS:
            row[f"mean8_{m}"] = g[m].mean()
            row[f"mean4_{m}"] = g4[m].mean()
            row[f"raan0_{m}"] = r0[m]
        comp.append(row)
    comp = pd.DataFrame(comp)
    comp.to_csv(ROOT / "results" / "raan_comparison.csv", index=False, float_format="%.4f")

    conv_lines, cmp_lines = [], []
    for m in METRICS:
        d4 = (comp[f"mean4_{m}"] - comp[f"mean8_{m}"]).abs()
        rel4 = d4 / comp[f"mean8_{m}"].abs()
        d0 = (comp[f"raan0_{m}"] - comp[f"mean8_{m}"]).abs()
        rel0 = d0 / comp[f"mean8_{m}"].abs()
        w4, w0 = rel4.idxmax(), rel0.idxmax()
        name = lambda i: f"h{comp.nominal_altitude_km[i]:g} i{comp.orbit_label[i]} el{comp.elevation_mask_deg[i]:g}"
        conv_lines.append(f"| {m} | {d4.median():.3f} | {100 * rel4.median():.1f} % | {d4.max():.3f} | {100 * rel4.max():.1f} % ({name(w4)}) |")
        cmp_lines.append(f"| {m} | {d0.median():.3f} | {100 * rel0.median():.1f} % | {d0.max():.3f} | {100 * rel0.max():.1f} % ({name(w0)}) |")

    # Preliminary single-RAAN sweep (window = propagation window, RAAN 0) vs main-sweep RAAN 0 runs
    pre = pd.read_csv(ROOT / "results" / "preliminary" / "single_raan" / "contact_summary.csv")
    pre["orbit_label"] = pre["orbit_label"].astype(str)
    new0 = runs[runs.raan_deg == 0.0]
    both = pre.merge(new0, on=["nominal_altitude_km", "orbit_label", "elevation_mask_deg"], suffixes=("_pre", "_main"))
    arch_lines = []
    for m in METRICS + ["mean_alt_km"]:
        d = (both[f"{m}_main"] - both[f"{m}_pre"]).abs()
        rel = d / both[f"{m}_pre"].abs()
        arch_lines.append(f"| {m} | {len(both)} | {d.median():.3f} | {d.max():.3f} | {100 * rel.max():.1f} % |")

    # ---------------------------------------------------------------- write report
    info_df = pd.DataFrame(info, columns=["case", "n_boundary_passes", "n_passes_under_1min", "shortest complete pass [s]"])
    text = "\n".join([
        "# RAAN-sweep sanity report", "",
        "Generated by `src/check_sweep.py`. Flags are for review; no result has been edited or removed.", "",
        "## Completeness", *completeness, "",
        "## Run integrity",
        *(integrity or [f"- All {len(orbits)} GMAT runs completed; all {len(expected_files)} contact reports and "
                        f"{len(orbits)} state logs passed the integrity checks."]), "",
        f"## Anomaly flags ({len(flags)})", "",
        "| Rule | Case | Metric | Observed | Why flagged |", "|---|---|---|---|---|",
        *(flags or ["| - | - | - | - | no flags |"]), "",
        f"## Boundary and short passes (A2, A4): {len(info_df)} runs", "",
        "Boundary passes are clipped / midpoint-counted / excluded from duration stats as defined in "
        "`parse_contacts.py`. Short passes are kept and counted.", "",
        *(md_table(info_df, "{:.1f}") if len(info_df) else ["none"]), "",
        "## RAAN sampling check: 4-value subset (0/90/180/270°) vs 8-value mean", "",
        "Absolute and relative difference |mean4 - mean8| over all 50 inclined cases (25 orbits x 2 masks).", "",
        "| Metric | Median abs | Median rel | Max abs | Max rel (case) |", "|---|---|---|---|---|",
        *conv_lines, "",
        "## Single RAAN (0°) vs RAAN mean (8 values)", "",
        "How much the representative value moves when one arbitrary phasing is replaced by the RAAN mean "
        "(inclined cases only; per-case values in `results/raan_comparison.csv`).", "",
        "| Metric | Median abs | Median rel | Max abs | Max rel (case) |", "|---|---|---|---|---|",
        *cmp_lines, "",
        "## Preliminary single-RAAN sweep vs main-sweep RAAN = 0 runs", "",
        f"Same orbits and RAAN; differences come only from the analysis window starting {C.WINDOW_OFFSET_H:g} h "
        "after the epoch and the boundary rules.", "",
        "| Metric | Cases | Median abs diff | Max abs diff | Max rel diff |", "|---|---|---|---|---|",
        *arch_lines,
    ])
    (ROOT / "results" / "sanity_report.md").write_text(text + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 1 if integrity_fail else 0


if __name__ == "__main__":
    sys.exit(main())
