"""Tests of the formatting pipeline on small synthetic datasets."""

import h5py
import numpy as np
import pandas as pd
import pytest
import scipy.io as sio

from ephys_behavior_formatting import AlignedSpikes, PlexonExperiment, Unit, UnitCriteria
from ephys_behavior_formatting.aligned import bin_spikes, make_bin_edges
from ephys_behavior_formatting.behavior import (
    chronometric_table,
    load_performance,
    psychometric_table,
)
from ephys_behavior_formatting.trials import event_times, load_event_struct, trial_params
from ephys_behavior_formatting.units import compute_unit_metrics

RNG = np.random.default_rng(0)


# ----------------------------------------------------------------- binning
def test_make_bin_edges():
    edges = make_bin_edges(0.4, 2.0, 0.001)
    assert len(edges) == 2401
    assert edges[0] == pytest.approx(-0.4) and edges[-1] == pytest.approx(2.0)


def test_bin_spikes_assigns_left_closed_bins():
    spikes = np.array([0.95, 1.0, 1.05, 1.1, 1.1, 2.5])
    counts = bin_spikes(spikes, np.array([1.0, 2.0]), np.array([-0.1, 0.0, 0.1, 0.2]))
    # trial 1: [0.9,1.0) has 0.95; [1.0,1.1) has 1.0 and 1.05; [1.1,1.2) has both 1.1s
    np.testing.assert_array_equal(counts, [[1, 2, 2], [0, 0, 0]])


# ------------------------------------------------------------------- units
def _unit(unit_id=1, rate=10.0, duration=300.0, label="good"):
    spikes = np.sort(RNG.uniform(0, duration, int(rate * duration)))
    template = -np.exp(-((np.arange(40) - 15) ** 2) / 10) * 100
    waveforms = template + RNG.normal(0, 5, (200, 40))
    return Unit(unit_id, spikes, waveforms, label)


def test_unit_metrics_are_sensible():
    unit = _unit(rate=10.0)
    metrics = unit.quality_metrics()
    assert metrics["firing_rate"] == pytest.approx(10.0, rel=0.05)
    assert metrics["presence_ratio"] == 1.0
    assert metrics["snr"] > 5
    assert 0 <= metrics["amplitude_cutoff"] <= 0.5


def test_isi_violations_detects_refractory_spikes():
    clean = Unit(1, np.arange(0, 100, 0.01), np.zeros((0, 40)))
    contaminated = Unit(
        2, np.sort(np.r_[clean.spike_times, clean.spike_times[::10] + 0.0005]), np.zeros((0, 40))
    )
    assert clean.isi_violations()[1] == 0
    assert contaminated.isi_violations()[1] == 1000
    assert np.isnan(contaminated.snr())  # no waveforms


def test_unit_criteria():
    units = [
        _unit(1, rate=10),
        _unit(2, rate=0.5),
        _unit(3, rate=10, label="mua"),
        _unit(4, rate=10, duration=30),
    ]
    metrics = compute_unit_metrics(units)

    assert UnitCriteria(min_firing_rate=1.0).mask(metrics).to_dict() == {
        1: True,
        2: False,
        3: True,
        4: True,
    }
    assert list(UnitCriteria(quality_labels=("good",)).mask(metrics)) == [True, True, False, True]
    # presence_ratio is NaN for a unit spanning < 60 s, which fails the threshold
    assert not UnitCriteria(min_presence_ratio=0.9).mask(metrics)[4]
    crit = UnitCriteria(min_firing_rate=1.0, include_ids=[2], exclude_ids=[1])
    assert crit.mask(metrics).to_dict() == {1: False, 2: True, 3: True, 4: True}
    assert crit.describe() == {"min_firing_rate": 1.0, "include_ids": [2], "exclude_ids": [1]}


