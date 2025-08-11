import platform
import uuid
import hashlib
import subprocess
import json
import os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from datetime import datetime


class LicenseManager:
    def __init__(self, public_key_path="public.pem", license_file="license.json", tolerance=0.66):
        self.license_file = license_file
        self.public_key = self._load_public_key(public_key_path)
        self.tolerance = tolerance
        self.hardware_fingerprint = self._collect_fingerprint()

    def _load_public_key(self, path):
        with open(path, "rb") as f:
            return serialization.load_pem_public_key(f.read())

    def _collect_fingerprint(self):
        return {
            "cpu": self._get_cpu_id(),
            "motherboard": self._get_motherboard_id(),
            "mac": self._get_mac_address()
        }

    def _get_cpu_id(self):
        try:
            if platform.system() == "Windows":
                # Try PowerShell first (works on Windows 11)
                try:
                    command = 'Get-WmiObject Win32_Processor | Select-Object -ExpandProperty ProcessorId'
                    result = subprocess.check_output(["powershell", command], stderr=subprocess.DEVNULL, shell=True)
                    return result.decode().strip()
                except:
                    # Fall back to WMIC if PowerShell fails (for older Windows)
                    return subprocess.check_output(
                        ['wmic', 'cpu', 'get', 'ProcessorId'], stderr=subprocess.DEVNULL
                    ).decode().split("\n")[1].strip()
            elif platform.system() == "Linux":
                return subprocess.check_output(
                    "cat /proc/cpuinfo | grep 'Serial' || lscpu", shell=True
                ).decode().strip()
        except:
            return None

    def _get_motherboard_id(self):
        try:
            if platform.system() == "Windows":
                # Try PowerShell first
                try:
                    command = 'Get-WmiObject Win32_BaseBoard | Select-Object -ExpandProperty SerialNumber'
                    result = subprocess.check_output(["powershell", command], stderr=subprocess.DEVNULL, shell=True)
                    return result.decode().strip()
                except:
                    # Fall back to WMIC
                    return subprocess.check_output(
                        ['wmic', 'baseboard', 'get', 'SerialNumber'], stderr=subprocess.DEVNULL
                    ).decode().split("\n")[1].strip()
            elif platform.system() == "Linux":
                return open("/sys/class/dmi/id/board_serial", "r").read().strip()
        except:
            return None

    def _get_mac_address(self):
        mac = uuid.getnode()
        return ':'.join(('%012X' % mac)[i:i + 2] for i in range(0, 12, 2))

    def _verify_signature(self, license_data, signature):
        data = json.dumps(license_data, sort_keys=True).encode()
        try:
            self.public_key.verify(
                signature,
                data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True
        except Exception:
            return False

    def _compare_fingerprints(self, stored):
        match = sum(1 for k in self.hardware_fingerprint if stored.get(k) == self.hardware_fingerprint[k])
        return match / len(self.hardware_fingerprint)

    def load_license(self):
        if not os.path.exists(self.license_file):
            return {"status": "no_license"}

        with open(self.license_file, "r") as f:
            full_data = json.load(f)

        signature = bytes.fromhex(full_data.pop("signature", ""))
        if not self._verify_signature(full_data, signature):
            return {"status": "invalid_signature"}

        match = self._compare_fingerprints(full_data.get("hardware_info", {}))
        if match < self.tolerance:
            return {"status": "hardware_mismatch", "match": match}

        if full_data["license_type"] == "temporary":
            if datetime.strptime(full_data["expires"], "%Y-%m-%d") < datetime.today():
                return {"status": "expired"}
            return {"status": "valid_temporary", "license": full_data}

        return {"status": "valid_permanent", "license": full_data}
