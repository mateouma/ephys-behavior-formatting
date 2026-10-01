"""Readers for the per-trial Plexon/xPC ``.dat`` files, via the MATLAB Engine.

Each trial of a Plexon session is saved as several ``.dat`` files that differ only
in a type tag: ``EVTS`` (event times and outcome), ``BEHV`` (task parameters),
``CONT`` (hand/eye tracking), ``SPKW`` (spike times and waveforms) and ``RAWN``
(LFP). They are parsed by the lab's MATLAB readers (in the ``matlab/`` folder next
to this module), called through the MATLAB Engine for Python so the output
matches the MATLAB pipeline exactly.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MATLAB_DIR = Path(__file__).parent / "matlab"

_engine = None


def get_matlab_engine():
    """The shared MATLAB engine, started on first use with the readers on its path."""
    global _engine
    if _engine is None:
        try:
            import matlab.engine
        except ImportError as err:
            raise ImportError(
                "MATLAB Engine for Python is not installed; run scripts/install_matlab_engine.sh."
            ) from err
        _engine = matlab.engine.start_matlab()
        _engine.addpath(str(MATLAB_DIR), nargout=0)
    return _engine


def stop_matlab_engine() -> None:
    """Shut down the shared MATLAB engine, if running."""
    global _engine
    if _engine is not None:
        _engine.quit()
        _engine = None


def _to_numpy(value, keep_2d: bool = False):
    """Convert a MATLAB engine value to numpy / Python types.

    Scalars become Python numbers, row/column vectors become 1-D arrays, and
    matrices stay 2-D. ``keep_2d`` keeps a single-row matrix 2-D (e.g. one spike's
    waveform).
    """
    if isinstance(value, str):
        return value
    arr = np.asarray(value)
    if arr.size == 1 and not keep_2d:
        item = arr.item()
        return int(item) if isinstance(item, float) and item.is_integer() else item
    if arr.ndim == 2 and min(arr.shape) == 1 and not keep_2d:
        return arr.ravel()
    return arr


def _struct_to_dict(struct, matrix_fields: tuple[str, ...] = ()) -> dict:
    """Convert a MATLAB struct (returned by the engine as a dict) field by field."""
    return {name: _to_numpy(value, keep_2d=name in matrix_fields) for name, value in struct.items()}


def _call(function: str, base_dir: str | Path, file_id: str, *args, nargout: int = 1):
    path = Path(base_dir) / file_id
    if not path.exists():
        raise FileNotFoundError(path)
    # The MATLAB readers open [baseDir fileId], so baseDir needs a trailing separator.
    base = str(base_dir).rstrip("/\\") + "/"
    return getattr(get_matlab_engine(), function)(base, file_id, *args, nargout=nargout)


def read_event_data(base_dir: str | Path, file_id: str) -> dict:
    """Read an ``EVTS`` file: header fields, event times (ms, xPC clock) and ``TrialOutcome``."""
    return _struct_to_dict(_call("readEventData", base_dir, file_id))


def read_behavioral_data(base_dir: str | Path, file_id: str) -> dict:
    """Read a ``BEHV`` file: the trial's task parameters (``TrialType``, ``Delay``, ...)."""
    return _struct_to_dict(_call("readBehavioralData", base_dir, file_id))


def parse_cont_data(base_dir: str | Path, file_id: str, version_id: str = "BU001") -> dict:
    """Read a ``CONT`` file: continuous hand (``HandX/Y/Z``), eye (``EyeX/Y``,
    ``PupilArea``) and photobox signals, with their timestamps ``t``."""
    eng = get_matlab_engine()
    # parseContData is a MEX file; run it from its own folder as the old pipeline did.
    previous_dir = eng.pwd(nargout=1)
    eng.cd(str(MATLAB_DIR), nargout=0)
    try:
        cont, _header = _call("parseContData", base_dir, file_id, version_id, nargout=2)
    finally:
        eng.cd(previous_dir, nargout=0)
    return _struct_to_dict(cont)


def read_spike_waveforms(base_dir: str | Path, file_id: str) -> dict:
    """Read a ``SPKW`` file.

    Returns
    -------
    dict
        ``xPCtimeStamp`` (ms, xPC clock), ``CBtimeStamp`` (Cerebus samples),
        ``channelId``, ``unit`` (0 = unsorted), ``numData``, ``data``
        (waveforms, shape (n_spikes, 80)), plus the file header fields.
    """
    spikes = _struct_to_dict(
        _call("readSpikeWaveforms", base_dir, file_id), matrix_fields=("data",)
    )
    dtypes = {
        "xPCtimeStamp": np.float64,
        "CBtimeStamp": np.uint32,
        "channelId": np.uint16,
        "unit": np.uint8,
        "numData": np.uint8,
        "data": np.int16,
    }
    for name, dtype in dtypes.items():
        if name in spikes:
            spikes[name] = np.atleast_1d(np.asarray(spikes[name], dtype=dtype))
    return spikes


def read_raw_lfp_data(base_dir: str | Path, file_id: str) -> dict:
    """Read a ``RAWN`` file.

    Returns
    -------
    dict
        ``lfp`` (shape (32, n_samples)), ``xPCtime``, ``CBfirstTime``,
        ``CBlastTime``, ``totalNumPackets``, plus the file header fields.
    """
    lfp = _struct_to_dict(
        _call("readRawLFPdata", base_dir, file_id), matrix_fields=("lfp", "totalNumPackets")
    )
    dtypes = {
        "xPCtime": np.float64,
        "CBfirstTime": np.uint32,
        "CBlastTime": np.uint32,
        "totalNumPackets": np.uint8,
        "lfp": np.int16,
    }
    for name, dtype in dtypes.items():
        if name in lfp:
            lfp[name] = np.asarray(lfp[name], dtype=dtype)
    return lfp
