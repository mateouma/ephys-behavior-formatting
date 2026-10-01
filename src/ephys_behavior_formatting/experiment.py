"""Recording-system-agnostic experiment interface.

:class:`Experiment` holds everything shared between recording systems: the unit
list, trial parameters, unit selection, and event alignment. Subclasses
(:class:`~ephys_behavior_formatting.neuropixels.NeuropixelsExperiment`,
:class:`~ephys_behavior_formatting.plexon.PlexonExperiment`) only implement how
units, trial parameters, and event times are read from their files.
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from collections.abc import Iterable

import numpy as np
import pandas as pd

from .aligned import AlignedSpikes, bin_spikes, make_bin_edges
from .trials import TrialParams
from .units import Unit, UnitCriteria, compute_unit_metrics


class Experiment(ABC):
    """One recording session: sorted units plus the trials of the behavioral task.

    Typical use::

        exp.load_units()                                   # read spikes + waveforms
        exp.unit_metrics()                                 # inspect quality metrics
        criteria = UnitCriteria(quality_labels=("good",), min_firing_rate=1.0)
        aligned = exp.align_spikes("CheckerboardDrawnTime", pre_time=0.4,
                                   post_time=2.0, criteria=criteria)
        aligned.save("/path/to/output_dir")

    Parameters
    ----------
    monkey_id : str
        Short, anonymized monkey identifier (e.g. ``'B'``, ``'T'``), used in output
        file names and metadata.
    session_date, roi, task_type : str
        Session metadata, stored in every output file.
    """

    probe_type: str = ""

    def __init__(
        self, monkey_id: str, session_date: str, roi: str = "DLPFC", task_type: str = "CHKDLAY"
    ):
        self.metadata = {
            "monkey_id": monkey_id,
            "session_date": str(session_date),
            "roi": roi,
            "task_type": task_type,
            "probe_type": self.probe_type,
        }
        self.units: list[Unit] = []
        self._trial_params: TrialParams | None = None
        self._unit_metrics: pd.DataFrame | None = None

    # ------------------------------------------------- recording-system hooks
    @abstractmethod
    def available_units(self) -> dict[int, str]:
        """All units in the recording, as ``{unit_id: quality_label}``."""

    @abstractmethod
    def _read_units(self, unit_labels: dict[int, str], n_jobs: int) -> list[Unit]:
        """Read spike times and waveforms of the given units."""

    @abstractmethod
    def _read_trial_params(self) -> TrialParams:
        """Read the per-trial behavioral parameters."""

    @abstractmethod
    def event_names(self) -> tuple[str, ...]:
        """Names of the task events that trials can be aligned to."""

    @abstractmethod
    def event_times(self, event_name: str) -> np.ndarray:
        """Time (s, spike clock) of ``event_name`` on every trial; NaN if it did not occur."""

    # ------------------------------------------------------------------ units
    def load_units(
        self,
        unit_ids: Iterable[int] | None = None,
        quality_labels: Iterable[str] | None = None,
        n_jobs: int = 1,
    ) -> list[Unit]:
        """Read units into :attr:`units`, replacing any loaded before.

        Parameters
        ----------
        unit_ids : iterable of int, optional
            Units to load. Default: all units in the recording.
        quality_labels : iterable of str, optional
            Only load units with these sorter labels (e.g. ``("good", "mua")``).
        n_jobs : int
            Number of worker processes (where the recording system supports it).
            ``-1`` uses all cores.
        """
        unit_labels = self.available_units()
        if unit_ids is not None:
            wanted = set(unit_ids)
            missing = wanted - unit_labels.keys()
            if missing:
                raise KeyError(f"Units not found in recording: {sorted(missing)}")
            unit_labels = {u: q for u, q in unit_labels.items() if u in wanted}
        if quality_labels is not None:
            quality_labels = set(quality_labels)
            unit_labels = {u: q for u, q in unit_labels.items() if q in quality_labels}

        self.units = self._read_units(unit_labels, n_jobs)
        self._unit_metrics = None
        print(f"Loaded {len(self.units)} of {len(self.available_units())} units.")
        return self.units

    @property
    def unit_ids(self) -> np.ndarray:
        """Ids of the loaded units."""
        return np.array([unit.unit_id for unit in self.units])

    def get_unit(self, unit_id: int) -> Unit:
        """The loaded unit with id ``unit_id``."""
        for unit in self.units:
            if unit.unit_id == unit_id:
                return unit
        raise KeyError(f"Unit {unit_id} is not loaded.")

    def unit_metrics(self, recompute: bool = False, **metric_kwargs) -> pd.DataFrame:
        """Quality metrics of the loaded units (one row per unit, cached).

        ``metric_kwargs`` (e.g. ``isi_threshold_ms``) are passed to
        :meth:`Unit.quality_metrics` and force a recompute.
        """
        if not self.units:
            raise RuntimeError("No units loaded; call load_units() first.")
        if self._unit_metrics is None or recompute or metric_kwargs:
            self._unit_metrics = compute_unit_metrics(self.units, **metric_kwargs)
        return self._unit_metrics

    def select_units(self, criteria: UnitCriteria | None = None) -> np.ndarray:
        """Ids of the loaded units that pass ``criteria`` (all units if ``None``)."""
        if criteria is None:
            return self.unit_ids
        keep = criteria.mask(self.unit_metrics())
        return keep.index[keep].to_numpy()

    # ----------------------------------------------------------------- trials
    @property
    def trial_params(self) -> TrialParams:
        """Per-trial behavioral parameters (see :func:`ephys_behavior_formatting.trials.trial_params`)."""
        if self._trial_params is None:
            self._trial_params = self._read_trial_params()
        return self._trial_params

    def trial_params_frame(self) -> pd.DataFrame:
        """Trial parameters as a DataFrame (one row per trial)."""
        return pd.DataFrame(self.trial_params)

    @property
    def n_trials(self) -> int:
        return len(next(iter(self.trial_params.values())))

    # -------------------------------------------------------------- alignment
    def align_spikes(
        self,
        event_name: str,
        pre_time: float,
        post_time: float,
        bin_size: float = 0.001,
        criteria: UnitCriteria | None = None,
        unit_ids: Iterable[int] | None = None,
        savetags: Iterable[int] | None = None,
    ) -> AlignedSpikes:
        """Bin each unit's spikes around ``event_name`` on every trial.

        Parameters
        ----------
        event_name : str
            Event to align to (see :meth:`event_names`).
        pre_time, post_time : float
            Window before / after the event (s). Bins cover ``[-pre_time, post_time)``.
        bin_size : float
            Bin width (s).
        criteria : UnitCriteria, optional
            Keep only units passing these criteria.
        unit_ids : iterable of int, optional
            Keep only these units (applied after ``criteria``). Default: all loaded units.
        savetags : iterable of int, optional
            Keep only trials from these SaveTags (recording blocks).

        Returns
        -------
        AlignedSpikes
            Counts of shape ``(n_trials, n_units, n_bins)``. Trials on which the event
            did not occur are dropped; ``trial_indices`` records which trials remain.
        """
        selected = self.select_units(criteria)
        if unit_ids is not None:
            unit_ids = np.asarray(list(unit_ids))
            not_loaded = set(unit_ids.tolist()) - set(self.unit_ids.tolist())
            if not_loaded:
                raise KeyError(f"Units not loaded: {sorted(not_loaded)}")
            selected = selected[np.isin(selected, unit_ids)]
        if len(selected) == 0:
            raise ValueError("No units selected.")
        units = [self.get_unit(u) for u in selected]

        times = self.event_times(event_name)
        if len(times) != self.n_trials:
            raise RuntimeError(f"{len(times)} event times for {self.n_trials} trials.")
        keep = ~np.isnan(times)
        if not keep.all():
            warnings.warn(
                f"Dropping {np.sum(~keep)} trials without a {event_name} event.", stacklevel=2
            )
        if savetags is not None:
            keep &= np.isin(self.trial_params["trial_savetags"], list(savetags))
        trial_indices = np.flatnonzero(keep)

        bin_edges = make_bin_edges(pre_time, post_time, bin_size)
        # uint16 keeps memory manageable for long windows of 1 ms bins.
        counts = np.stack(
            [bin_spikes(u.spike_times, times[keep], bin_edges).astype(np.uint16) for u in units],
            axis=1,
        )

        return AlignedSpikes(
            spike_counts=counts,
            bin_edges=bin_edges,
            event_name=event_name,
            unit_ids=selected,
            unit_quality_labels=np.array([u.quality_label for u in units]),
            trial_params={k: np.asarray(v)[keep] for k, v in self.trial_params.items()},
            trial_indices=trial_indices,
            metadata=dict(self.metadata),
            unit_metrics=self.unit_metrics().loc[selected],
            unit_criteria=criteria.describe() if criteria is not None else {},
        )
