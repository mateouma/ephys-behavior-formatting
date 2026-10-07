#!/usr/bin/env python
"""Build the ``allTrials`` .mat file for every Plexon session in a folder.

Each ``YYYYMMDD``-named subfolder of ``base_dir`` that contains the session's raw
per-trial ``.dat`` files is assembled with ``PlexonSessionProcessor`` and saved as
``{monkey_id}{task}{YYYYMMDD}.mat`` in ``save_dir``. Other folders are skipped.
Requires MATLAB and the MATLAB Engine for Python (``scripts/install_matlab_engine.sh``).

Usage (with the ephys-fmt env active):

    python scripts/build_plexon_alltrials.py /path/to/sessions /path/to/CFD_plexon_data T --dry-run
    python scripts/build_plexon_alltrials.py /path/to/sessions /path/to/CFD_plexon_data T
    python scripts/build_plexon_alltrials.py /path/to/sessions out/ T --task COLGRID --lfp --overwrite
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from ephys_behavior_formatting.plexon import PlexonSessionProcessor
from ephys_behavior_formatting.plexon.readers import stop_matlab_engine


def is_session_date(name: str) -> bool:
    """Whether ``name`` is a valid ``YYYYMMDD`` date."""
    if len(name) != 8 or not name.isdigit():
        return False
    try:
        datetime.strptime(name, "%Y%m%d")
    except ValueError:
        return False
    return True


def find_sessions(base_dir: Path, task_type: str) -> list[PlexonSessionProcessor]:
    """Processors for the date-named folders in ``base_dir`` that have event ``.dat`` files."""
    processors = []
    for session_dir in sorted(d for d in base_dir.iterdir() if d.is_dir()):
        if not is_session_date(session_dir.name):
            continue
        processor = PlexonSessionProcessor(session_dir, task_type=task_type)
        try:
            processor.event_files()
        except FileNotFoundError:
            print(f"Skipping {session_dir.name}: no {task_type} .dat files")
            continue
        processors.append(processor)
    return processors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_dir", type=Path, help="Folder containing the YYYYMMDD session folders")
    parser.add_argument("save_dir", type=Path, help="Where to write the allTrials .mat files")
    parser.add_argument("monkey_id", help="Monkey id used in the output file name (e.g. T)")
    parser.add_argument("--task", default="CHKDLAY", help="Task tag in the .dat file names (default: CHKDLAY)")
    parser.add_argument("--no-spikes", action="store_true", help="Leave out spike data")
    parser.add_argument("--lfp", action="store_true", help="Include LFP data")
    parser.add_argument("--overwrite", action="store_true", help="Rebuild sessions whose .mat file already exists")
    parser.add_argument("--dry-run", action="store_true", help="List the sessions that would be built, then exit")
    args = parser.parse_args()

    processors = find_sessions(args.base_dir, args.task)
    todo = []
    for processor in processors:
        date = processor.session_dir.name
        out_path = args.save_dir / f"{args.monkey_id}{args.task}{date}.mat"
        if out_path.exists() and not args.overwrite:
            print(f"Skipping {date}: {out_path.name} already exists")
        else:
            todo.append(processor)

    print(f"\n{len(todo)} session(s) to build: {', '.join(p.session_dir.name for p in todo) or '-'}")
    if args.dry_run or not todo:
        return 0

    failed = []
    try:
        for processor in todo:
            date = processor.session_dir.name
            print(f"\n=== Session {date} ===")
            try:
                processor.process(include_spikes=not args.no_spikes, include_lfp=args.lfp)
                processor.save(args.save_dir, monkey_id=args.monkey_id, date=date)
            except Exception as err:  # noqa: BLE001 - report and continue with the next session
                print(f"Error building session {date}: {err}")
                failed.append(date)
    finally:
        stop_matlab_engine()

    print(f"\nBuilt {len(todo) - len(failed)} of {len(todo)} session(s).")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
