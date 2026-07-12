"""Operating-state segmentation - density-valley band finding.

Faithful port of the Phase-2 ``common.py`` helpers (find_density_valleys,
band_activity, assign_band_labels, describe_bands). These infer a machine's
natural operating bands from the historical distribution of its activity
indicator using kernel-density estimation and histogram-floor splitting - a
descriptive statistical technique, NOT a fitted/trained model. Output is
byte-identical to Phase-2 (see tests/test_parity_operating_state.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from scipy.stats import gaussian_kde

# Logging cadence constants (documented median/mode across all units).
NOMINAL_INTERVAL_MIN = 30
GAP_CAP_MIN = 4 * NOMINAL_INTERVAL_MIN  # 2 h - beyond this a logging gap, not a dwell
SHORT_EPISODE_MIN = 3 * NOMINAL_INTERVAL_MIN  # shorter episodes are candidate transitions


def find_density_valleys(values: np.ndarray, min_points: int = 20) -> list[float]:
    """Return x-positions of significant KDE density valleys (candidate cut
    points between operating levels). A valley qualifies if its depth is below
    75% of the shallower of its two neighbouring peaks."""
    values = values[~np.isnan(values)]
    if len(values) < min_points or np.std(values) < 1e-9:
        return []
    grid = np.linspace(values.min(), values.max(), 512)
    try:
        kde = gaussian_kde(values)
        density = kde(grid)
    except Exception:  # noqa: BLE001 - singular covariance etc. -> no valleys
        return []
    minima_idx = argrelextrema(density, np.less)[0]
    maxima_idx = argrelextrema(density, np.greater)[0]
    valleys: list[float] = []
    for idx in minima_idx:
        left_peaks = maxima_idx[maxima_idx < idx]
        right_peaks = maxima_idx[maxima_idx > idx]
        if len(left_peaks) == 0 or len(right_peaks) == 0:
            continue
        peak_h = min(density[left_peaks[-1]], density[right_peaks[0]])
        if peak_h > 0 and density[idx] < 0.75 * peak_h:
            valleys.append(float(grid[idx]))
    return valleys


def band_activity(
    series: pd.Series, low_frac_threshold: float = 0.03, max_bands: int = 4
) -> list[float]:
    """Sorted cut points partitioning the indicator into operating bands.

    Two stages: (1) split off a discrete near-floor mass (OFF/idle) if it is at
    least ``low_frac_threshold`` of readings; (2) KDE the remainder for further
    valleys (partial vs full load).
    """
    vals = series.dropna().to_numpy(dtype=float)
    if len(vals) < 30:
        return []
    vmin, vmax = vals.min(), vals.max()
    rng = vmax - vmin if vmax > vmin else 1.0
    tol = 0.01 * rng
    floor_mask = vals <= (vmin + tol)
    cutpoints: list[float] = []
    remainder = vals
    if floor_mask.mean() >= low_frac_threshold:
        rest = vals[~floor_mask]
        if len(rest) > 20:
            cutpoints.append(float((vmin + tol + rest.min()) / 2))
            remainder = rest
    cutpoints.extend(find_density_valleys(remainder))
    cutpoints = sorted({round(c, 4) for c in cutpoints})
    if len(cutpoints) > max_bands - 1:
        cutpoints = cutpoints[:1] + sorted(cutpoints[1:], key=lambda c: -abs(c))[: max_bands - 2]
        cutpoints = sorted(cutpoints)
    return cutpoints


def assign_band_labels(frame: pd.DataFrame, col: str, cutpoints: list[float]) -> pd.Series:
    """Integer band index per row via cut points (NaN where the value is null)."""
    edges = [-np.inf, *cutpoints, np.inf]
    return pd.cut(frame[col], bins=edges, labels=False, include_lowest=True)


def describe_bands(frame: pd.DataFrame, col: str, band_idx: pd.Series) -> dict[int, str]:
    """Engineering label per band index, from its position, mean-vs-max, and CV."""
    vmax = frame[col].max()
    n_bands = int(band_idx.dropna().max()) + 1 if band_idx.notna().any() else 0
    labels: dict[int, str] = {}
    for b in range(n_bands):
        vals = frame.loc[band_idx == b, col]
        if vals.empty:
            labels[b] = f"Band {b}"
            continue
        mean_v = vals.mean()
        cv = (
            (vals.std() / mean_v)
            if mean_v not in (0, np.nan) and not pd.isna(mean_v) and mean_v != 0
            else np.nan
        )
        if b == 0 and vmax > 0 and mean_v / vmax < 0.05:
            labels[b] = "Machine OFF / Idle"
        elif b == n_bands - 1:
            labels[b] = (
                "Full Load / Stable Operation"
                if (pd.notna(cv) and abs(cv) < 0.15)
                else "High Load (Variable)"
            )
        elif n_bands == 2:
            labels[b] = "Running"
        else:
            labels[b] = f"Partial Load (Band {b})"
    return labels
