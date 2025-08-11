from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                               QLineEdit, QSpinBox, QComboBox, QMessageBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
                               QPushButton, QSizePolicy)


class ConnectionDialog(QDialog):
    def __init__(self, parent=None, connection_data=None):
        super().__init__(parent)
        self.setWindowTitle("Connection Settings")
        self.resize(400, 200)

        # Create form layout
        layout = QFormLayout(self)

        # Connection name
        self.name_input = QLineEdit()
        layout.addRow("Connection Name:", self.name_input)

        # IP address
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        layout.addRow("IP Address:", self.ip_input)

        # Port
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(4001)  # Default Pelco port
        layout.addRow("Port:", self.port_input)

        # Protocol selection
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["Pelco-D", "Pelco-P"])
        layout.addRow("Protocol:", self.protocol_combo)

        # Camera address (for Pelco protocols)
        self.address_input = QSpinBox()
        self.address_input.setRange(1, 255)
        self.address_input.setValue(1)
        layout.addRow("Camera Address:", self.address_input)

        # Create layout with label and + button
        rtsp_header_layout = QHBoxLayout()

        # Title
        rtsp_title = QLabel("RTSP Streams (Optional):")
        rtsp_title.setStyleSheet("font-weight: bold;")

        # Add button styled
        self.add_rtsp_btn = QPushButton("＋Add")
        self.add_rtsp_btn.setFixedSize(45, 24)
        self.add_rtsp_btn.clicked.connect(lambda: self.add_rtsp_entry())

        # Add to header layout
        rtsp_header_layout.addWidget(rtsp_title)
        rtsp_header_layout.addStretch()
        rtsp_header_layout.addWidget(self.add_rtsp_btn)

        # Place the header into a QWidget so it can be added to the form layout
        rtsp_header_widget = QWidget()
        rtsp_header_widget.setLayout(rtsp_header_layout)
        layout.addRow(rtsp_header_widget)

        # Vertical layout for all entries
        self.rtsp_entries_layout = QVBoxLayout()
        self.rtsp_entries = []

        # Container widget to hold RTSP entries layout
        rtsp_widget = QWidget()
        rtsp_widget.setLayout(self.rtsp_entries_layout)
        layout.addRow(rtsp_widget)

        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

        # Fill with existing data if provided
        if connection_data:
            self.name_input.setText(connection_data.get("name", "System"))
            self.ip_input.setText(connection_data.get("ip", "192.168.3.175"))
            self.port_input.setValue(connection_data.get("port", 8005))

            protocol_index = self.protocol_combo.findText(connection_data.get("protocol", "Pelco-D"))
            if protocol_index >= 0:
                self.protocol_combo.setCurrentIndex(protocol_index)

            self.address_input.setValue(connection_data.get("address", 1))
            # Load RTSP URLs (new dictionary format)
            rtsp_dict = connection_data.get("rtsp_urls", {})

            if rtsp_dict:
                for key, url in rtsp_dict.items():
                    self.add_rtsp_entry(key, url)

    def add_rtsp_entry(self, key: str = "", url: str = ""):
        key_input = QLineEdit(key)
        key_input.setPlaceholderText("e.g. visible")
        key_input.setFixedWidth(100)  # Small fixed width for key

        url_input = QLineEdit(url)
        url_input.setPlaceholderText("rtsp://admin:!Inf2019@192.168.0.177:554/net0")

        url_input.setMinimumWidth(300)  # Let it stretch
        url_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        remove_btn = QPushButton("－Delete")
        remove_btn.setFixedSize(55, 28)

        remove_btn.clicked.connect(lambda: self.remove_rtsp_entry(entry_layout, (key_input, url_input)))

        entry_layout = QHBoxLayout()
        entry_layout.addWidget(key_input)
        entry_layout.addWidget(url_input)
        entry_layout.addWidget(remove_btn)

        self.rtsp_entries_layout.addLayout(entry_layout)
        self.rtsp_entries.append((key_input, url_input))

    def remove_rtsp_entry(self, layout, entry):
        """Remove an RTSP row"""
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.rtsp_entries_layout.removeItem(layout)
        self.rtsp_entries.remove(entry)

    def get_connection_data(self):
        rtsp_urls = {}
        for key_input, url_input in self.rtsp_entries:
            key = key_input.text().strip()
            url = url_input.text().strip()
            if key and url:
                rtsp_urls[key] = url

        return {
            "name": self.name_input.text(),
            "ip": self.ip_input.text(),
            "port": self.port_input.value(),
            "protocol": self.protocol_combo.currentText(),
            "address": self.address_input.value(),
            "rtsp_urls": rtsp_urls
        }


class PresetDialog(QDialog):
    def __init__(self, parent=None, preset_num=None, preset_name="", preset_type=0):
        super().__init__(parent)
        self.setWindowTitle("Edit Preset" if preset_num else "Add Preset")

        layout = QFormLayout(self)

        # Number input
        self.number_input = QSpinBox()
        if preset_type == 0:  # Positional
            self.number_input.setRange(1, 79)
        else:  # Functional
            self.number_input.setRange(80, 256)

        if preset_num:
            self.number_input.setValue(preset_num)
        layout.addRow("Preset Number:", self.number_input)

        # Name input
        self.name_input = QLineEdit(preset_name)
        layout.addRow("Preset Name:", self.name_input)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def get_preset_data(self):
        return {
            "number": self.number_input.value(),
            "name": self.name_input.text(),
            "type": "positional" if self.number_input.value() <= 79 else "functional"
        }