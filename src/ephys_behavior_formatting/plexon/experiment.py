"""Plexon sessions, read from the ``allTrials`` file made by :class:`PlexonSessionProcessor`."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import numpy as np
import scipy.io as sio

from .. import trials as cfd
from ..experiment import Experiment
from ..trials import TrialParams, target_colors
from ..units import Unit

#: Plexon's unit number for spikes that were not sorted into a unit.
UNSORTED = 0

#: Fields of a trial's ``events`` that are not event times (file header, see
#: ``matlab/parseFileHeader.m``, plus the outcome).
NON_EVENT_FIELDS = {
    "Type",
    "Task",
    "Version",
    "SaveTag",
    "CerebusId",
    "GlobalTrialId",
    "UniqueId",
    "MonkeyName",
    "TrialOutcome",
}


def plexon_unit_id(channel: int | np.ndarray, unit: int | np.ndarray):
    """Encode a (channel, unit) pair as one id: ``channel * 100 + unit`` (e.g. 1302)."""
    return np.asarray(channel, dtype=np.int64) * 100 + np.asarray(unit, dtype=np.int64)


class PlexonExperiment(Experiment):
    """A Plexon session: spikes, events and task parameters for every completed trial.

    Spike and event times are both on the xPC clock (ms in the files, converted to
    s). Spike times are the xPC timestamp of the packet each spike arrived in, so
    their resolution is about 1 ms.

    Parameters
    ----------
    all_trials_path : str or Path
        Session ``.mat`` file with ``allTrials`` (from :class:`PlexonSessionProcessor`).
    monkey_id : str
        Short, anonymized monkey identifier (e.g. ``'B'``, ``'T'``), used in output
        file names and metadata.
    session_date, roi, task_type : str
        Session metadata, stored in every output file.
    valid_savetags : iterable of int, optional
        Keep only trials from these SaveTags (recording blocks), e.g. from
        :func:`~ephys_behavior_formatting.plexon.annotations.read_valid_savetags`.
        Default: all trials.
    include_unsorted : bool
        Treat each channel's unsorted spikes (unit 0) as a unit, labelled
        ``'unsorted'``. Sorted units are labelled ``'good'``.
    n_waveforms : int
        Number of waveforms to sample per unit (used for SNR and amplitude cutoff).
    events_path : str or Path, optional
        The session's ``CFDeventStruct.mat``, the only source of reaction times
        (Plexon files have no hand-movement event). Trials are matched to it by
        unique id. Without it, ``trial_RTs`` is all NaN.
    """

    probe_type = "Plexon"

    def __init__(
        self,
        all_trials_path: str | Path,
        monkey_id: str,
        session_date: str,
        roi: str = "DLPFC",
        task_type: str = "CHKDLAY",
        valid_savetags: Iterable[int] | None = None,
        include_unsorted: bool = False,
        n_waveforms: int = 200,
        events_path: str | Path | None = None,
    ):
        super().__init__(monkey_id, session_date, roi, task_type)
        self.all_trials_path = Path(all_trials_path)
        self.events_path = Path(events_path) if events_path is not None else None
        self.include_unsorted = include_unsorted
        self.n_waveforms = n_waveforms

        print(f"Loading {self.all_trials_path.name}...")
        mat = sio.loadmat(str(self.all_trials_path), squeeze_me=True, struct_as_record=False)
        trials = np.atleast_1d(mat["allTrials"])
        # allTrials is in file-listing order; put trials in the order they were run.
        trials = trials[np.argsort([t.events.GlobalTrialId for t in trials], kind="stable")]
        if valid_savetags is not None:
            valid_savetags = set(valid_savetags)
            trials = trials[[int(t.SaveTag) in valid_savetags for t in trials]]
        self.trials = trials
        print(f"{len(trials)} trials.")

        self._collect_spikes()

    def _collect_spikes(self) -> None:
        """Concatenate all trials' spikes into flat arrays (one row per spike)."""
        unit_ids, times, waveforms = [], [], []
        for trial in self.trials:
            spikes = getattr(trial, "spikes", None)
            if spikes is None or np.size(spikes.xPCtimeStamp) == 0:
                continue
            channel = np.atleast_1d(spikes.channelId)
            unit = np.atleast_1d(spikes.unit)
            data = np.atleast_2d(spikes.data)
            if not len(channel) == len(unit) == np.size(spikes.xPCtimeStamp) == len(data):
                raise ValueError(f"Inconsistent spike arrays in trial {trial.header.fileId}")
            unit_ids.append(plexon_unit_id(channel, unit))
            times.append(np.atleast_1d(spikes.xPCtimeStamp) / 1000)
            waveforms.append(data)

        self._spike_units = np.concatenate(unit_ids)
        self._spike_times = np.concatenate(times)
        self._waveforms = np.concatenate(waveforms)

    # ------------------------------------------------------------------ units
    def available_units(self) -> dict[int, str]:
        ids = np.unique(self._spike_units)
        labels = {int(u): ("unsorted" if u % 100 == UNSORTED else "good") for u in ids}
        if not self.include_unsorted:
            labels = {u: q for u, q in labels.items() if q != "unsorted"}
        return labels

    def _read_units(self, unit_labels: dict[int, str], n_jobs: int) -> list[Unit]:
        units = []
        for unit_id, label in unit_labels.items():
            rows = np.flatnonzero(self._spike_units == unit_id)
            rows = rows[np.argsort(self._spike_times[rows], kind="stable")]
            picks = rows[np.unique(np.linspace(0, len(rows) - 1, self.n_waveforms).astype(int))]
            units.append(
                Unit(unit_id, self._spike_times[rows], self._waveforms[picks].astype(float), label)
            )
        return units

    # ----------------------------------------------------------------- trials
    def _read_trial_params(self) -> TrialParams:
        """Trial parameters from each trial's ``events`` and ``params``.

        Same keys as for Neuropixels sessions (see
        :func:`ephys_behavior_formatting.trials.trial_params`). ``trial_RTs`` comes
        from the CFD event struct (see ``events_path``) and is NaN for trials
        without a match there.
        """
        params = lambda name: np.array([getattr(t.params, name) for t in self.trials])
        correct = np.array([t.TrialOutcome == "Correct Choice" for t in self.trials])

        # CorrectResponse is the side code of the correct target (1 = right, 2 = left);
        # on error trials the monkey chose the other side.
        correct_side = params("CorrectResponse").astype(int)
        chosen_side = np.where(correct, correct_side, 3 - correct_side)
        action_choices = np.where(chosen_side == 1, "right", "left")
        configs, color_choices = target_colors(
            params("LeftTargetColor"), params("RightTargetColor"), action_choices
        )

        result = {
            "trial_outcomes": np.where(correct, "correct", "incorrect"),
            "trial_RTs": np.full(len(self.trials), np.nan),
            "trial_action_choices": action_choices,
            "trial_cues": params("CentralCuenSquares").astype(np.int32),
            "trial_configs": configs,
            "trial_color_choices": color_choices,
            "trial_delay_lengths": np.floor(params("Delay")).astype(np.int32),
            "trial_savetags": np.array([int(t.SaveTag) for t in self.trials], dtype=np.int32),
            "trial_unique_ids": np.array(
                [round(float(t.events.UniqueId)) for t in self.trials], dtype=np.int64
            ),
        }
        if self.events_path is not None:
            result["trial_RTs"] = self._reaction_times(result)
        return result

    def _reaction_times(self, params: TrialParams) -> np.ndarray:
        """Reaction times (ms) from the CFD event struct, matched by unique trial id."""
        reference = cfd.trial_params(cfd.load_event_struct(self.events_path))
        match = cfd.match_unique_ids(params["trial_unique_ids"], reference["trial_unique_ids"])
        found = match >= 0

        # Make sure the matched trials really are the same trials.
        for key in ("trial_outcomes", "trial_action_choices", "trial_cues", "trial_savetags"):
            if not np.array_equal(params[key][found], reference[key][match[found]]):
                raise ValueError(f"{key} differs between allTrials and {self.events_path.name}.")
        if not found.all():
            print(f"{np.sum(~found)} trials not in {self.events_path.name}; their RT is NaN.")

        rts = np.full(len(found), np.nan)
        rts[found] = reference["trial_RTs"][match[found]]
        return rts

    def event_names(self) -> tuple[str, ...]:
        return tuple(n for n in self.trials[0].events._fieldnames if n not in NON_EVENT_FIELDS)

    def event_times(self, event_name: str) -> np.ndarray:
        if event_name not in self.event_names():
            raise KeyError(f"Unknown event {event_name!r}. Available: {self.event_names()}")
        times = [getattr(t.events, event_name, np.nan) for t in self.trials]
        return np.array([np.nan if np.size(x) == 0 else float(x) for x in times]) / 1000
