"""
Independent Python cross-check of the GMAT contact results.

Same defined problem as the GMAT runs (constants, station, initial elements,
epoch, masks, window rules), independent implementation:
  * own Keplerian -> Cartesian conversion and own two-body + J2 dynamics,
    integrated with scipy's DOP853 (not SGP4, not GMAT states)
  * Skyfield ONLY for the GCRS -> ITRS (Earth-fixed) rotation and the
    Earth's pole direction (IAU 2000A, built-in IERS UT1; no polar motion)
  * own station geometry, elevation and event detection
The pass metrics use the shared parse_contacts.summarise(), so the window and
boundary rules are identical by construction.
Method and pre-registered tolerances: results/crosscheck/METHOD_AND_CRITERIA.md

Outputs
    results/crosscheck/python/<orbit>_el<mask>.csv   Python contact list (committed)
    results/crosscheck/python/metrics.csv            Python per-run metrics (committed)
    results/crosscheck/python/<orbit>_states.npz     trajectory every 60 s (not committed)

Examples
    uv run src/crosscheck.py                          # all 5 cross-check orbits
    uv run src/crosscheck.py --only h500_i0_raan0     # one orbit (other rows in metrics.csv kept)
"""

import argparse
import os
from datetime import datetime, timedelta

# Some antivirus products set SSLKEYLOGFILE to a device path that makes
# OpenSSL crash the Python process when an SSL context is created (Skyfield
# imports urllib). No network access is needed here, so drop the variable
# for this process only.
os.environ.pop("SSLKEYLOGFILE", None)

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, minimize_scalar
from skyfield.api import load
from skyfield.framelib import itrs

import cases as C
import parse_contacts as P
from gmat_reference import CROSSCHECK
from run_gmat import ROOT

OUT = ROOT / "results" / "crosscheck" / "python"
TS = load.timescale(builtin=True)
EPOCH = datetime.strptime(C.EPOCH_UTC_GMAT, P.GMAT_TIME)
T_END_S = C.PROPAGATION_DAYS * 86400.0
SAMPLE_S = 5.0          # elevation sampling step for event search
GRAZE_WINDOW_DEG = 0.5  # refine local elevation maxima this close below the mask


# ----------------------------------------------------------------------------- frames
def skyfield_time(t_s):
    """Skyfield Time for seconds after the epoch (UTC; no leap second in the window)."""
    return TS.utc(EPOCH.year, EPOCH.month, EPOCH.day, EPOCH.hour, EPOCH.minute, EPOCH.second + np.asarray(t_s))


def gcrs_to_itrs(t_s) -> np.ndarray:
    """Rotation matrix/matrices GCRS -> ITRS; shape (3,3) or (3,3,N)."""
    return itrs.rotation_at(skyfield_time(t_s))


def pole_unit_vector() -> np.ndarray:
    """Earth's rotation pole (ITRS z-axis) in GCRS, at mid-propagation.

    With r_itrs = R r_gcrs, the ITRS z-axis expressed in GCRS is the third
    row of R. Held constant: it moves by < 1 arcsec over the 7 days.
    """
    return gcrs_to_itrs(T_END_S / 2)[2, :]


# ----------------------------------------------------------------------------- dynamics
def kepler_to_cartesian(a, e, inc, raan, aop, ta, mu=C.MU_KM3_S2):
    """Classical elements (km, rad) -> inertial position/velocity (km, km/s)."""
    p = a * (1 - e**2)
    r_pf = p / (1 + e * np.cos(ta)) * np.array([np.cos(ta), np.sin(ta), 0.0])
    v_pf = np.sqrt(mu / p) * np.array([-np.sin(ta), e + np.cos(ta), 0.0])
    cO, sO, ci, si, cw, sw = np.cos(raan), np.sin(raan), np.cos(inc), np.sin(inc), np.cos(aop), np.sin(aop)
    Q = np.array([  # perifocal -> inertial: Rz(-raan) Rx(-inc) Rz(-aop)
        [cO * cw - sO * sw * ci, -cO * sw - sO * cw * ci, sO * si],
        [sO * cw + cO * sw * ci, -sO * sw + cO * cw * ci, -cO * si],
        [sw * si, cw * si, ci],
    ])
    return Q @ r_pf, Q @ v_pf


def make_rhs(k: np.ndarray):
    """Two-body + J2 acceleration with the J2 symmetry axis along k."""
    mu, re, j2 = C.MU_KM3_S2, C.R_EQ_KM, C.J2

    def rhs(_t, y):
        r = y[:3]
        rn = np.linalg.norm(r)
        z = r @ k
        a_kep = -mu * r / rn**3
        a_j2 = -1.5 * j2 * mu * re**2 / rn**5 * ((1 - 5 * z**2 / rn**2) * r + 2 * z * k)
        return np.concatenate([y[3:], a_kep + a_j2])

    return rhs


def propagate(orbit: C.Orbit):
    r0, v0 = kepler_to_cartesian(orbit.sma_km, C.ECC, np.radians(orbit.inc_deg), np.radians(orbit.raan_deg),
                                 np.radians(C.AOP_DEG), np.radians(C.TA_DEG))
    sol = solve_ivp(make_rhs(pole_unit_vector()), (0.0, T_END_S), np.concatenate([r0, v0]),
                    method="DOP853", rtol=1e-12, atol=1e-9, dense_output=True)
    if not sol.success:
        raise RuntimeError(sol.message)
    return sol


