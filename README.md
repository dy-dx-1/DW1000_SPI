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

with DW1000(bus=0, cs=0, channel=5, PRF=64, bitrate=7,
            preamble_length=128, preamble_code=9, smart_tx_power=True) as dw:
    dw.transmit([0x01, 0x02, 0x03], ranging=False)
    data = dw.listen(timeout=0.1)
```

Ranging: `transmit(..., ranging=True)` returns `(ok, tx_timestamp)` and
`listen(ranging=True)` returns `(data, rx_timestamp)`; timestamps are raw 40-bit
ticks, convert to seconds with `DW1000.TIME_UNIT`.

## Listen timeout

`listen(timeout=...)` is the maximum time to wait for a frame to **start** (preamble detected).
If a frame starts within that window, `listen()` keeps going until the frame has had time to finish,
so frames are never cut off at the end of the window. A call can therefore take up to `timeout` plus
one frame's air time.

When no `timeout` is given, `DW1000.DEFAULT_LISTEN_TIMEOUT` is used (15 ms by default). Choose it
from your protocol, not from the radio settings. It should be at least the time the other device needs
before it starts sending (for example its reply delay), plus a few ms for Python/OS scheduling jitter.
The frame's own air time does not need to be included. It is read at every call, so you can change it
at any time:

```python
DW1000.DEFAULT_LISTEN_TIMEOUT = 0.05   # all devices
dw.DEFAULT_LISTEN_TIMEOUT = 0.05       # one device
dw.listen(timeout=0.05)                # one call
```

`dw.frame_duration(n_bytes)` returns the approximate air time of a frame with the current settings,
which helps when choosing reply delays and timeouts:

| Settings | Max-size frame (125 bytes) |
|---|---|
| 6.8 Mbps, 128-symbol preamble | ~0.3 ms |
| 850 kbps, 1024-symbol preamble | ~2.3 ms |
| 110 kbps, 2048-symbol preamble | ~12.2 ms |
| 110 kbps, 4096-symbol preamble | ~14.3 ms |

## Bitrate and type hints

The DW1000 supports three bitrates: 110 kbps, 850 kbps and 6.8 Mbps. For 6.8 Mbps you can pass
`bitrate=6`, `bitrate=6.8` or `bitrate=7`; all three configure exactly the same 6.8 Mbps bitrate.

The package ships type hints (it includes a `py.typed` marker), so type checkers such as mypy or
Pylance check your arguments against them. `bitrate` is annotated as `Literal[110, 850, 6, 7]`,
because Python's `Literal` type cannot contain floats. As a result, `bitrate=6.8` works fine at
runtime but a type checker will flag it. Use `6` or `7` if you want type-checked code.

## Notes

Always use the context manager so the SPI connection is closed properly.
Only the standard SFD and standard (<=127 byte) frames are currently supported.

Messages use the standard `logging` module (logger name `dw1000_spi`). By default only real warnings
are shown (e.g. a transmit timeout). Pass `verbose=True` to `DW1000(...)` to also see status messages,
or configure it yourself, e.g. `logging.getLogger("dw1000_spi").setLevel(logging.DEBUG)`.
