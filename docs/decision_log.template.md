# Decision log

Engineering decisions taken in this project, in the order they were made. Each entry records what was observed, the evidence, what was tested and what was decided. Numbers are filled in from the project data by `src/report_numbers.py`; the git history shows where each decision was implemented.

Labels: **Established** = shown directly by a simulation or check in this repository; **Hypothesis** = a possible explanation that was not tested.

---

## D1. Define "circular" by osculating elements and report the actual altitude
- **Observation:** in the first single case (500 km, 0°), pass durations varied smoothly over the day although the orbit was specified as circular.
- **Evidence:** in an early diagnostic run (not kept in the repository) duration correlated almost perfectly with altitude at mid-pass; in the committed sweep the propagated geocentric radius minus R<sub>eq</sub> ranged {{BaseMinAlt}}–{{BaseMaxAlt}} km (mean {{BaseMeanAlt}} km).
- **Hypothesis:** e = 0 is an osculating value at the epoch; under J2 the circular-velocity start point becomes the highest point of a slightly eccentric orbit.
- **Test:** compared osculating Keplerian input with GMAT's Brouwer mean-element input at 0° and 51.6° (diagnostic runs, not kept in the repository).
- **Result:** Brouwer input made the 0° orbit nearly circular but at a lower mean radius, and the offset depended on inclination, so it did not remove the issue by itself.
- **Decision:** keep the osculating input (transparent and standard); keep the nominal altitude as the case label and report the actual mean/min/max altitude for every run. Largest nominal-minus-mean offset in the sweep: {{MaxAltOffset}} km.
- **Confidence:** high (Established).
- **Limitation:** "nominal altitude" is a label for the initial state, not the mean altitude.

## D2. Average inclined orbits over 8 initial RAAN values
- **Observation:** in a preliminary single-RAAN sweep, the 45° altitude trend was irregular.
- **Evidence:** at 500 km, 45°, a test of 4 RAAN values × 2 epochs gave a spread in contact time larger than the change to the adjacent 100 km altitude step (`results/preliminary/epoch_raan/`).
- **Hypothesis:** over 7 days an inclined ground track drifts little, so the result depends on where the first revolutions fall relative to Singapore.
- **Test:** reran every inclined and SSO orbit at {{NRaan}} predefined RAAN values (0°–{{RaanLast}}° in {{RaanStep}}° steps, not tuned to any target), {{NRuns}} GMAT runs in total.
- **Result:** the 4-value subset mean differs from the 8-value mean by a median of {{SubsetMedRel}} % or less and at most {{SubsetMaxRel}} % across metrics. The tested spread remains real, e.g. {{RaanCMin}}–{{RaanCMax}} min/day at 500 km, 45°, 10° mask.
- **Decision:** report the RAAN mean as the representative value and keep min/max; keep the preliminary single-RAAN sweep in `results/preliminary/` as evidence.
- **Confidence:** medium-high. The 8-RAAN mean is an empirical average over the tested initial node positions, not a converged average over all phasings.
- **Limitation:** week-to-week variability for a real mission is described only by the tested spread.

## D3. Fix the epoch and sample only RAAN
- **Observation:** in the epoch/RAAN test, 1 Jan with RAAN 0° gave the same results as 1 Jul with RAAN 180° (and vice versa).
- **Evidence:** `results/preliminary/epoch_raan/epoch_raan_check.csv`.
- **Hypothesis:** with no Sun in the model, only the node's position relative to the rotating Earth matters; half a year shifts that by about 180°.
- **Decision:** keep the epoch fixed and sample RAAN only.
- **Confidence:** high for this model (Established by the test).
- **Limitation:** would not hold once lighting (e.g. SSO local time) matters.

## D4. Resolve every pass that touches the analysis window
- **Observation:** the preliminary sweep had a pass cut by the window edge, with an incomplete duration.
- **Decision:** propagate {{WindowMargin}} h beyond both edges of a {{WindowDays}}-day window starting {{WindowOffset}} h after the epoch; clip contact time to the window; count a pass if its midpoint lies inside; exclude edge passes from pass-duration statistics and count them separately. Raw GMAT reports are never modified.
- **Test:** the rules were tested on synthetic passes (one per edge case); the preliminary single-RAAN sweep and the main-sweep RAAN = 0° runs are compared in `results/sanity_report.md`.
- **Confidence:** high (Established).
- **Limitation:** the analysis window starts {{WindowOffset}} h after the epoch at which the initial state is defined.

