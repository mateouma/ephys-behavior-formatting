"""Generate event-aligned h5 datasets for the sessions listed in a TOML config.

Run it with ``python scripts/generate_h5_dataset.py config.toml`` (see
``scripts/example_config.toml`` for the format). The config lists:

- ``output_dir``: where the h5 files go.
- ``[defaults]``: settings shared by all sessions (``roi``, ``task_type``,
  ``bin_size``, ``n_jobs``, ...); any session can override them.
- ``[[alignments]]``: one entry per output file per session (event name and window).
- ``[criteria]``: :class:`~ephys_behavior_formatting.units.UnitCriteria` fields.
  A session's own ``criteria`` table is merged on top.
- ``[[sessions]]``: one entry per session, with ``probe = "neuropixels"`` or
  ``"plexon"`` and the paths that recording system needs.

Relative paths are resolved against the config file's folder.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
import tomllib
import traceback
from pathlib import Path

from .aligned import aligned_filename
from .experiment import Experiment
from .neuropixels import NeuropixelsExperiment
from .plexon import PlexonExperiment
from .units import UnitCriteria

TOP_LEVEL_KEYS = {"output_dir", "defaults", "alignments", "criteria", "sessions"}
ALIGNMENT_KEYS = {"event_name", "pre_time", "post_time"}
CRITERIA_KEYS = {f.name for f in dataclasses.fields(UnitCriteria)}

#: Settings any session may have (or inherit from ``[defaults]``).
COMMON_KEYS = {
    "probe", "monkey_id", "session_date", "roi", "task_type", "events_path", "n_waveforms",
    "n_jobs", "bin_size", "savetags", "criteria", "alignments",
}  # fmt: skip
#: Settings for each recording system: (required, optional).
PROBE_KEYS = {
    "neuropixels": ({"kilosort_dir", "events_path"}, {"raw_dir", "labels_file"}),
    "plexon": ({"all_trials_path"}, {"valid_savetags", "include_unsorted"}),
}
PATH_KEYS = {"kilosort_dir", "events_path", "raw_dir", "all_trials_path"}
DEFAULTS = {"roi": "DLPFC", "task_type": "CHKDLAY", "bin_size": 0.001, "n_jobs": 1}


class ConfigError(ValueError):
    """The config file is invalid."""


# ----------------------------------------------------------------- config
def load_config(path: str | Path) -> dict:
    """Read and validate a config, returning it with every session fully resolved.

    Each returned session has all its settings (defaults merged in), absolute paths,
    its ``alignments`` list and its merged ``criteria`` dict.
    """
    path = Path(path)
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    base = path.parent

    _check_keys(raw, TOP_LEVEL_KEYS, "config")
    if "output_dir" not in raw:
        raise ConfigError("config: missing output_dir")
    if not raw.get("sessions"):
        raise ConfigError("config: no [[sessions]]")

    defaults = {**DEFAULTS, **raw.get("defaults", {})}
    _check_keys(defaults, _all_session_keys(), "[defaults]")
    alignments = raw.get("alignments", [])
    criteria = raw.get("criteria", {})

    sessions = []
    for i, entry in enumerate(raw["sessions"]):
        where = f"session {i + 1} ({entry.get('monkey_id', '?')} {entry.get('session_date', '?')})"
        session = {**defaults, **entry}
        session["criteria"] = {**criteria, **entry.get("criteria", {})}
        session["alignments"] = entry.get("alignments", alignments)
        _validate_session(session, entry, where)
        for key in PATH_KEYS & session.keys():
            session[key] = _resolve(session[key], base)
        sessions.append(session)

    return {"output_dir": _resolve(raw["output_dir"], base), "sessions": sessions}


def _all_session_keys() -> set[str]:
    return COMMON_KEYS.union(*(req | opt for req, opt in PROBE_KEYS.values()))


def _check_keys(table: dict, allowed: set[str], where: str) -> None:
    unknown = set(table) - allowed
    if unknown:
        raise ConfigError(f"{where}: unknown setting(s) {sorted(unknown)}")


def _validate_session(session: dict, entry: dict, where: str) -> None:
    """Check a session (``entry`` merged with the defaults) before anything runs."""
    probe = session.get("probe")
    if probe not in PROBE_KEYS:
        raise ConfigError(f"{where}: probe must be one of {sorted(PROBE_KEYS)}, not {probe!r}")
    required, optional = PROBE_KEYS[probe]
    # Settings written on the session itself must apply to its recording system;
    # [defaults] may hold settings for either.
    _check_keys(entry, COMMON_KEYS | required | optional, where)
    missing = (required | {"monkey_id", "session_date"}) - session.keys()
    if missing:
        raise ConfigError(f"{where}: missing {sorted(missing)}")
    if not session["alignments"]:
        raise ConfigError(f"{where}: no [[alignments]]")
    for alignment in session["alignments"]:
        _check_keys(alignment, ALIGNMENT_KEYS, f"{where} alignment")
        if ALIGNMENT_KEYS - alignment.keys():
            raise ConfigError(f"{where}: each alignment needs {sorted(ALIGNMENT_KEYS)}")
    _check_keys(session["criteria"], CRITERIA_KEYS, f"{where} criteria")


def _resolve(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


# ---------------------------------------------------------------- running
def metadata(session: dict) -> dict:
    """The output metadata of a session (used for file names)."""
    keys = ("monkey_id", "session_date", "roi", "task_type")
    return {key: str(session[key]) for key in keys}


def output_paths(session: dict, output_dir: Path) -> list[Path]:
    """The h5 file each of a session's alignments is written to."""
    meta = metadata(session)
    return [output_dir / aligned_filename(meta, a["event_name"]) for a in session["alignments"]]


