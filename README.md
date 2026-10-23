# dw1000-spi

Python driver for the Decawave (Qorvo) DW1000 UWB transceiver over SPI, using `spidev`.
Runs on Linux boards with SPI (e.g. Raspberry Pi).

## Install

```bash
pip install dw1000-spi
```

## Usage

```python
from dw1000_spi import DW1000

with DW1000(bus=0, cs=0, channel=5, PRF=64, bitrate=6.8,
            preamble_length=128, preamble_code=9, smart_tx_power=True) as dw:
    dw.transmit([0x01, 0x02, 0x03], ranging=False)
    data = dw.listen(timeout=0.1)
```

Ranging: `transmit(..., ranging=True)` returns `(ok, tx_timestamp)` and
`listen(ranging=True)` returns `(data, rx_timestamp)`; timestamps are raw 40-bit
ticks, convert to seconds with `DW1000.TIME_UNIT`.

Always use the context manager so the SPI connection is closed properly.
Only the standard SFD and standard (<=127 byte) frames are currently supported.