## D5. Keep short grazing passes
- **Observation:** {{NShort}} passes shorter than 1 min ({{ShortPct}} % of {{NPassesTotal}}).
- **Decision:** keep them (they are geometrically valid) and count them in `n_passes_under_1min`.
- **Limitation:** their usefulness for communications needs a link analysis (not done).

## D6. Keep a 60 s maximum step
- **Test:** 500 km, 0°, RAAN 0° rerun with a 30 s maximum step (`results/convergence/`).
- **Result:** identical pass start/stop times at the report's 1 ms resolution; durations within {{StepDurMicro}} µs.
- **Decision:** keep 60 s for the sweep. **Confidence:** high for this case; checked on one orbit only.

## D7. Pre-register the cross-check tolerances
- **Decision:** before comparing, fix the independent Python method and tolerances in writing (trajectory ≤ {{TolTrajKm}} km, pass times ≤ {{TolEventS}} s for passes ≥ 2 min, identical counts, contact time ≤ {{TolContactPct}} %) in `results/crosscheck/METHOD_AND_CRITERIA.md`.
- **Result, round 1:** {{ROnePass}}/{{RTotal}} PASS, {{ROneInv}} INVESTIGATE, all on pass counts.
- **Investigation (verified cause):** the counts were identical integers; the comparison script rebuilt them from CSV values rounded to 4 decimals and required exact equality.
- **Decision:** fix the comparison script, change no tolerance, keep the round-1 output (`comparison_round1.md`). Round 2: {{RTwoPass}}/{{RTotal}} PASS.
- **Confidence:** high (Established).

## D8. Do not investigate the trajectory residual further
- **Observation:** Python and GMAT differ by up to {{TrajInertialM}} m (inertial) and {{TrajFixedM}} m (Earth-fixed), inside the {{TolTrajKm}} km tolerance but larger than the a priori estimate.
- **Hypothesis (untested):** the different treatment of Earth's pole/J2 axis may contribute.
- **Decision:** no further investigation: the residual passed the pre-registered criteria and all {{NMatched}} matched passes agree within {{MaxDtMs}} ms.
- **Confidence in the decision:** high; confidence in the hypothesis: low (untested).

## D9. Use GMAT's default Earth ellipsoid and state it exactly
- **Observation:** GMAT scripts cannot print Earth's flattening.
- **Test:** recovered it from GMAT's own geodetic output: f = {{Flattening}} (1/f = {{InvFlattening}}), GMAT's default, not exactly WGS-84.
- **Decision:** keep GMAT's value, use the same value in the Python cross-check, and state it in the README instead of "WGS-84".
- **Limitation:** the difference from WGS-84 moves the station by well under 1 m (not quantified further).

## D10. Generate every reported number from the data
- **Decision:** the report and this log take their numbers from `src/report_numbers.py`, which also asserts each qualitative claim the report makes and the baseline (500 km, 0°, 10° mask: {{BaseN}} passes in the window, {{BasePPD}} passes/day, {{BaseCMD}} min/day). If the data change so that a claim fails, the build stops.

## D11. Keep the visual scenarios separate from the sweep and test them in the GUI
- **Observation:** with a `GroundTrackPlot` added, the visual scripts run in GmatConsole reported 0 contact events.
- **Test:** bisection on the 500 km, 0° case: the OpenFrames 3D view alone gave the normal report; any `GroundTrackPlot` (with or without the station, with default settings) gave 0 events in the console; the same script run in the GUI gave the full report.
- **Result:** a console-only behaviour of GMAT R2026a (cause inside GMAT not investigated).
- **Decision:** the sweep scripts stay plot-free and run in the console; `run_gmat.py --visual` adds the display resources to copies of the same cases and test-runs them in the GUI, checking that every contact report is byte-identical to `results/raw/`. The elevation plot uses the declination in a topocentric frame at NTU, checked against the cross-check's elevation formula.
- **Confidence:** high (Established by the bisection and the byte-identical GUI reports).
- **Limitation:** what the plots look like can only be checked by eye; GMAT scripts cannot save screenshots.
