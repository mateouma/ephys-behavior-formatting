"""Neuropixels (SpikeGLX + Kilosort) sessions."""

from __future__ import annotations

import os
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from . import spikeglx, trials
from .constants import HEADSTAGE_TRUE_SAMPLE_RATE, NI_TRUE_SAMPLE_RATE
from .experiment import Experiment
from .trials import TrialParams
from .units import Unit


class NeuropixelsExperiment(Experiment):
    """A Neuropixels session sorted with Kilosort, with task events from the NI-DAQ.

    Spike times are converted to seconds with the headstage's calibrated sample
    rate and event times with the calibrated NI-DAQ rate (see
    :mod:`~ephys_behavior_formatting.constants`). By default the two clocks are
    assumed to start together, as in the old pipeline; call :meth:`sync_clocks`
    to instead map event times onto the probe clock using the shared sync pulse.

    Parameters
    ----------
    kilosort_dir : str or Path
        Folder with the Kilosort output (``spike_times.npy``, ``spike_clusters.npy``,
        ``cluster_KSLabel.tsv``, ...).
    events_path : str or Path
        The session's ``CFDeventStruct.mat``.
    monkey_id : str
        Short, anonymized monkey identifier (e.g. ``'B'``, ``'T'``), used in output
        file names and metadata.
    session_date, roi, task_type : str
        Session metadata, stored in every output file.
    raw_dir : str or Path, optional
        Folder with the ``.ap.bin`` / ``.ap.meta`` files. Default: ``kilosort_dir``
        if it contains them, else its parent folder.
    labels_file : str
        Tab-separated file in ``kilosort_dir`` with the unit labels:
        ``cluster_KSLabel.tsv`` (Kilosort's labels) or ``cluster_group.tsv``
        (labels after manual curation in Phy).
    events_key : str
        Variable name of the event struct inside ``events_path``.
    n_waveforms : int
        Number of waveforms to sample per unit (used for SNR and amplitude cutoff).
    """

    probe_type = "Neuropixels"

    #: Samples per waveform, before and after the spike time.
    WAVEFORM_WINDOW = (41, 41)

    def __init__(
        self,
        kilosort_dir: str | Path,
        events_path: str | Path,
        monkey_id: str,
        session_date: str,
        roi: str = "DLPFC",
        task_type: str = "CHKDLAY",
        raw_dir: str | Path | None = None,
        labels_file: str = "cluster_KSLabel.tsv",
        events_key: str = "CFDeventStruct",
        n_waveforms: int = 200,
    ):
        super().__init__(monkey_id, session_date, roi, task_type)
        self.kilosort_dir = Path(kilosort_dir)
        self.raw_dir = (
            Path(raw_dir) if raw_dir is not None else self._find_raw_dir(self.kilosort_dir)
        )
        self.labels_file = labels_file
        self.n_waveforms = n_waveforms

        self.ap_bin_path = _single(self.raw_dir.glob("*.ap.bin"), "*.ap.bin", self.raw_dir)
        self.ap_meta = spikeglx.read_meta(self.ap_bin_path)
        self.headstage_serial = self.ap_meta["imDatHs_sn"]
        if self.headstage_serial in HEADSTAGE_TRUE_SAMPLE_RATE:
            self.fs = HEADSTAGE_TRUE_SAMPLE_RATE[self.headstage_serial]
        else:
            self.fs = spikeglx.sample_rate(self.ap_meta)
            warnings.warn(
                f"No calibrated rate for headstage {self.headstage_serial}; "
                f"using the nominal {self.fs} Hz from the .meta file.",
                stacklevel=2,
            )
        self.nidaq_fs = NI_TRUE_SAMPLE_RATE

        self.events_path = Path(events_path)
        self.events = trials.load_event_struct(self.events_path, events_key)

        # Kilosort spike times are in probe samples.
        self._spike_samples = np.load(self.kilosort_dir / "spike_times.npy").ravel()
        self._spike_clusters = np.load(self.kilosort_dir / "spike_clusters.npy").ravel()

        #: Linear map from NI-DAQ samples to probe samples, set by :meth:`sync_clocks`.
        self.clock_sync: dict | None = None

    @staticmethod
    def _find_raw_dir(kilosort_dir: Path) -> Path:
        for candidate in (kilosort_dir, kilosort_dir.parent):
            if any(candidate.glob("*.ap.meta")):
                return candidate
        raise FileNotFoundError(f"No .ap.meta in {kilosort_dir} or its parent; pass raw_dir.")

    # ------------------------------------------------------------------ units
    def available_units(self) -> dict[int, str]:
        labels = pd.read_csv(self.kilosort_dir / self.labels_file, sep="\t")
        id_column, label_column = labels.columns[:2]
        return dict(zip(labels[id_column].astype(int), labels[label_column].astype(str)))

    def _read_units(self, unit_labels: dict[int, str], n_jobs: int) -> list[Unit]:
        raw = spikeglx.memmap_raw(self.ap_bin_path, self.ap_meta)
        n_ap_channels = spikeglx.channel_counts_im(self.ap_meta)[0]

        def read(unit_id: int) -> Unit:
            samples = np.sort(self._spike_samples[self._spike_clusters == unit_id])
            waveforms = _peak_channel_waveforms(
                raw, samples, n_ap_channels, self.n_waveforms, self.WAVEFORM_WINDOW
            )
            return Unit(unit_id, samples / self.fs, waveforms, unit_labels[unit_id])

        # Waveform reads are I/O bound, so threads parallelize them well.
        workers = os.cpu_count() if n_jobs == -1 else max(n_jobs, 1)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(
                tqdm(pool.map(read, unit_labels), total=len(unit_labels), desc="Loading units")
            )

    # ----------------------------------------------------------------- trials
    def _read_trial_params(self) -> TrialParams:
        return trials.trial_params(self.events)

    def event_names(self) -> tuple[str, ...]:
        return trials.event_names(self.events)

    def event_times(self, event_name: str) -> np.ndarray:
        if self.clock_sync is None:
            return trials.event_times(self.events, event_name, self.nidaq_fs)
        nidaq_samples = trials.event_times(self.events, event_name, sample_rate=1.0)
        probe_samples = self.clock_sync["slope"] * nidaq_samples + self.clock_sync["intercept"]
        return probe_samples / self.fs

    # ------------------------------------------------------------ clock sync
    def sync_clocks(
        self,
        imec_sync_bit: int = 6,
        nidaq_sync_channel: int = 4,
        nidaq_bin_path: str | Path | None = None,
    ) -> dict:
        """Map NI-DAQ samples onto probe samples using the shared sync pulse.

        Finds the sync pulse onsets on both devices, fits
        ``probe_sample = slope * nidaq_sample + intercept``, and from then on
        :meth:`event_times` uses that fit instead of assuming the clocks start
        together. Reading the probe's sync channel can take several minutes.

        Parameters
        ----------
        imec_sync_bit : int
            Bit of the probe's sync word that carries the pulse.
        nidaq_sync_channel : int
            Saved NI-DAQ channel (analog) that carries the pulse.
        nidaq_bin_path : str or Path, optional
            The ``.nidq.bin`` file. Default: the one in the parent of ``raw_dir``.

        Returns
        -------
        dict
            ``slope``, ``intercept``, ``n_pulses`` and ``max_residual_samples``.
        """
        from npyx.inout import get_npix_sync

        print("Reading probe sync pulses (this may take a while)...")
        onsets, _ = get_npix_sync(str(self.raw_dir), filt_key="highpass", unit="samples")
        probe_onsets = np.asarray(onsets[imec_sync_bit], dtype=float)

        if nidaq_bin_path is None:
            nidaq_bin_path = _single(
                self.raw_dir.parent.glob("*.nidq.bin"), "*.nidq.bin", self.raw_dir.parent
            )
        nidaq_onsets = nidaq_pulse_onsets(nidaq_bin_path, nidaq_sync_channel).astype(float)

        if len(probe_onsets) != len(nidaq_onsets):
            raise RuntimeError(
                f"Found {len(probe_onsets)} probe and {len(nidaq_onsets)} NI-DAQ sync pulses; "
                "check imec_sync_bit and nidaq_sync_channel."
            )
        slope, intercept = np.polyfit(nidaq_onsets, probe_onsets, 1)
        residuals = probe_onsets - (slope * nidaq_onsets + intercept)
        self.clock_sync = {
            "slope": float(slope),
            "intercept": float(intercept),
            "n_pulses": len(probe_onsets),
            "max_residual_samples": float(np.abs(residuals).max()),
        }
        return self.clock_sync


