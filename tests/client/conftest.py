"""Test setup for the vendored client's own suite.

These tests came from the standalone client repo in s07 and use `aresponses`,
which runs a real local HTTP server. Home Assistant's test harness installs
pytest_socket and blocks all socket use by default, so without this every test
that touches the transport fails with SocketBlockedError -- an environment
mismatch, not a defect in the code under test.
"""

import pytest


@pytest.fixture(autouse=True)
def _allow_local_sockets(socket_enabled):
    """Permit the loopback server aresponses needs, for this directory only."""
    return socket_enabled
