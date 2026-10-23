import pytest

pytest.importorskip("spidev")  # driver imports spidev (Linux only)

from dw1000_spi import DW1000


def test_valid_config():
    assert DW1000.check_valid_uwb_config(5, 64, 6.8, 128, 9, True)


def test_invalid_preamble_code():
    assert not DW1000.check_valid_uwb_config(5, 64, 6.8, 128, 1, True)


def test_smart_tx_needs_6_8():
    assert not DW1000.check_valid_uwb_config(5, 64, 110, 2048, 9, True)
