"""
Generate every number quoted in the report and the decision log from the
committed project data, so that nothing numerical is typed by hand.

Reads   results/contact_summary.csv, results/contact_runs.csv, results/raw/,
        results/convergence/ (30 s step check), results/crosscheck/*,
        results/sanity_report.md, src/cases.py
Writes  report/numbers.tex          LaTeX macros, one per quoted number
        docs/decision_log.md        filled from docs/decision_log.template.md
        README.md                   filled from docs/README.template.md

Every qualitative statement the report makes about the data (e.g. "contact
time rises with altitude at every inclination") is ASSERTED here, and the
required baseline (500 km / 0 deg / 10 deg: 99 passes, 14.14 passes/day,
109.70 min/day) is checked. If the data change so that a statement no
longer holds, this script stops with an error instead of producing a
report that silently disagrees with the data.

Example
    uv run src/report_numbers.py
"""

import math
import re
import sys

import numpy as np
import pandas as pd

import cases as C
import compare_crosscheck as X
import parse_contacts as P
from run_gmat import RAW, ROOT

RESULTS = ROOT / "results"
values: dict[str, str] = {}          # macro name -> formatted value


def put(name: str, value, fmt: str = "{:.2f}") -> None:
    assert re.fullmatch(r"[A-Za-z]+", name), f"macro names must be letters only: {name}"
    values[name] = fmt.format(value) if not isinstance(value, str) else value


def claim(condition: bool, text: str) -> None:
    """A statement the report makes about the data; stop if it is false."""
    if not condition:
        sys.exit(f"CLAIM NO LONGER SUPPORTED BY THE DATA: {text}")


# ----------------------------------------------------------------------------- data
S = pd.read_csv(RESULTS / "contact_summary.csv")
S["orbit_label"] = S["orbit_label"].map(lambda v: f"{float(v):g}" if v != "SSO" else "SSO")
R = pd.read_csv(RESULTS / "contact_runs.csv")


def row(h, lab, mask=10.0):
    r = S[(S.nominal_altitude_km == h) & (S.orbit_label == lab) & (S.elevation_mask_deg == mask)]
    assert len(r) == 1, (h, lab, mask)
    return r.iloc[0]


# ----------------------------------------------------------------------------- baseline guard
base_report = RAW / "h500_i0_raan0_el10.txt"
base_passes = P.classify(P.read_report(base_report))
base = P.summarise(P.read_report(base_report))
n_base = int(base_passes.counted.sum())
b = row(500, "0")
claim(n_base == 99 and f"{base['passes_per_day']:.2f}" == "14.14" and f"{base['contact_min_per_day']:.2f}" == "109.70",
      "baseline 500 km / 0 deg / 10 deg = 99 passes, 14.14 passes/day, 109.70 min/day")
claim(abs(b.mean_passes_per_day - base["passes_per_day"]) < 1e-4
      and abs(b.mean_contact_min_per_day - base["contact_min_per_day"]) < 1e-4,
      "contact_summary.csv baseline row matches the raw report")
put("BaseN", n_base, "{:d}")
put("BasePPD", base["passes_per_day"])
put("BaseCMD", base["contact_min_per_day"])
put("BaseMeanAlt", b.mean_alt_km, "{:.1f}")
put("BaseMinAlt", b.min_alt_km, "{:.1f}")
put("BaseMaxAlt", b.max_alt_km, "{:.1f}")
put("SSOFiveMeanAlt", row(500, "SSO").mean_alt_km, "{:.1f}")
offset = (S.nominal_altitude_km - S.mean_alt_km).max()
put("MaxAltOffset", offset, "{:.1f}")

