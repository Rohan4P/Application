OTILS_AVAILABLE = False
import logging as LogLevel

# --- Library info -----
__version__ = "2.07.240712"
PROTOCOL_VERSION = '5.2.7'
SUPPORTED_INTERFACES = ['RS485', 'RS422', 'RS232', 'USB']


class PelcoModel:
    DEFAULT = 'DEFAULT'
    RAW = 'JOHN_CENA'


# --- General info ------
COMMAND_SIZE = 7
GENERAL_RESPONSE_SIZE = 4
EXTENDED_RESPONSE_SIZE = 7
QUERY_RESPONSE_SIZE = 18
MAX_SPEED = 0x40
EXTENDED_MAX_SPEED = 0xFF
KILL_CODE = 'DIE'

# --- Byte values ------
SYNC_BYTE = 0xff

# --- Indices ----------
SYNC_INDEX = 0
ADDR_INDEX = 1
CMD1_INDEX = 2
CMD2_INDEX = 3
DATA1_INDEX = 4
DATA2_INDEX = 5
CKSM_INDEX = 6

RESP1_INDEX = 2
RESP2_INDEX = 3

QUERY_DATA1_INDEX = 2
QUERY_DATA15_INDEX = 16

# --- Enums -----
TYPE_STANDARD = 'STD'
TYPE_EXTENDED = 'EXT'
TYPE_ALTERNATE = 'ALT'
TYPE_STOP = 'STP'

CMD2_PAN_RIGHT = 0x02
CMD2_PAN_LEFT = 0x04
CMD2_TILT_UP = 0x08
CMD2_TILT_DOWN = 0x10
CMD2_ZOOM_TELE = 0x20
CMD2_ZOOM_WIDE = 0x40
CMD2_FOCUS_FAR = 0x80
CMD1_FOCUS_NEAR = 0x01
CMD1_IRIS_OPEN = 0x02
CMD1_IRIS_CLOSE = 0x04

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
EXT_CMD_QUERY_MAGNIFICATION_RESPONSE = 0x63

# Standard device errors
ERR_NONE = (0x01, 'None')
ERR_SEND = (0x02, 'Failed to send message')
ERR_CHECKSUM = (0x03, 'Invalid checksum')
ERR_MESSAGE = (0x04, 'Invalid message structure')
ERR_TIMEOUT = (0x05, 'Response timeout')
ERR_NOT_READY = (0x06, 'Device not ready')
ERR_UNKNOWN = (0x07, 'Unknown response')
ERR_UNKNOWN_CMD = (0x08, 'Unknown command')
ERR_INVALID_INPUT_PARAM = (0x09, 'Invalid parameters to function call')
ERR_NOT_SUPPORTED = (0x0a, 'Function not supported')

# Custom errors
ERR_SYNC = (-1, 'Out of sync')
ERR_BAD_VALUE = (-2, 'Invalid value in response')
ERR_BAD_PAN = (-3, 'Invalid pan speed')
ERR_BAD_TILT = (-4, 'Invalid tilt speed')

# A mapping of request CMD2 bytes to response CMD2 bytes
REQUEST_RESPONSE_MAP = {
    EXT_CMD_QUERY_PAN: EXT_CMD_QUERY_PAN_RESPONSE,
    EXT_CMD_QUERY_TILT: EXT_CMD_QUERY_TILT_RESPONSE,
    EXT_CMD_QUERY_ZOOM: EXT_CMD_QUERY_ZOOM_RESPONSE
}

CMD_UP_LEFT = 0x0C
CMD_UP_RIGHT = 0x0A
CMD_DOWN_LEFT = 0x14
CMD_DOWN_RIGHT = 0x12

MOVEMENT_COMMANDS = (
    EXT_CMD_SET_PAN, EXT_CMD_SET_TILT, CMD2_PAN_LEFT, CMD2_PAN_RIGHT, CMD2_TILT_DOWN, CMD2_TILT_UP,
    CMD_UP_LEFT, CMD_UP_RIGHT, CMD_DOWN_LEFT, CMD_DOWN_RIGHT
)


class Mode:
    PROXY = 0
    """PROXY mode is used for processing data from external sources, such as keyboards.
    In this mode, a dedicated read-only serial loop is used, but writes are still possible,
    e.g. for responding to query requests."""
    NORMAL = 1
    """NORMAL mode causes the PelcoDevice to behave like a traditional device object,
    communicating with a physical Pelco-compliant device using a one-to-one relationship between
    requests and responses."""
    WRITE_ONLY = 2
    """WRITE_ONLY mode is used for when we don't care about receiving responses. Doesn't use a serial loop."""
    VIRTUAL = 3
    """VIRTUAL mode is used when no actual communication is required."""


""" THE FOLLOWING methods are common across many Octagon device libraries, they have been copied from the
    device_library_REFONLY.py file present on the main octagon.git repo. 
    
    :func get_enum_list(enum)                               :returns ARRAY
    :func get_enum_from_string(enum, string)                :returns Tuple(..., STRING)
    :func get_enum_from_value(enum, value)                  :returns Tuple(..., STRING)
    :func enum_has_value(enum, value)                       :returns BOOL
    :func bytes_to_string(btes)                             :returns STRING
    
    :func success(data)                                     :returns DICT(success=True, data=...)
    :func error(message, code=0x00, data=None)              :returns DICT(success=False, error=...)
    
    :enum AutofocusMode
    :enum ConnectionState
    
"""
DEFAULT_CONFIG = {
    "sendAddress": 1,
    "deviceName": 'none',
    "timeout": 1.0,
    "mode": 0,  # Mode.PROXY
    "maxSpeed": MAX_SPEED
}


class ConnectionState:
    INITIALIZING = 'INITIALIZING'
    CONNECTED = 'CONNECTED'
    DISCONNECTED = 'DISCONNECTED'


class AutofocusMode:
    MANUAL = 'MANUAL'
    ZOOM_TRIGGER = 'ZOOM_TRIGGER'


def bytes_to_string(btes):
    """ Takes a 'bytes' object and returns nicely formatted, spaced string like 0xFF 0x01 ... """
    return ' '.join(["0x{:02x}".format(b).upper().replace('X', 'x') for b in btes])


def get_enum_list(enum):
    """ Return array of all enum members """
    return [enum.__dict__[m] for m in dir(enum) if not (m.startswith('__') or m.endswith('__'))]


def get_enum_from_string(enum, string):
    """ Provide the public string value and return the enum Tuple value -Assumes: (PROTOCOL_VALUE, PUBLIC_STRING) """
    match = [enum.__dict__[m] for m in dir(enum) if
             not (m.startswith('__') or m.endswith('__')) and enum.__dict__[m][1] == string]
    return match[0] if len(match) == 1 else None


def get_enum_from_value(enum, val):
    """ Provide the protocol int / byte value and return the enum Tuple value -Assumes: (PROTOCOL_VALUE, PUBLIC_STRING) """
    match = [enum.__dict__[m] for m in dir(enum) if not (m.startswith('__') or m.endswith('__')) \
             and enum.__dict__[m][0] == val]
    return match[0] if len(match) == 1 else None


def enum_has_value(enum, value):
    """ Return True if 'value' is within the 'enum' enumeration class """
    return value in [enum.__dict__[mem] for mem in dir(enum) if not mem.startswith('__')]


def success(data=None):
    return {
        'success': True,
        'data': data
    }


def error(err, data=None):
    return {
        'success': False,
        'error': {
            'code': err[0],
            'message': err[1],
            'data': data
        }
    }


from .pelco import *
