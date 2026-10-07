# ephys-behavior-formatting
Custom pipeline for formatting electrophysiological and behavioral data from experiments in the Chand Lab. 

## Setup

Requires conda and, for the Plexon readers, a local MATLAB install.

```bash
conda env create -f environment.yml
conda activate ephys-fmt

# MATLAB Engine for Python (installed into the env only; MATLAB itself is not modified).
# Defaults to the `matlab` on your PATH; pass a matlabroot to target a specific release.
bash scripts/install_matlab_engine.sh                    # e.g. ~/.local/MATLAB/R2025a
bash scripts/install_matlab_engine.sh /usr/local/MATLAB  # e.g. R2024a

pytest   # import smoke tests
```

To update an existing env after editing `environment.yml`:

```bash
conda env update -n ephys-fmt -f environment.yml --prune
```

### Version constraints
- **Python 3.11**: npyx 4.1.x requires `<3.12`; MATLAB Engine R2024a supports 3.9–3.11.
- **numpy < 2, pandas < 3**: npyx 4.1.x and the old pipeline were written against numpy 1.x.
- **ipython < 9**: npyx 4.1.x imports `IPython.core.display.display`, removed in IPython 9.

## Usage

See `notebooks/generate_h5_dataset.ipynb` for a full walkthrough of Neuropixels and Plexon sessions.

### Batch script

To process sessions without the notebook, list them in a TOML config (see `scripts/example_config.toml`) and run:

```bash
python scripts/generate_h5_dataset.py config.toml --dry-run   # check the config, list outputs
python scripts/generate_h5_dataset.py config.toml             # write the h5 files
python scripts/generate_h5_dataset.py config.toml --only 20250325 --overwrite
```

The config sets the output folder, shared `[defaults]`, the `[[alignments]]` to write (one file each), the unit `[criteria]`, and one `[[sessions]]` entry per session. Sessions can override any default and add their own criteria, which are merged on top of the shared ones.
Neuropixels sessions whose NI-DAQ and probe clocks aren't aligned can set `sync_clocks = true` (with optional `imec_sync_bit`, `nidaq_sync_channel` and `nidaq_bin_path`) to map event times onto the probe clock using the shared sync pulse.
- **Validation:** the whole config is checked before anything runs, so a typo or a setting for the wrong recording system fails immediately.
- **Existing files:** files that already exist are skipped unless you pass `--overwrite`.
- **Failures:** a session that fails is reported and the rest still run; the exit code is non-zero if any session failed.

### In Python

```python
from ephys_behavior_formatting import AlignedSpikes, NeuropixelsExperiment, UnitCriteria

exp = NeuropixelsExperiment(kilosort_dir, events_path, monkey_id="B", session_date="20250325")
exp.load_units(n_jobs=8)
exp.unit_metrics()                       # quality metrics, one row per unit

criteria = UnitCriteria(quality_labels=("good",), min_firing_rate=1.0, max_isi_violations_ratio=0.5)
aligned = exp.align_spikes("CheckerboardDrawnTime", pre_time=0.4, post_time=2.0,
                           bin_size=0.001, criteria=criteria)
aligned.save(output_dir)                 # -> B_CHKDLAY_DLPFC_20250325_CheckerboardAligned.h5

aligned = AlignedSpikes.load(path)
```

Plexon sessions work the same way through `PlexonExperiment`. It reads the session's `allTrials` `.mat` file, which `PlexonSessionProcessor` assembles from the raw per-trial `.dat` files. Plexon files have no hand-movement event, so reaction times come from the session's `CFDeventStruct.mat`, passed as `events_path`. Trials are matched to it by unique ID, after checking that their other parameters agree. Trials it doesn't contain, or sessions without one, get NaN RTs.

### Unit selection

`UnitCriteria` keeps units that pass every criterion that is set:

| Criterion | Metric |
|---|---|
| `quality_labels` | sorter label (`good` / `mua`, or `unsorted` for Plexon unit 0) |
| `min_num_spikes` | spike count |
| `min_firing_rate`, `max_firing_rate` | mean rate (Hz) |
| `max_isi_violations_ratio` | refractory violations (1.5 ms) relative to firing rate |
| `min_presence_ratio` | fraction of 60 s bins with spikes |
| `max_amplitude_cutoff` | estimated fraction of spikes below detection threshold |
| `min_snr` | waveform peak-to-peak / (2 × noise SD) |
| `include_ids`, `exclude_ids` | always keep / drop these unit ids |

A NaN metric fails its threshold.

### Output file (`*Aligned.h5`)

| Path | Contents |
|---|---|
| `spike_counts` | spike counts, shape (trials, units, time bins) |
| `bin_edges` | bin edges (s) relative to the event; bin *i* is `[edge_i, edge_i+1)` |
| `trial_indices` | index of each trial in the session (trials without the event are dropped) |
| `trial_params/` | `trial_outcomes`, `trial_RTs` (ms; NaN where unknown for Plexon), `trial_action_choices`, `trial_cues`, `trial_configs`, `trial_color_choices`, `trial_delay_lengths`, `trial_savetags`, `trial_unique_ids` |
| `units/unit_ids`, `units/quality_labels` | unit ids (Kilosort cluster id; `channel*100 + unit` for Plexon) and labels |
| `units/metrics/` | quality metrics of each unit |
| attributes | `monkey_id`, `session_date`, `roi`, `task_type`, `probe_type`, `align_event`, `bin_size`, `unit_criteria` |

Changes from the old format: `trial_rasters` → `spike_counts` (counts, not 0/1, and
each spike is now in the bin it occurred in; the old code placed it one bin late),
`time_bins` → `bin_edges`, `unit_quality_labels` → `units/quality_labels`,
`trial_coherences` → `trial_cues`. `trial_configs` now reads target colors left to right
(`GR` = green left, red right; target code 2 = green, 3 = red), which inverts the old
labels, and `trial_color_choices` is `red` / `green` instead of `R` / `G`.

## Layout

```
src/ephys_behavior_formatting/
    experiment.py      shared Experiment base class (units, trials, alignment)
    neuropixels.py     NeuropixelsExperiment (Kilosort + SpikeGLX)
    plexon/            PlexonExperiment, PlexonSessionProcessor, .dat readers (+ MATLAB parsers)
    units.py           Unit, quality metrics, UnitCriteria
    trials.py          trial parameters and event times from CFDeventStruct.mat
    aligned.py         AlignedSpikes and the h5 format
    behavior.py        performance tables, psychometric / chronometric summaries
    spikeglx.py        SpikeGLX .meta/.bin helpers
notebooks/             example workflows
tests/                 pytest tests
scripts/               setup / utility scripts
OLDPIPELINEFILES/      reference copy of the old (poetry-based) pipeline
```