def nidaq_pulse_onsets(
    bin_path: str | Path, channel: int, threshold: float | None = None
) -> np.ndarray:
    """Sample indices of rising edges of a pulse recorded on a NI-DAQ analog channel.

    Parameters
    ----------
    bin_path : str or Path
        The ``.nidq.bin`` file.
    channel : int
        Saved-channel index of the pulse.
    threshold : float, optional
        Voltage separating low from high. Default: midway between the signal's
        minimum and maximum.
    """
    meta = spikeglx.read_meta(bin_path)
    raw = spikeglx.memmap_raw(bin_path, meta)
    volts = spikeglx.gain_correct_ni(raw[[channel], :], [channel], meta)[0]
    if threshold is None:
        threshold = (volts.min() + volts.max()) / 2
    high = volts > threshold
    return np.flatnonzero(~high[:-1] & high[1:]) + 1


def _peak_channel_waveforms(
    raw: np.memmap,
    spike_samples: np.ndarray,
    n_channels: int,
    n_waveforms: int,
    window: tuple[int, int],
) -> np.ndarray:
    """Waveforms (raw ADC units) of evenly spaced spikes, on the unit's peak channel.

    The peak channel is the one where the mean waveform has the largest
    peak-to-peak amplitude.
    """
    before, after = window
    usable = spike_samples[(spike_samples >= before) & (spike_samples + after < raw.shape[1])]
    if len(usable) == 0:
        return np.zeros((0, before + after), dtype=np.int16)

    picks = usable[np.unique(np.linspace(0, len(usable) - 1, n_waveforms).astype(int))].astype(int)
    snippets = np.stack(
        [raw[:n_channels, t - before : t + after] for t in picks]
    )  # (n, chan, time)
    peak_channel = np.ptp(snippets.mean(axis=0), axis=1).argmax()
    return snippets[:, peak_channel, :]


def _single(paths, pattern: str, folder: Path) -> Path:
    paths = sorted(paths)
    if len(paths) != 1:
        raise FileNotFoundError(f"Expected one {pattern} in {folder}, found {len(paths)}.")
    return paths[0]
