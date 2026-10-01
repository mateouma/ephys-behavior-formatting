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

## Layout

```
src/ephys_behavior_formatting/   package code
tests/                           pytest tests
scripts/                         setup / utility scripts
OLDPIPELINEFILES/                reference copy of the old (poetry-based) pipeline
```