# ----------------------------------------------------------------------------- run structure
orbits = C.all_orbits()
put("NAlt", len(C.ALTITUDES_KM), "{:d}")
put("NOrbits", len(C.ALTITUDES_KM) * (len(C.FIXED_INCLINATIONS_DEG) + 1), "{:d}")
put("NRuns", len(orbits), "{:d}")
put("NReports", len(R), "{:d}")
put("NCases", len(S), "{:d}")
put("NRaan", len(C.RAAN_SAMPLES_DEG), "{:d}")
put("RaanStep", C.RAAN_SAMPLES_DEG[1] - C.RAAN_SAMPLES_DEG[0], "{:g}")
put("RaanLast", C.RAAN_SAMPLES_DEG[-1], "{:g}")
sso = [C.sso_inclination_deg(h) for h in C.ALTITUDES_KM]
put("SSOIncMin", min(sso))
put("SSOIncMax", max(sso))
put("IncList", ", ".join(f"{i:g}°" for i in C.FIXED_INCLINATIONS_DEG))
put("AltStep", C.ALTITUDES_KM[1] - C.ALTITUDES_KM[0], "{:d}")
put("MaxStep", C.MAX_STEP_S, "{:g}")
put("WindowDays", C.DURATION_DAYS, "{:g}")
put("WindowOffset", C.WINDOW_OFFSET_H, "{:g}")
put("WindowMargin", C.WINDOW_MARGIN_H, "{:g}")
put("Flattening", C.EARTH_FLATTENING, "{:.7f}")
put("InvFlattening", 1 / C.EARTH_FLATTENING, "{:.3f}")
put("StationLat", C.STATION_LAT_DEG, "{:g}")
put("StationLon", C.STATION_LON_DEG, "{:g}")
put("MaskBase", C.MIN_ELEVATION_BASELINE_DEG, "{:g}")
put("MaskSens", C.MIN_ELEVATION_SENSITIVITY_DEG, "{:g}")

# ----------------------------------------------------------------------------- 30 s step check
conv = RESULTS / "convergence"
dt_edges, dt_dur = 0.0, 0.0
for m in C.MASKS_DEG:
    a = P.read_report(RAW / f"h500_i0_raan0_el{m:g}.txt")
    c = P.read_report(conv / f"h500_i0_raan0_step30_el{m:g}.txt")
    claim(len(a) == len(c), "30 s step run has the same passes as the 60 s run")
    dt_edges = max(dt_edges, (a.start - c.start).abs().max().total_seconds(), (a.stop - c.stop).abs().max().total_seconds())
    dt_dur = max(dt_dur, (a.duration_s - c.duration_s).abs().max())
claim(dt_edges == 0.0, "30 s step: identical start/stop times at the report's 1 ms resolution")
claim(dt_dur < 1e-5, "30 s step: durations agree to better than 10 microseconds")
put("StepDurMicro", max(dt_dur * 1e6, 0.0), "{:.1f}")

# ----------------------------------------------------------------------------- sanity report
sanity = (RESULTS / "sanity_report.md").read_text(encoding="utf-8")
n_flags = int(re.search(r"## Anomaly flags \((\d+)\)", sanity).group(1))
put("NFlags", n_flags, "{:d}")
n_short = int(R.n_passes_under_1min.sum())
n_total = int(np.rint(R.passes_per_day * C.DURATION_DAYS).sum())
put("NShort", n_short, "{:d}")
put("NPassesTotal", f"{n_total:,d}".replace(",", "\\,"))     # thin-space thousands separator
put("ShortPct", 100 * n_short / n_total, "{:.1f}")

# ----------------------------------------------------------------------------- RAAN averaging
comp = pd.read_csv(RESULTS / "raan_comparison.csv")
metrics = ["passes_per_day", "contact_min_per_day", "mean_pass_min", "max_pass_min", "longest_gap_h"]
rel = pd.concat([(comp[f"mean4_{m}"] - comp[f"mean8_{m}"]).abs() / comp[f"mean8_{m}"].abs() for m in metrics], axis=1)
put("SubsetMedRel", 100 * rel.median().max(), "{:.1f}")
put("NInclinedCases", len(comp), "{:d}")
put("SubsetMaxRel", 100 * rel.max().max(), "{:.1f}")
r45 = row(500, "45")
put("RaanCMin", r45.min_contact_min_per_day, "{:.1f}")
put("RaanCMax", r45.max_contact_min_per_day, "{:.1f}")
put("RaanPMin", r45.min_passes_per_day)
put("RaanPMax", r45.max_passes_per_day)
# Preliminary tests: epoch/RAAN spread vs adjacent altitude step at 500 km, 45 deg
er = pd.read_csv(RESULTS / "preliminary" / "epoch_raan" / "epoch_raan_check.csv")
pre = pd.read_csv(RESULTS / "preliminary" / "single_raan" / "contact_summary.csv")
pre45 = pre[(pre.orbit_label.astype(str) == "45") & (pre.elevation_mask_deg == 10)].set_index("nominal_altitude_km")
spread = er.contact_min_per_day.max() - er.contact_min_per_day.min()
step = min(abs(pre45.loc[500].contact_min_per_day - pre45.loc[400].contact_min_per_day),
           abs(pre45.loc[600].contact_min_per_day - pre45.loc[500].contact_min_per_day))
