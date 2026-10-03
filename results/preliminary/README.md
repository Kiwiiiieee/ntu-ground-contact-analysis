# Preliminary runs

Unmodified GMAT output from two preliminary tests that set the method of the main sweep.

- `single_raan/`: single-RAAN sweep, 30 orbits x 2 masks with one initial node (RAAN = 0 deg);
  analysis window = propagation window (7 days from the epoch), one mask per GMAT run.
  Compared with the main-sweep RAAN = 0 deg runs in `results/sanity_report.md`.
- `epoch_raan/`: initial-condition test at 500 km, 45 deg (4 RAAN x 2 epochs, 10 deg mask).
  It showed that the initial node position changes the 7-day contact statistics of inclined
  orbits by more than one altitude step, which is why the main sweep averages over
  8 RAAN values. It also showed that epoch and RAAN act as one degree of freedom in this
  Sun-free model (1 Jan / RAAN 0 deg gives the same results as 1 Jul / RAAN 180 deg).

The method of the main sweep is described in the top-level README.
