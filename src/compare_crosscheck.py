"""
Compare the independent Python results with GMAT, using the tolerances
pre-registered in results/crosscheck/METHOD_AND_CRITERIA.md.
Neither dataset is modified; each result is classified PASS or INVESTIGATE.

Inputs
    GMAT:   results/raw/<case>.txt (contact reports), results/contact_runs.csv
            (parsed per-run metrics), results/crosscheck/gmat_reference/ (states)
    Python: results/crosscheck/python/ (contacts, metrics, states)
Outputs
    results/crosscheck/comparison.md
    results/crosscheck/comparison_events.csv      one row per matched pass
    results/crosscheck/comparison_trajectory.csv  max position difference per orbit
    results/crosscheck/comparison_aggregates.csv  one row per orbit x mask x metric

Example
    uv run src/compare_crosscheck.py
"""

import sys

import numpy as np
import pandas as pd

import cases as C
import parse_contacts as P
from gmat_reference import CROSSCHECK, OUT as GMAT_REF
from run_gmat import RAW, ROOT

PY = ROOT / "results" / "crosscheck" / "python"
OUT = ROOT / "results" / "crosscheck"

# Pre-registered tolerances (METHOD_AND_CRITERIA.md). Do not edit after the fact.
TOL_T1_KM = 0.1
TOL_T2_KM = 0.1
TOL_E2_S = 0.5      # passes >= 120 s
TOL_E3_S = 2.0      # passes 60-120 s
TOL_A3_REL = 0.005  # contact_min_per_day
TOL_A4_REL = 0.005  # mean_pass_min
TOL_A5_S = 1.0      # max_pass_min
TOL_A6_S = 2.0      # longest_gap_h

verdict = lambda ok: "PASS" if ok else "INVESTIGATE"


def trajectory_rows() -> list[dict]:
    rows = []
    for name in CROSSCHECK:
        g = pd.read_csv(GMAT_REF / f"{name}_states.txt", sep=r"\s+")
        p = np.load(PY / f"{name}_states.npz")
        idx = np.rint(g["Sat.ElapsedSecs"].values / 60.0).astype(int)   # GMAT steps are 60 s
        gi = g[[f"Sat.EarthMJ2000Eq.{c}" for c in "XYZ"]].values.T
        gf = g[[f"Sat.EarthFixed.{c}" for c in "XYZ"]].values.T
        d_in = np.linalg.norm(p["r_gcrs"][:, idx] - gi, axis=0)
        d_fx = np.linalg.norm(p["r_itrs"][:, idx] - gf, axis=0)
        rows.append(dict(orbit=name, max_inertial_km=d_in.max(), max_earth_fixed_km=d_fx.max(),
                         T1=verdict(d_in.max() <= TOL_T1_KM), T2=verdict(d_fx.max() <= TOL_T2_KM)))
    return rows


def match_passes(gm: pd.DataFrame, py: pd.DataFrame):
    """Pairs of overlapping passes, plus unmatched ones on each side."""
    overlaps = [(i, j) for i, a in gm.iterrows() for j, b in py.iterrows()
                if a.start < b.stop and b.start < a.stop]
    gi = pd.Series([i for i, _ in overlaps]).value_counts()
    pj = pd.Series([j for _, j in overlaps]).value_counts()
    one_to_one = (len(overlaps) == len(gm) == len(py)) and (gi.max() == 1 if len(gi) else True) \
        and (pj.max() == 1 if len(pj) else True)
    unmatched_g = sorted(set(gm.index) - set(gi.index))
    unmatched_p = sorted(set(py.index) - set(pj.index))
    return overlaps, one_to_one, unmatched_g, unmatched_p