claim(spread > step, "preliminary test: RAAN/epoch spread exceeded the change to an adjacent altitude")

# ----------------------------------------------------------------------------- validation
traj = pd.read_csv(RESULTS / "crosscheck" / "comparison_trajectory.csv")
events = pd.read_csv(RESULTS / "crosscheck" / "comparison_events.csv")
aggs = pd.read_csv(RESULTS / "crosscheck" / "comparison_aggregates.csv")
put("TrajInertialM", 1000 * traj.max_inertial_km.max(), "{:.0f}")
put("TrajFixedM", 1000 * traj.max_earth_fixed_km.max(), "{:.0f}")
put("NMatched", len(events), "{:d}")
put("MaxDtMs", 1000 * max(events.d_start_s.abs().max(), events.d_stop_s.abs().max()), "{:.1f}")
put("TolTrajKm", X.TOL_T1_KM, "{:g}")
# Structure of the validation residuals (appendix figure caption)
res_all = np.concatenate([events.d_start_s, events.d_stop_s]) * 1e3
eq = events.case_id.str.startswith("h500_i0_")
res_eq = np.concatenate([events[eq].d_start_s, events[eq].d_stop_s]) * 1e3
res_inc = np.concatenate([events[~eq].d_start_s, events[~eq].d_stop_s]) * 1e3
put("ResRmsMs", np.sqrt(np.mean(res_all**2)), "{:.1f}")
put("ResEqMaxMs", np.abs(res_eq).max(), "{:.1f}")
put("ResIncMaxMs", np.abs(res_inc).max(), "{:.1f}")
claim(np.abs(res_eq).max() < np.abs(res_inc).max(), "equatorial residuals are smaller than inclined-orbit residuals")
traj_eq = traj[traj.orbit == "h500_i0_raan0"].max_inertial_km.iloc[0]
traj_inc = traj[traj.orbit != "h500_i0_raan0"].max_inertial_km
put("TrajEqM", 1000 * traj_eq, "{:.0f}")
put("TrajIncMinM", 1000 * traj_inc.min(), "{:.0f}")
put("TrajIncMaxM", 1000 * traj_inc.max(), "{:.0f}")
claim(traj_eq < traj_inc.min(), "equatorial trajectory residual is the smallest of the five orbits")
# Peak elevation vs timing residual (validation figure, panel B). Peak
# elevations come from GMAT's state logs via make_figures.py, which saves them
# to results/crosscheck/pass_peak_elevations.csv (committed).
pk_file = RESULTS / "crosscheck" / "pass_peak_elevations.csv"
if not pk_file.exists():
    sys.exit("missing results/crosscheck/pass_peak_elevations.csv: run `uv run src/make_figures.py` first")
pk = pd.read_csv(pk_file)
pk["res_ms"] = 1e3 * np.maximum(pk.d_start_s.abs(), pk.d_stop_s.abs())
pk_eq = pk.case_id.str.startswith("h500_i0_")
eq_peak_min = pk[pk_eq].peak_el.min()
inc_high = pk[~pk_eq & (pk.peak_el >= eq_peak_min)]
put("EqPeakMin", eq_peak_min, "{:.0f}")
put("NIncHigh", len(inc_high), "{:d}")
put("ResIncHighMaxMs", inc_high.res_ms.max(), "{:.1f}")
claim(len(inc_high) > 0 and inc_high.res_ms.max() > np.abs(res_eq).max(),
      "inclined passes as high as the equatorial ones still have larger residuals (orbit and peak elevation confounded)")

put("TolEventS", X.TOL_E2_S, "{:g}")
put("TolContactPct", 100 * X.TOL_A3_REL, "{:g}")


