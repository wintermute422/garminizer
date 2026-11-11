"""Pure analytics on activity and wellness series: numpy only, no database, no I/O.

``physio`` (TRIMP, HR zones, NP/IF/TSS, efficiency, decoupling), ``curves`` (1 Hz resampling,
mean-max curves, best efforts), ``load`` (EWMA load, PMC, ACWR, monotony/strain), ``series``
(LTTB, thinning, splits, elevation, rolling mean, trend, lagged pairs, correlation), ``geo``
(distances, map tiles, squares/clusters, start places, track simplification), ``stats`` (day
streaks, active weeks) and ``body`` (weight trend). The one exception is ``pipeline``, which
reads activities and writes the derived tables with these functions.

Every function accepts array-likes and converts them with ``np.asarray(..., dtype=float)``.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IndexArray = NDArray[np.intp]

__all__ = ["FloatArray", "IndexArray"]
