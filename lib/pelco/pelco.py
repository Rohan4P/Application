"""
Library for building and parsing commands and responses in Pelco's D-protocol.
This iteration is a full abstraction over a serial Pelco device, rather than a thin library wrapper

Authors: Scott Kemperman, Jeremy Krenbrink
Created: May 22, 2019
Updated: September 16, 2019

--- Possible CMD values ---

U: up           D: down
R: right        L: left
T: zoom tele    W: zoom wide
N: focus near   F: focus far
O: iris open    C: iris close

--- Shortlist of useful EXT_CMD values ---
EXT_CMD_SET_PRESET = 0x03
EXT_CMD_CALL_PRESET = 0x07
EXT_CMD_CLEAR_PRESET = 0x05
EXT_CMD_SET_AUX = 0x09
EXT_CMD_CLEAR_AUX = 0x0B
EXT_CMD_SET_PAN = 0x4B
EXT_CMD_SET_TILT = 0x4D
EXT_CMD_SET_ZOOM = 0x4F
EXT_CMD_QUERY_PAN = 0x51
EXT_CMD_QUERY_TILT = 0x53
EXT_CMD_QUERY_ZOOM = 0x55
EXT_CMD_QUERY_PAN_RESPONSE = 0x59
EXT_CMD_QUERY_TILT_RESPONSE = 0x5B
EXT_CMD_QUERY_ZOOM_RESPONSE = 0x5D
EXT_CMD_SET_MAGNIFICATION = 0x5F
EXT_CMD_QUERY_MAGNIFICATION = 0x61

--- Examples ---

Example Standard message ([255, 1, 0, 10, 32, 48, 91]):
    "success": True,
    "data": {
        "addr": 1,
        "type": "STD",      (TYPE_STANDARD)
        "cmd": "UR",        (UP + RIGHT)
        "panSpeed": 0.5,    (DATA1 / 64)
        "tiltSpeed": 0.75,  (DATA2 / 64)
    }

Example Extended message ([255, 2, 0, 75, 128, 128, 77]):
    "success": True,
    "data": {
        "addr": 2,
        "type": "EXT",      (TYPE_EXTENDED)
        "id": "0x4B",       (d75 - EXT_CMD_SET_PAN)
        "data": 18020       (int.from_bytes([DATA1, DATA2], 'big'))
    }

"""

import binascii
import time
import inspect
from queue import *
from datetime import datetime
from threading import Thread
from . import Mode
from . import *
from . import __version__


