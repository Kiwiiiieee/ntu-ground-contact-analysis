# NTU Ground-Contact Analysis

## Engineering question
How do orbit altitude and inclination change the daily contact time between a LEO small satellite and NTU's ground station in Singapore?

![Daily contact time vs nominal altitude](figures/fig_contact_vs_altitude.png)
*Daily geometric contact time with NTU vs nominal altitude, for a {{MaskBase}}° and a {{MaskSens}}° elevation mask (GMAT, two-body + J2, {{WindowDays}}-day window). Lines: mean over the {{NRaan}} starting RAAN values of inclined orbits; bands: their min–max range. The 45°, 51.6° and SSO cases are in the bottom row on their own scale. More figures below.*

**Report:** [`report/report.pdf`](report/report.pdf), 3 pages + appendix (source: `report/report.tex`; build with `uv run src/build_report.py`, which regenerates every number first).

## Mission visualised in GMAT

GMAT GUI renders of two of the simulated cases, for illustration only; all quantitative results come from the contact reports and the figures below.

![GMAT 3D view, 500 km, 45 deg](docs/media/s1_3d_500km_45deg.png)
*500 km, 45°, starting RAAN 0°, at {{ShotOneTime}} (near the peak of a daylight pass over NTU, peak elevation about {{ShotOnePeak}}°): the last two orbits around Earth, with the satellite on the ring just south-east of NTU (OpenFrames 3D view).*

![GMAT ground track, 500 km, 51.6 deg](docs/media/s2_groundtrack_500km_51p6deg.png)
*500 km, 51.6°, starting RAAN 0°: the 24 h of ground track up to {{ShotTwoTime}} (near the peak of a pass over NTU, peak elevation about {{ShotTwoPeak}}°); only a few of the day's revolutions pass close to Singapore (GMAT ground-track plot).*

## Animations

24 h of ground track drawing itself, from GMAT's state log, with GMAT's own contact intervals (orange) and NTU's {{MaskBase}}° visibility circle, which brightens while the satellite is in contact; the counter shows passes and contact minutes so far. Illustrations of the geometry; the numbers are those of the first 24 h of one run (RAAN 0°), not the {{WindowDays}}-day RAAN means used in the results. The inclination animation is in the Figures section.

![Altitude: 45 deg, 500 vs 800 km](docs/media/anim_altitude_45deg.gif)
*Altitude, 45°: the same number of passes in these 24 h, but at 800 km the visibility circle is wider and each pass longer, so contact time is higher.*

## Setup

