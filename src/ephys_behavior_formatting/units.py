"""Single units, their quality metrics, and metric-based unit selection."""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d


@dataclass
class Unit:
    """A sorted unit: its spike train plus a sample of its waveforms.

    Attributes
    ----------
    unit_id : int
        Identifier of the unit. Kilosort cluster id for Neuropixels;
        ``channel * 100 + unit`` for Plexon.
    spike_times : np.ndarray
        Sorted spike times in seconds, on the same clock as the task events.
    waveforms : np.ndarray, shape (n_waveforms, n_samples)
        Sample of spike waveforms on the unit's peak channel.
    quality_label : str
        Sorter label (e.g. Kilosort's ``'good'`` / ``'mua'``).
    """

    unit_id: int
    spike_times: np.ndarray = field(repr=False)
    waveforms: np.ndarray = field(repr=False)
    quality_label: str = "good"

    # ----------------------------------------------------------------- metrics
    @property
    def num_spikes(self) -> int:
        return len(self.spike_times)

    @property
    def duration(self) -> float:
        """Time between the first and last spike (s)."""
        return float(self.spike_times[-1] - self.spike_times[0]) if self.num_spikes > 1 else 0.0

    def firing_rate(self) -> float:
        """Mean firing rate (Hz) between the first and last spike."""
        return self.num_spikes / self.duration if self.duration > 0 else 0.0

    def isi_violations(
        self, isi_threshold_ms: float = 1.5, min_isi_ms: float = 0.0
    ) -> tuple[float, int]:
        """Refractory-period violations (Hill et al., 2011).

        Returns
        -------
        ratio : float
            Rate of violations relative to the unit's firing rate. Values well above
            0 indicate contamination.
        count : int
            Number of inter-spike intervals shorter than ``isi_threshold_ms``.
        """
        if self.num_spikes < 2:
            return 0.0, 0

        threshold_s = isi_threshold_ms / 1000
        count = int(np.sum(np.diff(self.spike_times) < threshold_s))

        rate = self.firing_rate()
        violation_time = 2 * self.num_spikes * (threshold_s - min_isi_ms / 1000)
        if rate == 0 or violation_time <= 0:
            return 0.0, count
        return (count / violation_time) / rate, count

    def presence_ratio(
        self, bin_duration_s: float = 60.0, mean_fr_ratio_thresh: float = 0.0
    ) -> float:
        """Fraction of ``bin_duration_s`` bins in which the unit fires.

        A bin counts as "present" if its spike count exceeds
        ``mean_fr_ratio_thresh`` times the count expected from the mean rate.
        NaN if the unit spans less than one bin.
        """
        if self.duration < bin_duration_s:
            return np.nan

        n_bins = int(self.duration / bin_duration_s)
        edges = np.linspace(self.spike_times[0], self.spike_times[-1], n_bins + 1)
        counts, _ = np.histogram(self.spike_times, bins=edges)
        threshold = self.firing_rate() * bin_duration_s * mean_fr_ratio_thresh
        return float(np.sum(counts > threshold) / n_bins)

    def _peak_sign(self) -> str:
        mean_wf = self.waveforms.mean(axis=0)
        return "neg" if abs(mean_wf.min()) > abs(mean_wf.max()) else "pos"

    def amplitude_cutoff(
        self, num_histogram_bins: int = 100, histogram_smoothing_value: float = 3
    ) -> float:
        """Estimated fraction of spikes missed by the detection threshold.

        Fits the amplitude distribution of the sampled waveforms and measures how
        much of it is cut off on the low-amplitude side (Allen Institute
        ``ecephys_spike_sorting``). Capped at 0.5; NaN without waveforms.
        """
        if len(self.waveforms) == 0:
            return np.nan

        if self._peak_sign() == "neg":
            amplitudes = np.abs(self.waveforms.min(axis=1))
        else:
            amplitudes = np.abs(self.waveforms.max(axis=1))

        pdf, bin_edges = np.histogram(amplitudes, num_histogram_bins, density=True)
        pdf = gaussian_filter1d(pdf, histogram_smoothing_value)
        bin_size = np.mean(np.diff(bin_edges[:-1]))

        # The cutoff is where the pdf, right of its peak, comes back down to the
        # height it has at the lowest amplitude.
        peak = np.argmax(pdf)
        pdf_above = np.abs(pdf[peak:] - pdf[0])
        if np.sum(pdf_above == pdf_above.min()) > 1:
            warnings.warn(
                f"Unit {self.unit_id}: amplitude pdf has no unique minimum; "
                "amplitude_cutoff may be unreliable with this few waveforms.",
                stacklevel=2,
            )
        cutoff = np.argmin(pdf_above) + peak
        return float(min(np.sum(pdf[cutoff:]) * bin_size, 0.5))

    def snr(self) -> float:
        """Peak-to-peak amplitude of the mean waveform over 2x the residual noise SD.

        Noise is estimated from residuals after subtracting the mean waveform
        (Allen Institute ``ecephys_spike_sorting``). NaN with fewer than two waveforms.
        """
        if len(self.waveforms) < 2:
            return np.nan
        mean_wf = self.waveforms.mean(axis=0)
        noise = np.nanstd(self.waveforms - mean_wf)
        return float(np.ptp(mean_wf) / (2 * noise)) if noise > 0 else np.nan

    def quality_metrics(self, isi_threshold_ms: float = 1.5, presence_bin_s: float = 60.0) -> dict:
        """All quality metrics for this unit, as a flat dict."""
        isis = np.diff(self.spike_times)
        isi_ratio, isi_count = self.isi_violations(isi_threshold_ms=isi_threshold_ms)
        return {
            "unit_id": self.unit_id,
            "quality_label": self.quality_label,
            "num_spikes": self.num_spikes,
            "firing_rate": self.firing_rate(),
            "isi_mean": float(isis.mean()) if len(isis) else np.nan,
            "isi_std": float(isis.std()) if len(isis) else np.nan,
            "isi_violations_ratio": isi_ratio,
            "isi_violations_count": isi_count,
            "presence_ratio": self.presence_ratio(bin_duration_s=presence_bin_s),
            "amplitude_cutoff": self.amplitude_cutoff(),
            "snr": self.snr(),
        }