def round_result(md):
    m = re.search(r"\*\*(\d+) of (\d+) checks PASS, (\d+) INVESTIGATE\.\*\*", (RESULTS / "crosscheck" / md).read_text(encoding="utf-8"))
    return tuple(int(g) for g in m.groups())


r1, r2 = round_result("comparison_round1.md"), round_result("comparison.md")
claim(r2[0] == r2[1] and r2[2] == 0, "round 2: all checks PASS")
claim((aggs.result == "PASS").all(), "all aggregate checks PASS")
put("ROnePass", r1[0], "{:d}"); put("RTotal", r1[1], "{:d}"); put("ROneInv", r1[2], "{:d}")
put("RTwoPass", r2[0], "{:d}")

# ----------------------------------------------------------------------------- results (10 deg mask, RAAN mean)
lo_h, hi_h = min(C.ALTITUDES_KM), max(C.ALTITUDES_KM)
put("HLo", lo_h, "{:d}"); put("HHi", hi_h, "{:d}")
for lab, key in [("0", "Zero"), ("10", "Ten"), ("20", "Tw")]:
    put(f"P{key}Lo", row(lo_h, lab).mean_passes_per_day)
    put(f"P{key}Hi", row(hi_h, lab).mean_passes_per_day)
    put(f"C{key}Lo", row(lo_h, lab).mean_contact_min_per_day, "{:.1f}")
    put(f"C{key}Hi", row(hi_h, lab).mean_contact_min_per_day, "{:.1f}")
put("GTwLo", row(lo_h, "20").mean_longest_gap_h)
put("GTwHi", row(hi_h, "20").mean_longest_gap_h)
put("MPZeroLo", row(lo_h, "0").mean_mean_pass_min)
put("MPZeroHi", row(hi_h, "0").mean_mean_pass_min)

d10 = S[S.elevation_mask_deg == 10]
low = d10[d10.orbit_label.isin(["0", "10"])]
put("LowPMin", low.mean_passes_per_day.min()); put("LowPMax", low.mean_passes_per_day.max())
put("LowGMin", low.mean_longest_gap_h.min()); put("LowGMax", low.mean_longest_gap_h.max())
# Key findings box: 'about 13-15 passes/day' for 0-10 deg (whole-number bounds of the data)
put("LowPLoInt", math.floor(low.mean_passes_per_day.min()), "{:d}")
put("LowPHiInt", math.ceil(low.mean_passes_per_day.max()), "{:d}")
claim(math.floor(low.mean_passes_per_day.min()) == 13 and math.ceil(low.mean_passes_per_day.max()) == 15,
      "0 deg and 10 deg give about 13-15 passes/day")
claim(all(abs(row(h, "0").mean_passes_per_day - row(h, "10").mean_passes_per_day) < 0.2 for h in C.ALTITUDES_KM),
      "0 deg and 10 deg give nearly the same passes per day at every altitude")
claim(all(row(h, "10").mean_contact_min_per_day < row(h, "0").mean_contact_min_per_day for h in C.ALTITUDES_KM),
      "10 deg gives less contact time than 0 deg at every altitude")
eq = [row(h, "0").mean_passes_per_day for h in C.ALTITUDES_KM]
claim(all(np.diff(eq) < 0), "equatorial passes per day fall with altitude")
tw = [row(h, "20") for h in C.ALTITUDES_KM]
claim(all(np.diff([r.mean_passes_per_day for r in tw]) > 0), "20 deg: passes per day rise with altitude")
gaps20 = [r.mean_longest_gap_h for r in tw]
# The report states only the end points and that the trend is NOT monotonic
# (it rises between 500 and 600 km); both are asserted.
claim(gaps20[-1] < gaps20[0], "20 deg: longest gap is shorter at the highest than at the lowest altitude")
claim(not all(np.diff(gaps20) < 0), "20 deg: longest gap is not monotonic in altitude (as stated)")

# Gap structure at 500 km, 10 deg mask, all RAAN runs pooled (Fig. gaps):
# clusters found by the largest jump in the sorted gaps (no hand-set threshold).
from run_gmat import report_path


def pooled_gaps(label: str, alt: int = 500):
    runs = [o for o in C.all_orbits() if o.alt_km == alt and o.inc_label == label]
    return [P.window_gaps_h(P.read_report(report_path(o, C.MIN_ELEVATION_BASELINE_DEG))) for o in runs]


