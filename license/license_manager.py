# license/license_manager.py
import os
import json
import base64
import hashlib
import platform
import uuid
import subprocess
from datetime import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class LicenseManager:
    def __init__(self, public_key_path="public.pem", license_file="license.lic", tolerance=0.66):
        self.license_file = license_file
        self.public_key = self._load_public_key(public_key_path) if os.path.exists(public_key_path) else None
        self.tolerance = tolerance
        self.hardware_fingerprint = self._collect_fingerprint()
        self.device_id = self._generate_device_id()

        # cache
        self._last_license_data = None

    # ---------------- Public Methods ---------------- #

    def get_device_id(self):
        return self.device_id

    def register_device(self, customer_name=""):
        """Save device info into a JSON file for registration"""
        device_info = {
            "device_id": self.device_id,
            "hardware_info": self.hardware_fingerprint,
            "customer_name": customer_name,
            "registration_date": datetime.now().isoformat()
        }
        file_path = f"device_info_{self.device_id}.json"
        with open(file_path, "w") as f:
            json.dump(device_info, f, indent=2)
        return file_path

    def install_license(self, license_path):
        """Validate and install license file"""
        try:
            with open(license_path, "r") as f:
                content = f.read().strip()

            # decode base64
            decoded = base64.b64decode(content).decode()
            license_data = json.loads(decoded)

            sig = license_data.get("signature")
            if not sig:
                return {"success": False, "message": "Invalid license format (no signature)"}

            raw_sig = bytes.fromhex(sig)
            data = {k: v for k, v in license_data.items() if k != "signature"}

            if not self._verify_signature(data, raw_sig):
                return {"success": False, "message": "Signature verification failed"}

            # Save validated license
            with open(self.license_file, "w") as f:
                f.write(content)

            return {"success": True, "message": "License installed successfully"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def load_license(self, force=False):
        """Load and validate license"""
        if self._last_license_data and not force:
            return self._last_license_data

        if not os.path.exists(self.license_file):
            return {"status": "no_license"}

        try:
            with open(self.license_file, "r") as f:
                content = f.read().strip()
            decoded = base64.b64decode(content).decode()
            full_data = json.loads(decoded)

            signature = bytes.fromhex(full_data.pop("signature", ""))
            if not self._verify_signature(full_data, signature):
                return {"status": "invalid_signature"}

            # Device ID check
            if full_data["device_id"] != self.device_id:
                return {"status": "hardware_mismatch"}

            if full_data.get("license_type") == "temporary":
                if datetime.strptime(full_data.get("expires"), "%Y-%m-%d") < datetime.today():
                    return {"status": "expired"}
                result = {"status": "valid_temporary", "license": full_data}
            else:
                result = {"status": "valid_permanent", "license": full_data}

            self._last_license_data = result
            return result

        except Exception as e:
            return {"status": "invalid_license", "error": str(e)}
    # ---------------- Internal Helpers ---------------- #

    def _load_public_key(self, path):
        try:
            with open(path, "rb") as f:
                return serialization.load_pem_public_key(f.read())
        except Exception:
            return None

    def _collect_fingerprint(self):
        return {
            "cpu": self._get_cpu_id(),
            "motherboard": self._get_motherboard_id(),
            "mac": self._get_mac_address()
        }

    def _generate_device_id(self):
        """Generate a short unique device ID from fingerprint"""
        fingerprint_str = json.dumps(self.hardware_fingerprint, sort_keys=True)
        return base64.b64encode(hashlib.sha256(fingerprint_str.encode()).digest()).decode()[:16]

    def _get_cpu_id(self):
        try:
            if platform.system() == "Windows":
                cmd = ["powershell", "-Command",
                       "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty ProcessorId"]
                res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
                return res.decode().strip() or "Unknown_CPU"
            elif platform.system() == "Linux":
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "Serial" in line or "ID" in line:
                            return line.split(":")[1].strip()
                return "Unknown_CPU"

        except Exception:
            return "Unknown_CPU"

    def _get_motherboard_id(self):
        try:
            if platform.system() == "Windows":
                cmd = ["powershell", "-Command",
                       "Get-CimInstance Win32_BaseBoard | Select-Object -ExpandProperty SerialNumber"]
                res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
                return res.decode().strip() or "Unknown_MB"
            elif platform.system() == "Linux":
                try:
                    return open("/sys/class/dmi/id/board_serial", "r").read().strip()
                except FileNotFoundError:
                    return "Unknown_MB"

        except Exception:
            return "Unknown_MB"

    def _get_mac_address(self):
        try:
            mac = uuid.getnode()
            mac_str = ':'.join(('%012X' % mac)[i:i + 2] for i in range(0, 12, 2))
            return mac_str if mac_str != '00:00:00:00:00:00' else "Unknown_MAC"
        except Exception:
            return "Unknown_MAC"

    def _verify_signature(self, license_data, signature):
        if not self.public_key:
            return False
        data = json.dumps(license_data, sort_keys=True).encode()
        try:
            self.public_key.verify(
                signature,
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except Exception:
            return False
