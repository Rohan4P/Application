import base64
import json
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QComboBox, QSpinBox
)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class LicenseGenerator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("License Generator")
        self.setMinimumWidth(450)

        self.private_key = None  # Will hold the loaded private key

        layout = QVBoxLayout()

        # --- Private Key Verification ---
        self.key_label = QLabel("No private key loaded")
        self.load_key_btn = QPushButton("Load Private Key")
        self.load_key_btn.clicked.connect(self.load_private_key)

        key_layout = QHBoxLayout()
        key_layout.addWidget(self.key_label)
        key_layout.addWidget(self.load_key_btn)
        layout.addLayout(key_layout)

        # --- Device ID Input ---
        self.device_id = QLineEdit()
        self.license_type = QComboBox()
        self.license_type.addItems(["permanent", "temporary"])
        self.duration = QSpinBox()
        self.duration.setRange(1, 3650)
        self.duration.setValue(30)

        form = [
            ("Device ID", self.device_id),
            ("License Type", self.license_type),
            ("Duration (days)", self.duration)
        ]
        for label, widget in form:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(widget)
            layout.addLayout(row)

        # --- Generate License Button (Initially Disabled) ---
        self.generate_btn = QPushButton("Generate License")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self.generate_license)
        layout.addWidget(self.generate_btn)

        self.setLayout(layout)

    def load_private_key(self):
        """Select and verify private key"""
        key_path, _ = QFileDialog.getOpenFileName(self, "Select Private Key", "", "PEM Files (*.pem)")
        if not key_path:
            return

        try:
            with open(key_path, "rb") as f:
                self.private_key = serialization.load_pem_private_key(f.read(), password=None)

            # Simple verification: try signing some data
            test_data = b"verify_key"
            self.private_key.sign(
                test_data,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256()
            )

            # Update UI
            self.key_label.setText(f"Private key loaded: {key_path.split('/')[-1]}")
            self.generate_btn.setEnabled(True)

            # Disable verify button after successful verification
            self.load_key_btn.setEnabled(False)

            QMessageBox.information(self, "Success", "Private key verified successfully!")

        except Exception as e:
            self.private_key = None
            self.generate_btn.setEnabled(False)
            self.key_label.setText("No private key loaded")
            QMessageBox.critical(self, "Error", f"Failed to load private key:\n{str(e)}")

    def generate_license(self):
        if not self.private_key:
            QMessageBox.warning(self, "Error", "No private key loaded")
            return

        device_id = self.device_id.text().strip()
        if not device_id:
            QMessageBox.warning(self, "Error", "Device ID is required")
            return

        license_type = self.license_type.currentText()
        issued = datetime.today().strftime("%Y-%m-%d")

        license_data = {
            "device_id": device_id,
            "issued": issued,
            "license_type": license_type,
        }

        if license_type == "temporary":
            expires = (datetime.today() + timedelta(days=self.duration.value())).strftime("%Y-%m-%d")
            license_data["expires"] = expires

        try:
            # Sign license
            data_bytes = json.dumps({k: v for k, v in license_data.items() if k != "signature"}, sort_keys=True).encode()
            signature = self.private_key.sign(
                data_bytes,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256()
            )
            license_data["signature"] = signature.hex()

            # Save as base64 .lic
            save_path, _ = QFileDialog.getSaveFileName(self, "Save License", "license.lic", "License Files (*.lic)")
            if save_path:
                license_json = json.dumps(license_data, indent=2)
                encoded = base64.b64encode(license_json.encode()).decode()
                with open(save_path, "w") as f:
                    f.write(encoded)
                QMessageBox.information(self, "Success", f"License saved: {save_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


if __name__ == "__main__":
    app = QApplication([])
    window = LicenseGenerator()
    window.show()
    app.exec()
