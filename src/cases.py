"""
Case definitions and shared constants for the NTU ground-contact study.

Everything that changes a number in the results lives here, so the
assumptions can be read (and challenged) in one place.
"""

from dataclasses import dataclass
import math

# --------------------------------------------------------------------------
# Earth model: EGM96 truncated to degree 2, order 0 (two-body + J2 only).
# Values are copied from GMAT R2026a data/gravity/earth/EGM96.cof so that
# the GMAT runs and the Python cross-check use identical constants.
# --------------------------------------------------------------------------
MU_KM3_S2 = 398600.4415           # Earth gravitational parameter [km^3/s^2]
R_EQ_KM = 6378.1363               # Earth equatorial radius [km]
C20_NORMALISED = -4.84165371736e-4
J2 = -C20_NORMALISED * math.sqrt(5.0)   # un-normalised J2 = 1.08262668e-3

# Earth ellipsoid used by GMAT for the station position and its horizon
# (HorizonReference = Ellipsoid): GMAT's default Earth, R_eq = 6378.1363 km
# and flattening 0.0033527 (1/f = 298.267). GMAT scripts cannot print this
# value; it was recovered from GMAT's own geodetic output by
# src/gmat_reference.py (see README). Note: this is NOT exactly WGS-84
# (6378.137 km, 1/f = 298.257223563); the difference moves the station by
# well under 1 m.
EARTH_FLATTENING = 0.0033527

# --------------------------------------------------------------------------
# Ground station: NTU, Singapore. APPROXIMATE coordinates, not the surveyed
# antenna position. Height 0 m above the WGS-84 ellipsoid (approximate).
# --------------------------------------------------------------------------
STATION_NAME = "NTU"
STATION_LAT_DEG = 1.35            # geodetic latitude, north positive
STATION_LON_DEG = 103.68          # east longitude
STATION_ALT_KM = 0.0

MIN_ELEVATION_BASELINE_DEG = 10.0
MIN_ELEVATION_SENSITIVITY_DEG = 5.0

# --------------------------------------------------------------------------
# Initial conditions and numerical settings. These are explicit ASSUMPTIONS,
# not physically preferred values. For a circular orbit the argument of
# perigee has no physical meaning; GMAT needs a value, so 0 deg is used by
# convention and the in-orbit position is set by the true anomaly.
# --------------------------------------------------------------------------
EPOCH_UTC_GMAT = "01 Jan 2026 00:00:00.000"   # GMAT UTCGregorian format
AOP_DEG = 0.0
TA_DEG = 0.0
ECC = 0.0                         # osculating eccentricity at epoch

# Initial node position. The model has no Sun, so contact geometry depends
# only on where the ascending node sits relative to the rotating Earth;
# epoch and RAAN are therefore one degree of freedom. The epoch is fixed and
# RAAN is sampled at 8 evenly spaced, PREDEFINED values (not tuned to any
# target). Results are reported as mean/min/max over these values.
RAAN_SAMPLES_DEG = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
# For an equatorial orbit RAAN is degenerate (the orbit plane is the same
# for every RAAN), so only one value is run.
EQUATORIAL_RAAN_DEG = [0.0]

# Analysis window: 7 days starting WINDOW_OFFSET_H after the initial epoch.
# GMAT propagates WINDOW_MARGIN_H beyond both window edges, so every pass
# that touches the window is fully resolved (needed for the midpoint rule
# in parse_contacts.py). The initial state itself is still defined at the
# epoch above.
DURATION_DAYS = 7.0
WINDOW_OFFSET_H = 1.0
WINDOW_MARGIN_H = 1.0             # must exceed the longest possible pass (~15 min)
PROPAGATION_DAYS = (WINDOW_OFFSET_H + 24.0 * DURATION_DAYS + WINDOW_MARGIN_H) / 24.0

MAX_STEP_S = 60.0                 # RK89 maximum step (30 s used for a convergence check)

ALTITUDES_KM = [400, 500, 600, 700, 800]
FIXED_INCLINATIONS_DEG = [0.0, 10.0, 20.0, 45.0, 51.6]
MASKS_DEG = [MIN_ELEVATION_BASELINE_DEG, MIN_ELEVATION_SENSITIVITY_DEG]


def sso_inclination_deg(alt_km: float) -> float:
    """Sun-synchronous inclination for a circular orbit at alt_km.

    The J2 nodal regression rate must equal the mean motion of the Sun,
    360 deg per tropical year:
        dRAAN/dt = -1.5 * n * J2 * (R/a)^2 * cos(i)       (e = 0)
    Solving for i gives the value below (always slightly above 90 deg,
    i.e. retrograde, so the node drifts eastward).
    """
    a = R_EQ_KM + alt_km
    n = math.sqrt(MU_KM3_S2 / a**3)                         # rad/s
    raan_dot_sun = 2.0 * math.pi / (365.2422 * 86400.0)     # rad/s
    cos_i = -raan_dot_sun / (1.5 * n * J2 * (R_EQ_KM / a) ** 2)
    return math.degrees(math.acos(cos_i))


@dataclass(frozen=True)
class Orbit:
    """One GMAT run. Both elevation masks are evaluated in the same run."""
    alt_km: float           # NOMINAL altitude: sets the initial osculating SMA
    inc_deg: float
    inc_label: str          # "0", "51.6", "SSO", ... (used in names and plots)
    raan_deg: float
    max_step_s: float = MAX_STEP_S

    @property
    def sma_km(self) -> float:
        # Altitude is measured above the equatorial radius (circular orbit).
        return R_EQ_KM + self.alt_km

    @property
    def name(self) -> str:
        inc = self.inc_label.replace(".", "p")
        name = f"h{self.alt_km:g}_i{inc}_raan{self.raan_deg:g}"
        if self.max_step_s != MAX_STEP_S:
            name += f"_step{self.max_step_s:g}"
        return name

    def report_name(self, mask_deg: float) -> str:
        return f"{self.name}_el{mask_deg:g}"


def all_orbits() -> list[Orbit]:
    """Full sweep: altitude x inclination x RAAN sample (both masks per run)."""
    orbits = []
    for h in ALTITUDES_KM:
        incs = [(inc, f"{inc:g}") for inc in FIXED_INCLINATIONS_DEG] + [(sso_inclination_deg(h), "SSO")]
        for inc, label in incs:
            raans = EQUATORIAL_RAAN_DEG if inc == 0.0 else RAAN_SAMPLES_DEG
            orbits += [Orbit(h, inc, label, r) for r in raans]
    return orbits


if __name__ == "__main__":
    # Quick look at the SSO inclinations and the size of the sweep.
    for h in ALTITUDES_KM:
        print(f"{h:4d} km  SSO inclination = {sso_inclination_deg(h):.3f} deg")
    print(f"{len(all_orbits())} GMAT runs, {len(all_orbits()) * len(MASKS_DEG)} contact reports")
