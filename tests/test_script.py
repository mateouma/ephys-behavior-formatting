"""Tests of the config-driven pipeline behind scripts/generate_h5_dataset.py."""

import numpy as np
import pytest
from test_pipeline import _cfd_for_plexon_session, _plexon_session

from ephys_behavior_formatting import AlignedSpikes
from ephys_behavior_formatting.pipeline import ConfigError, load_config, main


def _write_config(tmp_path, session_extra="", top_extra=""):
    _plexon_session(tmp_path / "TCHKDLAY20220309.mat")
    _cfd_for_plexon_session(tmp_path / "CFDeventStruct.mat")
    config = tmp_path / "config.toml"
    config.write_text(f"""
output_dir = "out"
{top_extra}
[defaults]
bin_size = 0.01

[[alignments]]
event_name = "CheckerboardDrawnTime"
pre_time = 0.5
post_time = 1.0

[[alignments]]
event_name = "TargetsDrawnTime"
pre_time = 1.0
post_time = 0.5

[criteria]
min_num_spikes = 50

[[sessions]]
probe = "plexon"
monkey_id = "T"
session_date = "20220309"
all_trials_path = "TCHKDLAY20220309.mat"
events_path = "CFDeventStruct.mat"
{session_extra}
""")
    return config


def test_pipeline_writes_one_file_per_alignment(tmp_path, capsys):
    config = _write_config(tmp_path)
    assert main([str(config)]) == 0

    out = tmp_path / "out"
    names = sorted(p.name for p in out.iterdir())
    assert names == [
        "T_CHKDLAY_DLPFC_20220309_CheckerboardAligned.h5",
        "T_CHKDLAY_DLPFC_20220309_TargetsAligned.h5",
    ]

    aligned = AlignedSpikes.load(out / names[1])
    assert aligned.spike_counts.shape == (6, 2, 150)  # both sorted units have >= 50 spikes
    assert aligned.unit_criteria == {"min_num_spikes": 50}
    assert aligned.metadata["monkey_id"] == "T"
    np.testing.assert_array_equal(
        aligned.trial_params["trial_RTs"], [np.nan, 401, 402, 403, 404, 405]
    )

    # A rerun skips existing files; --overwrite redoes them.
    assert main([str(config)]) == 0
    assert "skipping" in capsys.readouterr().out
    assert main([str(config), "--overwrite"]) == 0


def test_session_criteria_merge_over_global(tmp_path):
    config = load_config(_write_config(tmp_path, session_extra="criteria = { min_snr = 2.0 }"))
    assert config["sessions"][0]["criteria"] == {"min_num_spikes": 50, "min_snr": 2.0}
    assert config["sessions"][0]["all_trials_path"] == tmp_path / "TCHKDLAY20220309.mat"


def test_dry_run_writes_nothing(tmp_path, capsys):
    assert main([str(_write_config(tmp_path)), "--dry-run"]) == 0
    assert not (tmp_path / "out").exists()
    assert "new" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("session_extra", "top_extra", "message"),
    [
        ("bin_sise = 0.01", "", "unknown setting"),  # typo
        ('kilosort_dir = "ks"', "", "unknown setting"),  # Neuropixels setting on a Plexon session
        ("criteria = { min_snrr = 2 }", "", "criteria"),
        ('probe = "openephys"', "", None),  # duplicate key -> TOML error
    ],
)
def test_invalid_configs_are_rejected(tmp_path, session_extra, top_extra, message):
    config = _write_config(tmp_path, session_extra, top_extra)
    if message is None:
        assert main([str(config)]) == 2
        return
    with pytest.raises(ConfigError, match=message):
        load_config(config)
    assert main([str(config)]) == 2


def _write_neuropixels_config(tmp_path, session_extra=""):
    config = tmp_path / "config.toml"
    config.write_text(f"""
output_dir = "out"

[[alignments]]
event_name = "CheckerboardDrawnTime"
pre_time = 0.5
post_time = 1.0

[[sessions]]
probe = "neuropixels"
monkey_id = "B"
session_date = "20250325"
kilosort_dir = "SESS/SESS_imec0/kilosort"
events_path = "CFDeventStruct.mat"
{session_extra}
""")
    return config


def test_sync_clocks_options(tmp_path):
    config = load_config(
        _write_neuropixels_config(
            tmp_path, 'sync_clocks = true\nnidaq_sync_channel = 2\nnidaq_bin_path = "s.nidq.bin"'
        )
    )
    session = config["sessions"][0]
    assert session["sync_clocks"] is True
    assert session["nidaq_sync_channel"] == 2
    assert session["nidaq_bin_path"] == tmp_path / "s.nidq.bin"


@pytest.mark.parametrize(
    ("session_extra", "message"),
    [
        ("nidaq_sync_channel = 2", "only apply with sync_clocks"),
        ('sync_clocks = "yes"', "true or false"),
    ],
)
def test_invalid_sync_clocks_options_are_rejected(tmp_path, session_extra, message):
    with pytest.raises(ConfigError, match=message):
        load_config(_write_neuropixels_config(tmp_path, session_extra))


def test_sync_clocks_rejected_on_plexon_session(tmp_path):
    with pytest.raises(ConfigError, match="unknown setting"):
        load_config(_write_config(tmp_path, session_extra="sync_clocks = true"))
