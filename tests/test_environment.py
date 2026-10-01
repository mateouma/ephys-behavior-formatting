"""Smoke tests that the conda environment provides what the pipeline imports."""

import importlib

import pytest

MODULES = [
    "ephys_behavior_formatting",
    "numpy",
    "scipy",
    "pandas",
    "h5py",
    "matplotlib",
    "neo",
    "spikeinterface",
    "mat73",
    "npyx",
    "npyx.spk_wvf",
    "npyx.spk_t",
    "npyx.inout",
    "npyx.c4.acg_augmentations",
    "tkinter",
]


@pytest.mark.parametrize("name", MODULES)
def test_import(name):
    importlib.import_module(name)


def test_matlab_engine_importable():
    pytest.importorskip("matlab.engine")
