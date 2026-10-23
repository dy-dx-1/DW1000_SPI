import spidev 
import logging
import time 
from typing import Literal, overload

# Library logger. Without any configuration, Python shows only WARNING and above (on stderr).
# Apps can opt in to more with e.g. logging.basicConfig(level=logging.INFO), or use verbose=True.
logger = logging.getLogger(__name__)
_PKG_LOGGER = logging.getLogger("dw1000_spi")


def _enable_console_logging()->None:
    """ Attaches a console handler showing INFO and above for the dw1000_spi logger (only once per process). """
    if not any(getattr(h, "_dw1000_console", False) for h in _PKG_LOGGER.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[DW1000] %(levelname)s: %(message)s"))
        setattr(handler, "_dw1000_console", True)  # marker so we never add it twice
        _PKG_LOGGER.addHandler(handler)
    if _PKG_LOGGER.level == logging.NOTSET or _PKG_LOGGER.level > logging.INFO:
        _PKG_LOGGER.setLevel(logging.INFO)

# Channel-specific UWB configuration values
# Maps channel -> {register_name: [values]}
_CHANNEL_RF_CONFIG = {
    1: {
        '0x28_B': [0xD8],
        '0x28_C': [0x40, 0x5C, 0x00, 0x00],
        '0x2A'  : [0xC9],
        '0x2B_7': [0x07, 0x04, 0x00, 0x09],
        '0x2B_B': [0x1E],
    },
    2: {
        '0x28_B': [0xD8],
        '0x28_C': [0xA0, 0x5C, 0x04, 0x00],
        '0x2A'  : [0xC2],
        '0x2B_7': [0x08, 0x05, 0x40, 0x08],
        '0x2B_B': [0x26],
    },
    3: {
        '0x28_B': [0xD8],
        '0x28_C': [0xC0, 0x6C, 0x08, 0x00],
        '0x2A'  : [0xC5],
        '0x2B_7': [0x09, 0x10, 0x40, 0x08],
        '0x2B_B': [0x5E],
    },
    4: {
        '0x28_B': [0xBC],
        '0x28_C': [0x80, 0x5C, 0x04, 0x00],
        '0x2A'  : [0x95],
        '0x2B_7': [0x08, 0x05, 0x40, 0x08],
        '0x2B_B': [0x26],
    },
    5: {
        '0x28_B': [0xD8],
        '0x28_C': [0xE0, 0x3F, 0x1E, 0x00],
        '0x2A'  : [0xC0],
        '0x2B_7': [0x1D, 0x04, 0x00, 0x08],
        '0x2B_B': [0xA6],
    },
    7: {
        '0x28_B': [0xBC],
        '0x28_C': [0xE0, 0x7D, 0x1E, 0x00],
        '0x2A'  : [0x93],
        '0x2B_7': [0x1D, 0x04, 0x00, 0x08],
        '0x2B_B': [0xA6],
    },
}

# TX power configuration: channel -> {PRF: [values]}
# Used for register 0x1E
# these are if smart TX power is disabled 
_NO_SMART_TX_POWER_CONFIG = {  
    1: {16: [0x75, 0x75, 0x75, 0x75], 64: [0x67, 0x67, 0x67, 0x67]},
    2: {16: [0x75, 0x75, 0x75, 0x75], 64: [0x67, 0x67, 0x67, 0x67]},
    3: {16: [0x6F, 0x6F, 0x6F, 0x6F], 64: [0x8B, 0x8B, 0x8B, 0x8B]},
    4: {16: [0x5F, 0x5F, 0x5F, 0x5F], 64: [0x9A, 0x9A, 0x9A, 0x9A]},
    5: {16: [0x48, 0x48, 0x48, 0x48], 64: [0x85, 0x85, 0x85, 0x85]},
    7: {16: [0x92, 0x92, 0x92, 0x92], 64: [0xD1, 0xD1, 0xD1, 0xD1]},
}

# these are if smart TX power is enabled 
_SMART_TX_POWER_CONFIG = {
    1: {16: [0x75, 0x55, 0x35, 0x15], 64: [0x67, 0x47, 0x27, 0x07]},
    2: {16: [0x75, 0x55, 0x35, 0x15], 64: [0x67, 0x47, 0x27, 0x07]},
    3: {16: [0x6F, 0x4F, 0x2F, 0x0F], 64: [0x8B, 0x6B, 0x4B, 0x2B]},
    4: {16: [0x5F, 0x3F, 0x1F, 0x1F], 64: [0x9A, 0x7A, 0x5A, 0x3A]},
    5: {16: [0x48, 0x28, 0x08, 0x0E], 64: [0x85, 0x65, 0x45, 0x25]},
    7: {16: [0x92, 0x72, 0x52, 0x32], 64: [0xD1, 0xB1, 0x71, 0x51]},
}

# LDE replica coefficient (sub-register 0x2E:2804 LDE_REPC) per RX preamble code.
# User manual Table 47 (values for 850 kbps & 6.8 Mbps; divide by 8 at 110 kbps).
_LDE_REPC = {
    1: 0x5998,  2: 0x5998,  3: 0x51EA,  4: 0x428E,  5: 0x451E,  6: 0x2E14,
    7: 0x8000,  8: 0x51EA,  9: 0x28F4, 10: 0x3332, 11: 0x3AE0, 12: 0x3D70,
   13: 0x3AE0, 14: 0x35C2, 15: 0x2B84, 16: 0x35C2, 17: 0x3332, 18: 0x35C2,
   19: 0x35C2, 20: 0x47AE, 21: 0x3AE0, 22: 0x3850, 23: 0x30A2, 24: 0x3850,
}

class DW1000:
    """
    Class defining interactions with the Decawave DW1000 UWB chip through SPI.
    Communicates in SPI mode 0. 
    
    IMPORTANT: Use a context manager to ensure that the connection is properly closed. 

    Raises RuntimeError if the chip does not answer correctly at start-up and ValueError if the UWB
    settings are invalid. Messages go through the "dw1000_spi" logger: by default only warnings are shown,
    verbose=True also prints status messages to the console.
    """
    TIME_UNIT = 1.5650040064102565e-11  # seconds / tick for the DW1000
    DW_LISTEN_TIMEOUT = 0.015           # Delay used to wait during RX 

    def __init__(self, bus:int, cs:int, channel:Literal[1,2,3,4,5,7], PRF:Literal[16,64], bitrate:Literal[110,850,6,7],
                 preamble_length:Literal[64,128,256,512,1024,1536,2048,4096], preamble_code:int, 
                 smart_tx_power:bool, tx_power_settings:list[int]|None=None, verbose:bool=False): 
        self.verbose = verbose
        if verbose:
            _enable_console_logging()  # show INFO messages on the console
        self._uwb_config:dict|None = None  # Last applied UWB settings, re-applied after a full soft reset
        self._closed = True               # Nothing to close until the port is opened
        self.spi = spidev.SpiDev() 
        self.spi.open(bus, cs) 
        self._closed = False

        try:
            self.spi.max_speed_hz = 3_000_000 # On init, should not exceed 3MHz  
            self.spi.mode = 0b00              # GPIO 5 and 6 dictate the mode, should be untouched 

            self.prep_device_for_use()        # Checks that device initialized properly and sets clock to 20MHz
            self.config_uwb_settings(channel, PRF, bitrate, preamble_length, preamble_code, smart_tx_power, tx_power_settings) # Checks validity of settings and applies them 
        except BaseException:
            # Don't leave the SPI port open if setup failed 
            try:
                self.close(verbose=False)
            except Exception:
                pass
            raise
        logger.info("DW1000 DEVICE READY")
    
    def prep_device_for_use(self): 
        """
        After a reset:
            - Checks that the device properly turned on & communicates (device ID)
            - Checks the clock PLL lock (CPLOCK) and SLEEP-to-INIT (SLP2INIT) status flags. Only logs a warning:
              the manual (SYS_STATUS, p.83) says the CPLOCK flag "may not be reliable and is only used for debug
              purposes", so it should not be treated as a hard failure.
            - Loads LDE microcode (Table 4, p.22 of user manual)
            - Sets comm speed to 20MHz

        RAISES:
            - RuntimeError if the device ID is wrong (wiring / SPI problem).
        """
        ## Checking device ID is expected for DW1000 
        d_id = self.read_register([0x00], 4, reverse=True)
        if d_id != ['0xde', '0xca', '0x1', '0x30']:
            raise RuntimeError(f"Could not validate DW1000 connection: wrong device ID, expected ['0xde', '0xca', '0x1', '0x30'], got {d_id}. Is it plugged in correctly?")
        
        ## Checking CLK PLL locked and device completed INIT mode (debug-level flags, see docstring)
        cfg = self.read_register([0x0F], 5, return_ints=True) # SYS_STATUS
        cplock = (cfg[0] >> 1) & 1    # CPLOCK: bit 1 of SYS_STATUS (bit 1 of octet 0)
        slp2init = (cfg[2] >> 7) & 1  # SLP2INIT: bit 23 of SYS_STATUS (bit 7 of octet 2)
        if not (cplock and slp2init):
            logger.warning(f"DW1000 status flags not set after start-up (CPLOCK={cplock}, SLP2INIT={slp2init}). "
                           "These flags are not fully reliable, but if communication fails, try replugging the device.")

        ## Loading LDE microcode as per steps in p.22 of user manual 
        self.write_register([0xF6, 0x00], [0x01, 0x03])
        self.write_register([0xED, 0x06], [0x00, 0x80])
        time.sleep(150e-6)
        self.write_register([0xF6, 0x00], [0x00, 0x02])
        
        ## Make sure LDE loads after sleep 
        aon = self.read_register([0x6C, 0x00], 2, return_ints=True)
        value = aon[0] | (aon[1] << 8)
        value |= (1 << 11)   # ONW_LLDE
        new_aon = [value & 0xFF, (value >> 8) & 0xFF]
        if aon!=new_aon: 
            self.write_register([0xEC, 0x00], new_aon)

        ## If we get here, DW1000 should be in IDLE state, set rate to maximum 
        self.spi.max_speed_hz = 20_000_000 # In IDLE state, can operate at 20MHz 
    
    def close(self, verbose:bool=True)->None: 
        """ Closes the SPI connection (safe to call more than once). verbose=False skips the log message. """
        if self._closed: 
            return 
        self._closed = True
        try: 
            self.write_register([0x8D], [0x40]) # turning off all RX / TX 
        finally: 
            self.spi.close() 
        if verbose: 
            logger.info("DW1000 connection closed")

    def __enter__(self):
        return self 

    def __exit__(self, exc_type, exc_val, exc_tb): 
        self.close() 
        logger.debug("DW1000 exited context manager successfully")

    def __del__(self):
        try:
            self.close(verbose=False) 
        except Exception: 
            pass 

    @overload
    def read_register(self, header:list[int], length:int, reverse:bool=..., return_ints:Literal[False]=...)->list[str]: ...
    @overload
    def read_register(self, header:list[int], length:int, reverse:bool=..., *, return_ints:Literal[True])->list[int]: ...
    @overload
    def read_register(self, header:list[int], length:int, reverse:bool=..., return_ints:bool=...)->list[int]|list[str]: ...

    def read_register(self, header:list[int], length:int, reverse:bool=False, return_ints:bool=False)->list[int]|list[str]:
        """
        Reads the value of a register. Checks argument types, but NOT that the register address,
        sub-address or length are valid for the DW1000.

        ARGS: 
            - header: 1 to 3 octet header of the transaction in list format
            - length: Size of register in octets
            - reverse: Reverse output. By default, read is done LSB first as specified in DW1000 user manual.  
            - return_ints: Return int values instead of hex strings
        RETURNS:
            - List of values read from the register (ints if return_ints, else hex strings like '0x1f').
        RAISES:
            - TypeError if header is not a list, length not an int or reverse not a bool.
        """
        if not isinstance(header, list) or not isinstance(length, int) or not isinstance(reverse, bool): 
            raise TypeError("read_register: header must be a list, length an int and reverse a bool")
        response = self.spi.xfer2(header + [0]*length) # xfer2 is supposed to keep CS pressed for the entire transaction, although some sources differ, I use it to be safe. At worst its equivalent to xfer 
        response = response[len(header):]              # throwing away the header
        if reverse: response.reverse() 
        return response if return_ints else [hex(octet) for octet in response]
    
    def write_register(self, header:list[int], data:list[int])->None:
        """
        Writes values to a register. Checks argument types, but NOT that the register address,
        sub-address or data length are valid for the DW1000.

        ARGS:
            - header: 1 to 3 octet header of the transaction in list format
            - data: List of octets to write to the register (LSB first)
        RAISES:
            - TypeError if header is not a list or data is not a non-empty list of ints.
        """
        if not isinstance(header, list) or not isinstance(data, list) or not data or not all(isinstance(b, int) for b in data): 
            raise TypeError("write_register: header must be a list and data a non-empty list of ints")
        self.spi.xfer2(header + data) 

    def soft_reset(self, rx_only:bool=False)->None:
        """
        Performs a soft reset of the IC with the SOFTRESET bits of PMSC_CTRL0 (0x36:00), as specified by the
        user manual (PMSC_CTRL0 SOFTRESET field, p.179).

        ARGS:
            - rx_only:
                - False (default): full reset of TX, RX, host interface and PMSC ("essentially a reset of the IC").
                  The device goes back through INIT, where register configurations are only restored from the AON
                  memory if that was set up (p.15), which this driver does not do. So after the reset, the start-up
                  checks and LDE microcode load are re-run, and the last UWB configuration passed to
                  config_uwb_settings() is re-applied automatically. Slow (~10ms + reconfiguration).
                - True: light RX-only reset (see _rx_reset()). Keeps clocks, SPI speed and configuration.
        RAISES:
            - RuntimeError (full reset only) if the device ID check fails afterwards.
        """
        if rx_only:
            self._rx_reset()
            logger.debug("RX-only reset of DW1000 completed.")
            return

        # Getting the initial configuration to ensure we don't overwrite bits
        pmsc = self.read_register([0x76, 0x00], 4, return_ints=True) # should be smthing like: [0, 2, 48, 240]
        # Since we are about to reset the device, lower the speed to init values
        self.spi.max_speed_hz = 3_000_000

        # Setting SYSCLKS to 01
        pmsc[0] = (pmsc[0] & 0b11111100) | 0x01 # turning first 2 bits to 0 and then 01
        self.write_register([0xF6, 0x00], pmsc)
        # Clearing SOFTRESET (bits 28-31) to all zeros
        pmsc[3] = pmsc[3] & 0x0F
        self.write_register([0xF6, 0x00], pmsc)
        # Waiting a bit
        time.sleep(0.01)
        # Setting SOFTRESET (bits 28-31) back to all ones
        pmsc[3] = (pmsc[3] & 0x0F) | 0xF0
        self.write_register([0xF6, 0x00], pmsc)
        # Setting SYSCLKS back to 00 (auto mode for reset)
        pmsc[0] = (pmsc[0] & 0b11111100) | 0x00
        self.write_register([0xF6, 0x00], pmsc) 
        
        # Reset done, run our init checks and set speed back to 20MHz
        self.prep_device_for_use()
        # Configuration registers are back to their defaults: re-apply the last UWB configuration
        if self._uwb_config is not None:
            self.config_uwb_settings(**self._uwb_config)
        logger.info("Soft reset of DW1000 completed.")

    def _rx_reset(self)->None:
        """
        Light RX-only reset: pulses the RX reset bit (bit 28 of PMSC_CTRL0, i.e. bit 4 of octet 3) low then high.
        As per the manual (PMSC_CTRL0 SOFTRESET field, p.179): "To apply a receiver-only soft reset, clear and
        set bit 28 only." No clock switch, SPI speed change or delay is needed, and the UWB configuration and LDE
        microcode are kept. Only octet 3 of PMSC_CTRL0 is touched.
        The manual (note p.31) requires this reset after any RX error or timeout event (RXPTO, RXSFDTO, RXPHE,
        RXRFSL, RXRFTO, ...) so that the next good frame gets a correctly calculated timestamp.
        """
        softreset = self.read_register([0x76, 0x03], 1, return_ints=True)[0]  # PMSC_CTRL0 octet 3 (bits 24-31)
        self.write_register([0xF6, 0x03], [softreset & ~0x10 & 0xFF])         # bit 28 low: RX held in reset
        self.write_register([0xF6, 0x03], [softreset | 0x10])                 # bit 28 high: RX released

    @overload
    def transmit(self, data:list[int], ranging:Literal[False], timeout:float=...)->bool: ...
    @overload
    def transmit(self, data:list[int], ranging:Literal[True], timeout:float=...)->tuple[bool, int|None]: ...
    @overload
    def transmit(self, data:list[int], ranging:bool, timeout:float=...)->bool|tuple[bool, int|None]: ...

    def transmit(self, data:list[int], ranging:bool, timeout:float=0.05)->bool|tuple[bool, int|None]:
        """
        Transmits a message with the DW1000 and waits until it is sent (or the timeout expires).

        ARGS:
            - data: List of bytes to send (LSB first), at most 125 bytes (+2 CRC octets added by the chip)
            - ranging: Bool indicating if ranging type of message
            - timeout: Max amount of time [s] to wait for confirmed send of message
        RETURNS:
            - ranging False: bool indicating if the frame was sent
            - ranging True: (sent, tx_timestamp), tx_timestamp being the TX time (reg 0x17) IN CLK TICKS
              (raw 40bit value), or None if the frame was not sent
        RAISES:
            - ValueError if data is longer than 125 bytes (extended frames are not supported)
        """
        tx_timestamp = None
        txfrs = 0
        # NOTE: currently not supporting extended data frames, messages shouldn't exceed 127 bytes 
        if len(data) + 2 > 127: # +2 for the CRC octets
            raise ValueError(f"DW1000.transmit(): {len(data)} data bytes + 2 CRC octets exceeds 127 bytes (extended frames not supported)")
        ### Writing data to TX buffer 
        self.write_register([0x89], data)
        ### Setting frame length in Transmit Frame Control 
        data_length = len(data) + 2 # adding 2 octets of CRC check 
        curr = self.read_register([0x08], 2, return_ints=True)
        tx_fctrl = data_length | ((curr[1] & 0x60)<<8)  # TFLEN == data_length, keeping TXBR and 0 TFLE and R 
        tx_fctrl |= int(ranging)<<15
        self.write_register([0x88], [tx_fctrl & 0xFF, (tx_fctrl>>8) & 0xFF])
        ### Starting transmission in System Control Register, this automatically clears TXFRS 
        self.write_register([0x8D], [0x02])
        ### Checking if TX completed with TXFRS in SYS_STATUS
        t1 = time.perf_counter() 
        while (time.perf_counter()-t1)<timeout: 
            txfrs = self.read_register([0x0F], 1, return_ints=True)[0] >> 7  
            if txfrs: 
                if ranging: ## If TX OK & ranging, return TX_TIME too 
                    tx_time = self.read_register([0x17], 5, return_ints=True)
                    tx_timestamp = tx_time[0] | tx_time[1]<<8 | tx_time[2]<<16 | tx_time[3]<<24 | tx_time[4]<<32
                break # DW1000 will return to IDLE automatically 
        else: 
            # TODO Can add more in depth inspection of error bits in future 
            logger.warning("Transmit timeout in DW1000.transmit(), returning to IDLE")
            self.disable_rx_tx() # Force return to IDLE 

        return (bool(txfrs), tx_timestamp) if ranging else bool(txfrs)

    def disable_rx_tx(self): 
        """ Disables all TX and RX activity (SYS_CTRL 0x0D), forcing return to IDLE """ 
        self.write_register([0x8D], [0x40])

    def enable_rx(self): 
        """
        Enable RX (RXENAB in SYS_CTRL 0x0D).
        Per the SYS_STATUS bit descriptions (p.83-88), every RX event/error bit (RXPRD, RXSFDD, LDEDONE, RXPHD,
        RXPHE, RXDFR, RXFCG, RXFCE, RXRFSL, RXRFTO, LDEERR, RXPTO, RXSFDTO, ...) is "automatically cleared by the
        next receiver enable", so no explicit clearing of SYS_STATUS is needed before listening.
        """
        self.write_register([0x8D], [0, 1]) 

    def packet_available(self)->bool: 
        """
        Checks if the DW1000 received a valid message. 
       
        RETURNS: 
        - True if we did 
        - False if we didn't
            - NOTE: DW1000 stays in RX mode in this case. If an RX error or timeout occurred, RX is reset
              (light RX-only reset, required by the manual p.31) and re-enabled, which clears the error bits.
        """
        status = self.read_register([0x0F], 5, return_ints=True) # SYS_STATUS 0x0F 
        bits8_23 = status[1] | status[2]<<8 # putting it into 16bit format for ease of comparison 
        # Good frames have: RXFCG, RXDFR, RXPHD, LDEDONE, RXSFDD and RXPRD set  
        if (bits8_23 & 0x006F)==0x006F: # Good frame 
            return True 
        # Either received a bad frame or nothing 
        else: 
            # Bottom of p.31 in manual indicates we should reset RX after error or timeout event 
            # If any of RXPHE, RXFCE, RXRFSL, RXRFTO, LDEERR, RXSFDTO, , RXPTO are true, we soft reset RX and exit 
            err_or_to_mask = 0x04<<24 | 0x27<<16 | 0x90<<8 # aforementioned error/TO bits 
            bits8_31 = status[1]<<8 | status[2]<<16 | status[3]<<24
            if (bits8_31 & err_or_to_mask)!=0: # If any of these bits are 1, there's a problem 
                logger.info("RX timeout or error during DW1000.listen(), resetting RX")
                self.disable_rx_tx()  # TRXOFF: back to IDLE
                self._rx_reset()      # light RX-only reset
                # Re-enabling RX again, we'll keep looping if there's time left.
                # This also clears the latched RX status/error bits (see enable_rx()).
                self.enable_rx()
            # If we didn't get anything, DW1000 stays in RX mode 
            return False 

    @overload
    def receive_packet(self, return_ints:Literal[True]=...)->tuple[list[int]|None, int|None]: ...
    @overload
    def receive_packet(self, return_ints:Literal[False])->tuple[list[str]|None, int|None]: ...
    @overload
    def receive_packet(self, return_ints:bool=...)->tuple[list[int]|list[str]|None, int|None]: ...

    def receive_packet(self, return_ints:bool=True)->tuple[list[int]|list[str]|None, int|None]:
        """
        Reads the RX buffer. This should only be called if the packet_available() method returns True.

        ARGS:
        - return_ints: List data format in ints or in hex strings

        RETURNS:
        - List of data found in RX buffer (without the 2 CRC octets)
        - Timestamp of RX reception in clock ticks (int of raw 40 bit value)
        - (None, None) if an extended frame (>127 bytes, not supported) was received; the device is then fully
          soft-reset (UWB configuration is re-applied automatically, see soft_reset())
        """
        # Getting RX timestamp 
        rx_time = self.read_register([0x15], 5, return_ints=True)
        rx_stamp = rx_time[0] | rx_time[1]<<8 | rx_time[2]<<16 | rx_time[3]<<24 | rx_time[4]<<32
        # Checking RXFINFO for frame length 
        rx_finfo = self.read_register([0x10], 4, return_ints=True)
        rxfle_rxflen = (rx_finfo[0] | (rx_finfo[1]<<8)) & 0x3FF
        # NOTE: currently not supporting non std operation, so RXFLE should be 0 
        if rxfle_rxflen>0x7F: # Currently, messages should be <= 127bytes 
            logger.warning("DW1000.receive_packet(): received extended data frame (RXFLE!=0). Currently not supporting this, check the message?")
            self.soft_reset()
            return None, None 
        # Now reading buffer with frame length 
        rxfle_rxflen-=2 # throwing away FCS at the end 
        data = self.read_register([0x11], rxfle_rxflen, return_ints=return_ints)  
        return data, rx_stamp

    @overload
    def listen(self, ranging:Literal[False]=..., timeout:float=..., return_ints:Literal[True]=...)->list[int]|None: ...
    @overload
    def listen(self, ranging:Literal[False]=..., timeout:float=..., *, return_ints:Literal[False])->list[str]|None: ...
    @overload
    def listen(self, ranging:Literal[True], timeout:float=..., return_ints:Literal[True]=...)->tuple[list[int]|None, int|None]: ...
    @overload
    def listen(self, ranging:Literal[True], timeout:float=..., *, return_ints:Literal[False])->tuple[list[str]|None, int|None]: ...
    @overload
    def listen(self, ranging:bool=..., timeout:float=..., return_ints:bool=...)->list[int]|list[str]|None|tuple[list[int]|list[str]|None, int|None]: ...

    def listen(self, ranging:bool=False, timeout:float=DW_LISTEN_TIMEOUT, return_ints:bool=True)->list[int]|list[str]|None|tuple[list[int]|list[str]|None, int|None]:
        """
        Sets the DW1000 to RX mode and listens for messages.
        Returns the first message found, if any, then disables RX (the DW1000 goes back to IDLE; the SPI
        connection stays open).

        ARGS:
            - ranging: If we are ranging, will return the RX timestamp too (reg 0x15)
            - timeout: Max amount of time [s] to stay listening
            - return_ints: Whether to return in hex string format or pure ints
        RETURNS:
            - ranging False: the data received as a list of bytes, or None if nothing was received in time
            - ranging True: (data, rx_timestamp), rx_timestamp being in CLK TICKS (raw 40bit value);
              (None, None) if nothing was received in time
        """
        data = None 
        rx_stamp = None 

        self.enable_rx()  # automatically clears any past latched receive bits 
        start = time.perf_counter() 
        while (time.perf_counter()-start)<timeout: 
            if self.packet_available(): 
                data, rx_stamp = self.receive_packet(return_ints=return_ints) 
                break 
        self.disable_rx_tx()  
        return (data, rx_stamp) if ranging else data 
    
    @staticmethod
    def check_valid_uwb_config(channel:int, PRF:int, bitrate:float, preamble_length:int, preamble_code:int, smart_tx_power:bool)->bool: 
        """ 
        Checks if a specific UWB configuration is valid based on the DW1000 user manual. 
        """
        if type(channel)!=int or type(PRF)!=int or type(preamble_code)!=int: 
            return False 
        if channel not in [1,2,3,4,5,7]: 
            return False 
        if not (PRF==64 or PRF==16):
            return False 
        ## Checking preambles (p.202)
        if PRF==64 and channel!=4 and channel!=7: 
            allowed_preambles = [9,10,11,12] 
        elif PRF==64 and (channel==4 or channel==7):
            allowed_preambles = [17,18,19,20] 
        elif PRF==16 and channel==1: 
            allowed_preambles = [1, 2] 
        elif PRF==16 and (channel==2 or channel==5): 
            allowed_preambles = [3, 4] 
        elif PRF==16 and channel==3: 
            allowed_preambles = [5, 6] 
        elif PRF==16 and (channel==4 or channel==7): 
            allowed_preambles = [7, 8] 
        if not preamble_code in allowed_preambles:
            return False 
        ## Checking bitrate
        if bitrate not in [110, 850, 6.8, 6, 7]: 
            return False 
        ## Preamble length 
        if preamble_length not in [64,128,256,512,1024,1536,2048,4096]: 
            return False 
        ## Preamble and bitrate combination (for DRX_TUNE1b, p.133 of user manual)
        if (preamble_length>1024) and (bitrate==110): 
            pass # ok 
        elif (128<=preamble_length<=1024) and (bitrate!=110):
            pass # ok
        elif preamble_length==64 and bitrate!=110 and bitrate!=850: 
            pass # ok 
        else: 
            logger.debug("Invalid bitrate-preamble config for DRX_TUNE1b")
            return False 
        ## Smart TX Power can only be used with 6.8 bitrate
        if smart_tx_power: 
            if bitrate not in [6.8, 6, 7]: 
                return False 
        ## If all passed, everything ok 
        return True 

    def config_uwb_settings(self, channel:Literal[1,2,3,4,5,7], PRF:Literal[16,64], bitrate:Literal[110,850,6,7], 
                            preamble_length:Literal[64,128,256,512,1024,1536,2048,4096], preamble_code:int,
                            smart_tx_power:bool, tx_power_settings:list[int]|None=None)->None: 
        """
        Configures the DW1000's UWB settings. Validates the settings before applying them. 
        
        ARGS: 
            - channel: Communication channel 
            - PRF: Pulse repetition frequency (16 or 64MHz) 
            - preamble_code: Code associated to PRF, see user manual. 
            - bitrate: Bitrate, 110kps, 850kps or 6.8Mbps (latter can be passed as 6, 7 or 6.8, all correspond to 6.8)
            - preamble_length: in symbols
            - smart_tx_power: bool (whether to use it or not), can only be used with 6.8Mbps bitrate
            - tx_power_settings: ONLY USE IF SURE! List of exactly 4 ints (0-255), the bytes of the 0x1E register
              in LSB order, e.g. [0x67, 0x67, 0x67, 0x67] (NOT 0x67676767). Leave at None for the defaults.

        RAISES:
            - ValueError if the combination of settings is not supported, or if tx_power_settings is not a
              list of 4 ints between 0 and 255. Nothing is written to the device in that case.

        Modifies the following registers:
            - 0x1F    - Channel Control
            - 0x08    - Transmit Frame Control 
            - 0x28:0B - RF_RXCTRLH
            - 0x28:0C - RF_TXCTRL 
            - 0x2A:0B - TC_PGDELAY
            - 0x2B:07 - FS_PLLCFG
            - 0x2B:0B - FS_PLLTUNE
            - 0x27:02 - DRX_TUNE0b
            - 0x27:04 - DRX_TUNE1a
            - 0x27:06 - DRX_TUNE1b
            - 0x27:08 - DRX_TUNE2
            - 0x23:04 - AGC_TUNE1
            - 0x23:0C - AGC_TUNE2
            - 0x23:12 - AGC_TUNE3
            - 0x2E:1806 - LDE_CFG2
            - 0x2E:2804 - LDE_REPC (depends on preamble code, divided by 8 at 110 kbps)
            - 0x27:26 - DRX_TUNE4H (depends on preamble length)
            - 0x1E    - TX Power
            - 0x04    - System Configuration

        Not modified: 0x2E:0806 LDE_CFG1 is left at its default NSTDEV of 12. The manual (p.22 and p.165) says
        13 can give more accuracy in close-up line-of-sight conditions, while 12 may be better where
        non-line-of-sight performance matters.

        The settings are remembered and re-applied automatically after a full soft_reset().
        """
        if not self.check_valid_uwb_config(channel, PRF, bitrate, preamble_length, preamble_code, smart_tx_power):
            # This ensures that the combination of values is valid 
            # and simplifies following if/elses 
            raise ValueError(f"Unsupported UWB config for DW1000: channel={channel}, PRF={PRF}, bitrate={bitrate}, "
                             f"preamble_length={preamble_length}, preamble_code={preamble_code}, smart_tx_power={smart_tx_power}")
        if tx_power_settings is not None:
            if (not isinstance(tx_power_settings, list) or len(tx_power_settings) != 4
                    or not all(isinstance(b, int) and not isinstance(b, bool) and 0 <= b <= 0xFF for b in tx_power_settings)):
                raise ValueError(f"tx_power_settings must be a list of 4 ints between 0 and 255 (0x1E register bytes, LSB first), got {tx_power_settings!r}")
        
        ###################### 0x1F - Channel Control ######################
        og_cfg = self.read_register([0x1F], 4, return_ints=True) 
        new_cfg = 0x00_00_00_00
        ## First byte is the channel for RX and TX 
        byte1 = int(f"0x{channel}{channel}", base=16) 
        new_cfg |= byte1
        ## Second byte is entirely reserved, we don't change it  
        new_cfg |= og_cfg[1] << 8 # shifting left by 8 to match register layout 
        ## Now we look at bits 19-16 
        # RXPRF (bit 19-18) will set the PRF 
        # DWSFD (bit 17) left at 0 to use std DW SFD. Also leaving RNSSFD and TNSSFD at 0 for this. 
        # Reserved bit 16 is left unchanged. 
            # To get the value of bit16, we'll have to modify whole octet (23-16)
            # but it's ok, we'll just write over it next step, since TX_PCODE is part of it
        if PRF==16: # 16MHz: RXPRF at 0b01
            prf_cfg = (og_cfg[2] & 0x01) | 0x04 
        elif PRF==64: # 64MHz: RXPRF at 0b10
            prf_cfg = (og_cfg[2] & 0x01) | 0x08
        new_cfg |= prf_cfg << 16  
        ## Now writing TX_PCODE and RX_PCODE (bits 31-22) 
        new_cfg |= preamble_code << 22 
        new_cfg |= preamble_code << 27 
        ## Finally splitting this into bytes and sending 
        chan_cfg = [new_cfg & 0xFF, (new_cfg>>8) & 0xFF, (new_cfg>>16) & 0xFF, (new_cfg>>24) & 0xFF]
        self.write_register([0x9F], chan_cfg) 

        ###################### 0x08 - Transmit Frame Control ######################
        og_cfg = self.read_register([0x08], 5, return_ints = True) 
        new_cfg = 0x00_00_00_00_00 
        # TFLEN, TFLE and R stay unchanged (bits 0-12) 
        new_cfg |= ((og_cfg[1]<<8) | og_cfg[0])  & 0x1FFF # mask only keeps bits 0-12 
        # TXBR sets bitrate (bits 13-14)
        if bitrate == 110:
            new_cfg |= 0b00<<13 
        elif bitrate == 850:
            new_cfg |= 0b01<<13 
        else: # check_valid_uwb_config ensures other values are 6.8, 6 or 7
            new_cfg |= 0b10<<13 
        # TR (bit 15) unchanged 
        new_cfg |= (og_cfg[1]<<8) & 0x8000
        # TXPRF - Sets PRF (bits 16-17)
        if PRF==16: 
            new_cfg |= 0b01<<16
        elif PRF==64: 
            new_cfg |= 0b10<<16 
        # TXPSR and PE - Sets preamble length (bits 18-21)
        if preamble_length==64: 
            bits = 0b0001
        elif preamble_length==128: 
            bits = 0b0101
        elif preamble_length==256: 
            bits = 0b1001
        elif preamble_length==512: 
            bits = 0b1101
        elif preamble_length==1024: 
            bits = 0b0010
        elif preamble_length==1536: 
            bits = 0b0110
        elif preamble_length==2048: 
            bits = 0b1010
        elif preamble_length==4096: 
            bits = 0b0011
        new_cfg |= bits<<18
        # Not touching the rest (bits 22-40)
        new_cfg |= ((og_cfg[2] & 0xC0)<<16) # bits 22 and 23 
        new_cfg |= og_cfg[3]<<24 
        new_cfg |= og_cfg[4]<<32
        ## Splitting into bytes and sending 
        new_cfg = [new_cfg&0xFF, (new_cfg>>8)&0xFF, (new_cfg>>16)&0xFF, (new_cfg>>24)&0xFF, (new_cfg>>32)&0xFF]
        self.write_register([0x88], new_cfg)        

        ###################### 0x28:0B, 0x28:0C, 0x2A:0B, 0x2B:07 and 0x2B:0B ######################
        channel_config = _CHANNEL_RF_CONFIG[channel]
        
        og_0x28_B = self.read_register([0x68, 0x0B], 1, return_ints=True)
        if og_0x28_B != channel_config['0x28_B']:
            self.write_register([0xE8, 0x0B], channel_config['0x28_B'])
        
        og_0x28_C = self.read_register([0x68, 0x0C], 4, return_ints=True)
        if og_0x28_C != channel_config['0x28_C']:
            self.write_register([0xE8, 0x0C], channel_config['0x28_C'])
            # NOTE: for some reason, the last (0x00) byte I send doesn't seem to affect it
            # it always reads as 0xDE after the operation. But all other bytes are good. 
            # i assume those bytes are just not writeable or are overwritten immediately. 
        
        og_0x2A = self.read_register([0x6A, 0x0B], 1, return_ints=True)
        if og_0x2A != channel_config['0x2A']:
            self.write_register([0xEA, 0x0B], channel_config['0x2A'])
        
        og_0x2B_7 = self.read_register([0x6B, 0x07], 4, return_ints=True)
        if og_0x2B_7 != channel_config['0x2B_7']:
            self.write_register([0xEB, 0x07], channel_config['0x2B_7'])
        
        og_0x2B_B = self.read_register([0x6B, 0x0B], 1, return_ints=True)
        if og_0x2B_B != channel_config['0x2B_B']:
            self.write_register([0xEB, 0x0B], channel_config['0x2B_B'])
        
        ###################### 0x27:02 ######################
        # NOTE: Currently only supports standard SFD! 
        tune0b = self.read_register([0x67, 0x02], 2, return_ints=True)
        if bitrate == 110:
            new_cfg = [0x0A, 0x00]
        elif bitrate == 850:
            new_cfg = [0x01, 0x00]
        else: # check_valid_uwb_config ensures other values are 6.8, 6 or 7
            new_cfg = [0x01, 0x00] 
        if tune0b!=new_cfg: 
            self.write_register([0xE7, 0x02], new_cfg) 
        ###################### 0x27:04 ######################
        tune1a = self.read_register([0x67, 0x04], 2, return_ints=True)
        if PRF==16: 
            new_cfg = [0x87, 0x00]
        elif PRF==64:
            new_cfg = [0x8D, 0x00]
        if tune1a!=new_cfg:
            self.write_register([0xE7, 0x04], new_cfg)
        ###################### 0x27:06 ######################
        tune1b = self.read_register([0x67, 0x06], 2, return_ints=True)
        if (preamble_length>1024) and (bitrate==110): 
            new_cfg = [0x64, 0x00]
        elif (128<=preamble_length<=1024) and (bitrate!=110):
            new_cfg = [0x20, 0x00]
        elif preamble_length==64 and bitrate!=110 and bitrate!=850: 
            new_cfg = [0x10, 0x00]
        if tune1b!=new_cfg: 
            self.write_register([0xE7, 0x06], new_cfg)
        ###################### 0x27:08 ######################
        tune2 = self.read_register([0x67, 0x08], 4, return_ints=True)
        # NOTE: this sets PAC size, using recommended # of Table 5 user manual (p.29)
        if preamble_length<=128: 
            PAC_size = 8 
            if PRF==16:
                new_cfg = [0x2D,0x00,0x1A,0x31] 
            elif PRF==64: 
                new_cfg = [0x6B,0x00,0x3B,0x31] 
        elif preamble_length<=512: 
            PAC_size = 16 
            if PRF==16:
                new_cfg = [0x52,0x00,0x1A,0x33]
            elif PRF==64: 
                new_cfg = [0xBE,0x00,0x3B,0x33]
        elif preamble_length==1024: 
            PAC_size = 32 
            if PRF==16:
                new_cfg = [0x9A,0x00,0x1A,0x35]
            elif PRF==64: 
                new_cfg = [0x5E,0x01,0x3B,0x35]
        elif preamble_length>=1536: 
            PAC_size = 64 
            if PRF==16:
                new_cfg = [0x1D,0x01,0x1A,0x37]
            elif PRF==64: 
                new_cfg = [0x96,0x02,0x3B,0x37]
        if tune2!=new_cfg: 
            self.write_register([0xE7, 0x08], new_cfg)
        ###################### 0x23:04 ######################
        agc = self.read_register([0x63, 0x04], 2, return_ints=True)
        if PRF==16:
            new_cfg = [0x70, 0x88]
        elif PRF==64: 
            new_cfg = [0x9B, 0x88]
        if agc!=new_cfg: 
            self.write_register([0xE3, 0x04], new_cfg) 
        ###################### 0x23:0C ######################
        agc = self.read_register([0x63, 0x0C], 4, return_ints=True)
        new_cfg = [0x07,0xA9,0x02,0x25] 
        if agc!=new_cfg: 
            self.write_register([0xE3, 0x0C], new_cfg) 
        ###################### 0x23:12 ######################
        agc = self.read_register([0x63, 0x12], 2, return_ints=True)
        new_cfg = [0x55, 0x00]
        if agc!=new_cfg: 
            self.write_register([0xE3, 0x12], new_cfg) 
        ###################### 0x2E:1806 ####################
        # This is a 3 octet read, 0x86 comes from 0x80|(0x1806&0x7F) 
        # and 0x30 comes from 0x1806>>7 as per header construction rules of user manual. 
        lde = self.read_register([0x6E, 0x86, 0x30], 2, return_ints=True)
        if PRF==16:
            new_cfg = [0x07, 0x16]
        elif PRF==64: 
            new_cfg = [0x07, 0x06] 
        if lde!=new_cfg:
            self.write_register([0xEE, 0x86, 0x30], new_cfg)
        ###################### 0x2E:2804 - LDE_REPC ####################
        # Replica avoidance coefficient, depends on the RX preamble code (manual Table 47, p.167).
        # Values in the table are for 850 kbps and 6.8 Mbps; at 110 kbps they must be divided by 8.
        # 3 octet header: 0x84 = 0x80|(0x2804&0x7F) and 0x50 = 0x2804>>7
        repc = _LDE_REPC[preamble_code]
        if bitrate == 110:
            repc >>= 3
        lde_repc = self.read_register([0x6E, 0x84, 0x50], 2, return_ints=True)
        new_cfg = [repc & 0xFF, (repc>>8) & 0xFF]
        if lde_repc!=new_cfg:
            self.write_register([0xEE, 0x84, 0x50], new_cfg)
        ###################### 0x27:26 - DRX_TUNE4H ####################
        # Depends on the expected preamble length (manual Table 31, p.136): 0x0010 for 64 symbols,
        # 0x0028 for 128 symbols or more. The manual warns not to write any other value to this register.
        tune4h = self.read_register([0x67, 0x26], 2, return_ints=True)
        new_cfg = [0x10, 0x00] if preamble_length == 64 else [0x28, 0x00]
        if tune4h!=new_cfg:
            self.write_register([0xE7, 0x26], new_cfg)
        ###################### 0x04 ######################
        sys_cfg = self.read_register([0x04], 4, return_ints=True) 
        sys_cfg = sys_cfg[0] | sys_cfg[1]<<8 | sys_cfg[2]<<16 | sys_cfg[3]<<24
        curr_DIS_STXP = (sys_cfg >> 18) & 1 
        if smart_tx_power: 
            new_DIS_STXP = 0 
        else: 
            new_DIS_STXP = 1 
        if curr_DIS_STXP!=new_DIS_STXP: 
            sys_cfg &= ~(1 << 18) # clear only bit 18 
            sys_cfg |= (new_DIS_STXP << 18)
            new_cfg = [sys_cfg & 0xFF, (sys_cfg>>8) & 0xFF, (sys_cfg>>16) & 0xFF, (sys_cfg>>24) & 0xFF]
            self.write_register([0x84], new_cfg)
        ###################### 0x1E ######################
        tx_power = self.read_register([0x1E], 4, return_ints=True)
        if tx_power_settings is not None:
            # tx power settings (validated above) are the 4 bytes to write to 0x1E, LSB first
            # NOTE: ex: NOT 0x67676767 but [0x67, 0x67, 0x67, 0x67]
            new_cfg = tx_power_settings
        else: 
            if smart_tx_power: 
                new_cfg = _SMART_TX_POWER_CONFIG[channel][PRF]
            else: 
                new_cfg = _NO_SMART_TX_POWER_CONFIG[channel][PRF]
        if tx_power != new_cfg: 
            self.write_register([0x9E], new_cfg)
        ###################### DONE! ######################
        to_print = f"""
        --- DW 1000 UWB settings configured. ---
        Channel: {channel}
        Bitrate: {bitrate}
        PRF: {PRF}
        Preamble length: {preamble_length}
        Preamble code: {preamble_code}
        PAC size: {PAC_size}
        Smart TX Power: {smart_tx_power} 
        TX Power Settings (LSB first): {[hex(_) for _ in new_cfg]}
        **NOTE**: Settings currently only support standard SFD."""
        logger.info(to_print)
        # Remember the settings so a full soft_reset() can re-apply them
        self._uwb_config = dict(channel=channel, PRF=PRF, bitrate=bitrate, preamble_length=preamble_length,
                                preamble_code=preamble_code, smart_tx_power=smart_tx_power,
                                tx_power_settings=tx_power_settings)