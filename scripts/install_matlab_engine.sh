#!/usr/bin/env bash
# Install MATLAB Engine for Python into the active conda env.
#
# Usage (with the env activated):
#   bash scripts/install_matlab_engine.sh [matlabroot]
#
# matlabroot defaults to the directory containing the `matlab` executable on PATH,
# falling back to /usr/local/MATLAB. The matlabengine version must match the
# MATLAB release (e.g. R2024a -> 24.1.x), which is read from VersionInfo.xml.
set -euo pipefail

if [[ $# -ge 1 ]]; then
    MATLABROOT="$1"
elif command -v matlab >/dev/null 2>&1; then
    MATLABROOT="$(dirname "$(dirname "$(readlink -f "$(command -v matlab)")")")"
else
    MATLABROOT=/usr/local/MATLAB
fi

VERSION_XML="$MATLABROOT/VersionInfo.xml"
if [[ ! -f "$VERSION_XML" ]]; then
    echo "No MATLAB install found at $MATLABROOT (missing VersionInfo.xml)." >&2
    exit 1
fi

# e.g. <version>24.1.0.2653294</version> -> 24.1
MAJOR_MINOR="$(sed -n 's:.*<version>\([0-9]*\.[0-9]*\)\..*</version>.*:\1:p' "$VERSION_XML")"
NEXT_MINOR="${MAJOR_MINOR%.*}.$(( ${MAJOR_MINOR#*.} + 1 ))"
echo "MATLAB at $MATLABROOT (engine version $MAJOR_MINOR.x)"

export LD_LIBRARY_PATH="$MATLABROOT/bin/glnxa64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
python -m pip install "matlabengine>=${MAJOR_MINOR},<${NEXT_MINOR}"