short_all, long_all, ppw = [], [], []
for lab in ["45", "51.6", "SSO"]:
    per_run = pooled_gaps(lab)
    g = np.concatenate(per_run)
    short, long = P.split_at_largest_jump(g)
    short_all.append(short)
    long_all.append(long)
    # contact windows = groups of passes separated by long gaps; passes per window
    n_windows = sum(int((r > short.max()).sum()) + 1 for r in per_run)
    n_passes = sum(len(r) + 1 for r in per_run)
    ppw.append(n_passes / n_windows)
    claim(short.max() < 2.0 and long.min() > 9.0, f"{lab}: gaps split into ~1.5 h and ~10 h clusters")
short_all, long_all = np.concatenate(short_all), np.concatenate(long_all)
put("GapShortMed", np.median(short_all), "{:.1f}")
put("GapLongMin", long_all.min(), "{:.1f}")
put("GapLongMax", long_all.max(), "{:.1f}")
put("PassPerWinMin", min(ppw), "{:.1f}")
put("PassPerWinMax", max(ppw), "{:.1f}")
claim(1.0 <= min(ppw) and max(ppw) <= 2.0, "high-inclination contact windows hold one or two passes on average")
win_per_day = [(sum(int((r > 2.0).sum()) + 1 for r in pooled_gaps(lab))) / (len(pooled_gaps(lab)) * C.DURATION_DAYS)
               for lab in ["45", "51.6", "SSO"]]
put("WinPerDayMin", min(win_per_day), "{:.1f}")
put("WinPerDayMax", max(win_per_day), "{:.1f}")
claim(all(1.5 < w < 2.5 for w in win_per_day), "about two contact windows per day at 45 deg, 51.6 deg and SSO")
tw_short, tw_long = P.split_at_largest_jump(np.concatenate(pooled_gaps("20")))
tw_a, tw_b = P.split_at_largest_jump(tw_long)
put("TwGapA", np.median(tw_a), "{:.1f}")
put("TwGapB", np.median(tw_b), "{:.1f}")
claim(tw_short.max() < 2.0 and tw_a.size > 10 and tw_b.size > 10, "20 deg: long gaps form two clusters")

hi = d10[d10.orbit_label.isin(["45", "51.6", "SSO"])]
name = lambda r: f"{r.nominal_altitude_km:g}\\,km, {r.orbit_label if r.orbit_label == 'SSO' else r.orbit_label + '°'}"
put("HiPMin", hi.mean_passes_per_day.min()); put("HiPMax", hi.mean_passes_per_day.max())
put("HiCMin", hi.mean_contact_min_per_day.min(), "{:.1f}"); put("HiCMax", hi.mean_contact_min_per_day.max(), "{:.1f}")
put("HiCMinCase", name(hi.loc[hi.mean_contact_min_per_day.idxmin()]))
put("HiCMaxCase", name(hi.loc[hi.mean_contact_min_per_day.idxmax()]))
put("HiGMin", hi.mean_longest_gap_h.min()); put("HiGMax", hi.mean_longest_gap_h.max())
gap_floor = math.floor(hi.mean_longest_gap_h.min())
claim(gap_floor >= 10, "45 deg, 51.6 deg and SSO: longest gaps of at least 10 h")
put("HiGFloor", gap_floor, "{:d}")
put("HiPLoInt", math.floor(hi.mean_passes_per_day.min()), "{:d}")    # 'about 2-4 passes/day'
put("HiPHiInt", math.ceil(hi.mean_passes_per_day.max() - 0.5), "{:d}")
claim(math.floor(hi.mean_passes_per_day.min()) == 2 and round(hi.mean_passes_per_day.max()) == 4,
      "45 deg, 51.6 deg and SSO: about 2-4 passes per day")

for (lab, mask), g in S.groupby(["orbit_label", "elevation_mask_deg"]):
    g = g.sort_values("nominal_altitude_km")
    claim(all(np.diff(g.mean_contact_min_per_day) > 0), f"contact time rises with altitude ({lab}, {mask} deg mask)")
