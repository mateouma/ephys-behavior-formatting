"""Assemble per-trial Plexon ``.dat`` files into one session ``allTrials`` ``.mat`` file."""

from __future__ import annotations

from pathlib import Path

import scipy.io as sio
from tqdm.auto import tqdm

from . import readers

#: Outcomes of trials that are kept (the monkey made a choice).
COMPLETED_OUTCOMES = ("Correct Choice", "Wrong Choice")


class PlexonSessionProcessor:
    """Read every trial of a Plexon session and save them as ``allTrials``.

    Each completed trial becomes a struct with ``events``, ``params``,
    ``contBehavior``, ``TrialOutcome``, ``SaveTag``, ``TrialType``, ``header`` and,
    optionally, ``spikes`` and ``lfp``. Aborted trials are only counted, in
    :attr:`bad_trials`.

    Parameters
    ----------
    session_dir : str or Path
        Folder with the session's ``.dat`` files.
    task_type : str
        Task tag in the file names (e.g. ``'CHKDLAY'``, ``'COLGRID'``).
    event_tag : str
        Type tag of the event files, swapped for the other tags to find a trial's
        other files.
    version_id : str
        Format version passed to the continuous-data parser.
    """

    def __init__(
        self,
        session_dir: str | Path,
        task_type: str = "CHKDLAY",
        event_tag: str = "EVTS",
        version_id: str = "BU001",
    ):
        self.session_dir = Path(session_dir)
        self.task_type = task_type
        self.event_tag = event_tag
        self.version_id = version_id
        self.all_trials: list[dict] = []
        self.bad_trials = {
            "BrokeTarget": 0,
            "NoStart": 0,
            "BrokeCenter": 0,
            "SaveTag": [],
            "delayV": [],
        }

    def event_files(self) -> list[Path]:
        """The session's event files, sorted by name."""
        pattern = f"*-{self.task_type}*{self.event_tag}-*.dat"
        files = sorted(self.session_dir.glob(pattern))
        if not files:
            raise FileNotFoundError(f"No files matching {pattern} in {self.session_dir}")
        return files

    def process(self, include_spikes: bool = True, include_lfp: bool = True) -> list[dict]:
        """Read all trials into :attr:`all_trials`. Unreadable trials are reported and skipped."""
        self.all_trials = []
        for event_file in tqdm(self.event_files(), desc="Reading trials", unit="trial"):
            try:
                self._process_trial(event_file.name, include_spikes, include_lfp)
            except Exception as err:  # noqa: BLE001 - one corrupt trial shouldn't stop the session
                tqdm.write(f"Error processing {event_file.name}: {err}")
        self.print_summary()
        return self.all_trials

    def _file_for(self, event_file: str, tag: str) -> str:
        """Name of the trial's file with type ``tag`` (e.g. 'SPKW' for its spikes)."""
        return event_file.replace(self.event_tag, tag, 1)

    def _process_trial(self, event_file: str, include_spikes: bool, include_lfp: bool) -> None:
        events = readers.read_event_data(self.session_dir, event_file)
        params = readers.read_behavioral_data(self.session_dir, self._file_for(event_file, "BEHV"))
        outcome = events.get("TrialOutcome", "")

        if outcome == "Broke Target":
            self.bad_trials["BrokeTarget"] += 1
        elif outcome == "No Initiate":
            self.bad_trials["NoStart"] += 1
        elif outcome == "Broke Center":
            self.bad_trials["BrokeCenter"] += 1
            self.bad_trials["delayV"].append(params.get("Delay", 0))
            self.bad_trials["SaveTag"].append(events.get("SaveTag", 0))
        if outcome not in COMPLETED_OUTCOMES:
            return

        cont_file = self._file_for(event_file, "CONT")
        trial = {
            "params": params,
            "events": events,
            "contBehavior": readers.parse_cont_data(self.session_dir, cont_file, self.version_id),
            "TrialOutcome": outcome,
            "SaveTag": events.get("SaveTag", 0),
            "TrialType": params.get("TrialType", 0),
            "header": {
                "Task": events.get("Task", ""),
                "GlobalTrialId": events.get("GlobalTrialId", 0),
                "UniqueId": events.get("UniqueId", ""),
                "fileId": cont_file,
            },
        }
        spike_file = self._file_for(event_file, "SPKW")
        if include_spikes and (self.session_dir / spike_file).exists():
            trial["spikes"] = readers.read_spike_waveforms(self.session_dir, spike_file)
        lfp_file = self._file_for(event_file, "RAWN")
        if include_lfp and (self.session_dir / lfp_file).exists():
            trial["lfp"] = readers.read_raw_lfp_data(self.session_dir, lfp_file)

        self.all_trials.append(trial)

    def summary(self) -> dict:
        """Trial counts and accuracy of the processed session."""
        outcomes = [t["TrialOutcome"] for t in self.all_trials]
        trial_types = [t["TrialType"] for t in self.all_trials]
        n_correct = outcomes.count("Correct Choice")
        n_total = len(outcomes)
        return {
            "total_trials": n_total,
            "num_correct": n_correct,
            "num_incorrect": n_total - n_correct,
            "accuracy": n_correct / n_total if n_total else 0.0,
            "single_trials": trial_types.count(1),
            "double_trials": trial_types.count(2),
            "broke_center_holds": self.bad_trials["BrokeCenter"],
            "broke_center_pct": 100 * self.bad_trials["BrokeCenter"] / n_total if n_total else 0.0,
        }

    def print_summary(self) -> None:
        for key, value in self.summary().items():
            print(
                f"{key:>20s}: {value:.3f}" if isinstance(value, float) else f"{key:>20s}: {value}"
            )

    def save(self, save_dir: str | Path, monkey_id: str, date: str) -> Path:
        """Save ``allTrials`` and ``badTrials`` to ``{monkey_id}{task}{date}.mat`` in ``save_dir``."""
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        path = save_dir / f"{monkey_id}{self.task_type}{date}.mat"
        sio.savemat(path, {"allTrials": self.all_trials, "badTrials": self.bad_trials})
        print(f"Saved {len(self.all_trials)} trials to {path}")
        return path


def process_sessions(
    base_dir: str | Path,
    save_dir: str | Path,
    monkey_id: str,
    task_type: str = "CHKDLAY",
    session_slice: slice = slice(None),
    **process_kwargs,
) -> list[Path]:
    """Process several sessions, each a ``YYYYMMDD``-named folder in ``base_dir``.

    Parameters
    ----------
    session_slice : slice
        Which of the (date-sorted) session folders to process, e.g. ``slice(9, 14)``.
    process_kwargs
        Passed to :meth:`PlexonSessionProcessor.process`.

    Returns
    -------
    list of Path
        The files written. Sessions that fail are reported and skipped.
    """
    session_dirs = sorted(d for d in Path(base_dir).glob("20*") if d.is_dir())[session_slice]
    if not session_dirs:
        raise FileNotFoundError(f"No session folders in {base_dir}")

    written = []
    for session_dir in session_dirs:
        print(f"\n=== Session {session_dir.name} ===")
        processor = PlexonSessionProcessor(session_dir, task_type=task_type)
        try:
            processor.process(**process_kwargs)
            written.append(processor.save(save_dir, monkey_id, session_dir.name))
        except Exception as err:  # noqa: BLE001 - report and continue with the next session
            print(f"Error processing session {session_dir.name}: {err}")
    return written
