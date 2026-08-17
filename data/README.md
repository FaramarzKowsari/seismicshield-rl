# Data policy

`fixtures/synthetic_pulse.csv` is generated analytically and exists only to test software determinism. It is **not an earthquake record** and must never be used as empirical evidence.

The planned real-record pipeline prioritizes openly documented strong-motion sources such as AFAD/TADAS for Türkiye. Every acquired record must have a stable local ID, source metadata, acquisition timestamp, units, preprocessing log and checksum. Restricted datasets may have adapters but must not become mandatory for reproducing the public benchmark.
