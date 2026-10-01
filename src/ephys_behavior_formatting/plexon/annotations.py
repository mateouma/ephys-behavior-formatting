"""Hand-written session annotations for Plexon recordings (Excel sheets).

Each session has a sheet named ``YYYYMMDD...xlsx`` listing units (columns 1-5:
channel, unit, -, modulation, good quality), notes (column 10), and in cell
row 2 / column 11 the valid SaveTags, e.g. ``"SaveTag: 1, 2, 3"``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_SAVETAG_CELL = (1, 10)  # (row, column), 0-based, below the header row


def read_valid_savetags(excel_path: str | Path) -> np.ndarray | None:
    """SaveTags listed in a session's annotation sheet, or ``None`` if none are listed."""
    sheet = pd.read_excel(excel_path, header=0)
    cell = sheet.iloc[_SAVETAG_CELL]
    if pd.isna(cell):
        return None
    savetags = [
        int(part.strip())
        for part in str(cell).replace("SaveTag:", "").split(",")
        if part.strip().isdigit()
    ]
    return np.array(savetags) if savetags else None


def find_annotation_file(annotations_dir: str | Path, session_date: str) -> Path | None:
    """The annotation sheet for ``session_date`` (``YYYYMMDD``), if there is one.

    If several sheets share the date (several tasks in one session), the first is
    returned with a warning.
    """
    matches = sorted(Path(annotations_dir).glob(f"{session_date}*.xlsx"))
    if len(matches) > 1:
        print(
            f"Warning: {len(matches)} annotation files for {session_date}; using {matches[0].name}"
        )
    return matches[0] if matches else None


def read_annotations(excel_dir: str | Path, pattern: str = "*.xlsx") -> list[dict]:
    """Read every session's annotation sheet.

    Returns
    -------
    list of dict
        One entry per sheet with ``name``, ``date``, ``channelID``, ``unitID``,
        ``modulation``, ``goodQuality``, ``notes`` and ``savetag``.
    """
    files = sorted(Path(excel_dir).glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matching {pattern} in {excel_dir}")

    database = []
    for path in files:
        sheet = pd.read_excel(path, header=0)
        channel_ids = pd.to_numeric(sheet.iloc[:, 0], errors="coerce").to_numpy()
        valid = ~np.isnan(channel_ids)
        if not valid.all():
            print(f"Warning: {path.name} has rows without a channel id; skipping them.")
        savetags = read_valid_savetags(path)
        database.append(
            {
                "name": path.name,
                "date": path.name[:8],
                "channelID": channel_ids[valid],
                "unitID": pd.to_numeric(sheet.iloc[:, 1], errors="coerce").to_numpy()[valid],
                "modulation": sheet.iloc[:, 3].to_numpy()[valid],
                "goodQuality": sheet.iloc[:, 4].to_numpy()[valid],
                "notes": sheet.iloc[:, 9].to_numpy(),
                "savetag": savetags if savetags is not None else np.array([], dtype=int),
            }
        )
    return database


def annotations_summary(database: list[dict]) -> pd.DataFrame:
    """Per-session unit counts from :func:`read_annotations`."""
    return pd.DataFrame(
        {
            "name": entry["name"],
            "n_units": len(entry["channelID"]),
            "n_modulated": int(np.sum(entry["modulation"] == 1)),
            "n_good_quality": int(np.sum(entry["goodQuality"] == 1)),
        }
        for entry in database
    )