m10 = S[S.elevation_mask_deg == 10].set_index(["nominal_altitude_km", "orbit_label"])
m5 = S[S.elevation_mask_deg == 5].set_index(["nominal_altitude_km", "orbit_label"])
claim((m5.mean_contact_min_per_day >= m10.mean_contact_min_per_day).all(), "5 deg mask gives at least as much contact as 10 deg")

from gmat_reference import CROSSCHECK
put("NXOrbits", len(CROSSCHECK), "{:d}")
put("NXMasks", len(C.MASKS_DEG), "{:d}")
put("MaskAltDiff", 700 - 500, "{:d}")
# Mask vs altitude: 500 km at 5 deg vs 700 km at 10 deg, for 0 deg and 45 deg
for lab, key in [("0", "Zero"), ("45", "Ff")]:
    a, bb, c = row(500, lab, 10), row(500, lab, 5), row(700, lab, 10)
    put(f"Mask{key}A", a.mean_contact_min_per_day, "{:.1f}")
    put(f"Mask{key}B", bb.mean_contact_min_per_day, "{:.1f}")
    put(f"Mask{key}C", c.mean_contact_min_per_day, "{:.1f}")
    claim(abs(bb.mean_contact_min_per_day / c.mean_contact_min_per_day - 1) < 0.02,
          f"500 km at 5 deg is within 2 % of 700 km at 10 deg ({lab})")

# ----------------------------------------------------------------------------- equation examples (calculated)
mu, re_, j2 = C.MU_KM3_S2, C.R_EQ_KM, C.J2
a500 = C.R_EQ_KM + 500
vc = math.sqrt(mu / a500)
T = 2 * math.pi * math.sqrt(a500**3 / mu)
put("ExA", a500, "{:.1f}")
put("ExVc", vc, "{:.3f}")
put("ExT", T / 60, "{:.2f}")
put("ExEps", -mu / (2 * a500), "{:.2f}")
put("ExH", f"{math.sqrt(mu * a500):,.0f}".replace(",", "\\,"))   # thin-space thousands separator
a_kep = mu / a500**2
a_j2 = 1.5 * j2 * mu * re_**2 / a500**4          # equatorial plane (z = 0)
put("ExAKep", a_kep * 1e6, "{:.0f}")              # mm/s^2  (1 km/s^2 = 1e6 mm/s^2)
put("ExAJ", a_j2 * 1e6, "{:.2f}")
claim(1e-3 <= a_j2 / a_kep < 1e-2, "J2/Kepler ratio is of order 1e-3 (written as x 10^-3)")
put("ExAJRatio", a_j2 / a_kep * 1e3, "{:.2f}")          # used as \ExAJRatio\times10^{-3}
claim(abs(a_j2 / a_kep - 1.5 * j2 * (re_ / a500) ** 2) < 1e-12, "J2/Kepler ratio equals 1.5 J2 (R/a)^2 in the equatorial plane")
claim(1e-3 <= j2 < 1e-2, "J2 is of order 1e-3 (written as x 10^-3)")
put("JTwo", j2 * 1e3, "{:.6f}")                         # used as \JTwo\times10^{-3}
put("MU", mu, "{:.4f}")
put("REq", re_, "{:.4f}")
put("SSOIncFive", C.sso_inclination_deg(500))
put("SunRate", 360 / 365.2422, "{:.4f}")
revs = 86400 / T
put("RevsDay", revs, "{:.2f}")
# Revolutions per day relative to the rotating Earth (prograde equatorial):
# 86400/T - 86400/T_sidereal. Sanity check against the simulated pass rate.
SIDEREAL_DAY_S = 86164.0905
revs_rel = revs - 86400 / SIDEREAL_DAY_S
put("RevsRel", revs_rel, "{:.2f}")
put("EarthRevs", 86400 / SIDEREAL_DAY_S, "{:.2f}")
# Counting resolution: one pass in the window changes passes/day by 1/7 per
# run and by 1/(7*8) for an 8-RAAN mean. Expected count in the window from
# the two-body relative revolution rate: 99 or 100 depending on phase.
put("ResRun", 1 / C.DURATION_DAYS, "{:.3f}")
put("ResMean", 1 / (C.DURATION_DAYS * len(C.RAAN_SAMPLES_DEG)), "{:.3f}")
put("ResRunFrac", f"1/{C.DURATION_DAYS:g}")
put("ResMeanFrac", f"1/{C.DURATION_DAYS * len(C.RAAN_SAMPLES_DEG):g}")
window_revs = revs_rel * C.DURATION_DAYS
put("WindowRevs", window_revs, "{:.1f}")
claim(math.floor(window_revs) <= n_base <= math.ceil(window_revs),
      "observed 99 passes lies between floor and ceil of the expected relative revolutions in the window")
