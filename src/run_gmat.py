"""
Generate one GMAT script per orbit from gmat/contact_template.script and run
it with GmatConsole in batch mode. Each run evaluates both elevation masks
on the same trajectory and writes:
    results/raw/<orbit>_el10.txt, _el5.txt   ContactLocator reports (committed)
    gmat/generated/<orbit>_state.txt          geocentric radius per step (not committed)
    gmat/generated/<orbit>.log                GMAT console output (not committed)

GMAT location: set [gmat] console in local_settings.ini (see local_settings.example.ini),
or the GMAT_CONSOLE environment variable, or pass --gmat.

Examples
    uv run src/run_gmat.py --only h500_i0_raan0
    uv run src/run_gmat.py --all            # 205 orbits (both masks per run)
    uv run src/run_gmat.py --all --skip-existing   # resume an interrupted sweep
    uv run src/run_gmat.py --visual                # visual scenarios -> gmat/visual/, test-run in the GUI
"""

import argparse
import configparser
import filecmp
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import cases as C

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "gmat" / "contact_template.script"
GENERATED = ROOT / "gmat" / "generated"
RAW = ROOT / "results" / "raw"
MASK_A, MASK_B = C.MASKS_DEG     # template stations NTU_A / NTU_B


def state_path(orbit: C.Orbit) -> Path:
    return GENERATED / f"{orbit.name}_state.txt"


def log_path(orbit: C.Orbit) -> Path:
    return GENERATED / f"{orbit.name}.log"


def report_path(orbit: C.Orbit, mask_deg: float, out_dir: Path = RAW) -> Path:
    return out_dir / f"{orbit.report_name(mask_deg)}.txt"


def render(orbit: C.Orbit, out_dir: Path) -> str:
    """Fill the template placeholders for one orbit."""
    values = {
        "EPOCH_UTC": C.EPOCH_UTC_GMAT,
        "SMA_KM": f"{orbit.sma_km:.4f}",
        "ECC": f"{C.ECC:g}",
        "INC_DEG": f"{orbit.inc_deg:.4f}",
        "RAAN_DEG": f"{orbit.raan_deg:g}",
        "AOP_DEG": f"{C.AOP_DEG:g}",
        "TA_DEG": f"{C.TA_DEG:g}",
        "STATION_LAT_DEG": f"{C.STATION_LAT_DEG:g}",
        "STATION_LON_DEG": f"{C.STATION_LON_DEG:g}",
        "STATION_ALT_KM": f"{C.STATION_ALT_KM:g}",
        "MIN_EL_A_DEG": f"{MASK_A:g}",
        "MIN_EL_B_DEG": f"{MASK_B:g}",
        "MAX_STEP_S": f"{orbit.max_step_s:g}",
        "PROPAGATION_DAYS": f"{C.PROPAGATION_DAYS:.10f}",
        # GMAT accepts forward slashes on Windows.
        "REPORT_PATH_A": report_path(orbit, MASK_A, out_dir).as_posix(),
        "REPORT_PATH_B": report_path(orbit, MASK_B, out_dir).as_posix(),
        "STATE_PATH": state_path(orbit).resolve().as_posix(),
    }
    text = TEMPLATE.read_text()
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", val)
    leftover = re.findall(r"\{\{\w+\}\}", text)
    if leftover:
        raise ValueError(f"Unfilled placeholders in template: {leftover}")
    return text


def outputs(orbit: C.Orbit, out_dir: Path) -> list[Path]:
    return [report_path(orbit, m, out_dir) for m in C.MASKS_DEG] + [state_path(orbit)]


def run_orbit(orbit: C.Orbit, gmat_exe: Path, out_dir: Path) -> None:
    """Write the script, run GMAT, and check that every output exists."""
    GENERATED.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in outputs(orbit, out_dir):
        f.unlink(missing_ok=True)       # never mistake an old output for a new one
    script = GENERATED / f"{orbit.name}.script"
    script.write_text(render(orbit, out_dir))

    # GmatConsole resolves its data files relative to its own bin/ folder.
    proc = subprocess.run(
        [str(gmat_exe), "--run", str(script.resolve()), "--exit"],
        cwd=gmat_exe.parent, capture_output=True, text=True,
    )
    log_path(orbit).write_text(proc.stdout + proc.stderr)
    ok = "Mission run completed" in proc.stdout and all(f.exists() for f in outputs(orbit, out_dir))
    if not ok:
        raise RuntimeError(f"GMAT failed for {orbit.name} (exit {proc.returncode}); see {log_path(orbit)}")


LOCAL_SETTINGS = ROOT / "local_settings.ini"    # machine-specific, not committed


