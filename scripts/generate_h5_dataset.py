#!/usr/bin/env python
"""Generate event-aligned h5 datasets for the sessions in a TOML config.

Usage (with the ephys-fmt env active):

    python scripts/generate_h5_dataset.py scripts/example_config.toml --dry-run
    python scripts/generate_h5_dataset.py scripts/example_config.toml
    python scripts/generate_h5_dataset.py my_config.toml --only 20250325 --overwrite

See ``ephys_behavior_formatting.pipeline`` for the config format.
"""

import sys

from ephys_behavior_formatting.pipeline import main

if __name__ == "__main__":
    sys.exit(main())
