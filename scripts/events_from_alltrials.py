#!/usr/bin/env python
"""Build a ``CFDeventStruct.mat`` from the ``performance`` field of an ``allTrials`` file.

Some ``allTrials`` files (e.g. ``TCHKDLAY20240725.mat``) were saved with a per-trial
``performance`` struct holding the reaction time, so they don't need a separate
event file. ``PlexonExperiment`` still reads RTs from a CFD event struct, so this
script writes one with the fields that ``trials.trial_params`` uses. It is saved as
``{save_dir}/{YYYYMMDD}/CFDeventStruct.mat``. Pass that file as ``events_path`` and
the original file as ``all_trials_path``.

Differences from a real event struct:
- ``TrialEventTimes`` holds the allTrials event times, in ms on the xPC clock, not
  NI-DAQ samples.
- ``chosenSide`` uses the ``CorrectResponse`` codes, the same convention as the real
  structs. ``performance.ChosenSide`` 'left' is code 1, which the pipeline calls
  'right'.

Usage (with the ephys-fmt env active):

    python scripts/events_from_alltrials.py /path/to/TCHKDLAY20240725.mat ... --save-dir /path/to/TiberiusEvents
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import scipy.io as sio

from ephys_behavior_formatting.plexon.experiment import NON_EVENT_FIELDS

#: ``performance.ChosenSide`` -> ``CorrectResponse`` side code.
SIDE_CODES = {"left": 1, "right": 2}

#: Sessions whose median RT (ms) is below this are rejected as corrupt.
MIN_MEDIAN_RT = 150


def event_struct(trials: np.ndarray) -> np.ndarray:
    """One event-struct entry per trial, built from each trial's ``performance`` field."""
    dtype = [
        ("TrialEventTimes", object),
        ("OutcomeData", object),
        ("RT", object),
        ("correctness", object),
        ("chosenSide", object),
        ("ParameterData", object),
        ("taskType", object),
        ("cue", object),
        ("leftTarget", object),
        ("rightTarget", object),
    ]
    out = np.zeros(len(trials), dtype=dtype)
    for i, t in enumerate(trials):
        p, perf, ev = t.params, t.performance, t.events
        correct = t.TrialOutcome == "Correct Choice"
        if perf.TrialOutcome != t.TrialOutcome or int(perf.CueV) != int(p.CentralCuenSquares):
            raise ValueError(f"performance disagrees with events/params on trial {ev.UniqueId}")
        chosen = SIDE_CODES[perf.ChosenSide]
        expected = int(p.CorrectResponse) if correct else 3 - int(p.CorrectResponse)
        if chosen != expected:
            raise ValueError(f"ChosenSide disagrees with CorrectResponse on trial {ev.UniqueId}")

        names = [n for n in ev._fieldnames if n not in NON_EVENT_FIELDS]
        times = np.zeros(1, dtype=[(n, object) for n in names])
        for n in names:
            value = getattr(ev, n)
            times[0][n] = float(value) if np.size(value) else np.nan

        uid = round(float(ev.UniqueId))
        out[i] = (
            times,
            f"RT: {int(perf.RT)},Outcome:{1 if correct else -99},Target:{chosen}",
            float(perf.RT),
            1.0 if correct else 99.0,
            float(chosen),
            f"TT:{int(p.TrialType)},LT:{int(p.LeftTargetColor)},RT:{int(p.RightTargetColor)},"
            f"Cue:{int(p.CentralCuenSquares)},CR:{int(p.CorrectResponse)},D:{int(np.floor(p.Delay))},"
            f"STIM:{int(p.StimViewingTime)},TID:{int(ev.GlobalTrialId)},ST:{int(t.SaveTag)},UID:{uid}",
            str(ev.Task),
            float(p.CentralCuenSquares),
            float(p.LeftTargetColor),
            float(p.RightTargetColor),
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", type=Path, nargs="+", help="allTrials .mat files with a performance field")
    parser.add_argument("--save-dir", type=Path, required=True, help="Folder for the YYYYMMDD/CFDeventStruct.mat files")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing event files")
    args = parser.parse_args()

    failed = []
    for path in args.files:
        date = re.search(r"(\d{8})", path.stem)
        if date is None:
            print(f"Skipping {path.name}: no YYYYMMDD date in the name")
            continue
        out_path = args.save_dir / date.group(1) / "CFDeventStruct.mat"
        if out_path.exists() and not args.overwrite:
            print(f"Skipping {path.name}: {out_path} already exists")
            continue
        try:
            mat = sio.loadmat(str(path), squeeze_me=True, struct_as_record=False, variable_names=["allTrials"])
            trials = np.atleast_1d(mat["allTrials"])
            if not hasattr(trials[0], "performance"):
                raise ValueError("no performance field")
            events = event_struct(trials)
            # RTs are computed from contBehavior, which some files have mis-parsed.
            median_rt = np.median([float(rt) for rt in events["RT"]])
            if median_rt < MIN_MEDIAN_RT:
                raise ValueError(f"implausible RTs (median {median_rt:.0f} ms); check contBehavior")
        except Exception as err:  # noqa: BLE001 - report and continue with the next file
            print(f"Error processing {path.name}: {err}")
            failed.append(path.name)
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sio.savemat(out_path, {"CFDeventStruct": events.reshape(1, -1)})
        print(f"{path.name}: {len(events)} trials -> {out_path}")

    if failed:
        print(f"\nFailed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
