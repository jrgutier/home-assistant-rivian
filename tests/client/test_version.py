"""Test the module version."""

from custom_components.rivian.rivian_client import __version__ as VERSION


def test_version() -> None:
    """Test version."""
    assert VERSION != "0.0.0"
