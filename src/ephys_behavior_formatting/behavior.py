"""Behavioral performance tables and psychometric / chronometric summaries.

Reads the per-trial ``performance`` struct saved in MATLAB v7.3 ``allTrials``
files (e.g. by the ``physiologySummary`` script).
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pandas as pd

#: Cue value at which the checkerboard is balanced between the two colors.
NEUTRAL_CUE = 112.5


def load_performance(path: str | Path, key: str = "allTrials") -> pd.DataFrame:
    """Per-trial performance data (one row per trial) from a v7.3 ``.mat`` file.

    Numeric fields become floats and MATLAB char arrays become strings.
    """
    with h5py.File(path, "r") as f:
        refs = f[key]["performance"][:].ravel()
        rows = []
        for ref in refs:
            trial = f[ref]
            row = {}
            for name, dset in trial.items():
                values = dset[()]
                if np.issubdtype(values.dtype, np.floating):
                    row[name] = values.ravel()[0]
                else:  # MATLAB chars are stored as uint16 codes
                    row[name] = "".join(map(chr, values.ravel()))
            rows.append(row)
    return pd.DataFrame(rows)


def signed_coherence(cue: pd.Series | np.ndarray) -> np.ndarray:
    """Cue value as signed color coherence in %, from -100 to 100 (positive = red)."""
    return (np.asarray(cue, dtype=float) - NEUTRAL_CUE) / NEUTRAL_CUE * 100


def psychometric_table(
    performance: pd.DataFrame,
    cue_column: str = "CueV",
    choice_column: str = "ChosenColor",
    red_label: str = "red",
) -> pd.DataFrame:
    """Proportion of 'red' choices at each signed coherence.

    Returns
    -------
    pd.DataFrame
        Columns ``signed_coherence``, ``p_red``, ``se`` (binomial standard error)
        and ``n``, sorted by coherence.
    """
    df = pd.DataFrame(
        {
            "signed_coherence": signed_coherence(performance[cue_column]),
            "red": (performance[choice_column] == red_label).astype(float),
        }
    )
    table = df.groupby("signed_coherence")["red"].agg(p_red="mean", n="size").reset_index()
    table["se"] = np.sqrt(table["p_red"] * (1 - table["p_red"]) / table["n"])
    return table[["signed_coherence", "p_red", "se", "n"]]


def chronometric_table(
    performance: pd.DataFrame, cue_column: str = "CueV", rt_column: str = "RT"
) -> pd.DataFrame:
    """Mean reaction time at each signed coherence.

    Returns
    -------
    pd.DataFrame
        Columns ``signed_coherence``, ``mean_rt``, ``se`` (standard error of the
        mean) and ``n``, sorted by coherence. Trials without an RT are ignored.
    """
    df = pd.DataFrame(
        {
            "signed_coherence": signed_coherence(performance[cue_column]),
            "rt": pd.to_numeric(performance[rt_column], errors="coerce"),
        }
    ).dropna()
    table = (
        df.groupby("signed_coherence")["rt"].agg(mean_rt="mean", sd="std", n="size").reset_index()
    )
    table["se"] = table["sd"] / np.sqrt(table["n"])
    return table[["signed_coherence", "mean_rt", "se", "n"]]


def plot_psychometric(table: pd.DataFrame, ax=None):
    """Plot a :func:`psychometric_table`; returns the axes."""
    import matplotlib.pyplot as plt

    ax = ax or plt.subplots(figsize=(6, 4.5))[1]
    ax.errorbar(table["signed_coherence"], table["p_red"], yerr=table["se"], fmt="ko-", capsize=4)
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8)
    ax.axvline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.set(
        xlabel="Signed color coherence (%)",
        ylabel="Proportion red choices",
        xlim=(-100, 100),
        ylim=(0, 1),
    )
    return ax


def plot_chronometric(table: pd.DataFrame, ax=None):
    """Plot a :func:`chronometric_table`; returns the axes."""
    import matplotlib.pyplot as plt

    ax = ax or plt.subplots(figsize=(6, 4.5))[1]
    ax.errorbar(table["signed_coherence"], table["mean_rt"], yerr=table["se"], fmt="ko-", capsize=4)
    ax.axvline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.set(xlabel="Signed color coherence (%)", ylabel="Reaction time (ms)", xlim=(-100, 100))
    return ax
