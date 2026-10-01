"""Calibrated hardware constants for lab recording rigs."""

#: Measured sample rate (Hz) of the NI-DAQ card that records task events.
#: Used instead of the nominal rate in the .nidq.meta file.
NI_TRUE_SAMPLE_RATE = 19999.72

#: Measured sample rates (Hz) of each Neuropixels headstage, keyed by serial
#: number (``imDatHs_sn`` in the .ap.meta file).
HEADSTAGE_TRUE_SAMPLE_RATE = {
    "21140060": 30000.07511,
    "21140015": 30000.10391,
    "21460062": 30000.14581,
    "21140115": 30000.13073,
    "21460131": 29999.939496,
}