def main() -> int:
    traj = trajectory_rows()
    gmat_runs = pd.read_csv(ROOT / "results" / "contact_runs.csv").set_index("case_id")
    py_metrics = pd.read_csv(PY / "metrics.csv").set_index("case_id")
    by_name = {o.name: o for o in C.all_orbits()}

    event_rows, event_summary, agg_rows = [], [], []
    traceable = True
    for name in CROSSCHECK:
        for mask in C.MASKS_DEG:
            case = by_name[name].report_name(mask)
            gm = P.read_report(RAW / f"{case}.txt")
            py = pd.read_csv(PY / f"{case}.csv", parse_dates=["start", "stop"])
            pairs, one_to_one, ug, up = match_passes(gm, py)
            worst = {"E2": 0.0, "E3": 0.0}
            n_cls = {"E2": 0, "E3": 0, "short": 0}
            for i, j in pairs:
                a, b = gm.loc[i], py.loc[j]
                d_start = (b.start - a.start).total_seconds()
                d_stop = (b.stop - a.stop).total_seconds()
                cls = "E2" if a.duration_s >= 120 else ("E3" if a.duration_s >= 60 else "short")
                n_cls[cls] += 1
                if cls in worst:
                    worst[cls] = max(worst[cls], abs(d_start), abs(d_stop))
                event_rows.append(dict(case_id=case, gmat_start=a.start, gmat_duration_s=a.duration_s,
                                       d_start_s=d_start, d_stop_s=d_stop, d_duration_s=b.duration_s - a.duration_s,
                                       criterion=cls))
            event_summary.append(dict(
                case=case, gmat_passes=len(gm), python_passes=len(py),
                E1=verdict(one_to_one), unmatched_gmat=len(ug), unmatched_python=len(up),
                n_E2=n_cls["E2"], max_abs_dt_E2_s=worst["E2"], E2=verdict(worst["E2"] <= TOL_E2_S),
                n_E3=n_cls["E3"], max_abs_dt_E3_s=worst["E3"], E3=verdict(worst["E3"] <= TOL_E3_S) if n_cls["E3"] else "n/a",
                n_short=n_cls["short"],
            ))

            # Metrics at full precision from the contact lists themselves (the
            # CSVs are rounded to 4-6 decimals). Round 1 compared the rounded
            # CSV values, which made identical pass counts differ by ~1e-4;
            # see the investigation section of comparison.md.
            g, p = pd.Series(P.summarise(gm)), pd.Series(P.summarise(py))
            csv = gmat_runs.loc[case]
            traceable &= all(abs(csv[m] - g[m]) < 1e-4 for m in
                             ["passes_per_day", "contact_min_per_day", "mean_pass_min", "max_pass_min", "longest_gap_h"])
            n_g, n_p = int(P.classify(gm).counted.sum()), int(P.classify(py).counted.sum())
            checks = [
                ("A1", "passes in window", n_g, n_p, "identical", n_g == n_p),
                ("A2", "n_boundary_passes", g.n_boundary_passes, p.n_boundary_passes, "identical",
                 g.n_boundary_passes == p.n_boundary_passes),
                ("A3", "contact_min_per_day", g.contact_min_per_day, p.contact_min_per_day, "<= 0.5 %",
                 abs(p.contact_min_per_day - g.contact_min_per_day) <= TOL_A3_REL * g.contact_min_per_day),
                ("A4", "mean_pass_min", g.mean_pass_min, p.mean_pass_min, "<= 0.5 %",
                 abs(p.mean_pass_min - g.mean_pass_min) <= TOL_A4_REL * g.mean_pass_min),
                ("A5", "max_pass_min", g.max_pass_min, p.max_pass_min, "<= 1 s",
                 abs(p.max_pass_min - g.max_pass_min) * 60 <= TOL_A5_S),
                ("A6", "longest_gap_h", g.longest_gap_h, p.longest_gap_h, "<= 2 s",
                 abs(p.longest_gap_h - g.longest_gap_h) * 3600 <= TOL_A6_S),
            ]
            for cid, metric, gv, pv, tol, ok in checks:
                agg_rows.append(dict(case=case, id=cid, metric=metric, gmat=gv, python=pv, diff=pv - gv,
                                     tolerance=tol, result=verdict(bool(ok))))

    traj_df, ev_df, agg_df = pd.DataFrame(traj), pd.DataFrame(event_summary), pd.DataFrame(agg_rows)
    pd.DataFrame(event_rows).to_csv(OUT / "comparison_events.csv", index=False, float_format="%.6f")
    traj_df.to_csv(OUT / "comparison_trajectory.csv", index=False, float_format="%.6f")
    agg_df.to_csv(OUT / "comparison_aggregates.csv", index=False, float_format="%.6f")

    def md(df, fmt="{:.4g}"):
        lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
        for r in df.itertuples(index=False):
            lines.append("| " + " | ".join(fmt.format(v) if isinstance(v, float) else str(v) for v in r) + " |")
        return lines

    n_inv = int((traj_df[["T1", "T2"]] == "INVESTIGATE").values.sum()
                + (ev_df[["E1", "E2", "E3"]] == "INVESTIGATE").values.sum()
                + (agg_df.result == "INVESTIGATE").sum())
    n_total = int(traj_df[["T1", "T2"]].size + (ev_df[["E1", "E2", "E3"]] != "n/a").values.sum() + len(agg_df))
    text = "\n".join([
        "# Cross-check results: Python vs GMAT", "",
        "Generated by `src/compare_crosscheck.py` with the tolerances pre-registered in "
        "`METHOD_AND_CRITERIA.md`. Neither dataset was modified.", "",
        f"**{n_total - n_inv} of {n_total} checks PASS, {n_inv} INVESTIGATE.**", "",
        "## 1. Trajectory (every 60 s over 7 d + 2 h)", "", *md(traj_df), "",
        "## 2. Pass events", "",
        "Δt = Python − GMAT. Short passes (< 60 s) are listed but not scored.", "", *md(ev_df), "",
        "## 3. Aggregate metrics", "",
        f"GMAT values are recomputed from the raw reports at full precision; they match "
        f"`results/contact_runs.csv` to its 4-decimal rounding: {traceable}.", "",
        *md(agg_df), "",
        "## Investigation (round 1 -> round 2)", "",
        "1. **Verified discrepancy cause.** Round 1 (`comparison_round1.md`, kept unchanged as run) had 85/90 "
        "PASS and 5 INVESTIGATE, all A1 (pass count). The integer counts were identical (e.g. 99 vs 99); the "
        "comparison script had rebuilt them as passes_per_day x 7 from CSVs rounded to 4 decimals (GMAT, "
        "14.1429 x 7 = 99.0003) and 6 decimals (Python), then required equality to 1e-9. Fixed by comparing "
        "integer counts and computing all metrics at full precision from the contact lists. No tolerance was "
        "changed and neither dataset was modified; the comparison was rerun (this file).",
        "2. **Observed residual difference.** Trajectories differ by up to 20 m (inertial) and 28 m "
        "(Earth-fixed), inside the pre-registered 0.1 km tolerance and larger than the a priori estimate of ~1 m.",
        "3. **Hypothesised, unverified cause.** The different pole/J2-axis treatment (GMAT: full Earth-fixed "
        "frame with polar motion; Python: constant pole, no polar motion) may contribute. Not tested.",
        "4. **No further investigation.** The residual passed the pre-registered criteria and is far below the "
        "level that affects pass timing (<= 7 ms observed vs 0.5 s tolerance) or the contact metrics. The "
        "cross-check was timeboxed to one round with one investigation pass.", "",
    ])
    (OUT / "comparison.md").write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
