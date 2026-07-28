"""Write coordinator re-entrancy smoke test."""

from app.concurrency import WriteCoordinator


def test_write_coordinator_is_reentrant():
    coordinator = WriteCoordinator()
    with coordinator.write():
        with coordinator.write():
            assert True

