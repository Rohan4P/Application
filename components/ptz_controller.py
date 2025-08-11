import socket
import time
import threading
import struct
import serial
from lib.pelco.protocols import PelcoPTZCommands, PelcoPresets
from lib.pelco import *


class PTZController:
    def __init__(self, serial_port=None):
        self.serial_port = serial_port
        self.ip = ""
        self.port = 8005
        self.protocol = "Pelco-D"
        self.address = 1
        self.socket = None
        self.serial_port = None
        self.connected = False
        self.moving = False
        self.move_thread = None
        self.pelco_commands = PelcoPTZCommands
        self.pelco_presets = PelcoPresets
        self.pelco_device = PelcoDevice()
        self.get_address_callback = None

    def connect(self, ip="", port=4001, protocol="Pelco-D", address=1, serial_port=None):
        self.ip = ip
        self.port = port
        self.protocol = protocol
        self.address = address

        try:
            if serial_port:
                self.serial_port = serial.Serial(
                    port=serial_port,
                    baudrate=9600,
                    bytesize=8,
                    parity='N',
                    stopbits=1,
                    timeout=1
                )
                self.connected = True
                print(f"Connected to PTZ controller via serial port {serial_port}")
            else:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(5)
                self.socket.connect((self.ip, self.port))
                self.connected = True
                print(f"Connected to PTZ controller at {ip}:{port}")

            return True
        except Exception as e:
            print(f"Error connecting to PTZ controller: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from camera controller"""
        if self.moving:
            self.stop()

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        if self.serial_port:
            try:
                self.serial_port.close()
            except:
                pass
            self.serial_port = None

        self.connected = False
        print("Disconnected from PTZ controller")

    def is_connected(self):
        """Check if connected to camera controller"""
        return self.connected

    def send_command(self, command_bytes):
        """Send raw command bytes to the controller"""
        print("SEND :", command_bytes.hex(" "))
        if not self.connected:
            print("Not connected to PTZ controller")
            return False
        try:
            if self.socket:
                self.socket.send(command_bytes)
            elif self.serial_port:
                self.serial_port.write(command_bytes)
            return True
        except Exception as e:
            print(f"Error sending command: {e}")
            return False

    def read_command(self, len=1):
        if not self.connected:
            print("Not connected to PTZ controller")
            return False
        response = None
        try:
            if self.socket:
                response = self.socket.recv(len)
            elif self.serial_port:
                response = self.serial_port.read(len)
            return response
        except Exception as e:
            print(f"Error receiving command: {e}")
            return False

    def set_address_provider(self, callback):
        """Set function to retrieve current PTZ address dynamically"""
        self.get_address_callback = callback

    def create_pelco_command(self, cmd1, cmd2, data1=0, data2=0):
        """Create a Pelco-D protocol command packet"""
        sync_byte = 0xFF

        # Calculate checksum (sum of all bytes except sync and checksum, mod 256)
        checksum = (self.address + cmd1 + cmd2 + data1 + data2) % 256
        # Create command packet
        packet = struct.pack('BBBBBBB', sync_byte, self.address, cmd1, cmd2, data1, data2, checksum)
        return packet

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

        # Create and send command
        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, cmd, pan_value, tilt_value)
            self.send_command(packet)

    def stop(self):
        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.STOP[1], 0, 0)

            self.send_command(packet)
        self.moving = False

        if self.move_thread:
            self.move_thread.cancel()

    def zoom_tele(self, speed=100):
        speed_value = min(100, max(0, speed))

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.ZOOM_TELE[1], speed_value, speed_value)
            self.send_command(packet)

    def zoom_wide(self, speed=100):
        speed_value = min(100, max(0, speed))

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.ZOOM_WIDE[1], speed_value, speed_value)
            self.send_command(packet)

    def zoom_stop(self):
        self.stop()

    def focus_near(self, speed=100):
        speed_value = min(100, max(0, speed))

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(self.pelco_commands.FOCUS_NEAR[0], self.pelco_commands.FOCUS_NEAR[1],
                                               0, speed_value)
            self.send_command(packet)

    def focus_far(self, speed=100):
        speed_value = min(100, max(0, speed))

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.FOCUS_FAR[1], 0, speed_value)
            self.send_command(packet)

    def focus_stop(self):
        """Stop focus movement"""
        self.stop()

    def set_auto_focus(self, enabled):
        if self.protocol == "Pelco-D":
            if enabled:
                packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1], 0, self.pelco_presets.ZT_AF_ON)
            else:
                packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1],0, self.pelco_presets.ZT_AF_OFF)
            self.send_command(packet)

    def execute_focus(self):
        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1], 0, self.pelco_presets.EXECUTE_AUTOFOCUS)
            self.send_command(packet)

    def set_zoom(self, zoom):
        zoom_value = int(zoom * 100)
        packet = self.create_pelco_command(0, self.pelco_commands.SET_ZOOM[1], zoom_value >> 8, zoom_value & 0xff)
        self.send_command(packet)

    def set_focus(self, focus):
        focus_value = int(focus * 100)
        packet = self.create_pelco_command(0, self.pelco_commands.SET_FOCUS[1], focus_value >> 8, focus_value & 0xff)
        self.send_command(packet)

    def set_pan(self, degrees, speed=0):
        pan_value = int(degrees * 100)
        packet = self.create_pelco_command(speed, self.pelco_commands.SET_PAN[1], pan_value >> 8, pan_value & 0xff)
        self.send_command(packet)

    def set_tilt(self, degrees, speed=0):
        tilt_value = int(degrees * 100)
        packet = self.create_pelco_command(speed, self.pelco_commands.SET_TILT[1], tilt_value >> 8, tilt_value & 0xff)
        self.send_command(packet)

    def goto_preset(self, preset_num):
        """Move camera to a saved preset position"""

        if preset_num < 1 or preset_num > 255:
            print("Preset number must be between 1 and 255")
            return

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1], 0, preset_num)
            self.send_command(packet)

    def set_preset(self, preset_num):
        """Save current position as a preset"""
        if preset_num < 1 or preset_num > 255:
            print("Preset number must be between 1 and 255")
            return False

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.SET_PRESET[1], 0, preset_num)
        else:
            packet = self.create_pelco_p_command(self.pelco_commands["SET_PRESET"], 0, preset_num)

        success = self.send_command(packet)
        if success:
            print(f"Saved position as preset {preset_num}")
        return success

    def clear_preset(self, preset_num):
        if preset_num < 1 or preset_num > 255:
            print("Preset number must be between 1 and 255")
            return False

        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.CLEAR_PRESET[1], 0, preset_num)

            success = self.send_command(packet)
            if success:
                print(f"Cleared preset {preset_num}")
            return success

    def goto_home(self):
        if self.protocol == "Pelco-D":
            packet = self.create_pelco_command(0, self.pelco_commands.CALL_PRESET[1], 0, self.pelco_presets.HOME)
            self.send_command(packet)

    def query_position_value(self, opcode, callback):
        """Send a query command and execute callback on response."""
        # if not self.serial_port or not self.serial_port.is_open:
        #     return

        # Create and send query command
        packet = self.create_pelco_command(0x00, opcode, 0x00, 0x00)
        self.send_command(packet)

        # Wait and read response (adjust size as needed, 7 is typical for Pelco-D)
        try:
            response = self.read_command(7)
            if response and len(response) == 7:
                callback(self.pelco_device._parse(response))
        except Exception as e:
            print(f"Query failed: {e}")

    def get_pan(self, callback):
        return self.query_position_value(0x51, callback)

    def get_tilt(self, callback):
        return self.query_position_value(0x53, callback)

    def get_zoom(self, callback):
        return  self.query_position_value(0x55, callback)

    def get_focus(self, callback):
        return self.query_position_value(0x61, callback)