Requirements: [GMAT](https://software.nasa.gov/software/GSC-17177-1) R2026a (all results were produced with R2026a, build 26 Mar 2026) and Python {{VerPython}}.

**With uv (recommended).** The exact environment is locked in `uv.lock`.
```bash
uv sync
```
If `uv` fails with `invalid peer certificate: UnknownIssuer` (common on Windows when antivirus scans HTTPS traffic), tell it to use the Windows certificate store: `set UV_SYSTEM_CERTS=1` (cmd) or `$env:UV_SYSTEM_CERTS=1` (PowerShell), then retry.

If Python crashes with `OPENSSL_Uplink ... no OPENSSL_Applink` when Skyfield is imported, an antivirus product has set `SSLKEYLOGFILE` to a device path. `src/crosscheck.py` and `src/report_numbers.py` remove that variable for their own process; for other scripts, unset it in the shell first.

**With pip.**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
(`requirements.txt` is exported from `uv.lock`, so both routes give the same package versions.)

**Point the project at GMAT.** One setting, read by `src/run_gmat.py` and `src/gmat_reference.py`:
```powershell
Copy-Item local_settings.example.ini local_settings.ini
notepad local_settings.ini      # set: console = <full path to GmatConsole.exe of R2026a>
```
`local_settings.ini` is machine-specific and not committed. For one shell session, the `GMAT_CONSOLE` environment variable overrides it; for one command, `--gmat <path>` overrides both. Every run prints which GMAT it is using.

## Reproduce

```bash
uv run src/run_gmat.py --all      # {{NRuns}} GMAT runs, both masks per run -> results/raw/  (~30 min)
uv run src/build_summary.py       # -> results/contact_runs.csv, results/contact_summary.csv
uv run src/check_sweep.py         # -> results/sanity_report.md, results/raan_comparison.csv
uv run src/make_figures.py        # -> figures/ (needs src/gmat_reference.py first; run before build_report.py)
```
```bash
uv run src/gmat_reference.py      # GMAT reference states for the {{NXOrbits}} cross-check orbits (comparison only)
uv run src/crosscheck.py          # independent Python propagation and contacts -> results/crosscheck/python/
uv run src/compare_crosscheck.py  # -> results/crosscheck/comparison.md
```
```bash
uv run src/build_report.py        # numbers.tex, docs/decision_log.md and README.md from the data, then report/report.pdf
uv run src/run_gmat.py --visual   # GMAT visual scenarios -> gmat/visual/ (see "Open a visual scenario")
uv run src/make_animations.py     # GIFs -> docs/media/ (needs src/gmat_reference.py first)
```
A single orbit can be run with `--only h500_i45_raan90`; `--skip-existing` resumes an interrupted sweep.
With pip, replace `uv run` by `python` inside the activated environment.

**This README is generated** from `docs/README.template.md` by `src/report_numbers.py` (run by `build_report.py`): every result quoted here is filled in from the same data as the report, so the two cannot disagree. Edit the template, not this file.

## Run structure

| Level | Count | What it is |
|---|---|---|
| Orbital cases | {{NOrbits}} | {{NAlt}} nominal altitudes ({{HLo}}–{{HHi}} km) x 6 inclinations ({{IncList}}, SSO) |
| GMAT runs | {{NRuns}} | {{NEqRuns}} equatorial cases x 1 RAAN ({{NEqRuns}} runs) + {{NIncOrbits}} inclined/SSO cases x {{NRaan}} RAAN ({{NIncRuns}} runs) |
| Contact reports | {{NReports}} | Each run evaluates both elevation masks ({{MaskBase}}° and {{MaskSens}}°) on the same trajectory |
| Aggregated cases | {{NCases}} | {{NOrbits}} orbital cases x {{NMasks}} masks, one row each in `contact_summary.csv` |

## Traceability

Every number can be traced back to an unmodified GMAT output. Each step writes a new file and never overwrites the step before it:

1. **Raw GMAT contact report**: `results/raw/<orbit>_raan<R>_el<M>.txt`, written by GMAT's ContactLocator, never edited.
2. **Parsed per-run metrics**: `src/parse_contacts.py` applies the window and boundary rules; `src/build_summary.py` writes one row per report to `results/contact_runs.csv`.
3. **RAAN aggregation**: `src/build_summary.py` groups the runs by altitude x inclination x mask (mean/min/max over RAAN).
4. **Final summary CSV**: `results/contact_summary.csv`, checked by `src/check_sweep.py` (`results/sanity_report.md`).
5. **Numbers and claims**: `src/report_numbers.py` computes every number quoted in the report, the decision log and this README into `report/numbers.tex`, asserts the qualitative claims the report makes, and stops if one no longer holds.
6. **Figures**: `src/make_figures.py` plots the CSVs and raw reports without recomputing any reported metric, and stops if a plotted value differs from `report/numbers.tex` (ground-track, validation and elevation plots also use the GMAT state logs of `src/gmat_reference.py`).

## Reproduce it yourself

A hands-on path through the project, one step at a time. Commands are for PowerShell in the repository folder.

### a. One case in the GMAT GUI (500 km, 0°, RAAN 0°)

The template `gmat/contact_template.script` contains placeholders (`{{SMA_KM}}`, ...) and cannot be opened directly. Generate the filled-in script for one orbit first:
```powershell
uv run src/run_gmat.py --only h500_i0_raan0
```
This writes `gmat/generated/h500_i0_raan0.script` (and runs it once in batch mode).

1. Start the GUI: `GMAT.exe` in the same `bin` folder as the `GmatConsole.exe` in `local_settings.ini`.
2. **File → Open** → `gmat/generated/h500_i0_raan0.script`.
3. In the **Resources** tree, look at each object (double-click to see its fields):
   - **Spacecraft `Sat`**: the initial state. Epoch 01 Jan 2026 00:00:00 UTC, osculating Keplerian elements in `EarthMJ2000Eq`: SMA = 6878.1363 km (R<sub>eq</sub> + 500 km), ECC = 0, INC = 0°, RAAN = AOP = TA = 0°.
   - **GroundStations `NTU_A` and `NTU_B`**: the same site ({{StationLat}}° N, {{StationLon}}° E, 0 m, on the ellipsoid) with minimum elevation {{MaskBase}}° and {{MaskSens}}°. Two stations so that both masks are evaluated on one trajectory.
   - **ForceModel `FM`**: Earth gravity from `EGM96.cof` truncated to degree 2, order 0 (point mass + J2); drag and SRP off.
   - **Propagator `Prop`**: Runge-Kutta 89 using `FM`, max step {{MaxStep}} s.
   - **ContactLocators `CL_A` and `CL_B`** (under Event Locators): find the intervals when `Sat` is above the mask of `NTU_A` / `NTU_B`, and write them to the file in their `Filename` field.
   - **ReportFile `StateLog`**: geocentric radius at every step, used for the actual-altitude columns.
4. In the **Mission** tab: the mission sequence is a single `Propagate Prop(Sat) {Sat.ElapsedDays = 7.0833...}`, i.e. {{WindowDays}} days + 2 h (the {{WindowDays}}-day analysis window starts {{WindowOffset}} h after the epoch; see "Passes at the window edges").
5. **Run** (toolbar Run button or F5). The contact locators run automatically at the end of the propagation.
6. Find the contact report: the path is in `CL_A.Filename`, i.e. `results/raw/h500_i0_raan0_el10.txt` in this repository (open it in any text editor). The GUI run rewrites the same file with identical content, so `git status` should show no change to `results/raw/` afterwards; that is a quick reproducibility check.

### b. The pipeline in the terminal

```powershell
# 1. One GMAT case in batch mode -> results/raw/h500_i0_raan0_el10.txt and _el5.txt
uv run src/run_gmat.py --only h500_i0_raan0

# 2. Parse one contact report (integrity check + metrics for that run)
uv run src/parse_contacts.py results/raw/h500_i0_raan0_el10.txt

# 3. Build the per-run and RAAN-aggregated CSVs from all {{NReports}} reports
uv run src/build_summary.py

# 4. Sanity checks -> results/sanity_report.md
uv run src/check_sweep.py

# 5. Independent Python cross-check for one orbit, then the comparison
uv run src/gmat_reference.py                      # GMAT reference states (needed once, ~1 min)
uv run src/crosscheck.py --only h500_i0_raan0
uv run src/compare_crosscheck.py                  # -> results/crosscheck/comparison.md

# 6. Figures -> figures/, then numbers, README and report
uv run src/make_figures.py
uv run src/build_report.py
```
Steps 3 and 4 read every report plus the per-run state and log files in `gmat/generated/`, which are not committed. On a fresh clone, run the full sweep first (`uv run src/run_gmat.py --all`, ~30 min).

### c. Trace one number end to end

Example: daily contact time for 500 km, 0°, {{MaskBase}}° mask.

1. **Raw GMAT report** `results/raw/h500_i0_raan0_el10.txt`: {{TraceEvents}} contact intervals over the {{WindowDays}} d + 2 h propagation ("Number of events : {{TraceEvents}}" at the end).
2. **Window rules** (`src/parse_contacts.py`): {{TraceTouch}} intervals touch the {{WindowDays}}-day window (01 Jan 01:00 to 08 Jan 01:00 UTC). The first one, {{TraceFirstStart}}–{{TraceFirstStop}}, straddles the window start: only its last ~{{TraceClipS}} s count as contact time, and its midpoint ({{TraceFirstMid}}) is before the window, so it is not counted as a pass. Result: {{BaseN}} passes and {{TraceContactTotal}} min of contact in {{WindowDays}} days.
   ```powershell
   uv run src/parse_contacts.py results/raw/h500_i0_raan0_el10.txt
   ```
   prints `passes_per_day {{BasePPDThree}}` ({{BaseN}} / {{WindowDays}}), `contact_min_per_day {{BaseCMDThree}}` ({{TraceContactTotal}} / {{WindowDays}}), `n_boundary_passes {{BaseNBoundary}}`.
3. **Per-run row** in `results/contact_runs.csv`, `case_id = h500_i0_raan0_el10`: `passes_per_day {{BasePPDFour}}`, `contact_min_per_day {{BaseCMDFour}}`, `mean_alt_km {{BaseMeanAltFour}}`.
4. **Summary row** in `results/contact_summary.csv`: `nominal_altitude_km 500, orbit_label 0, elevation_mask_deg 10`, `n_raan 1`, so `mean_contact_min_per_day = min = max = {{BaseCMDFour}}` (an equatorial orbit has a single RAAN run; an inclined case would show the mean of {{NRaan}} runs here).
5. **Figures**: the 500 km, 0° cell of `figures/fig_contact_heatmap` (report Figure 1), and the blue 0° point at 500 km in the {{MaskBase}}° panel of `figures/fig_contact_vs_altitude` (report Figure 2). `make_figures.py` checks this value against `report/numbers.tex`.

## Open a visual scenario

The sweep scripts contain no plots, so the {{NRuns}} runs stay fast. For looking at the geometry, a separate visual mode writes {{NVisual}} GMAT scripts: the same orbit definitions as the sweep, plus a 3D view (OpenFrames: Earth, orbit and the NTU station), a ground track with NTU marked (the last 24 h of track are redrawn), and, for the mask comparison, an elevation-vs-time plot.

```powershell
uv run src/run_gmat.py --visual
```
This writes `gmat/visual/*_visual.script` (not committed: they contain absolute local paths) and test-runs each one in the GMAT GUI (minimized; it closes by itself). The check confirms each run completes and that its contact reports are byte-identical to the committed ones in `results/raw/`; the visuals do not change the physics.

**To look at one:** start `GMAT.exe` (same `bin` folder as in `local_settings.ini`) → **File → Open** → a script in `gmat/visual/` → **Run** (F5). The windows fill as the orbit is propagated; drag or scroll in the 3D view to rotate or zoom. Screenshots have to be taken from the GUI (GMAT scripts cannot save them).

| Script | What it shows |
|---|---|
| `h500_i0_raan0_visual` | Equatorial orbit: the ground track is a single line along the equator, just south of NTU, so the satellite comes past NTU on every revolution. |
| `h500_i45_raan0_visual` | 45° orbit: the track weaves between 45° N and 45° S and each revolution crosses the equator further west, so only a few revolutions a day pass near Singapore. |
| `h500_i51p6_raan0_visual` | ISS-like 51.6°: the same pattern as 45° with a wider latitude band; compare it with the 45° case. |
| `h600_iSSO_raan0_visual` | Sun-synchronous (retrograde, near-polar): the track covers almost all latitudes, and only a few revolutions a day pass near NTU. |
| `h800_i45_raan0_visual` | Same inclination as the 500 km, 45° case but higher: in the 3D view the orbit is visibly larger; compare its contact reports with the 500 km case for longer passes. |
| `h500_i45_raan0_masks_visual` | 5° vs 10° mask for 500 km, 45°: elevation seen from NTU against time, with flat lines at 10° and 5°. Each time the curve rises above a line is a pass for that mask; at 5° every pass starts earlier and ends later, and any peak between the two lines would be a pass for the 5° mask only. |

The elevation curve is `Sat.NTUTopo.DEC`, the declination in a topocentric frame centred on NTU (z-axis normal to the local horizon), which is the elevation angle. It was checked against the elevation formula of the Python cross-check, and it sits at the mask at the reported pass start and stop times.

**Known GMAT quirk:** in GmatConsole (R2026a), adding a `GroundTrackPlot` makes the `ContactLocator`s report no events. The same script in the GUI gives the full, identical reports. The sweep has no plots and runs in the console; the visual scenarios are GUI-only and are tested in the GUI.

## Results files

| File | Content |
|---|---|
| `results/raw/` | Unmodified GMAT contact reports, one per orbit x RAAN x mask |
| `results/contact_runs.csv` | One row per run (orbit x RAAN x mask) with all metrics |
| `results/contact_summary.csv` | One row per altitude x inclination x mask: `mean_*`, `min_*`, `max_*` over the RAAN samples. **The `mean_*` columns are the representative values.** |
| `results/raan_comparison.csv` | Per inclined case: {{NRaan}}-RAAN mean, 4-RAAN-subset mean, single-RAAN (0°) value |
| `results/sanity_report.md` | Completeness, integrity and anomaly checks |
| `results/crosscheck/` | Pre-registered method and criteria, Python results, both comparison rounds, peak elevations |
| `results/preliminary/` | Preliminary runs: single-RAAN sweep and the epoch/RAAN test that set the RAAN averaging |
| `docs/decision_log.md` | The project's engineering decisions (generated from `docs/decision_log.template.md`) |

## Assumptions and settings

All values live in [`src/cases.py`](src/cases.py).

| Item | Value | Note |
|---|---|---|
| Ground station | NTU, {{StationLat}}° N, {{StationLon}}° E, 0 m | **Approximate** coordinates and height, not the surveyed antenna position. Note: GMAT's default ellipsoid is not exactly WGS-84 (6378.137 km, 1/f = 298.257223563); the difference moves the station by well under 1 m |
| Horizon / elevation | GMAT default Earth ellipsoid (R<sub>eq</sub> {{REq}} km, f = {{Flattening}}); {{MaskBase}}° mask ({{MaskSens}}° as sensitivity case) | Both masks evaluated on the same trajectory in one GMAT run |
| Force model | Two-body + J2 (EGM96 truncated to degree 2, order 0) | No drag, no third bodies, no SRP |
| Integrator | Runge-Kutta 89, max step {{MaxStep}} s | Checked against 30 s (see below) |
| Epoch | 1 Jan 2026 00:00:00 UTC, fixed | Initial-condition assumption |
| Initial node (RAAN) | {{NRaan}} predefined values, 0°, {{RaanStep}}°, …, {{RaanLast}}°; one value (0°) for equatorial orbits | See "Initial node position" below |
| Other initial elements | e = 0, AOP = 0°, TA = 0° (osculating Keplerian) | Initial-condition assumptions, not preferred values. For a circular orbit AOP has no physical meaning; 0° is a convention |
| Altitude | Nominal altitude h sets the initial osculating SMA = R<sub>eq</sub> + h, with R<sub>eq</sub> = {{REq}} km | See "Nominal vs actual altitude" below |
| Analysis window | {{WindowDays}} days, from {{WindowOffset}} h after the epoch (01 Jan 01:00 to 08 Jan 01:00 UTC); results are daily averages | GMAT propagates {{WindowMargin}} h beyond both edges so every pass touching the window is fully resolved |
| Contact model | Geometric line of sight above the mask; no light-time or aberration | |

### Initial node position (RAAN)
A preliminary test at 500 km, 45° showed that the starting RAAN changed the {{WindowDays}}-day contact statistics by more than one {{AltStep}} km altitude step (`results/preliminary/epoch_raan/`). Every inclined case (10°, 20°, 45°, 51.6° and SSO) is therefore run at {{NRaan}} evenly spaced RAAN values, fixed in advance and not tuned to any target. The reported altitude and inclination results use the mean over these values, with the min and max kept to show the spread.

The {{NRaan}}-RAAN mean is an **empirical average over the tested initial node positions**, not a mathematically converged average over all possible RAAN values. As a check, the mean over the 4-value subset (0°, 90°, 180°, 270°) differs from the {{NRaan}}-value mean by a median of at most {{SubsetMedRel}} % per metric and by at most {{SubsetMaxRel}} % in the worst case ({{SubsetMaxCase}}). The mean is therefore reasonably settled, but not perfectly converged for every case. The spread (min to max) describes how sensitive a {{WindowDays}}-day window is to the initial phasing. Equatorial orbits have one plane whatever the RAAN, so they are run once.

The model has no Sun, so contact geometry depends only on where the node sits relative to the rotating Earth. Epoch and RAAN are then one degree of freedom (the test gave identical results for 1 Jan with RAAN 0° and 1 Jul with RAAN 180°), so the epoch is kept fixed and only RAAN is sampled.

### Passes at the window edges
- **Contact time** is clipped to the {{WindowDays}}-day window.
- **Pass count**: a pass counts if its midpoint lies inside the window.
- **Pass-duration statistics** (mean, max, min, passes under 1 min) use complete passes only; passes cut by the window edges are excluded there and counted in `n_boundary_passes`.
- Raw GMAT reports are never modified; these rules are applied in `src/parse_contacts.py`.

Short passes (under 1 min, low-elevation grazes) are kept and counted in `n_passes_under_1min`: {{NShort}} of {{NPassesTotal}} passes ({{ShortPct}} %) over all runs.

### What "contact" means here
All metrics describe **geometric contact**: the satellite is above the station's elevation mask with a clear line of sight. That is not the same as usable communications time. A real pass also needs a closing link budget (range, antenna gain, data rate), time for the antenna to acquire and track the satellite, and an antenna that can follow the pass (slew-rate limits near zenith). Very short grazing passes in particular may carry little or no data. These effects are not modelled; they are listed as limitations and future work.

### Nominal vs actual altitude
Each case is labelled by its **nominal altitude** ({{HLo}}–{{HHi}} km), which sets the initial osculating state: a circular orbit of radius R<sub>eq</sub> + h. Under J2 that state is not a circular orbit, so the altitude varies during the propagation (for 500 km, 0°: {{BaseMinAlt}}–{{BaseMaxAlt}} km, mean {{BaseMeanAlt}} km; across the sweep the mean lies up to {{MaxAltOffset}} km below the nominal value). The CSV therefore keeps the nominal altitude as the case label and adds what the trajectory actually did:

- `mean_alt_km`, `min_alt_km`, `max_alt_km` = **geocentric radius minus the equatorial radius** ({{REq}} km), sampled at every {{MaxStep}} s integrator step inside the {{WindowDays}}-day window. In the summary: mean over RAAN of the per-run mean, and the overall min/max.

This is a geometric altitude above a sphere, not the geodetic height above the ellipsoid (which GMAT's `Altitude` parameter reports and which also changes with latitude).

### Numerical check (500 km, 0°)
A rerun with a 30 s maximum step (instead of {{MaxStep}} s) gave identical pass start and stop times at the report's 1 ms resolution (durations within {{StepDurMicro}} µs).

## Figures

Produced by `uv run src/make_figures.py` (PDF for the report, PNG here). Every value that the report also quotes is checked against `report/numbers.tex`, and gap maxima against `results/contact_runs.csv`; the script stops on any mismatch. Bands and bars show the min–max over the tested starting RAAN: sensitivity to the initial node position over a {{WindowDays}}-day window, not numerical uncertainty. "Contact" is geometric visibility above the elevation mask, not usable link time.

| File | Shows | Data |
|---|---|---|
| `fig_contact_heatmap` | Contact min/day for every altitude × inclination case ({{MaskBase}}° mask, RAAN mean); one cell per simulated case, nothing interpolated | `results/contact_summary.csv` |
| `fig_contact_vs_altitude` | Contact min/day vs nominal altitude, both masks; low (0°–20°) and high (45°, 51.6°, SSO) inclinations in separate rows | `results/contact_summary.csv` |
| `fig_passes_per_day` | Passes/day per altitude ({{MaskBase}}° mask); inclinations as categories, SSO set apart | `results/contact_summary.csv` |
| `fig_interpass_gaps` | Every gap between consecutive passes at 500 km, {{MaskBase}}° mask, all RAAN runs pooled; bar = reported longest gap (gap structure below) | `results/raw/` via `parse_contacts.py` |
| `fig_ground_track_geometry` | 24 h ground track around NTU, 500 km, 51.6°, with GMAT-reported contact segments and NTU's {{MaskBase}}° visibility circle (report Figure 6; animated version below) | GMAT state log + `results/raw/` |
| `fig_gmat_python_validation` | (A) Python − GMAT position difference vs time (max per 100 min, inertial and Earth-fixed); (B) pass start/stop residuals vs peak elevation | GMAT and Python state logs, `results/crosscheck/comparison_events.csv`; peak elevations saved to `results/crosscheck/pass_peak_elevations.csv` |
| `fig_raan_sensitivity` | 500 km, 45°: contact, passes/day and longest gap for each of the {{NRaan}} starting RAAN runs | `results/contact_runs.csv` |
| `fig_visibility_geometry` | Schematic of elevation, mask and Earth central angle (not to scale); README only | — |
| `fig_elevation_masks` | Elevation at NTU vs time, 500 km 45°, with the {{MaskBase}}° and {{MaskSens}}° masks and the GMAT-reported passes; README only | GMAT state log + `results/raw/` |

![Contact time heatmap](figures/fig_contact_heatmap.png)
![Passes per day vs inclination](figures/fig_passes_per_day.png)
![Inter-pass gaps](figures/fig_interpass_gaps.png)

**Gap structure** (500 km, {{MaskBase}}° mask, all RAAN runs pooled): at 45°, 51.6° and SSO, contact comes in {{WinPerDayMin}}–{{WinPerDayMax}} windows per day of one or two passes (mean {{PassPerWinMin}}–{{PassPerWinMax}}) about one orbit ({{GapShortMed}} h) apart, separated by {{GapLongMin}}–{{GapLongMax}} h; at 20° the long gaps cluster at {{TwGapA}} and {{TwGapB}} h.

![Inclination: 500 km, 0 vs 51.6 deg](docs/media/anim_inclination_500km.gif)
*Inclination, 500 km, first 24 h: the equatorial orbit passes NTU on every revolution; at 51.6° only a few of the day's revolutions come within reach (contact in orange). Static version: Figure 6 of the [report](report/report.pdf).*

![GMAT vs Python validation](figures/fig_gmat_python_validation.png)
![RAAN sensitivity](figures/fig_raan_sensitivity.png)
![Visibility geometry](figures/fig_visibility_geometry.png)
![Elevation and masks](figures/fig_elevation_masks.png)

## Independent cross-check

An independent Python implementation of the same problem was compared with GMAT for {{NXOrbits}} orbits x {{NXMasks}} masks (500 km 0°, 45°, 51.6°; 800 km 45°; 600 km SSO; RAAN 0°), against the matching single GMAT runs. Method and tolerances were fixed in writing **before** the comparison ([`METHOD_AND_CRITERIA.md`](results/crosscheck/METHOD_AND_CRITERIA.md)); results are in [`comparison.md`](results/crosscheck/comparison.md).

- **Independent parts:** own Keplerian → Cartesian conversion, own two-body + J2 acceleration integrated with SciPy's DOP853 (rtol 1e-12), own station geometry, elevation and event detection. Skyfield is used only for the Earth-fixed rotation (IAU 2000A, IERS UT1, no polar motion) and the pole direction. No SGP4, and no GMAT state is used as input.
- **Shared on purpose:** the physical constants, case definitions and the window/boundary rules (`parse_contacts.summarise`), so both sides solve the same defined problem.
- **Result:** {{RTwoPass}} of {{RTotal}} checks PASS. Trajectories agree to ≤ {{TrajInertialM}} m (inertial) and ≤ {{TrajFixedM}} m (Earth-fixed) over {{WindowDays}} d + 2 h; all {{NMatched}} matched passes agree to ≤ {{MaxDtMs}} ms in start and stop time; pass counts, boundary passes, contact time, mean/max pass and longest gap agree within tolerance in all runs.

### Findings, separated by how well they are established

1. **Verified discrepancy cause.** The first comparison round gave {{ROnePass}}/{{RTotal}} PASS and {{ROneInv}} INVESTIGATE, all on the pass count (criterion A1). The integer counts were identical (e.g. {{BaseN}} vs {{BaseN}}), but the comparison script rebuilt them as passes per day × 7 from CSV values rounded to 4 decimals ({{BasePPDFour}} × {{WindowDays}} = {{RoundOneProduct}}) and then required exact equality. The script was fixed to compare integer counts at full precision, **without changing the pre-registered tolerance**, and the comparison was rerun: {{RTwoPass}}/{{RTotal}} PASS. The first-round output is kept unchanged in [`comparison_round1.md`](results/crosscheck/comparison_round1.md) as a record of the validation process.
2. **Observed residual difference.** Python and GMAT trajectories differ by up to {{TrajInertialM}} m in the inertial frame and {{TrajFixedM}} m in the Earth-fixed frame over {{WindowDays}} days + 2 h. This is comfortably inside the pre-registered {{TolTrajKm}} km tolerance, and larger than my a priori estimate of about 1 m. The inertial difference grows over the week for the inclined orbits and stays within {{TrajEqM}} m for the equatorial one; the Earth-fixed difference is present from the start for every orbit and varies with a period of about one day. The largest pass-timing residuals occur on low passes, but peak elevation and orbit are confounded: every equatorial pass is high (peak ≥ {{EqPeakMin}}°) and that orbit has the smallest trajectory difference, while the {{NIncHigh}} inclined passes that are as high still reach {{ResIncHighMaxMs}} ms.
3. **Hypothesised, untested causes.** Three, matching the report: the inertial growth may come from the different J2-axis treatment (GMAT applies J2 in its full Earth-fixed frame, true pole including polar motion; the Python propagator uses a constant pole direction); the daily Earth-fixed term from the frame conversion (Python applies no polar motion); and the larger timing residuals of low passes from their slow crossing of the mask (the same position difference shifts the crossing time more). **These are hypotheses, not established causes**; none was tested.
4. **Why they were not investigated further.** The residuals passed the pre-registered criteria, and they are far below the level that could affect the results: {{TrajFixedM}} m corresponds to milliseconds of pass timing (observed ≤ {{MaxDtMs}} ms against a {{TolEventS}} s tolerance), and every contact metric agreed. The cross-check was timeboxed to one comparison round with a single investigation pass, used for finding 1.

### Constants used by both implementations

| Constant | Value | Source |
|---|---|---|
| μ (Earth) | {{MU}} km³/s² | GMAT `EGM96.cof`; the same value recovered from GMAT output by vis-viva |
| R<sub>eq</sub> | {{REq}} km | GMAT `EGM96.cof` / GMAT default Earth |
| J2 | {{JTwoFull}} (from C̄20 = {{CTwentyNorm}}) | GMAT `EGM96.cof` |
| Earth flattening | {{Flattening}} | GMAT default Earth, recovered from GMAT's geodetic output (not scriptable) |
| UT1 − UTC (1 Jan 2026) | ≈ {{UTOneUTC}} s | GMAT: `eopc04_08.62-now`; Python: Skyfield built-in IERS table |
| Station, epoch, elements, masks, window | see table above | `src/cases.py` |

## Software versions
GMAT R2026a (build 26 Mar 2026), Python {{VerPython}}, NumPy {{VerNumpy}}, pandas {{VerPandas}}, Matplotlib {{VerMatplotlib}}, SciPy {{VerScipy}}, Skyfield {{VerSkyfield}}; all package versions are pinned in `uv.lock` / `requirements.txt`.

## References
- Satellite Research Centre (SaRC), NTU, [Research Capabilities](https://www.ntu.edu.sg/sarc/research-capabilities): source of the "about 14 passes per day over NTU for an equatorial orbit" figure, used only as a sanity check.
- NASA Goddard Space Flight Center, [General Mission Analysis Tool (GMAT)](https://software.nasa.gov/software/GSC-17177-1), R2026a.
- D. A. Vallado, *Fundamentals of Astrodynamics and Applications*, 4th ed., Microcosm Press, 2013.
- P. Virtanen et al., SciPy 1.0: fundamental algorithms for scientific computing in Python, *Nature Methods* 17, 261–272, 2020.
- B. Rhodes, Skyfield: high precision research-grade positions for planets and Earth satellites generator, Astrophysics Source Code Library, ascl:1907.024, 2019.

## License
Code: MIT, see [`LICENSE`](LICENSE). Report, figures and media (`report/`, `figures/`, `docs/media/`): © Kaoutar Ammara, all rights reserved; see [`LICENSE`](LICENSE).
