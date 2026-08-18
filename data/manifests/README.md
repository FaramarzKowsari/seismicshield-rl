# Ground-motion manifest contract

The frozen target is **40 known physical earthquake events and 160 real horizontal
acceleration records**: exactly four retained records per event. Splitting occurs at the
event level; an event may never leak between partitions. The allocation is 18 training
events (72 records), 6 validation events (24), 4 pilot events (16), and 12 confirmatory
events (48). Pilot events are permanently excluded from confirmatory inference because
they may inform feasibility decisions before the confirmatory analysis.

Eligibility requires a known physical event identity, horizontal acceleration, units
that convert deterministically to SI, `dt <= 0.020 s`, usable duration of at least 10 s,
absolute PGA of at least `0.15 g`, and complete provenance. The builder orders events
and records by SHA-256 using the frozen `SeismicShield-RL-v0.8.0-OSF-2026` salt, rather
than inspecting motion outcomes. It fails closed if the exact target cannot be met.

Source licensing and redistribution terms must be honored. The manifest records a URL
or durable access reference and cryptographic hashes; restricted raw data must remain
at its licensed source rather than being republished. Blank, placeholder, invented, or
synthetic earthquake records are forbidden. Synthetic metadata may exist only in
temporary test directories as explicitly labeled software-validation fixtures and must
never be written to this directory as a real manifest.

