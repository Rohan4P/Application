# ui/camera_control.py
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSpinBox


class CameraControlSection(QGroupBox):
    def __init__(self, main_window):
        super().__init__("Camera Control")
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("QGroupBox { font-weight: bold; }")
        layout = QVBoxLayout()

        # Status
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Status:"))
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: red;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # PTZ Address layout
        address_layout = QHBoxLayout()
        self.address_label = QLabel("PTZ Address: 1")
        self.address_input = QSpinBox()
        self.address_input.setRange(1, 255)
        self.address_input.setValue(self.main_window.ptz_controller.address)  # initial value

        self.set_address_btn = QPushButton("Set")
        self.set_address_btn.setFixedWidth(60)
        self.set_address_btn.clicked.connect(self.set_ptz_address)

        address_layout.addWidget(self.address_label)
        address_layout.addWidget(self.address_input)
        address_layout.addWidget(self.set_address_btn)

        layout.addLayout(address_layout)

        # Camera selection
        selector_layout = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedWidth(30)
        self.camera_combo = QComboBox()
        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedWidth(30)

        selector_layout.addWidget(self.prev_btn)
        selector_layout.addWidget(self.camera_combo)
        selector_layout.addWidget(self.next_btn)
        layout.addLayout(selector_layout)

        # Connection
        conn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.disconnect_btn = QPushButton("Disconnect")
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addWidget(self.disconnect_btn)
        layout.addLayout(conn_layout)

        # Stream type
        self.stream_button_layout = QHBoxLayout()
        layout.addLayout(self.stream_button_layout)
        self.stream_buttons = {}

        self.setLayout(layout)
        self.update_camera_combo()

    def set_ptz_address(self):
        new_address = self.address_input.value()
        self.main_window.ptz_controller.address = new_address
        self.address_label.setText(f"PTZ Address: {new_address}")
        self.main_window.statusBar().showMessage(f"PTZ Address set to {new_address}")

    def get_current_address(self):
        return self.address_input.value()

    def connect_signals(self):
        self.prev_btn.clicked.connect(self.main_window.previous_camera)
        self.next_btn.clicked.connect(self.main_window.next_camera)
        self.connect_btn.clicked.connect(self.main_window.connect_to_camera)
        self.disconnect_btn.clicked.connect(self.main_window.disconnect_camera)

    def update_camera_combo(self):
        self.camera_combo.clear()
        for conn in self.main_window.connections:
            self.camera_combo.addItem(conn.get("ip", "-") + "  :  " + conn.get("name", "Unnamed"))

    def set_stream_buttons(self, rtsp_map):
        # Clear previous buttons
        for btn in self.stream_buttons.values():
            self.stream_button_layout.removeWidget(btn)
            btn.deleteLater()
        self.stream_buttons.clear()

        # Create new buttons
        for stream_type, rtsp_url in rtsp_map.items():
            btn = QPushButton(stream_type.capitalize())
            btn.clicked.connect(lambda _, url=rtsp_url: self.main_window.video_stream.connect(url))
            self.stream_button_layout.addWidget(btn)
            self.stream_buttons[stream_type] = btn