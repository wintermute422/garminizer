"""Pure analytics on activity and wellness series: numpy only, no database, no I/O.

``physio`` (TRIMP, HR zones, NP/IF/TSS, efficiency, decoupling), ``curves`` (1 Hz resampling,
mean-max curves, best efforts), ``load`` (EWMA load, PMC, ACWR, monotony/strain), ``series``
(LTTB, splits, elevation, rolling mean, trend, correlation), ``geo`` (distances, map tiles,
squares/clusters, track simplification) and ``stats`` (day streaks).

Every function accepts array-likes and converts them with ``np.asarray(..., dtype=float)``.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IndexArray = NDArray[np.intp]

__all__ = ["FloatArray", "IndexArray"]
