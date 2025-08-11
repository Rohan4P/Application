import json
from license_manager import LicenseManager
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from datetime import datetime

def sign_license(data, private_key_path="private.pem"):
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    data_copy = data.copy()
    data_str = json.dumps(data_copy, sort_keys=True).encode()
    signature = private_key.sign(data_str, padding.PKCS1v15(), hashes.SHA256())
    data["signature"] = signature.hex()
    return data

def generate_license_file(license_type="permanent", expires="2025-12-31", out_file="license.json"):
    lm = LicenseManager()  # This will get local hardware info

    license_data = {
        "license_type": license_type,
        "hardware_info": lm._collect_fingerprint(),
        "issued": datetime.today().strftime("%Y-%m-%d"),
    }

    if license_type == "temporary":
        license_data["expires"] = expires

    signed = sign_license(license_data)
    with open(out_file, "w") as f:
        json.dump(signed, f, indent=2)

    print(f"License saved to {out_file}")

# Usage
if __name__ == "__main__":
    generate_license_file("permanent")