# -------------------------------------------------------- AlignedSpikes I/O
def _aligned():
    n_trials, n_units, n_bins = 5, 3, 10
    return AlignedSpikes(
        spike_counts=RNG.integers(0, 3, (n_trials, n_units, n_bins)).astype(np.uint16),
        bin_edges=make_bin_edges(0.004, 0.006, 0.001),
        event_name="CheckerboardDrawnTime",
        unit_ids=np.array([3, 7, 9]),
        unit_quality_labels=np.array(["good", "mua", "good"]),
        trial_params={
            "trial_outcomes": np.array(["correct", "incorrect"] * 2 + ["correct"]),
            "trial_cues": np.arange(n_trials),
        },
        trial_indices=np.array([0, 1, 2, 4, 5]),
        metadata={
            "monkey_id": "B",
            "session_date": "20250325",
            "roi": "DLPFC",
            "task_type": "CHKDLAY",
            "probe_type": "Neuropixels",
        },
        unit_metrics=pd.DataFrame(
            {"snr": [1.0, 2.0, 3.0], "quality_label": ["good", "mua", "good"]},
            index=pd.Index([3, 7, 9], name="unit_id"),
        ),
        unit_criteria={"min_snr": 1.0},
    )


def test_aligned_save_load_roundtrip(tmp_path):
    aligned = _aligned()
    path = aligned.save(tmp_path)
    assert path.name == "B_CHKDLAY_DLPFC_20250325_CheckerboardAligned.h5"
    with pytest.raises(FileExistsError):
        aligned.save(tmp_path)

    loaded = AlignedSpikes.load(path)
    np.testing.assert_array_equal(loaded.spike_counts, aligned.spike_counts)
    np.testing.assert_allclose(loaded.bin_edges, aligned.bin_edges)
    np.testing.assert_array_equal(loaded.unit_quality_labels, aligned.unit_quality_labels)
    for key, values in aligned.trial_params.items():
        np.testing.assert_array_equal(loaded.trial_params[key], values)
    pd.testing.assert_frame_equal(loaded.unit_metrics, aligned.unit_metrics, check_like=True)
    assert loaded.metadata == aligned.metadata
    assert loaded.unit_criteria == {"min_snr": 1.0}
    assert loaded.spike_counts.dtype == np.uint8  # stored in the smallest integer type


def test_aligned_selections():
    aligned = _aligned()
    window = aligned.time_window(0.0, 0.003)
    np.testing.assert_allclose(window.bin_starts, [0.0, 0.001, 0.002], atol=1e-12)
    np.testing.assert_array_equal(window.spike_counts, aligned.spike_counts[:, :, 4:7])

    correct = aligned.select_trials(aligned.trial_params["trial_outcomes"] == "correct")
    assert correct.n_trials == 3
    np.testing.assert_array_equal(correct.trial_indices, [0, 2, 5])