def find_gmat(cli_value: str | None) -> Path:
    """Locate GmatConsole.exe. First match wins:
    1. --gmat on the command line
    2. the GMAT_CONSOLE environment variable
    3. [gmat] console = ... in local_settings.ini (copy local_settings.example.ini)
    """
    path, source = cli_value, "--gmat"
    if not path and os.environ.get("GMAT_CONSOLE"):
        path, source = os.environ["GMAT_CONSOLE"], "GMAT_CONSOLE environment variable"
    if not path and LOCAL_SETTINGS.exists():
        cfg = configparser.ConfigParser()
        cfg.read(LOCAL_SETTINGS, encoding="utf-8")
        path, source = cfg.get("gmat", "console", fallback=None), LOCAL_SETTINGS.name
    if not path:
        sys.exit("GMAT not configured: copy local_settings.example.ini to local_settings.ini and set\n"
                 "[gmat] console = <full path to GmatConsole.exe>, or set GMAT_CONSOLE, or pass --gmat.")
    exe = Path(path.strip().strip('"'))
    if not exe.is_file():
        sys.exit(f"GmatConsole not found at: {exe} (from {source})")
    print(f"Using GMAT: {exe}  (from {source})", flush=True)
    return exe


# ----------------------------------------------------------------------------- visual mode
# Representative scenarios for looking at the geometry in the GMAT GUI. The
# sweep scripts are NOT changed: visual scripts are the same rendered case
# plus display resources, and write to their own folders (not committed,
# since they contain absolute local paths).
VISUAL_DIR = ROOT / "gmat" / "visual"
VISUAL_RESULTS = ROOT / "results" / "visual"
VISUAL_CASES = [
    # (orbit name, elevation plot?, scenario suffix)
    ("h500_i0_raan0", False, ""),
    ("h500_i45_raan0", False, ""),
    ("h500_i51p6_raan0", False, ""),
    ("h600_iSSO_raan0", False, ""),
    ("h800_i45_raan0", False, ""),
    ("h500_i45_raan0", True, "_masks"),       # 5 deg vs 10 deg comparison
]
GROUND_TRACK_POINTS = int(24 * 3600 / C.MAX_STEP_S)   # redraw the last 24 h of ground track


def visual_block(orbit: C.Orbit, elevation_plot: bool) -> str:
    """Display resources inserted before BeginMissionSequence."""
    lines = [
        "%------------------------------ Visual resources (visual mode only) ------------",
        "% 3D view (OpenFrames): Earth, orbit and the NTU station, inertial axes.",
        "Create OpenFramesInterface View3D;",
        "View3D.SolverIterations = Current;",
        "View3D.UpperLeft = [ 0 0 ];",
        "View3D.Size = [ 0.5 0.5 ];",
        "View3D.Add = {Sat, NTU_A, Earth};",
        "View3D.View = {View3DCamera};",
        "View3D.CoordinateSystem = EarthMJ2000Eq;",
        "View3D.Axes = On;",
        "View3D.XYPlane = Off;",
        "View3D.EclipticPlane = Off;",
        "View3D.EnableStars = On;",
        "View3D.ShowPlot = true;",
        "",
        "Create OpenFramesView View3DCamera;",
        "View3DCamera.ViewFrame = CoordinateSystem;",
        "View3DCamera.SetDefaultLocation = On;",
        "View3DCamera.SetCurrentLocation = Off;",
        "View3DCamera.DefaultEye = [ 20000 20000 12000 ];",
        "View3DCamera.DefaultCenter = [ 0 0 0 ];",
        "View3DCamera.DefaultUp = [ 0 0 1 ];",
        "",
        f"% Ground track with the NTU station; the last {GROUND_TRACK_POINTS} points (24 h) are redrawn.",
        "Create GroundTrackPlot Track;",
        "Track.SolverIterations = Current;",
        "Track.UpperLeft = [ 0.5 0 ];",
        "Track.Size = [ 0.5 0.5 ];",
        "Track.Add = {Sat, NTU_A};",
        "Track.DataCollectFrequency = 1;",
        "Track.UpdatePlotFrequency = 50;",
        f"Track.NumPointsToRedraw = {GROUND_TRACK_POINTS};",
        "Track.CentralBody = Earth;",
        "Track.ShowPlot = true;",
        "",
    ]
    if elevation_plot:
        lines += [
            "% Elevation of Sat seen from NTU: declination in the station's topocentric",
            "% frame (z normal to the local horizon) is the elevation angle. The two",
            "% horizontal lines are the 10 deg and 5 deg masks.",
            "Create CoordinateSystem NTUTopo;",
            "NTUTopo.Origin = NTU_A;",
            "NTUTopo.Axes = Topocentric;",
            "Create Variable MaskBaseline MaskSensitivity;",
            "Create XYPlot Elevation;",
            "Elevation.SolverIterations = Current;",
            "Elevation.UpperLeft = [ 0 0.5 ];",
            "Elevation.Size = [ 1 0.5 ];",
            "Elevation.XVariable = Sat.ElapsedDays;",
            "Elevation.YVariables = {Sat.NTUTopo.DEC, MaskBaseline, MaskSensitivity};",
            "Elevation.ShowGrid = true;",
            "Elevation.ShowPlot = true;",
            "",
        ]
    return "\n".join(lines)


