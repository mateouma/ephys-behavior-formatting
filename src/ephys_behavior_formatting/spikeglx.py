"""Helpers for reading SpikeGLX ``.meta`` and ``.bin`` files.

Adapted from the SpikeGLX ``readSGLX.py`` demo tools (Bill Karsh, HHMI Janelia).
Function names are snake_case versions of the originals; only the helpers the
pipeline needs (plus their dependencies) are kept.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def read_meta(bin_path: str | Path) -> dict[str, str]:
    """Parse the ``.meta`` file that sits next to a SpikeGLX ``.bin`` file.

    Parameters
    ----------
    bin_path : str or Path
        Path to the ``.bin`` file (the ``.meta`` file is found by swapping the suffix).

    Returns
    -------
    dict
        Metadata key -> string value. Leading ``~`` characters on keys are stripped,
        matching the MATLAB ``ReadMeta``.
    """
    meta_path = Path(bin_path).with_suffix(".meta")
    if not meta_path.exists():
        raise FileNotFoundError(f"No .meta file found for {bin_path}")

    meta = {}
    for line in meta_path.read_text().splitlines():
        key, _, value = line.partition("=")
        meta[key.lstrip("~")] = value
    return meta


def sample_rate(meta: dict[str, str]) -> float:
    """Nominal sample rate (Hz) recorded in the metadata."""
    if meta["typeThis"] == "imec":
        return float(meta["imSampRate"])
    return float(meta["niSampRate"])


def int_to_volts(meta: dict[str, str]) -> float:
    """Factor converting raw int16 samples to volts, before dividing by channel gain."""
    if meta["typeThis"] == "imec":
        max_int = int(meta.get("imMaxInt", 512))
        return float(meta["imAiRangeMax"]) / max_int
    return float(meta["niAiRangeMax"]) / 32768


def channel_counts_ni(meta: dict[str, str]) -> tuple[int, int, int, int]:
    """Number of (MN, MA, XA, DW) channels saved in a NI-DAQ file."""
    mn, ma, xa, dw = (int(x) for x in meta["snsMnMaXaDw"].split(","))
    return mn, ma, xa, dw


def channel_counts_im(meta: dict[str, str]) -> tuple[int, int, int]:
    """Number of (AP, LF, SY) channels saved in an imec file."""
    ap, lf, sy = (int(x) for x in meta["snsApLfSy"].split(","))
    return ap, lf, sy


def channel_gain_ni(ichan: int, saved_mn: int, saved_ma: int, meta: dict[str, str]) -> float:
    """Gain of saved NI-DAQ channel ``ichan`` (a saved-channel index, not acquired)."""
    if ichan < saved_mn:
        return float(meta["niMNGain"])
    if ichan < saved_mn + saved_ma:
        return float(meta["niMAGain"])
    return 1.0  # non-multiplexed channels have no extra gain


def gain_correct_ni(data: np.ndarray, channels: list[int], meta: dict[str, str]) -> np.ndarray:
    """Convert raw NI-DAQ samples to volts.

    Parameters
    ----------
    data : np.ndarray, shape (len(channels), n_samples)
        Raw int16 data for the requested channels only.
    channels : list of int
        Saved-channel indices corresponding to the rows of ``data``.
    meta : dict
        NI-DAQ metadata from :func:`read_meta`.
    """
    mn, ma, _, _ = channel_counts_ni(meta)
    fi2v = int_to_volts(meta)
    out = np.empty(data.shape, dtype=float)
    for row, chan in enumerate(channels):
        out[row] = data[row] * (fi2v / channel_gain_ni(chan, mn, ma, meta))
    return out


def memmap_raw(bin_path: str | Path, meta: dict[str, str]) -> np.memmap:
    """Read-only memory map of a SpikeGLX ``.bin`` file, shape (n_channels, n_samples)."""
    n_chan = int(meta["nSavedChans"])
    n_samples = int(meta["fileSizeBytes"]) // (2 * n_chan)
    # Fortran order matches the interleaved on-disk layout (and the MATLAB tools).
    return np.memmap(bin_path, dtype="int16", mode="r", shape=(n_chan, n_samples), order="F")
