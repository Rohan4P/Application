import socket
import time
import threading
import struct
import serial
from lib.pelco.protocols import PelcoPTZCommands, PelcoPresets
from lib.pelco import *


class PTZController:
    def __init__(self):
        self.ip = ""
        self.port = 8005
        self.protocol = "Pelco-D"
        self.address = 1
        self.socket = None
        self.connected = False
        self.moving = False
        self.move_thread = None
        self.pelco_commands = PelcoPTZCommands
        self.pelco_presets = PelcoPresets
        self.pelco_device = PelcoDevice()
        self.get_address_callback = None

    def connect(self, ip="", port=8005, protocol="Pelco-D", address=1):
        self.ip = ip
        self.port = port
        self.protocol = protocol
        self.address = address
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(0.5)
            self.socket.connect((self.ip, self.port))
            self.connected = True
            print(f"Connected to PTZ controller at {ip}")
            return True
        except Exception as e:
            print(f"Error connecting to PTZ controller at {ip}, Disconnected: {e}")
            self.connected = False
            return False

    def disconnect(self):
        if self.moving:
            self.stop()

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        self.connected = False
        print("Disconnected from PTZ controller")

    def is_connected(self):
        """Check if connected to camera controller"""
        return self.connected

    def handle_pelco_keyboard_command(self, message, callback=None):
        print("Pelco keyboard command received:", message)
        self.send(message, callback)

    def send(self, bytes_message, callback=None):
        if not self.connected:
            print("Not connected to PTZ controller")
            return False
        print(f"Sending {bytes_message.hex(" ")}")
        if callback:
            self._send_async(bytes_message, callback)
        else:
            return self._send(bytes_message)

    def _send_async(self, message, callback):
        self._send(message)
        try:
            rsp = self.socket.recv(7)
        except TimeoutError:
            callback(None)
            return
        callback(rsp)

    def _send(self, message):
        try:
            amnt_sent = self.socket.send(message)
            if amnt_sent < len(message):
                self._connected = False
            return amnt_sent
        except (ConnectionResetError, ConnectionAbortedError, ConnectionError) as err:
            self._connected = False

    def set_address_provider(self, callback):
        """Set function to retrieve current PTZ address dynamically"""
        self.get_address_callback = callback

    def create_pelco_command(self, cmd1=0, cmd2=0, data1=0, data2=0):
        sync = 0xFF
        packet = [self.address, cmd1, cmd2, data1, data2]
        packet.append(sum(packet) % 0x100)
        packet.insert(0, sync)
        return bytes(packet)

    def create_pelco_p_command(self, command, data1=0, data2=0):
        """Create a Pelco-P protocol command packet"""
        stx = 0xA0
        etx = 0xAF

        # Calculate checksum (XOR of all bytes except STX, ETX and checksum)
        checksum = self.address ^ command ^ data1 ^ data2

        # Create command packet
        packet = struct.pack('BBBBBBB', stx, self.address, command, data1, data2, checksum, etx)

        return packet

    def pan_tilt(self, pan_pct, tilt_pct):
        # Clamp speeds to valid range
        # pan_speed = max(0, min(100, pan_pct))
        # tilt_speed = max(0, min(100, tilt_pct))

        pan_value = abs(pan_pct)
        tilt_value = abs(tilt_pct)
        # Determine direction
        cmd = 0x00
        if pan_pct > 0:
            cmd |= self.pelco_commands.RIGHT[1]
        elif pan_pct < 0:
            cmd |= self.pelco_commands.LEFT[1]

        if tilt_pct > 0:
            cmd |= self.pelco_commands.UP[1]
        elif tilt_pct < 0:
            cmd |= self.pelco_commands.DOWN[1]
        # If no movement, send stop command
        if pan_pct == 0 and tilt_pct == 0:
            cmd = self.pelco_commands.STOP[1]
            pan_value = 0
            tilt_value = 0
        pan_value = int(pan_value / 100 * 64)
        tilt_value = int(tilt_value / 100 * 64)
        packet = self.create_pelco_command(0, cmd, pan_value, tilt_value)
        self.send(packet)

    def stop(self):
        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.STOP[1], 0, 0)

            self.send(packet)
        self.moving = False

        if self.move_thread:
            self.move_thread.cancel()

    def zoom_tele(self, speed=100):
        speed_value = min(100, max(0, speed))

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.ZOOM_TELE[1], speed_value, speed_value)
            self.send(packet)

    def zoom_wide(self, speed=100):
        speed_value = min(100, max(0, speed))

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.ZOOM_WIDE[1], speed_value, speed_value)
            self.send(packet)

    def zoom_stop(self):
        self.stop()

    def focus_near(self, speed=100):
        speed_value = min(100, max(0, speed))

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(self.pelco_commands.FOCUS_NEAR[0], self.pelco_commands.FOCUS_NEAR[1],
                                               0, speed_value)
            self.send(packet)

    def focus_far(self, speed=100):
        speed_value = min(100, max(0, speed))

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.FOCUS_FAR[1], 0, speed_value)
            self.send(packet)

    def focus_stop(self):
        """Stop focus movement"""
        self.stop()

    def set_auto_focus(self, enabled):
        if self.protocol == "Pelco-D":
            if enabled:
                packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1], 0, self.pelco_presets.ZT_AF_ON)
            else:
                packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1],0, self.pelco_presets.ZT_AF_OFF)
            self.send(packet)

    def execute_focus(self):
        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1], 0, self.pelco_presets.EXECUTE_AUTOFOCUS)
            self.send(packet)

    def set_zoom(self, zoom):
        zoom_value = int(zoom / 100 * 0xFFFF)
        packet = self.create_pelco_command(0, self.pelco_commands.SET_ZOOM[1], zoom_value >> 8, zoom_value & 0xff)
        self.send(packet)

    def set_focus(self, focus):
        focus_value = int(focus / 100 * 0xFFFF)

        packet = self.create_pelco_command(0, self.pelco_commands.SET_FOCUS[1], focus_value >> 8, focus_value & 0xff)
        self.send(packet)

    def set_pan(self, degrees, speed=0):
        pan_value = int(degrees * 100)
        speed = int(min(100, max(0, speed)) * 0x40 / 100)
        packet = self.create_pelco_command(speed, self.pelco_commands.SET_PAN[1], pan_value >> 8, pan_value & 0xff)
        self.send(packet)

    def set_tilt(self, degrees, speed=0):
        tilt_value = int(degrees * 100)
        speed = int(min(100, max(0, speed)) * 0x40 / 100)
        packet = self.create_pelco_command(speed, self.pelco_commands.SET_TILT[1], tilt_value >> 8, tilt_value & 0xff)
        self.send(packet)

    def goto_preset(self, preset_num):
        """Move camera to a saved preset position"""

        if preset_num < 1 or preset_num > 255:
            print("Preset number must be between 1 and 255")
            return

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1], 0, preset_num)
            self.send(packet)

    def set_preset(self, preset_num):
        """Save current position as a preset"""
        if preset_num < 1 or preset_num > 255:
            print("Preset number must be between 1 and 255")
            return False

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.SET_PRESET[1], 0, preset_num)
        else:
            packet = self.create_pelco_p_command(self.pelco_commands["SET_PRESET"], 0, preset_num)

        success = self.send(packet)
        if success:
            print(f"Saved position as preset {preset_num}")
        return success

    def clear_preset(self, preset_num):
        if preset_num < 1 or preset_num > 255:
            print("Preset number must be between 1 and 255")
            return False

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.CLEAR_PRESET[1], 0, preset_num)

            success = self.send(packet)
            if success:
                print(f"Cleared preset {preset_num}")
            return success

    def goto_home(self):
        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1], 0, self.pelco_presets.HOME)
            self.send(packet)

    def query_position_value(self, opcode, callback):
        """Send a query command and execute callback on response."""
        packet = self.create_pelco_command(0x00, opcode, 0x00, 0x00)
        self.send(packet, callback)

    def get_pan(self, callback):
        return self.query_position_value(0x51, callback)

    def get_tilt(self, callback):
        return self.query_position_value(0x53, callback)

    def get_zoom(self, callback):
        return self.query_position_value(0x55, callback)

    def get_focus(self, callback):
        return self.query_position_value(0x61, callback)