# ------------------------------------------------------------------ trials
def _event_struct(path, n_trials=4):
    fields = [
        "TrialEventTimes",
        "RT",
        "correctness",
        "chosenSide",
        "ParameterData",
        "cue",
        "leftTarget",
        "rightTarget",
    ]
    events = np.zeros((1, n_trials), dtype=[(f, "O") for f in fields])
    for i in range(n_trials):
        events[0, i] = (
            {"CheckerboardDrawnTime": 20000.0 * (i + 1), "TargetsDrawnTime": np.array([])},
            700 + i,
            [1, 99][i % 2],
            [1, 2][i // 2],
            f"TT:2,LT:3,RT:2,Cue:{100 + i},CR:2,D:{600 + i},STIM:900,TID:1,ST:{1 + i // 2},UID:{1000 + i}",
            100 + i,
            [2, 3][i % 2],
            [3, 2][i % 2],
        )
    sio.savemat(path, {"CFDeventStruct": events})
    return path


def test_trial_params_from_event_struct(tmp_path):
    events = load_event_struct(_event_struct(tmp_path / "CFDeventStruct.mat"))
    params = trial_params(events)
    np.testing.assert_array_equal(
        params["trial_outcomes"], ["correct", "incorrect", "correct", "incorrect"]
    )
    np.testing.assert_array_equal(
        params["trial_action_choices"], ["right", "right", "left", "left"]
    )
    # codes: 2 = green, 3 = red; configs read left to right
    np.testing.assert_array_equal(params["trial_configs"], ["GR", "RG", "GR", "RG"])
    np.testing.assert_array_equal(params["trial_color_choices"], ["red", "green", "green", "red"])
    np.testing.assert_array_equal(params["trial_cues"], [100, 101, 102, 103])
    np.testing.assert_array_equal(params["trial_delay_lengths"], [600, 601, 602, 603])
    np.testing.assert_array_equal(params["trial_savetags"], [1, 1, 2, 2])
    assert "trial_coherences" not in params

    np.testing.assert_allclose(event_times(events, "CheckerboardDrawnTime", 20000.0), [1, 2, 3, 4])
    assert np.isnan(event_times(events, "TargetsDrawnTime", 20000.0)).all()


def test_target_colors_ground_truth():
    """Cue > 112, correct, rightward reach: the monkey chose red, so red was on the right."""
    from ephys_behavior_formatting.trials import target_colors

    configs, colors = target_colors(np.array([2]), np.array([3]), np.array(["right"]))
    assert configs[0] == "GR" and colors[0] == "red"


# ------------------------------------------------------------------ Plexon
def _plexon_session(path, n_trials=6):
    """An allTrials file in the format PlexonSessionProcessor.save writes."""
    trials = []
    for i in range(n_trials):
        start = 10_000.0 * i  # ms
        correct = i % 3 != 0
        n_spikes = 50
        channel = np.repeat([1, 1, 2], [20, 20, 10]).astype(np.uint16)
        unit = np.repeat([0, 1, 1], [20, 20, 10]).astype(np.uint8)
        trials.append(
            {
                "events": {
                    "GlobalTrialId": i,
                    "SaveTag": 1 + i // 3,
                    "UniqueId": 6.4e10 + 10 * i,
                    "MonkeyName": "T",
                    "CheckerboardDrawnTime": start + 1000.0,
                    "TargetsDrawnTime": start + 2000.0,
                    "TrialOutcome": "Correct Choice" if correct else "Wrong Choice",
                },
                "params": {
                    "CorrectResponse": 1 + i % 2,
                    "LeftTargetColor": 2 + i % 2,
                    "RightTargetColor": 3 - i % 2,
                    "CentralCuenSquares": 50 + i,
                    "Delay": 600.7 + i,
                    "TrialType": 2,
                },
                "spikes": {
                    "xPCtimeStamp": start + np.sort(RNG.uniform(0, 3000, n_spikes)).round(),
                    "channelId": channel,
                    "unit": unit,
                    "data": RNG.integers(-100, 100, (n_spikes, 80)).astype(np.int16),
                },
                "TrialOutcome": "Correct Choice" if correct else "Wrong Choice",
                "SaveTag": 1 + i // 3,
                "TrialType": 2,
                "header": {"fileId": f"Tiberius-CHKDLAY-CONT-{i}.dat"},
            }
        )
    # Stored out of order, like the old processor's file-listing order.
    trials = [trials[k] for k in [3, 0, 5, 1, 4, 2]]
    sio.savemat(path, {"allTrials": trials, "badTrials": {"BrokeCenter": 0}})
    return path


def test_plexon_experiment(tmp_path):
    path = _plexon_session(tmp_path / "TiberiusCHKDLAY20220309.mat")
    exp = PlexonExperiment(path, monkey_id="T", session_date="20220309")

    assert exp.available_units() == {101: "good", 201: "good"}  # unsorted unit 0 excluded
    exp.load_units()
    assert exp.get_unit(101).num_spikes == 6 * 20

    params = exp.trial_params
    np.testing.assert_array_equal(params["trial_outcomes"], ["incorrect", "correct", "correct"] * 2)
    # CorrectResponse 1 = right, 2 = left; error trials chose the other side
    # CorrectResponse alternates 1, 2, ...; trials 0 and 3 are errors
    np.testing.assert_array_equal(
        params["trial_action_choices"], ["left", "left", "right", "right", "right", "left"]
    )
    np.testing.assert_array_equal(params["trial_delay_lengths"], np.floor(600.7 + np.arange(6)))
    assert np.isnan(params["trial_RTs"]).all()  # no events_path given
    np.testing.assert_array_equal(params["trial_configs"], ["GR", "RG"] * 3)
    np.testing.assert_array_equal(
        params["trial_color_choices"], ["green", "red", "red", "green", "red", "red"]
    )

    aligned = exp.align_spikes(
        "CheckerboardDrawnTime", pre_time=0.5, post_time=1.0, bin_size=0.01, savetags=[2]
    )
    assert aligned.spike_counts.shape == (3, 2, 150)
    np.testing.assert_array_equal(aligned.trial_indices, [3, 4, 5])
    assert aligned.metadata["probe_type"] == "Plexon"

    with_unsorted = PlexonExperiment(
        path, "T", "20220309", include_unsorted=True, valid_savetags=[1]
    )
    assert with_unsorted.available_units()[100] == "unsorted"
    assert with_unsorted.n_trials == 3


def _cfd_for_plexon_session(path, cue_offset=0):
    """A CFD event struct for the trials of ``_plexon_session``, minus its first trial.

    Odd trials' unique ids are 1 s off, as happens in real data.
    """
    fields = ["TrialEventTimes", "RT", "correctness", "chosenSide", "ParameterData", "cue",
              "leftTarget", "rightTarget"]  # fmt: skip
    trial_ids = range(1, 6)
    events = np.zeros((1, len(trial_ids)), dtype=[(f, "O") for f in fields])
    for n, i in enumerate(trial_ids):
        chose_right = ["left", "left", "right", "right", "right", "left"][i] == "right"
        uid = int(6.4e10) + 10 * i - i % 2
        events[0, n] = (
            {"TargetsDrawnTime": 0.0},
            400 + i,
            1 if i % 3 != 0 else 99,
            1 if chose_right else 2,
            f"TT:2,Cue:{50 + i},D:600,ST:{1 + i // 3},UID:{uid}",
            50 + i + cue_offset,
            2 + i % 2,
            3 - i % 2,
        )
    sio.savemat(path, {"CFDeventStruct": events})
    return path


def test_plexon_reaction_times_from_event_struct(tmp_path):
    session = _plexon_session(tmp_path / "TiberiusCHKDLAY20220309.mat")
    events = _cfd_for_plexon_session(tmp_path / "CFDeventStruct.mat")
    exp = PlexonExperiment(session, "T", "20220309", events_path=events)
    np.testing.assert_array_equal(exp.trial_params["trial_RTs"], [np.nan, 401, 402, 403, 404, 405])

    # A struct whose trials disagree with allTrials is rejected rather than misassigned.
    bad = _cfd_for_plexon_session(tmp_path / "bad.mat", cue_offset=1)
    with pytest.raises(ValueError, match="trial_cues"):
        PlexonExperiment(session, "T", "20220309", events_path=bad).trial_params_frame()


def test_match_unique_ids():
    from ephys_behavior_formatting.trials import match_unique_ids

    np.testing.assert_array_equal(match_unique_ids([10, 21, 30, 50], [31, 10, 20]), [1, 2, 0, -1])
    np.testing.assert_array_equal(match_unique_ids([5], [5]), [0])
    with pytest.raises(ValueError):
        match_unique_ids([10, 11], [10])


# ---------------------------------------------------------------- behavior
def _performance_file(path, rows):
    """A MATLAB v7.3-style file: allTrials/performance holds references to per-trial groups."""
    with h5py.File(path, "w") as f:
        refs = []
        for i, row in enumerate(rows):
            group = f.create_group(f"#refs#/t{i}")
            for key, value in row.items():
                data = (
                    np.array([[float(value)]])
                    if not isinstance(value, str)
                    else np.array([[ord(c)] for c in value], dtype=np.uint16)
                )
                group.create_dataset(key, data=data)
            refs.append(group.ref)
        f.create_group("allTrials").create_dataset(
            "performance", data=np.array(refs).reshape(-1, 1), dtype=h5py.ref_dtype
        )


def test_behavior_tables(tmp_path):
    rows = [
        {"CueV": 225.0, "ChosenColor": "red", "RT": 400.0},
        {"CueV": 225.0, "ChosenColor": "green", "RT": 500.0},
        {"CueV": 0.0, "ChosenColor": "green", "RT": 600.0},
    ]
    _performance_file(tmp_path / "allTrials.mat", rows)
    performance = load_performance(tmp_path / "allTrials.mat")
    assert list(performance["ChosenColor"]) == ["red", "green", "green"]

    psych = psychometric_table(performance)
    np.testing.assert_allclose(psych["signed_coherence"], [-100, 100])
    np.testing.assert_allclose(psych["p_red"], [0.0, 0.5])
    chrono = chronometric_table(performance)
    np.testing.assert_allclose(chrono["mean_rt"], [600.0, 450.0])
