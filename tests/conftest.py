"""Pytest configuration for pybmap tests."""

import os

import pytest

#: Environment variables that change what ``pybmap.connect()`` does. Any of
#: these leaking out of one test would silently redirect the next one to the
#: mock device or to a fixed address, so they are snapshotted and restored
#: around every test rather than trusted to each test's own cleanup.
_CONNECTION_ENV = (
    "BMAP_MOCK", "BMAP_MAC", "BOSE_MAC", "BMAP_DEVICE", "BMAP_TIMEOUT",
)


@pytest.fixture(autouse=True)
def _isolate_connection_env():
    saved = {key: os.environ.get(key) for key in _CONNECTION_ENV}
    for key in _CONNECTION_ENV:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def pytest_addoption(parser):
    parser.addoption(
        "--integration", action="store_true", default=False,
        help="Run integration tests (requires paired Bluetooth device)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="Need --integration flag to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
