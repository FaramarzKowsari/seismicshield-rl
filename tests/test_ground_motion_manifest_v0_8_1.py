from scripts.build_ground_motion_manifest_v0_8_1 import (
    EXPECTED_EVENTS,
    EXPECTED_RECORDS,
    PARTITIONS_V0_8_1,
    RECORDS_PER_EVENT,
    partition_for_event_rank,
)


def test_v0_8_1_manifest_dimensions_match_public_osf_registration():
    assert EXPECTED_EVENTS == 34
    assert EXPECTED_RECORDS == 136
    assert RECORDS_PER_EVENT == 4
    assert PARTITIONS_V0_8_1 == (
        ("training", 13),
        ("validation", 5),
        ("pilot", 4),
        ("confirmatory", 12),
    )


def test_v0_8_1_positional_partition_rule_is_exact():
    assert [partition_for_event_rank(i) for i in range(1, 14)] == ["training"] * 13
    assert [partition_for_event_rank(i) for i in range(14, 19)] == ["validation"] * 5
    assert [partition_for_event_rank(i) for i in range(19, 23)] == ["pilot"] * 4
    assert [partition_for_event_rank(i) for i in range(23, 35)] == ["confirmatory"] * 12
