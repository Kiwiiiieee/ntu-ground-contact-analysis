"""
GMAT reference trajectories for the Python cross-check.

Runs the unchanged sweep template for the cross-check orbits, adding one
ReportFile with the full state at every integrator step in both the
inertial (EarthMJ2000Eq) and Earth-fixed frames, plus GMAT's geodetic
latitude/height and osculating SMA. These states are used ONLY to compare
against the Python propagation and to recover the Earth constants GMAT
uses internally (GMAT scripts cannot print Earth.Mu or Earth.Flattening).
They are never used as input to the Python propagator.

Outputs (not committed, ~3 MB each; rebuild with this script):
    results/crosscheck/gmat_reference/<orbit>_states.txt
    results/crosscheck/gmat_reference/<orbit>_el10.txt, _el5.txt  (contact reports;
        must be identical to results/raw/, which this script verifies)

Example
    uv run src/gmat_reference.py
"""

import filecmp
import subprocess
import sys

import cases as C
import run_gmat as G

OUT = G.ROOT / "results" / "crosscheck" / "gmat_reference"

# The five cross-check orbits (RAAN = 0 deg for the inclined ones).
CROSSCHECK = ["h500_i0_raan0", "h500_i45_raan0", "h500_i51p6_raan0", "h800_i45_raan0", "h600_iSSO_raan0"]

STATE_FIELDS = [
    "Sat.ElapsedSecs",
    "Sat.EarthMJ2000Eq.X", "Sat.EarthMJ2000Eq.Y", "Sat.EarthMJ2000Eq.Z",
    "Sat.EarthMJ2000Eq.VX", "Sat.EarthMJ2000Eq.VY", "Sat.EarthMJ2000Eq.VZ",
    "Sat.EarthFixed.X", "Sat.EarthFixed.Y", "Sat.EarthFixed.Z",
    "Sat.Earth.Latitude", "Sat.Earth.Longitude", "Sat.Earth.Altitude", "Sat.Earth.SMA",
]


def orbits() -> list[C.Orbit]:
    by_name = {o.name: o for o in C.all_orbits()}
    return [by_name[n] for n in CROSSCHECK]


def main() -> None:
    gmat_exe = G.find_gmat(None)
    OUT.mkdir(parents=True, exist_ok=True)
    for orbit in orbits():
        states = OUT / f"{orbit.name}_states.txt"
        extra = "\n".join([
            "Create ReportFile RefStates;",
            f"RefStates.Filename = '{states.as_posix()}';",
            "RefStates.Add = {" + ", ".join(STATE_FIELDS) + "};",
            "RefStates.WriteHeaders = true;",
            "RefStates.Precision = 16;",
            "", "BeginMissionSequence;",
        ])
        text = G.render(orbit, OUT).replace("BeginMissionSequence;", extra, 1)
        script = OUT / f"{orbit.name}_reference.script"
        script.write_text(text)
        proc = subprocess.run([str(gmat_exe), "--run", str(script), "--exit"],
                              cwd=gmat_exe.parent, capture_output=True, text=True)
        if "Mission run completed" not in proc.stdout or not states.exists():
            sys.exit(f"GMAT reference run failed for {orbit.name}:\n{proc.stdout[-2000:]}")
        # The extra ReportFile must not change the contact results.
        same = all(filecmp.cmp(G.report_path(orbit, m, OUT), G.report_path(orbit, m, G.RAW), shallow=False)
                   for m in C.MASKS_DEG)
        print(f"{orbit.name}: states written; contact reports identical to results/raw: {same}")


if __name__ == "__main__":
    main()
