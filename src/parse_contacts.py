"""
Read GMAT ContactLocator reports and reduce each one to the study metrics.

Analysis window: 7 days starting WINDOW_OFFSET_H after the initial epoch.
GMAT propagates a margin beyond both edges, so every pass that touches the
window appears in the report with its full start and stop time. The raw
reports are never modified; the rules below are applied here.

Boundary rules (the same for every case)
    boundary pass         a pass that starts before or ends after the window
    contact time          clipped to the window: only contact inside the
                          7 days counts
    pass count            a pass counts if its midpoint lies inside the window
                          (so a boundary pass is counted at most once, in the
                          window that holds most of it)
    pass-duration stats   boundary passes are excluded from mean/max/min pass
                          duration and from n_passes_under_1min, and counted
                          in n_boundary_passes instead

Metric definitions
    passes_per_day        passes counted by the midpoint rule / 7 days
    contact_min_per_day   clipped contact time [min] / 7 days
    mean_pass_min         mean duration of complete passes [min]
    max_pass_min          longest complete pass [min]
    min_pass_min          shortest complete pass [min]
    longest_gap_h         longest time between the end of one pass and the
                          start of the next, for consecutive passes that
                          touch the window [h]. The time before the first
                          and after the last pass is cut off by the window,
                          so it is not treated as a gap.
    n_passes_under_1min   complete passes shorter than 60 s (low-elevation grazes)
    n_boundary_passes     passes cut by the window edges (flagged)

Example
    uv run src/parse_contacts.py results/raw/h500_i0_raan0_el10.txt
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import cases as C

# "01 Jan 2026 00:53:23.377    01 Jan 2026 01:01:01.835      458.45758830"
ROW = re.compile(
    r"^\s*(\d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2}\.\d{3})\s+"
    r"(\d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2}\.\d{3})\s+([\d.]+)\s*$"
)
EVENT_COUNT = re.compile(r"Number of events\s*:\s*(\d+)")
GMAT_TIME = "%d %b %Y %H:%M:%S.%f"

EPOCH = datetime.strptime(C.EPOCH_UTC_GMAT, GMAT_TIME)
PROP_END = EPOCH + timedelta(days=C.PROPAGATION_DAYS)
WINDOW_START = EPOCH + timedelta(hours=C.WINDOW_OFFSET_H)
WINDOW_END = WINDOW_START + timedelta(days=C.DURATION_DAYS)


def read_report(path: Path) -> pd.DataFrame:
    """Return one row per contact: start, stop (UTC) and duration_s."""
    rows = []
    for line in Path(path).read_text().splitlines():
        m = ROW.match(line)
        if m:
            rows.append((
                datetime.strptime(m.group(1), GMAT_TIME),
                datetime.strptime(m.group(2), GMAT_TIME),
                float(m.group(3)),
            ))
    return pd.DataFrame(rows, columns=["start", "stop", "duration_s"])


def reported_event_count(path: Path) -> int | None:
    """The 'Number of events' line GMAT writes at the end of the report."""
    m = EVENT_COUNT.search(Path(path).read_text())
    return int(m.group(1)) if m else None


def classify(passes: pd.DataFrame) -> pd.DataFrame:
    """Add the window bookkeeping columns used by summarise()."""
    p = passes.copy()
    p["in_window"] = (p["stop"] > WINDOW_START) & (p["start"] < WINDOW_END)
    p["boundary"] = p["in_window"] & ((p["start"] < WINDOW_START) | (p["stop"] > WINDOW_END))
    mid = p["start"] + (p["stop"] - p["start"]) / 2
    p["counted"] = p["in_window"] & (mid >= WINDOW_START) & (mid < WINDOW_END)
    clip_start = p["start"].clip(lower=WINDOW_START)
    clip_stop = p["stop"].clip(upper=WINDOW_END)
    p["clipped_s"] = ((clip_stop - clip_start).dt.total_seconds()).where(p["in_window"], 0.0)
    return p


def integrity_problems(path: Path) -> list[str]:
    """Checks that the report is complete and self-consistent.

    Returns a list of human-readable problems (empty list = report is OK).
    """
    problems = []
    passes = read_report(path)
    claimed = reported_event_count(path)
    if claimed is None:
        problems.append("no 'Number of events' line (report may be cut off)")
    elif claimed != len(passes):
        problems.append(f"GMAT reports {claimed} events but {len(passes)} rows were parsed")
    if passes.empty:
        return problems

    span_s = (passes["stop"] - passes["start"]).dt.total_seconds()
    # Report times are printed to 1 ms, so allow a 2 ms rounding error.
    if ((span_s - passes["duration_s"]).abs() > 2e-3).any():
        problems.append("stop - start does not match the reported duration")
    if (passes["duration_s"] <= 0).any():
        problems.append("non-positive pass duration")
    if not passes["start"].is_monotonic_increasing:
        problems.append("passes are not in time order")
    if (passes["start"].iloc[1:].values < passes["stop"].iloc[:-1].values).any():
        problems.append("overlapping passes")
    tol = timedelta(seconds=1)
    if passes["start"].min() < EPOCH - tol or passes["stop"].max() > PROP_END + tol:
        problems.append("pass outside the propagation span")
    # The margin must be wide enough that no pass touching the analysis
    # window is cut by the propagation start or end.
    p = classify(passes)
    cut = p["in_window"] & (((p["start"] - EPOCH).abs() < tol) | ((p["stop"] - PROP_END).abs() < tol))
    if cut.any():
        problems.append("a pass touching the window is cut by the propagation edge (margin too small)")
    return problems


def summarise(passes: pd.DataFrame) -> dict:
    """Reduce a contact table to the per-case metrics defined above."""
    days = C.DURATION_DAYS
    p = classify(passes) if not passes.empty else None
    nan = float("nan")
    if p is None or not p["in_window"].any():
        return dict(passes_per_day=0.0, contact_min_per_day=0.0, mean_pass_min=nan,
                    max_pass_min=nan, min_pass_min=nan, longest_gap_h=nan,
                    n_passes_under_1min=0, n_boundary_passes=0)

    w = p[p["in_window"]]
    complete = w[~w["boundary"]]
    gaps = w["start"].iloc[1:].values - w["stop"].iloc[:-1].values
    gaps_h = pd.to_timedelta(gaps).total_seconds() / 3600.0

    return dict(
        passes_per_day=int(p["counted"].sum()) / days,
        contact_min_per_day=w["clipped_s"].sum() / 60.0 / days,
        mean_pass_min=complete["duration_s"].mean() / 60.0,
        max_pass_min=complete["duration_s"].max() / 60.0,
        min_pass_min=complete["duration_s"].min() / 60.0,
        longest_gap_h=float(gaps_h.max()) if len(w) > 1 else nan,
        n_passes_under_1min=int((complete["duration_s"] < 60.0).sum()),
        n_boundary_passes=int(w["boundary"].sum()),
    )


def window_gaps_h(passes: pd.DataFrame) -> np.ndarray:
    """Gaps [h] between consecutive passes that touch the window (the
    definition behind longest_gap_h): next start minus previous stop."""
    p = classify(passes)
    w = p[p["in_window"]]
    return (w["start"].iloc[1:].values - w["stop"].iloc[:-1].values).astype("timedelta64[ms]").astype(float) / 3.6e6


def split_at_largest_jump(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split sorted values into two clusters at the largest ratio between
    neighbours (data-driven; no hand-set threshold)."""
    v = np.sort(np.asarray(values, float))
    i = int(np.argmax(v[1:] / v[:-1]))
    return v[: i + 1], v[i + 1:]


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        df = read_report(Path(arg))
        print(f"== {Path(arg).name}: {len(df)} contacts; integrity: {integrity_problems(Path(arg)) or 'OK'}")
        for k, v in summarise(df).items():
            print(f"   {k:20s} {v:.3f}" if isinstance(v, float) else f"   {k:20s} {v}")