claim(abs(revs_rel - base["passes_per_day"]) < 1 / C.DURATION_DAYS,
      "14.14 vs 14.22 differ by less than the 1/7 counting resolution")
put("WindowFloor", math.floor(window_revs), "{:d}")
put("WindowCeil", math.ceil(window_revs), "{:d}")

# Light-time/aberration convention: both implementations are geometric and
# instantaneous. GMAT: set in the template; Python: crosscheck.py evaluates
# elevation at the same instant with no correction.
tpl_text = (ROOT / "gmat" / "contact_template.script").read_text()
claim(all(re.search(rf"CL_{x}\.UseLightTimeDelay = false;", tpl_text) and re.search(rf"CL_{x}\.UseStellarAberration = false;", tpl_text)
          for x in "AB"), "GMAT contact locators use no light-time delay and no stellar aberration")
claim(abs(revs_rel - base["passes_per_day"]) < 0.2,
      "revolutions/day relative to Earth at 500 km is close to the simulated 0 deg pass rate")


def lam_deg(alt_km, el=C.MIN_ELEVATION_BASELINE_DEG):
    e = math.radians(el)
    return math.degrees(math.acos(re_ * math.cos(e) / (re_ + alt_km)) - e)


put("LamFive", lam_deg(b.mean_alt_km), "{:.1f}")
sso600 = row(600, "SSO")
put("LamSSO", lam_deg(sso600.mean_alt_km), "{:.1f}")
put("SSOSixMeanAlt", sso600.mean_alt_km, "{:.1f}")

# ----------------------------------------------------------------------------- README-only values
# Run structure
n_eq = sum(1 for o in orbits if o.inc_deg == 0)
put("NEqRuns", n_eq, "{:d}")
put("NIncOrbits", len(C.ALTITUDES_KM) * (len(C.FIXED_INCLINATIONS_DEG) + 1) - n_eq, "{:d}")
put("NIncRuns", len(orbits) - n_eq, "{:d}")
put("NMasks", len(C.MASKS_DEG), "{:d}")
import run_gmat as RG
put("NVisual", len(RG.VISUAL_CASES), "{:d}")

# End-to-end trace of the baseline (README section "Trace one number")
rep = P.read_report(base_report)
cls = P.classify(rep)
first = cls[cls.in_window].iloc[0]
claim(bool(first.boundary) and not bool(first.counted), "the first pass touching the window is a boundary pass that is not counted")
put("TraceEvents", len(rep), "{:d}")
put("TraceTouch", int(cls.in_window.sum()), "{:d}")
put("TraceFirstStart", f"{first.start:%H:%M:%S}")
put("TraceFirstStop", f"{first.stop:%H:%M:%S}")
put("TraceClipS", first.clipped_s, "{:.0f}")
put("TraceFirstMid", f"{first.start + (first.stop - first.start) / 2:%H:%M}")
put("TraceContactTotal", cls.clipped_s.sum() / 60, "{:.2f}")
put("BasePPDThree", base["passes_per_day"], "{:.3f}")
put("BaseCMDThree", base["contact_min_per_day"], "{:.3f}")
put("BasePPDFour", b.mean_passes_per_day, "{:.4f}")
put("BaseCMDFour", b.mean_contact_min_per_day, "{:.4f}")
put("BaseMeanAltFour", b.mean_alt_km, "{:.4f}")
put("BaseNBoundary", int(cls.boundary.sum()), "{:d}")
put("RoundOneProduct", float(f"{b.mean_passes_per_day:.4f}") * C.DURATION_DAYS, "{:.4f}")   # the round-1 defect
claim(float(values["RoundOneProduct"]) != n_base, "round-1 defect: 4-decimal passes/day x 7 is not the integer count")