def render_visual(orbit: C.Orbit, elevation_plot: bool) -> str:
    """The sweep script for this orbit plus display resources; outputs redirected."""
    text = render(orbit, VISUAL_RESULTS)
    # Keep the sweep's state log untouched: write the visual run's log elsewhere.
    text = text.replace(state_path(orbit).resolve().as_posix(),
                        (VISUAL_RESULTS / f"{orbit.name}_state.txt").resolve().as_posix())
    text = text.replace("BeginMissionSequence;", visual_block(orbit, elevation_plot) + "\nBeginMissionSequence;", 1)
    if elevation_plot:
        text = text.replace("BeginMissionSequence;",
                            f"BeginMissionSequence;\nMaskBaseline = {C.MIN_ELEVATION_BASELINE_DEG:g};\n"
                            f"MaskSensitivity = {C.MIN_ELEVATION_SENSITIVITY_DEG:g};", 1)
    return text


def write_visual_scripts() -> list[Path]:
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    VISUAL_RESULTS.mkdir(parents=True, exist_ok=True)
    by_name = {o.name: o for o in C.all_orbits()}
    paths = []
    for name, elev, suffix in VISUAL_CASES:
        path = VISUAL_DIR / f"{name}{suffix}_visual.script"
        path.write_text(render_visual(by_name[name], elev))
        paths.append(path)
    return paths


def run_visual(gmat_exe: Path) -> None:
    """Write the visual scripts, run each in the GMAT GUI (minimized, exits when
    done), and check that its contact reports equal the committed sweep reports.

    GUI, not console: in GmatConsole R2026a a GroundTrackPlot stops the
    ContactLocators from seeing the trajectory (they report 0 events). The
    same script run in the GUI gives the full, identical reports.
    """
    gui = True
    exe = gmat_exe.parent / "GMAT.exe"
    by_name = {o.name: o for o in C.all_orbits()}
    for path, (name, _, _) in zip(write_visual_scripts(), VISUAL_CASES):
        log = path.with_suffix(".gui.log" if gui else ".console.log")
        cmd = ([str(exe), "--minimize", "--no_splash", "--logfile", str(log), "--run", str(path.resolve()), "--exit"]
               if gui else [str(exe), "--run", str(path.resolve()), "--exit"])
        proc = subprocess.run(cmd, cwd=exe.parent, capture_output=True, text=True, timeout=900)
        if not gui:
            log.write_text(proc.stdout + proc.stderr)
        text = log.read_text(errors="replace") if log.exists() else ""
        completed = "Mission run completed" in text
        # Optional Python/MATLAB plugins that are not installed are reported as
        # load errors at start-up; they are unrelated to the run.
        errors = [l for l in text.splitlines() if "ERROR" in l.upper()
                  and "did not open" not in l and "Error loading" not in l]
        same = all(filecmp.cmp(report_path(by_name[name], m, VISUAL_RESULTS), report_path(by_name[name], m, RAW), shallow=False)
                   for m in C.MASKS_DEG)
        print(f"{path.name}: {'GUI' if gui else 'console'} run completed={completed}, "
              f"errors={len(errors)}, contact reports identical to results/raw={same}", flush=True)
        for e in errors[:5]:
            print("   ", e)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gmat", help="path to GmatConsole.exe (default: $GMAT_CONSOLE, then local_settings.ini)")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--only", nargs="+", help="orbit names to run, e.g. h500_i0_raan0")
    group.add_argument("--all", action="store_true", help="run the full sweep")
    group.add_argument("--visual", action="store_true",
                       help="write the visual scenarios to gmat/visual/ and test-run them in the GUI (sweep untouched)")
    p.add_argument("--skip-existing", action="store_true", help="skip orbits whose outputs all exist")
    p.add_argument("--max-step", type=float, default=C.MAX_STEP_S, help="RK89 max step [s]")
    p.add_argument("--out-dir", type=Path, default=RAW, help="where contact reports are written")
    args = p.parse_args()

    gmat_exe = find_gmat(args.gmat)
    if args.visual:
        run_visual(gmat_exe)
        return
    out_dir = args.out_dir.resolve()
    pool = C.all_orbits()
    if args.all:
        selected = pool
    else:
        wanted = set(args.only)
        selected = [o for o in pool if o.name in wanted]
        missing = wanted - {o.name for o in selected}
        if missing:
            sys.exit(f"Unknown orbit(s): {sorted(missing)}")
    # A non-default max step is only used for the convergence check.
    selected = [C.Orbit(**{**o.__dict__, "max_step_s": args.max_step}) for o in selected]
    if args.skip_existing:
        selected = [o for o in selected if not all(f.exists() for f in outputs(o, out_dir))]

    t0 = time.time()
    for i, orbit in enumerate(selected, 1):
        run_orbit(orbit, gmat_exe, out_dir)
        print(f"[{i}/{len(selected)}] {orbit.name}  ({time.time() - t0:.0f} s elapsed)", flush=True)


if __name__ == "__main__":
    main()
