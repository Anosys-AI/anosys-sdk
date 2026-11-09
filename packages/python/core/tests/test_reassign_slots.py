"""Dynamic column allocation in reassign(): no shared columns, reserved slots protected."""

from anosys_sdk_core.models import BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES
from anosys_sdk_core.util.batching import RESERVED_SLOTS, SLOT_LIMITS, reassign


def test_keys_from_later_calls_do_not_reuse_columns():
    key_to_cvs = BASE_KEY_MAPPING.copy()
    first = reassign({"attr_a": "x"}, key_to_cvs, DEFAULT_STARTING_INDICES)
    second = reassign({"attr_b": "y"}, key_to_cvs, DEFAULT_STARTING_INDICES)
    assert set(first) & set(second) == set()
    assert key_to_cvs["attr_a"] != key_to_cvs["attr_b"]
    # the same key keeps its column
    assert reassign({"attr_a": "z"}, key_to_cvs, DEFAULT_STARTING_INDICES) == {key_to_cvs["attr_a"]: "z"}


def test_dynamic_numbers_skip_fixed_columns():
    key_to_cvs = BASE_KEY_MAPPING.copy()   # server.port is fixed to cvn3, the dynamic start
    out = reassign({"retries": 4}, key_to_cvs, DEFAULT_STARTING_INDICES)
    assert "cvn3" not in out and key_to_cvs["retries"] != "cvn3"


def test_reserved_and_exhausted_slots():
    key_to_cvs = {}
    data = {f"k{i}": f"v{i}" for i in range(250)}
    out = reassign(data, key_to_cvs, {"string": 100, "number": 1, "bool": 1})
    assert not RESERVED_SLOTS & set(out)
    assert len(out) == SLOT_LIMITS["cvs"] - 99 - len(RESERVED_SLOTS)   # cvs100..cvs197
    assert len(set(key_to_cvs.values())) == len(key_to_cvs)            # no two keys share a column


def test_fixed_reserved_mappings_still_work():
    key_to_cvs = BASE_KEY_MAPPING.copy()
    out = reassign({"raw": "{}", "source": "x", "consent": "full;app"}, key_to_cvs, DEFAULT_STARTING_INDICES)
    assert out == {"cvs199": "{}", "cvs200": "x", "cvs198": "full;app"}
