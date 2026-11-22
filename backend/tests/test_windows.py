"""The Windows calls framewise makes, run for real on Windows and skipped elsewhere."""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="needs Windows")

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def execution_state() -> int:
    """This thread's execution state, read by setting it to what it already continuously is."""
    import ctypes

    set_state = ctypes.windll.kernel32.SetThreadExecutionState
    set_state.restype = ctypes.c_uint32
    set_state.argtypes = [ctypes.c_uint32]
    state = set_state(ES_CONTINUOUS)
    set_state(state)
    return state


def test_keeping_the_machine_awake_holds_off_sleep_until_the_block_ends():
    from framewise.cli import keep_machine_awake

    with keep_machine_awake():
        assert execution_state() & ES_SYSTEM_REQUIRED

    assert not execution_state() & ES_SYSTEM_REQUIRED
