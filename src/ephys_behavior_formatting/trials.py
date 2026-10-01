"""Trial parameters and event times from the task's ``CFDeventStruct.mat`` files.

The event struct has one entry per completed trial with fields such as
``TrialEventTimes`` (event name -> NI-DAQ sample index), ``RT``, ``correctness``,
``chosenSide``, ``cue``, ``leftTarget`` and ``ParameterData`` (a string like
``'TT:2,LT:3,RT:2,Cue:135,CR:2,D:601,STIM:900,TID:1,ST:1,UID:63910262980'``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import scipy.io as sio

TrialParams = dict[str, np.ndarray]

#: Target color codes in the event structs and Plexon files (``leftTarget``,
#: ``rightTarget``, ``LeftTargetColor``, ...). Verified from correct trials, where
#: cues above 112 lead to the red target.
TARGET_COLORS = {2: "green", 3: "red"}


def load_event_struct(path: str | Path, key: str = "CFDeventStruct") -> np.ndarray:
    """Load the per-trial event struct array (1-D, one element per trial)."""
    return sio.loadmat(str(path))[key].ravel()


def _scalar(value) -> float:
    """Unwrap a MATLAB scalar from its nested arrays; NaN if empty."""
    arr = np.asarray(value).squeeze()
    while arr.dtype == object and arr.size == 1:
        arr = np.asarray(arr.item()).squeeze()
    return float(arr) if arr.size == 1 else np.nan


def parse_parameter_data(parameter_data: str) -> dict[str, str]:
    """Split a ``ParameterData`` string into a dict, e.g. ``{'Cue': '135', 'ST': '1', ...}``."""
    return dict(item.split(":", 1) for item in parameter_data.split(",") if ":" in item)


def event_names(events: np.ndarray) -> tuple[str, ...]:
    """Names of the task events recorded in ``TrialEventTimes``."""
    return events[0]["TrialEventTimes"].dtype.names


def event_times(events: np.ndarray, event_name: str, sample_rate: float) -> np.ndarray:
    """Time (s) of ``event_name`` on every trial; NaN where the event did not occur.

    Event times are stored as NI-DAQ sample indices, so ``sample_rate`` should be
    the (calibrated) NI-DAQ rate.
    """
    if event_name not in event_names(events):
        raise KeyError(f"Unknown event {event_name!r}. Available: {event_names(events)}")
    samples = np.array([_scalar(trial["TrialEventTimes"][event_name]) for trial in events])
    return samples / sample_rate


def target_colors(
    left_codes: np.ndarray, right_codes: np.ndarray, action_choices: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Target configuration and chosen color, from the targets' color codes.

    Parameters
    ----------
    left_codes, right_codes : np.ndarray
        Color code of the left / right target on each trial (see ``TARGET_COLORS``).
    action_choices : np.ndarray
        'left' / 'right' reach on each trial.

    Returns
    -------
    configs : np.ndarray
        Target colors read left to right: 'GR' = green left, red right; 'RG' = red
        left, green right.
    color_choices : np.ndarray
        'red' / 'green': color of the target reached to.
    """
    left = np.array([TARGET_COLORS[int(c)] for c in left_codes])
    right = np.array([TARGET_COLORS[int(c)] for c in right_codes])
    configs = np.array([lc[0].upper() + rc[0].upper() for lc, rc in zip(left, right)])
    color_choices = np.where(np.asarray(action_choices) == "left", left, right)
    return configs, color_choices


def trial_params(events: np.ndarray) -> TrialParams:
    """Per-trial behavioral parameters, as a dict of equal-length arrays.

    Keys
    ----
    trial_outcomes : 'correct' / 'incorrect'
    trial_RTs : reaction time (ms)
    trial_action_choices : 'left' / 'right' (side the monkey reached to)
    trial_cues : checkerboard cue value (the struct's ``cue`` field)
    trial_configs : target colors left to right, 'GR' (green left, red right) or 'RG'
    trial_color_choices : 'red' / 'green', color of the target reached to
    trial_delay_lengths : delay period (ms)
    trial_savetags : SaveTag (recording block) of the trial
    trial_unique_ids : the task's unique trial id, for matching across files
    """
    col = lambda name: np.array([_scalar(trial[name]) for trial in events])
    params = [parse_parameter_data(str(np.squeeze(trial["ParameterData"]))) for trial in events]

    action_choices = np.where(col("chosenSide") == 1, "right", "left")
    configs, color_choices = target_colors(col("leftTarget"), col("rightTarget"), action_choices)

    return {
        "trial_outcomes": np.where(col("correctness") == 1, "correct", "incorrect"),
        "trial_RTs": col("RT").astype(np.int32),
        "trial_action_choices": action_choices,
        "trial_cues": col("cue").astype(np.int32),
        "trial_configs": configs,
        "trial_color_choices": color_choices,
        "trial_delay_lengths": np.array([int(p["D"]) for p in params], dtype=np.int32),
        "trial_savetags": np.array([int(p["ST"]) for p in params], dtype=np.int32),
        "trial_unique_ids": np.array([int(p["UID"]) for p in params], dtype=np.int64),
    }


def match_unique_ids(query: np.ndarray, reference: np.ndarray, tolerance: int = 1) -> np.ndarray:
    """For each id in ``query``, the index of the matching id in ``reference``, or -1.

    Unique trial ids are timestamps in seconds; the same trial can be stored with
    ids 1 s apart in different files (rounding), hence ``tolerance``.
    """
    query = np.asarray(query, dtype=float)
    order = np.argsort(reference)
    # Sentinels on both ends so every query has a left and right neighbour.
    padded = np.concatenate([[-np.inf], np.asarray(reference, dtype=float)[order], [np.inf]])
    right = np.searchsorted(padded, query)
    nearest = np.where(padded[right] - query < query - padded[right - 1], right, right - 1)
    found = np.abs(padded[nearest] - query) <= tolerance
    matches = np.where(found, order[np.clip(nearest - 1, 0, len(order) - 1)], -1)
    matched = matches[matches >= 0]
    if len(np.unique(matched)) != len(matched):
        raise ValueError("Unique ids do not match one-to-one.")
    return matches


def trial_params_frame(params: TrialParams) -> pd.DataFrame:
    """Trial parameters as a DataFrame (one row per trial)."""
    return pd.DataFrame(params)