def build_experiment(session: dict) -> Experiment:
    """Create the session's experiment object (reads trial and spike files)."""
    meta = metadata(session)
    common = {**meta, "n_waveforms": session.get("n_waveforms", 200)}
    if session["probe"] == "neuropixels":
        options = {k: session[k] for k in ("raw_dir", "labels_file") if k in session}
        return NeuropixelsExperiment(
            session["kilosort_dir"], session["events_path"], **common, **options
        )
    options = {
        k: session[k] for k in ("events_path", "valid_savetags", "include_unsorted") if k in session
    }
    return PlexonExperiment(session["all_trials_path"], **common, **options)


def run_session(session: dict, output_dir: Path, overwrite: bool = False) -> list[Path]:
    """Write a session's h5 files; returns the files written.

    Alignments whose file already exists are skipped unless ``overwrite`` is set.
    """
    todo = [
        (alignment, path)
        for alignment, path in zip(session["alignments"], output_paths(session, output_dir))
        if overwrite or not path.exists()
    ]
    if not todo:
        print("All outputs exist; skipping (use --overwrite to redo).")
        return []

    experiment = build_experiment(session)
    experiment.load_units(n_jobs=session["n_jobs"])
    criteria = UnitCriteria(**session["criteria"]) if session["criteria"] else None
    if criteria is not None:
        kept = experiment.select_units(criteria)
        print(f"{len(kept)} of {len(experiment.units)} units pass the criteria.")

    written = []
    for alignment, path in todo:
        aligned = experiment.align_spikes(
            **alignment,
            bin_size=session["bin_size"],
            criteria=criteria,
            savetags=session.get("savetags"),
        )
        aligned.save(path, overwrite=overwrite)
        print(f"  {alignment['event_name']}: {aligned.spike_counts.shape} -> {path}")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("config", type=Path, help="TOML config file")
    parser.add_argument("--overwrite", action="store_true", help="replace existing output files")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate the config and list outputs only"
    )
    parser.add_argument(
        "--only", nargs="+", metavar="DATE", help="only run sessions with these dates"
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (ConfigError, tomllib.TOMLDecodeError, FileNotFoundError) as err:
        print(f"Invalid config: {err}", file=sys.stderr)
        return 2

    sessions = config["sessions"]
    if args.only:
        sessions = [s for s in sessions if str(s["session_date"]) in args.only]
    output_dir = config["output_dir"]

    if args.dry_run:
        for session in sessions:
            print(f"{session['probe']:12s} {session['monkey_id']} {session['session_date']}")
            for path in output_paths(session, output_dir):
                print(f"    {'exists ' if path.exists() else 'new    '}{path}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    failed = []
    for n, session in enumerate(sessions, 1):
        label = f"{session['monkey_id']} {session['session_date']} ({session['probe']})"
        print(f"\n=== [{n}/{len(sessions)}] {label} ===")
        start = time.time()
        try:
            run_session(session, output_dir, overwrite=args.overwrite)
            print(f"Done in {time.time() - start:.0f} s.")
        except Exception:  # noqa: BLE001 - report and continue with the next session
            traceback.print_exc()
            failed.append(label)

    print(f"\n{len(sessions) - len(failed)} of {len(sessions)} sessions succeeded.")
    for label in failed:
        print(f"  FAILED: {label}")
    return 1 if failed else 0