class PelcoDevice:
    def __init__(self, serial_comm=None, model=PelcoModel.DEFAULT, config=None):
        if model not in get_enum_list(PelcoModel):
            raise ValueError("model '%s' not found" % model)

        # --- PUBLIC, LIBRARY STANDARD PROPERTIES ---
        self.model = model
        self.connection_state = ConnectionState.DISCONNECTED
        self.last_communication_time = None
        self.serial_number = None
        self.firmware_version = None
        self.library_version = __version__

        self._config = DEFAULT_CONFIG
        if config:
            self._config.update(config)

        self.device_name = self._config['deviceName']
        self.send_address = self._config['sendAddress']

        self._raw = model == PelcoModel.RAW
        self._timeout = self._config['timeout']
        self._mode = self._config['mode']
        self._max_speed = self._config['maxSpeed']

        self.port = serial_comm
        if self.port:
            self.port.timeout = self._config['timeout']

        if self._config['mode'] == Mode.PROXY and self.port:
            self.port.timeout = None

        if self._config['mode'] in [Mode.PROXY, Mode.VIRTUAL, Mode.WRITE_ONLY]:
            self.connection_state = ConnectionState.CONNECTED

        self._buffer = bytes()
        self._max_buffer_size = 256

        # Callbacks registered to receive incoming messages
        self._readers = []

        # Callbacks that filter incoming messages and may or may not block/consume them. PROXY mode only
        self._filters = []

        self._active = False

        # Outgoing & incoming data
        self._messages = Queue()
        self._responses = Queue()
        self._callback_queue = []
        self._command_queue = []

        self._serial_thread = None

        if self.port:
            self._start_serial_thread()

    def flush(self):
        self._buffer = b''

    @staticmethod
    def _find_packet(data):
        """Searches for valid Pelco packets and returns the matching bytes plus a tuple
        containing start and end indices."""
        for i in range(len(data)):
            checksum_index = i + COMMAND_SIZE - 1
            if checksum_index >= len(data):
                break
            if (
                    data[i] == 0xff
                    and
                    data[checksum_index] == sum(data[i + 1:checksum_index]) % 0x100
            ):
                return data[i:i + COMMAND_SIZE], (i, i + COMMAND_SIZE)
        return None, ()

    def _write_data(self, data):
        if self.port:
            if self._mode != Mode.NORMAL:
                # self._log_message(LogLevel.DEBUG, 'SEND: %s' % str(data))
                self.port.write(data)
            else:
                self._messages.put((False, data))

        else:
            print(binascii.hexlify(bytes(data)).upper())

    def disconnect(self):
        self._log_message(LogLevel.INFO, 'Manual disconnect')
        self.connection_state = ConnectionState.DISCONNECTED
        self._active = False
        self._messages.put((False, KILL_CODE))  # Send kill message
        if self._serial_thread.is_alive():
            self._serial_thread.join()
        if self.port and self.port.is_open:
            self.port.close()

    def register_filter(self, callback):
        self._filters.append(callback)
        self._log_message(LogLevel.INFO, 'registered filter (%d)' % len(self._filters))

    def unregister_filter(self, callback):
        self._filters.remove(callback)
        self._log_message(LogLevel.INFO, 'unregistered filter (%d)' % len(self._filters))

    def register_reader(self, callback):
        self._readers.append(callback)
        self._log_message(LogLevel.INFO, 'registered reader (%d)' % len(self._readers))

    def unregister_reader(self, callback):
        self._readers.remove(callback)
        self._log_message(LogLevel.INFO, 'unregistered reader (%d)' % len(self._readers))

    def _readonly_loop(self):
        """A read-only loop for PROXY devices that parses incoming messages and calls listeners."""
        while self._active:
            recv = self.port.read(1)
            if recv == b'':
                continue
            # self.log_message(LogLevel.DEBUG, 'RECV: %s' % str(recv))
            recv = self.ingest(recv)
            if not recv:
                continue

            self.last_communication_time = datetime.now()

            # Would now call all of the registered reader callbacks
            for msg in recv:
                self._log_message(LogLevel.DEBUG, 'RECV: %s' % str(msg))

                # First apply filters to see if command is blocked / consumed
                if not self._raw and msg['success']:
                    blocked = False
                    for filt in self._filters:
                        if filt(self, msg):
                            blocked = True
                            break
                    if blocked:
                        continue

                # Send remaining messages to all subscribers
                for reader in self._readers:
                    if not self._raw and not msg['success'] and msg['error']['code'] == ERR_SYNC[0]:
                        continue
                    reader(self, msg)

    def _read_write_loop(self):
        """A request-response loop for NORMAL devices that uses Queues to coordinate outgoing
        requests and incoming responses."""
        while self._active:
            # Wait for queue message to send
            expects_reply, data = self._messages.get(block=True)
            # End thread when requested
            if data == KILL_CODE:
                return

            self._last_command_ts = time.perf_counter()

            if hasattr(self.port, 'reset_input_buffer'):
                self.port.reset_input_buffer()

            # self._log_message(LogLevel.DEBUG, 'SEND: %s' % str(data))
            self.port.write(data)

            if expects_reply:
                self._command_queue.insert(0, data)
                self._await_response()

    def _await_response(self):
        while self._active:
            data = self.port.read(1)
            # self._log_message(LogLevel.DEBUG, 'RECV %s' % data)
            if data == b'':
                self._respond(error(ERR_TIMEOUT))
                break

            responses = self.ingest(data)
            if not responses:
                continue

            for response in responses:
                self._log_message(LogLevel.DEBUG, 'Response: %s' % str(response))
                self.last_communication_time = datetime.now()
                self.last_response_timeout = time.perf_counter() - self._last_command_ts
                self._respond(response)
            return

    def _respond(self, response):
        if self._mode == Mode.NORMAL and self._command_queue:
            self._command_queue.pop()

        if self._callback_queue:
            callback = self._callback_queue.pop()
            callback(response)
        else:
            self._responses.put(response)

    def _start_serial_thread(self):
        if not self._serial_thread or (self._serial_thread and not self._serial_thread.is_alive()):
            self._serial_thread = Thread(target=self.run)
            self._serial_thread.start()

    def initialize(self, callback):
        if not callback:
            callback = lambda x: x

        if self._mode != Mode.NORMAL:
            # Only run init sequence for NORMAL devices
            self.connection_state = ConnectionState.CONNECTED
            return callback(success())

        if self.connection_state == ConnectionState.INITIALIZING:
            message = error((ERR_NOT_READY[0], 'Device state busy: %s' % self.connection_state))
            self._log_message(LogLevel.WARNING, message)
            return callback(message)

        self._log_message(LogLevel.INFO, 'Running init sequence')

        self.connection_state = ConnectionState.INITIALIZING
        init_thread = Thread(target=self._init_sequence, args=(callback,))
        init_thread.start()
        return init_thread

    def _init_sequence(self, callback):
        # Ensure we are starting with clean Queues
        while not self._messages.empty():
            self._messages.get_nowait()
        while not self._responses.empty():
            self._responses.get_nowait()
        self._log_message(LogLevel.DEBUG, 'INIT cleared queues')

        self.connection_state = ConnectionState.CONNECTED
        if callback:
            callback(success())

    def run(self):
        self._active = True

        if self._mode == Mode.PROXY:
            self._readonly_loop()
        elif self._mode == Mode.NORMAL:
            self._read_write_loop()

        # WRITE_ONLY mode does not require a loop

    def ingest(self, data):
        # Ignore rogue data if we're in NORMAL mode
        if self._mode == Mode.NORMAL and len(self._command_queue) == 0:
            self._buffer = b''
            return []

        self._buffer += data
        # Cut off start of buffer (oldest bytes) if it gets too big
        self._buffer = self._buffer[len(self._buffer) - self._max_buffer_size:]

        responses = []

        while True:
            # _find_packet will return the matching data (match) and the index range (position) of the match,
            # or None, ()
            match, position = self._find_packet(self._buffer)

            if not match:
                break

            self._buffer = self._buffer[position[-1]:]

            try:
                responses.append(self._parse(match))
            except (KeyError, IndexError, ValueError):
                responses.append(error(ERR_BAD_VALUE))

        # Throw away garbage bytes
        i = self._buffer.find(b'\xff')
        if i >= 0:
            self._buffer = self._buffer[i:]
        else:
            self._buffer = b''

        return responses

    def _parse(self, packet):
        if self._raw:
            return packet

        addr, c1, c2, d1, d2 = packet[ADDR_INDEX], packet[CMD1_INDEX], packet[CMD2_INDEX], \
                               packet[DATA1_INDEX], packet[DATA2_INDEX]

        # Initialize to default of direct byte values in case of unknown packet
        data = {"addr": addr, "c1": c1, "c2": c2, "d1": d1, "d2": d2}
        if sum((c1, c2, d1, d2)) == 0:
            data = {"addr": addr, "type": TYPE_STOP}

        # Handle standard command
        elif c1 <= 4 and c2 % 2 == 0:
            cmd_string = ''
            pan_speed = 0
            tilt_speed = 0
            if c1 & 0x4:
                cmd_string += 'C'
            elif c1 & 0x2:
                cmd_string += 'O'
            if c1 & 0x1:
                cmd_string += 'N'
            elif c2 & 0x80:
                cmd_string += 'F'
            if c2 & 0x40:
                cmd_string += 'W'
            elif c2 & 0x20:
                cmd_string += 'T'
            if c2 & 0x10:
                cmd_string += 'D'
                tilt_speed = round(d2 / self._max_speed, 4)
            if c2 & 0x8:
                cmd_string += 'U'
                tilt_speed = round(d2 / self._max_speed, 4)
            if c2 & 0x4:
                cmd_string += 'L'
                pan_speed = round(d1 / self._max_speed, 4)
            if c2 & 0x2:
                cmd_string += 'R'
                pan_speed = round(d1 / self._max_speed, 4)

            if tilt_speed > 1:
                return error(ERR_BAD_TILT, data=tilt_speed)

            if pan_speed > 1:
                return error(ERR_BAD_PAN, data=pan_speed)

            # Could include error generation if cmd_string == ''

            data = {"addr": addr, "type": TYPE_STANDARD, "cmd": cmd_string, "panSpeed": pan_speed,
                    "tiltSpeed": tilt_speed}

        # Handle Extended command
        elif c2 % 2 == 1:
            if c2 in [EXT_CMD_SET_AUX, EXT_CMD_CLEAR_AUX, EXT_CMD_CLEAR_PRESET,
                      EXT_CMD_SET_PRESET, EXT_CMD_CALL_PRESET]:
                value = d2

            elif c2 == EXT_CMD_QUERY_PAN_RESPONSE:
                pan = int.from_bytes(bytes([d1, d2]), 'big') / 100
                return success(round(pan, 2))

            elif c2 == EXT_CMD_QUERY_TILT_RESPONSE:
                tilt = int.from_bytes(bytes([d1, d2]), 'big') / 100
                if 0 <= tilt <= 90:
                    tilt = -tilt
                elif 270 <= tilt <= 360:
                    tilt = 360 - tilt
                else:
                    return error(ERR_BAD_VALUE)
                return success(round(tilt, 2))

            elif c2 in [EXT_CMD_QUERY_ZOOM_RESPONSE, EXT_CMD_QUERY_MAGNIFICATION_RESPONSE]:
                return success(round(((d1 << 8) + d2) / 0xFFFF * 100, 2))

            elif c2 == EXT_CMD_SET_PAN:
                value = int.from_bytes(bytes([d1, d2]), 'big') / 100

            elif c2 == EXT_CMD_SET_TILT:
                value = int.from_bytes(bytes([d1, d2]), 'big') / 100
                if 90 >= value >= 0:
                    value = -value
                elif 360 >= value >= 270:
                    value = 360 - value
            elif c2 in [EXT_CMD_SET_ZOOM]:
                value = round(((d1 << 8) + d2) / 0xFFFF, 2) * 100
            else:
                value = round(((d1 << 8) + d2) / 0xFFFF, 2) * 100
            data = {"addr": addr, "type": TYPE_EXTENDED, "c1": round(c1 / EXTENDED_MAX_SPEED, 4)*100, "id": c2, "data": value}

        else:
            # Unknown command returns full structure
            data = {"addr": addr, "type": TYPE_ALTERNATE, "c1": c1, "c2": c2, "d1": d1, "d2": d2}

        return {'success': True, 'data': data}

    # SEND commands --------------------------------------------

    def start_zoom_tele(self):
        self._write_data(self._command(0, CMD2_ZOOM_TELE, 0, 0))

    def start_zoom_wide(self):
        self._write_data(self._command(0, CMD2_ZOOM_WIDE, 0, 0))

    def start_focus_far(self):
        self._write_data(self._command(0, CMD2_FOCUS_FAR, 0, 0))

    def start_focus_near(self):
        self._write_data(self._command(CMD1_FOCUS_NEAR, 0, 0, 0))

    def start_iris_open(self):
        self._write_data(self._command(CMD1_IRIS_OPEN, 0, 0, 0))

    def start_iris_close(self):
        self._write_data(self._command(CMD1_IRIS_CLOSE, 0, 0, 0))

    def stop(self):
        self._write_data(self._command(0, 0, 0, 0))

    def set_preset(self, preset_id):
        if preset_id < 1 or preset_id > 255:
            raise ValueError("Preset values must be in range 1 to 255")

        self._write_data(self._command(0, EXT_CMD_SET_PRESET, 0, preset_id))

    def call_preset(self, preset_id):
        if preset_id < 1 or preset_id > 255:
            raise ValueError("Preset values must be in range 1 to 255")

        self._write_data(self._command(0, EXT_CMD_CALL_PRESET, 0, preset_id))

    def set_auxiliary(self, aux_id):
        if aux_id < 0 or aux_id > 255:
            return error(ERR_INVALID_INPUT_PARAM)

        self._write_data(self._command(0, EXT_CMD_SET_AUX, 0, aux_id))

    def clear_auxiliary(self, aux_id):
        if aux_id < 0 or aux_id > 255:
            return error(ERR_INVALID_INPUT_PARAM)

        self._write_data(self._command(0, EXT_CMD_CLEAR_AUX, 0, aux_id))

    def clear_preset(self, preset_id):
        if preset_id < 1 or preset_id > 255:
            raise ValueError("Preset values must be in range 1 to 255")

        self._write_data(self._command(0, EXT_CMD_CLEAR_PRESET, 0, preset_id))

    def magnification_query_response(self, magnification_pct):
        if magnification_pct < 0 or magnification_pct > 100:
            raise ValueError("'magnification_pct' must be in range 0.0 to 100.0")

        position = int(magnification_pct / 100 * 0xFFFF)
        self._write_data(
            self._command(cmd2=EXT_CMD_QUERY_MAGNIFICATION_RESPONSE, data1=position >> 8, data2=position & 0xff))

    def zoom_query_response(self, zoom_pct):
        if zoom_pct < 0 or zoom_pct > 100:
            raise ValueError("'zoom_pct' must be in range 0.0 to 100.0")

        position = int(zoom_pct / 100 * 0xFFFF)
        self._write_data(self._command(cmd2=EXT_CMD_QUERY_ZOOM_RESPONSE, data1=position >> 8, data2=position & 0xff))

    def pan_query_response(self, pan_degrees):
        if pan_degrees < 0 or pan_degrees > 359.99:
            raise ValueError("'pan_degrees' must be in range 0 to 359.99")

        position = int(pan_degrees * 100)
        self._write_data(self._command(cmd2=EXT_CMD_QUERY_PAN_RESPONSE, data1=position >> 8, data2=position & 0xff))

    def tilt_query_response(self, tilt_degrees):
        if tilt_degrees < -90 or tilt_degrees > 90:
            raise ValueError("'tilt_degrees' must be in range -90 to 90")

        if tilt_degrees <= 0:
            tilt_val = -tilt_degrees
        else:
            tilt_val = 360 - tilt_degrees

        tilt_val = int(tilt_val * 100)
        self._write_data(self._command(cmd2=EXT_CMD_QUERY_TILT_RESPONSE, data1=tilt_val >> 8, data2=tilt_val & 0xff))

    def relative_speed_control(self, pan_pct, tilt_pct):
        if not (-100 <= pan_pct <= 100 and -100 <= tilt_pct <= 100):
            raise ValueError('Speed percent values must be in range -100 to 100')

        if pan_pct == 0 and tilt_pct == 0:
            self._write_data(self._command(0, 0, 0, 0))
        else:
            cmd2, data1, data2 = 0, 0, 0
            if pan_pct != 0:
                cmd2 = CMD2_PAN_RIGHT if pan_pct > 0 else CMD2_PAN_LEFT
                data1 = int(abs(pan_pct) / 100 * 64)
            if tilt_pct != 0:
                cmd2 += CMD2_TILT_UP if tilt_pct > 0 else CMD2_TILT_DOWN
                data2 = int(abs(tilt_pct) / 100 * 64)
            self._write_data(self._command(0, cmd2, data1, data2))

    def set_absolute_position(self, pan_degrees, tilt_degrees):
        if not (0 <= pan_degrees < 360):
            raise ValueError("'pan_degrees' must be in range 0 to 359.99")
        if not (-90 <= tilt_degrees <= 90):
            raise ValueError("'tilt_degrees' must be in range -90 to 90")

        pan_value = pan_degrees * 100

        if tilt_degrees > 0:
            tilt_value = (360 - tilt_degrees) * 100
        else:
            tilt_value = -tilt_degrees * 100

        pan_value = int(pan_value)
        tilt_value = int(tilt_value)

        self._write_data(self._command(0, EXT_CMD_SET_PAN, pan_value >> 8, pan_value & 0xff))
        self._write_data(self._command(0, EXT_CMD_SET_TILT, tilt_value >> 8, tilt_value & 0xff))

    # SET commands -----------------    -----------------------
    def set_pan(self, pan_degrees):
        if not (0 <= pan_degrees < 360):
            raise ValueError("'pan_degrees' must be in range 0 to 359.99")

        pan_value = int(pan_degrees * 100)
        self._write_data(self._command(0, EXT_CMD_SET_PAN, pan_value >> 8, pan_value & 0xff))
        return success()

    def set_tilt(self, tilt_degrees):
        if not (-90 <= tilt_degrees <= 90):
            raise ValueError("'tilt_degrees' must be in range -90 to 90")

        if tilt_degrees > 0:
            tilt_value = (360 - tilt_degrees) * 100
        else:
            tilt_value = -tilt_degrees * 100

        tilt_value = int(tilt_value)

        self._write_data(self._command(0, EXT_CMD_SET_TILT, tilt_value >> 8, tilt_value & 0xff))
        return success()

    def set_zoom(self, zoom_pct):
        if zoom_pct < 0 or zoom_pct > 100:
            raise ValueError("'zoom_pct' must be in range 0.0 to 100.0")

        zoom_value = int(zoom_pct / 100 * 0xFFFF)
        self._write_data(self._command(0, EXT_CMD_SET_ZOOM, zoom_value >> 8, zoom_value & 0xff))
        return success()

    def set_magnification(self, magnification_pct):
        if not (0 <= magnification_pct <= 100):
            raise ValueError("'magnification_pct' must be in range 0.0 to 100.0")

        mag_value = int(magnification_pct / 100 * 0xFFFF)
        self._write_data(self._command(0, EXT_CMD_SET_MAGNIFICATION, mag_value >> 8, mag_value & 0xff))
        return success()

    # GET commands -----------------    -----------------------

    def get_pan(self, callback=None):
        return self._get_response(self._command(0, EXT_CMD_QUERY_PAN, 0, 0), callback)

    def get_tilt(self, callback=None):
        return self._get_response(self._command(0, EXT_CMD_QUERY_TILT, 0, 0), callback)

    def get_zoom(self, callback=None):
        return self._get_response(self._command(0, EXT_CMD_QUERY_ZOOM, 0, 0), callback)

    def get_magnification(self, callback=None):
        return self._get_response(self._command(0, EXT_CMD_QUERY_MAGNIFICATION, 0, 0), callback)

    def get_lens_position(self, callback=None):
        response = error(ERR_NOT_SUPPORTED)
        return callback(response) if callback else response

    # -----------------------------------------------------

    def _command(self, cmd1=0, cmd2=0, data1=0, data2=0):
        packet = [self.send_address, cmd1, cmd2, data1, data2]
        packet.append(sum(packet) % 0x100)
        packet.insert(0, SYNC_BYTE)
        return bytes(packet)

    def _get_response(self, data, callback=None, ignore_state=False):
        if not ignore_state and self.connection_state == ConnectionState.INITIALIZING:
            response = error((ERR_NOT_READY[0], 'device state: %s' % self.connection_state))
            if callback:
                callback(response)
            else:
                return response

        self._messages.put((True, data))

        if callback:
            self._callback_queue.insert(0, callback)
            return

        try:
            return self._responses.get(block=True)
        except Empty:
            return error(ERR_TIMEOUT)

    def _log_message(self, level, message):
        print(level, '[%s] - %s: %s' % (level, self.device_name, message))