# ----------------------------------------------------------------------------- geometry
def station_itrs() -> tuple[np.ndarray, np.ndarray]:
    """Station position and local up (ellipsoid normal) in the Earth-fixed frame."""
    lat, lon = np.radians(C.STATION_LAT_DEG), np.radians(C.STATION_LON_DEG)
    f = C.EARTH_FLATTENING
    e2 = f * (2 - f)
    n = C.R_EQ_KM / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    h = C.STATION_ALT_KM
    pos = np.array([(n + h) * np.cos(lat) * np.cos(lon), (n + h) * np.cos(lat) * np.sin(lon), (n * (1 - e2) + h) * np.sin(lat)])
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    return pos, up


STATION, UP = station_itrs()


def r_itrs(sol, t_s) -> np.ndarray:
    """Satellite Earth-fixed position, shape (3,) or (3,N)."""
    t_s = np.asarray(t_s, dtype=float)
    r = sol.sol(t_s)[:3]
    R = gcrs_to_itrs(t_s)
    return R @ r if t_s.ndim == 0 else np.einsum("ijn,jn->in", R, r)


def elevation_deg(sol, t_s) -> np.ndarray:
    # Geometric and instantaneous: satellite and station at the same time t,
    # no light-time delay or aberration (same convention as the GMAT template:
    # UseLightTimeDelay = false, UseStellarAberration = false).
    rho = r_itrs(sol, t_s) - (STATION if np.ndim(t_s) == 0 else STATION[:, None])
    s = (UP @ rho) / np.linalg.norm(rho, axis=0)
    return np.degrees(np.arcsin(s))


# ----------------------------------------------------------------------------- events
def find_passes(sol, mask_deg: float, grid: np.ndarray, el_grid: np.ndarray) -> pd.DataFrame:
    """Rise/set times where elevation crosses the mask, refined with Brent's method."""
    g = el_grid - mask_deg
    f = lambda t: float(elevation_deg(sol, t)) - mask_deg
    root = lambda a, b: brentq(f, a, b, xtol=1e-4, rtol=1e-15)
    rises, sets = [], []
    if g[0] > 0:
        rises.append(grid[0])                       # in view at propagation start
    for i in range(len(g) - 1):
        a, b = grid[i], grid[i + 1]
        if g[i] <= 0 < g[i + 1]:
            rises.append(root(a, b))
        elif g[i] > 0 >= g[i + 1]:
            sets.append(root(a, b))
    # Short grazes can rise and set between two samples: refine local maxima
    # that lie just below the mask.
    for i in range(1, len(g) - 1):
        if g[i - 1] < g[i] >= g[i + 1] and -GRAZE_WINDOW_DEG < g[i] <= 0:
            a, b = grid[i - 1], grid[i + 1]
            peak = minimize_scalar(lambda t: -f(t), bounds=(a, b), method="bounded", options={"xatol": 1e-4})
            if -peak.fun > 0:
                rises.append(root(a, peak.x))
                sets.append(root(peak.x, b))
    if g[-1] > 0:
        sets.append(grid[-1])                       # in view at propagation end
    rises, sets = np.sort(rises), np.sort(sets)
    if len(rises) != len(sets) or np.any(sets <= rises):
        raise RuntimeError("unpaired rise/set times")
    start = [EPOCH + timedelta(seconds=float(t)) for t in rises]
    stop = [EPOCH + timedelta(seconds=float(t)) for t in sets]
    return pd.DataFrame({"start": start, "stop": stop, "duration_s": sets - rises})


def main() -> None:
    ap = argparse.ArgumentParser(description="Independent Python cross-check")
    ap.add_argument("--only", nargs="+", choices=CROSSCHECK, help="run only these cross-check orbits")
    names = ap.parse_args().only or CROSSCHECK
    OUT.mkdir(parents=True, exist_ok=True)
    by_name = {o.name: o for o in C.all_orbits()}
    grid = np.arange(0.0, T_END_S, SAMPLE_S)
    grid = np.append(grid, T_END_S)
    t60 = np.arange(0.0, T_END_S + 1e-6, 60.0)
    rows = []
    for name in names:
        orbit = by_name[name]
        sol = propagate(orbit)
        el = np.concatenate([elevation_deg(sol, chunk) for chunk in np.array_split(grid, 20)])
        y60 = sol.sol(t60)
        np.savez(OUT / f"{name}_states.npz", t=t60, r_gcrs=y60[:3], v_gcrs=y60[3:], r_itrs=r_itrs(sol, t60),
                 n_rhs_evals=sol.nfev)
        for mask in C.MASKS_DEG:
            passes = find_passes(sol, mask, grid, el)
            out = passes.assign(start=passes.start.map(lambda d: d.isoformat(timespec="microseconds")),
                                stop=passes.stop.map(lambda d: d.isoformat(timespec="microseconds")))
            out.to_csv(OUT / f"{orbit.report_name(mask)}.csv", index=False, float_format="%.6f")
            rows.append({"case_id": orbit.report_name(mask), **P.summarise(passes)})
        print(f"{name}: {sol.nfev} RHS evaluations; passes (10°/5°): "
              f"{[len(pd.read_csv(OUT / f'{orbit.report_name(m)}.csv')) for m in C.MASKS_DEG]}", flush=True)
    new = pd.DataFrame(rows)
    metrics = OUT / "metrics.csv"
    if metrics.exists() and names != CROSSCHECK:        # keep the rows of orbits not rerun
        old = pd.read_csv(metrics)
        new = pd.concat([old[~old.case_id.isin(new.case_id)], new])
        order = [by_name[o].report_name(m) for o in CROSSCHECK for m in C.MASKS_DEG]
        new = new.set_index("case_id").reindex(order).dropna(how="all").reset_index()
    new.to_csv(metrics, index=False, float_format="%.6f")


if __name__ == "__main__":
    main()
