"""Event-aligned, binned spike counts and their HDF5 file format.

An :class:`AlignedSpikes` holds spike counts of shape ``(n_trials, n_units, n_bins)``
around one task event, together with the trial parameters and unit information
needed to analyze them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

FORMAT_VERSION = "1.0"

#: Session-level metadata stored as HDF5 attributes.
METADATA_KEYS = ("monkey_id", "session_date", "roi", "task_type", "probe_type")


def make_bin_edges(pre_time: float, post_time: float, bin_size: float) -> np.ndarray:
    """Bin edges (s, relative to the event) covering ``[-pre_time, post_time)``.

    The number of bins is rounded, so ``pre_time + post_time`` should be a
    multiple of ``bin_size``.
    """
    n_bins = round((pre_time + post_time) / bin_size)
    return -pre_time + np.arange(n_bins + 1) * bin_size


def aligned_filename(metadata: dict, event_name: str) -> str:
    """``{monkey_id}_{task}_{roi}_{date}_{Event}Aligned.h5``.

    For example ``B_CHKDLAY_DLPFC_20250325_CheckerboardAligned.h5``.
    """
    m = metadata
    alignment = event_name.replace("DrawnTime", "")
    return f"{m['monkey_id']}_{m['task_type']}_{m['roi']}_{m['session_date']}_{alignment}Aligned.h5"


def bin_spikes(
    spike_times: np.ndarray, event_times: np.ndarray, bin_edges: np.ndarray
) -> np.ndarray:
    """Count one unit's spikes in bins around each event.

    Parameters
    ----------
    spike_times : np.ndarray
        Sorted spike times (s).
    event_times : np.ndarray, shape (n_trials,)
        Event time (s) on each trial, on the same clock as ``spike_times``.
    bin_edges : np.ndarray, shape (n_bins + 1,)
        Edges relative to the event (s). Bin ``i`` covers ``[edge_i, edge_i+1)``.

    Returns
    -------
    np.ndarray, shape (n_trials, n_bins)
        Spike counts.
    """
    # Number of spikes before each absolute edge; differences give per-bin counts.
    abs_edges = event_times[:, None] + bin_edges[None, :]
    cumulative = np.searchsorted(spike_times, abs_edges, side="left")
    return np.diff(cumulative, axis=1)


def _smallest_uint(max_value: int) -> type:
    for dtype in (np.uint8, np.uint16, np.uint32):
        if max_value <= np.iinfo(dtype).max:
            return dtype
    return np.uint64


@dataclass
class AlignedSpikes:
    """Spike counts of many units, aligned to one task event across trials.

    Attributes
    ----------
    spike_counts : np.ndarray, shape (n_trials, n_units, n_bins)
        Number of spikes of each unit in each time bin of each trial.
    bin_edges : np.ndarray, shape (n_bins + 1,)
        Bin edges in seconds relative to the event.
    event_name : str
        Name of the event trials are aligned to (e.g. ``'CheckerboardDrawnTime'``).
    unit_ids : np.ndarray, shape (n_units,)
        Unit identifiers, in the order of the ``spike_counts`` unit axis.
    unit_quality_labels : np.ndarray, shape (n_units,)
        Sorter labels of the units.
    trial_params : dict of np.ndarray
        Per-trial parameters (see :func:`ephys_behavior_formatting.trials.trial_params`),
        restricted to the trials in ``spike_counts``.
    trial_indices : np.ndarray, shape (n_trials,)
        Index of each trial in the session's full trial list.
    metadata : dict
        Session metadata (``monkey_id``, ``session_date``, ``roi``, ``task_type``,
        ``probe_type``).
    unit_metrics : pd.DataFrame, optional
        Quality metrics of the units (indexed by unit id).
    unit_criteria : dict
        The :class:`~ephys_behavior_formatting.units.UnitCriteria` used to select units.
    """

    spike_counts: np.ndarray
    bin_edges: np.ndarray
    event_name: str
    unit_ids: np.ndarray
    unit_quality_labels: np.ndarray
    trial_params: dict[str, np.ndarray]
    trial_indices: np.ndarray
    metadata: dict = field(default_factory=dict)
    unit_metrics: pd.DataFrame | None = None
    unit_criteria: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ shape
    @property
    def n_trials(self) -> int:
        return self.spike_counts.shape[0]

    @property
    def n_units(self) -> int:
        return self.spike_counts.shape[1]

    @property
    def bin_size(self) -> float:
        return float(np.mean(np.diff(self.bin_edges)))

    @property
    def bin_starts(self) -> np.ndarray:
        """Left edge of each bin (s)."""
        return self.bin_edges[:-1]

    @property
    def bin_centers(self) -> np.ndarray:
        """Center of each bin (s)."""
        return self.bin_edges[:-1] + np.diff(self.bin_edges) / 2

    def trial_params_frame(self) -> pd.DataFrame:
        """Trial parameters as a DataFrame (one row per trial)."""
        return pd.DataFrame(
            self.trial_params, index=pd.Index(self.trial_indices, name="trial_index")
        )

    def time_window(self, start: float, stop: float) -> AlignedSpikes:
        """A copy restricted to bins whose start lies in ``[start, stop)`` (s)."""
        keep = np.flatnonzero((self.bin_starts >= start) & (self.bin_starts < stop))
        if keep.size == 0:
            raise ValueError(f"No bins start within [{start}, {stop}).")
        edges = self.bin_edges[np.append(keep, keep[-1] + 1)]
        return _replace(self, spike_counts=self.spike_counts[:, :, keep], bin_edges=edges)

    def select_trials(self, mask: np.ndarray) -> AlignedSpikes:
        """A copy keeping only the trials where ``mask`` (boolean or indices) is set."""
        return _replace(
            self,
            spike_counts=self.spike_counts[mask],
            trial_params={k: v[mask] for k, v in self.trial_params.items()},
            trial_indices=self.trial_indices[mask],
        )

    # -------------------------------------------------------------------- I/O
    def default_filename(self) -> str:
        """See :func:`aligned_filename`."""
        return aligned_filename(self.metadata, self.event_name)

    def save(self, path: str | Path, overwrite: bool = False) -> Path:
        """Write to HDF5.

        Parameters
        ----------
        path : str or Path
            Output file, or a directory to write :meth:`default_filename` into.
        overwrite : bool
            Replace an existing file. Otherwise an existing file raises an error.

        Returns
        -------
        Path
            The file written.
        """
        path = Path(path)
        if path.is_dir():
            path = path / self.default_filename()
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} exists; pass overwrite=True to replace it.")
        path.parent.mkdir(parents=True, exist_ok=True)

        counts = self.spike_counts.astype(_smallest_uint(int(self.spike_counts.max(initial=0))))
        gzip = {"compression": "gzip"}
        string = h5py.string_dtype()

        with h5py.File(path, "w") as f:
            f.attrs["format_version"] = FORMAT_VERSION
            f.attrs["align_event"] = self.event_name
            f.attrs["bin_size"] = self.bin_size
            for key in METADATA_KEYS:
                if key in self.metadata:
                    f.attrs[key] = str(self.metadata[key])
            f.attrs["unit_criteria"] = json.dumps(self.unit_criteria)

            dset = f.create_dataset("spike_counts", data=counts, chunks=True, **gzip)
            dset.attrs["dims"] = ["trial", "unit", "time_bin"]
            f.create_dataset("bin_edges", data=self.bin_edges)
            f.create_dataset("trial_indices", data=self.trial_indices)

            units = f.create_group("units")
            units.create_dataset("unit_ids", data=self.unit_ids)
            units.create_dataset(
                "quality_labels", data=_strings(self.unit_quality_labels), dtype=string
            )
            if self.unit_metrics is not None:
                metrics = units.create_group("metrics")
                for column in self.unit_metrics.columns:
                    values = self.unit_metrics.loc[self.unit_ids, column].to_numpy()
                    if values.dtype == object:
                        metrics.create_dataset(column, data=_strings(values), dtype=string)
                    else:
                        metrics.create_dataset(column, data=values)

            trials = f.create_group("trial_params")
            for key, values in self.trial_params.items():
                values = np.asarray(values)
                if values.dtype.kind in "UO":
                    trials.create_dataset(key, data=_strings(values), dtype=string, **gzip)
                else:
                    trials.create_dataset(key, data=values, **gzip)

        return path

    @classmethod
    def load(cls, path: str | Path) -> AlignedSpikes:
        """Read a file written by :meth:`save`."""
        with h5py.File(path, "r") as f:
            units = f["units"]
            unit_ids = units["unit_ids"][:]
            metrics = None
            if "metrics" in units:
                metrics = pd.DataFrame(
                    {k: _read(units["metrics"][k]) for k in units["metrics"]},
                    index=pd.Index(unit_ids, name="unit_id"),
                )
            return cls(
                spike_counts=f["spike_counts"][:],
                bin_edges=f["bin_edges"][:],
                event_name=f.attrs["align_event"],
                unit_ids=unit_ids,
                unit_quality_labels=_read(units["quality_labels"]),
                trial_params={k: _read(v) for k, v in f["trial_params"].items()},
                trial_indices=f["trial_indices"][:],
                metadata={k: f.attrs[k] for k in METADATA_KEYS if k in f.attrs},
                unit_metrics=metrics,
                unit_criteria=json.loads(f.attrs.get("unit_criteria", "{}")),
            )


def _strings(values) -> np.ndarray:
    """Strings as an object array, the form h5py writes as variable-length strings."""
    return np.asarray(values).astype(str).astype(object)


def _read(dset: h5py.Dataset) -> np.ndarray:
    """Read a dataset, decoding variable-length strings to a str array."""
    if h5py.check_string_dtype(dset.dtype):
        return dset.asstr()[:].astype(str)
    return dset[:]


def _replace(aligned: AlignedSpikes, **changes) -> AlignedSpikes:
    values = {name: getattr(aligned, name) for name in aligned.__dataclass_fields__}
    values.update(changes)
    return AlignedSpikes(**values)