# Worst case of the 4-vs-8 RAAN subset comparison
worst_metric = rel.max().idxmax()
wi = rel[worst_metric].idxmax()
wc = comp.loc[wi]
put("SubsetMaxCase", f"{metrics[worst_metric].replace('_', ' ')}, {wc.nominal_altitude_km:g}\\,km, "
                     f"{wc.orbit_label}°, {wc.elevation_mask_deg:g}° mask")

# Constants table
put("JTwoFull", f"{j2 * 1e3:.8f}e-3")
put("CTwentyNorm", f"{C.C20_NORMALISED:.11e}")
import os as _os
_os.environ.pop("SSLKEYLOGFILE", None)
from skyfield.api import load as _sf_load
_ts = _sf_load.timescale(builtin=True)
_t = _ts.utc(2026, 1, 1)
# UT1 - UTC = (UT1 - TT) + (TT - UTC); TT - UTC = 37 leap seconds + 32.184 s in 2026
put("UTOneUTC", (_t.ut1 - _t.tt) * 86400 + 37.0 + 32.184, "{:+.3f}")
claim(abs(float(values["UTOneUTC"])) < 0.9, "UT1-UTC within the IERS bound of 0.9 s")

# Software versions (from the installed environment, i.e. uv.lock)
import importlib.metadata as _md
import platform as _pf
put("VerPython", _pf.python_version())
for _pkg, _key in [("scipy", "VerScipy"), ("skyfield", "VerSkyfield"), ("numpy", "VerNumpy"),
                   ("pandas", "VerPandas"), ("matplotlib", "VerMatplotlib")]:
    put(_key, _md.version(_pkg))

# GMAT screenshots (README): the capture instants are image facts (shown in the
# GMAT window); check that each lies inside a GMAT-reported pass and take that
# pass's peak elevation from results/crosscheck/pass_peak_elevations.csv.
from datetime import datetime as _dt
for key, case, stamp in [("ShotOne", "h500_i45_raan0_el10", "07 Jan 2026 06:59:15"),
                         ("ShotTwo", "h500_i51p6_raan0_el10", "07 Jan 2026 08:40:56")]:
    when = _dt.strptime(stamp, "%d %b %Y %H:%M:%S")
    passes = P.read_report(RAW / f"{case}.txt")
    inside = passes[(passes.start <= when) & (passes.stop >= when)]
    claim(len(inside) == 1, f"screenshot instant {stamp} lies inside a GMAT pass of {case}")
    rows = pk[(pk.case_id == case) & (pd.to_datetime(pk.gmat_start) == inside.start.iloc[0])]
    claim(len(rows) == 1, f"peak elevation available for the screenshot pass of {case}")
    put(f"{key}Time", stamp + " UTC")
    put(f"{key}Peak", rows.peak_el.iloc[0], "{:.0f}")


# ----------------------------------------------------------------------------- write outputs
tex = ["% Generated by src/report_numbers.py from the project data. Do not edit by hand."]
tex += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(values.items())]
(ROOT / "report" / "numbers.tex").write_text("\n".join(tex) + "\n", encoding="utf-8")


def fill_template(template, target):
    """Fill {{Name}} placeholders from `values`; stop on any unknown name.
    Placeholders with underscores (e.g. the GMAT template's {{SMA_KM}}, quoted
    in the README) are not value names and are left as they are."""
    tpl = (ROOT / template).read_text(encoding="utf-8")
    pat = r"\{\{([A-Za-z]+)\}\}"
    missing = sorted(set(re.findall(pat, tpl)) - set(values))
    if missing:
        sys.exit(f"{template} uses unknown values: {missing}")
    out = re.sub(pat, lambda m: values[m.group(1)].replace("\\,", " "), tpl)
    out = f"<!-- Generated from {template} by src/report_numbers.py; edit the template, not this file. -->\n" + out
    (ROOT / target).write_text(out, encoding="utf-8")


fill_template("docs/decision_log.template.md", "docs/decision_log.md")
fill_template("docs/README.template.md", "README.md")

print(f"report/numbers.tex: {len(values)} values; docs/decision_log.md and README.md written; all claims hold.")
print(f"baseline: {values['BaseN']} passes, {values['BasePPD']} passes/day, {values['BaseCMD']} min/day")
