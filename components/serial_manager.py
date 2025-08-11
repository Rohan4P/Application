import serial
import threading
from serial.tools import list_ports
from lib.pelco import PelcoDevice, PelcoModel


class SerialHandler:
    def __init__(self, defaults):
        self._keyboard_event_subscribers = []
        self._commPort = defaults.get('serialCom')
        self._protocol = defaults.get('protocol')
        self._baud = defaults.get('baud')
        self._serial_device = None
        self._serial_com = None
        self._connected = False

    def register_keyboard_subscriber(self, subscriber):
        self._keyboard_event_subscribers.append(subscriber)

    def get_backup_values(self):
        return dict(protocol=self._protocol, serialCom=self._commPort, baud=self._baud)

    def connect(self, port, baudrate, protocol):
        if self._serial_com and self._serial_com.is_open:
            return True  # Already connected

        try:
            self._serial_com = serial.Serial(port, baudrate, timeout=0.1)
            self._serial_device = PelcoDevice(
                self._serial_com,
                model=PelcoModel.RAW,
                config=dict(deviceName=port, rawMode=True, timeout=0.25)
            )
            self._serial_device.register_reader(self._handle_keyboard_message)
            self._connected = True
            return True
        except serial.SerialException as err:
            print(f"[SerialHandler] Connection error: {err}")
            return False

    def disconnect(self):
        if self._serial_com and self._serial_com.is_open:
            self._serial_com.close()
        self._connected = False

    def is_connected(self):
        return self._connected

    def _handle_keyboard_message(self, pelco_device, message):
        for listener in self._keyboard_event_subscribers:
            listener(message)

    @staticmethod
    def list_ports():
        return [com.device for com in list_ports.comports()]
