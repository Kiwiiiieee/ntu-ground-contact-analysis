# Cross-check: method and pre-registered acceptance criteria

Written **before** the Python/GMAT comparison was run. The tolerances below are not to be changed after seeing the results.

## Purpose
To test whether an independent implementation of the same defined problem reproduces the GMAT results. GMAT is not modified to improve agreement.

## Cases (5 orbits x 2 masks = 10 comparisons)
500 km 0°, 500 km 45°, 500 km 51.6°, 800 km 45°, 600 km SSO (97.788°). RAAN = 0° for all. Each is compared with the matching single GMAT run (`results/contact_runs.csv`, RAAN = 0), not with the RAAN averages.

## Independent Python method (`src/crosscheck.py`)

| Step | Python implementation | Independent of GMAT? |
|---|---|---|
| Initial state | Own Keplerian → Cartesian conversion (e = 0, AOP = 0, TA = 0, RAAN, i, a = R<sub>eq</sub> + h) with μ, in the GCRS axes (taken as equal to GMAT's EarthMJ2000Eq; the frame bias is ~20 mas, < 1 m at orbit radius) | Yes |
| Dynamics | Own two-body + J2 acceleration: **a** = −μ**r**/r³ − (3/2) J2 μ R<sub>eq</sub>² / r⁵ · [ (1 − 5 z²/r²) **r** + 2 z **k** ], with z = **r**·**k** and **k** the unit vector of Earth's rotation pole | Yes |
| J2 axis **k** | Pole of the ITRS frame expressed in GCRS (Skyfield), evaluated once at the middle of the propagation and held constant (precession/nutation move it by < 1″ in 7 days) | Frame data from Skyfield, not GMAT |
| Integrator | `scipy.integrate.solve_ivp`, DOP853, rtol = 1e-12, atol = 1e-9 (km, km/s), dense output | Yes |
| Earth-fixed frame | Skyfield `itrs.rotation_at(t)`: IAU 2000A precession-nutation, Earth rotation from built-in IERS UT1−UTC (matches GMAT's EOP file to 0.1 ms for Jan 2026). **No polar motion** (GMAT applies it; ~0.3″, ≈ 10 m at the surface) | Skyfield, not GMAT |
| Station | Geodetic 1.35° N, 103.68° E, 0 m on the ellipsoid R<sub>eq</sub> = 6378.1363 km, f = 0.0033527 | Own conversion |
| Elevation | el = asin(**ρ**·**u** / \|**ρ**\|), **ρ** = satellite − station (Earth-fixed), **u** = ellipsoid normal at the station | Own |
| Event detection | Elevation − mask sampled every 5 s; sign changes refined with Brent's method (xtol 1e-4 s); local elevation maxima within 0.5° below the mask are refined to catch short grazes the 5 s grid would miss | Own |
| Metrics | Same window and boundary rules as the GMAT analysis, applied by the shared `parse_contacts.summarise()`: the metric *definitions* are deliberately shared, the geometry and events are not | Shared definitions only |

Constants common to both (from `src/cases.py`, which holds the values from GMAT's `EGM96.cof` and GMAT's own output): μ = 398600.4415 km³/s², R<sub>eq</sub> = 6378.1363 km, J2 = 1.08262668e-3, f = 0.0033527, epoch 1 Jan 2026 00:00:00 UTC, 7-day window from 01:00 UTC, propagation 7 d + 2 h.

Known implementation differences: GMAT uses IAU-1976/1980 precession-nutation with polar motion from its EOP file and applies J2 in its full Earth-fixed frame; Python uses IAU 2000A without polar motion and a constant J2 axis. GMAT integrates with RK89 (60 s max step); Python with DOP853.

## Pre-registered acceptance criteria

Each comparison is classified **PASS** (within tolerance) or **INVESTIGATE** (outside tolerance).

### 1. Trajectory (GMAT reference states from `src/gmat_reference.py`, every 60 s)
| ID | Quantity | Tolerance | Why |
|---|---|---|---|
| T1 | max \|Δ**r**\| in the inertial frame over the whole propagation | ≤ 0.1 km | Same ODE, same constants, same initial state: expected differences are integrator error (≪ 1 m) and the J2-axis treatment (< 1″, ≲ 1 m). 0.1 km is ~13 ms of along-track motion, well below the event tolerances. |
| T2 | max \|Δ**r**\| in the Earth-fixed frame | ≤ 0.1 km | Adds the frame conversion: polar motion not applied in Python (≈ 10 m at orbit radius), nutation model difference (≲ 2 m), UT1 agreement to 0.1 ms (< 0.1 m). |

### 2. Pass events
| ID | Quantity | Tolerance | Why |
|---|---|---|---|
| E1 | Pass matching | Every GMAT pass overlaps exactly one Python pass and vice versa | Same geometry must give the same set of passes. |
| E2 | \|Δstart\|, \|Δstop\| for passes ≥ 120 s | ≤ 0.5 s | For a pass of at least 2 min, elevation crosses the mask at ≳ 0.02°/s; a 0.1 km position error at ≤ 2500 km range is ≲ 0.0023°, i.e. ≲ 0.12 s. 0.5 s leaves a 4x margin for event-root tolerances. |
| E3 | \|Δstart\|, \|Δstop\| for passes 60–120 s | ≤ 2 s | Shallower grazes cross the mask more slowly, so the same position error maps to a larger timing error. |
| — | Passes < 60 s | Listed, not scored | Timing of near-grazes is ill-conditioned; they are reported individually. |

### 3. Aggregate metrics (per orbit and mask, same window and boundary rules)
| ID | Metric | Tolerance | Why |
|---|---|---|---|
| A1 | Passes counted in the window | Identical | Integer count; any difference is a real event difference. |
| A2 | n_boundary_passes | Identical | Same reason. |
| A3 | contact_min_per_day | ≤ 0.5 % relative | Worst case: 0.5 s at both edges of every pass (up to ~30 passes in 7 days) against ≥ ~100 min of total contact. |
| A4 | mean_pass_min | ≤ 0.5 % relative | Follows from A3 with identical counts. |
| A5 | max_pass_min | ≤ 1 s absolute | Sum of two E2 edge tolerances. |
| A6 | longest_gap_h | ≤ 2 s absolute | Two pass edges, allowing for an E3 pass at one end. |

If the pass counts differ only because of an unmatched pass shorter than 60 s, the affected aggregates are still classified INVESTIGATE; the investigation then checks whether that pass explains the difference.

## Investigation rule
One investigation pass for any INVESTIGATE result, checking in order: propagation/J2, initial state, Earth-fixed transformation, Earth rotation, ellipsoid, station geometry, elevation, event tolerances, window handling. GMAT is not changed. Remaining differences are documented with their likely source and whether they affect the conclusions.