def compute_unit_metrics(units: list[Unit], **metric_kwargs) -> pd.DataFrame:
    """Quality metrics for a list of units, one row per unit (indexed by ``unit_id``).

    ``metric_kwargs`` are passed to :meth:`Unit.quality_metrics`.
    """
    rows = [unit.quality_metrics(**metric_kwargs) for unit in units]
    return pd.DataFrame(rows).set_index("unit_id")


# Maps each UnitCriteria threshold field to (metric column, comparison).
_THRESHOLDS = {
    "min_num_spikes": ("num_spikes", ">="),
    "min_firing_rate": ("firing_rate", ">="),
    "max_firing_rate": ("firing_rate", "<="),
    "max_isi_violations_ratio": ("isi_violations_ratio", "<="),
    "min_presence_ratio": ("presence_ratio", ">="),
    "max_amplitude_cutoff": ("amplitude_cutoff", "<="),
    "min_snr": ("snr", ">="),
}


@dataclass
class UnitCriteria:
    """Inclusion criteria for units, based on sorter labels and quality metrics.

    Every criterion left as ``None`` is ignored. A unit is kept only if it passes
    all the criteria that are set. A metric that is NaN (e.g. ``presence_ratio``
    for a unit spanning less than one bin) fails any threshold on that metric.

    Examples
    --------
    >>> UnitCriteria(quality_labels=("good",), min_firing_rate=1.0, min_snr=3.0)
    """

    quality_labels: tuple[str, ...] | None = None
    min_num_spikes: int | None = None
    min_firing_rate: float | None = None
    max_firing_rate: float | None = None
    max_isi_violations_ratio: float | None = None
    min_presence_ratio: float | None = None
    max_amplitude_cutoff: float | None = None
    min_snr: float | None = None
    #: Unit ids to always keep, regardless of the criteria above.
    include_ids: list[int] = field(default_factory=list)
    #: Unit ids to always drop, regardless of the criteria above.
    exclude_ids: list[int] = field(default_factory=list)

    def mask(self, metrics: pd.DataFrame) -> pd.Series:
        """Boolean Series (indexed like ``metrics``) of the units that pass."""
        keep = pd.Series(True, index=metrics.index)

        if self.quality_labels is not None:
            keep &= metrics["quality_label"].isin(self.quality_labels)

        for name, (column, op) in _THRESHOLDS.items():
            threshold = getattr(self, name)
            if threshold is None:
                continue
            values = metrics[column]
            keep &= (values >= threshold) if op == ">=" else (values <= threshold)  # NaN -> False

        keep[keep.index.isin(self.include_ids)] = True
        keep[keep.index.isin(self.exclude_ids)] = False
        return keep

    def describe(self) -> dict:
        """The criteria that are set, as a plain dict (for saving alongside data)."""
        return {k: v for k, v in asdict(self).items() if v not in (None, [])}
