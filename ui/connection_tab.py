# ui/connection_tab.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFrame, QSpinBox
)


class ConnectionTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.init_ui()
        self.update_button_states()

    def init_ui(self):
        layout = QVBoxLayout()

        # Connection list group
        conn_group = QGroupBox("Camera Connections")
        conn_layout = QVBoxLayout()

        self.conn_combo = QComboBox()
        conn_layout.addWidget(self.conn_combo)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.edit_btn = QPushButton("Edit")
        self.del_btn = QPushButton("Delete")
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.del_btn)
        conn_layout.addLayout(btn_layout)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # Connection details
        details_group = QGroupBox("Camera Details")
        details_layout = QFormLayout()

        self.name_label = QLabel("-")
        self.ip_label = QLabel("-")
        self.port_label = QLabel("-")
        self.protocol_label = QLabel("-")
        self.rtsp_label = QLabel("-")

        details_layout.addRow("Name:", self.name_label)
        details_layout.addRow("IP Address:", self.ip_label)
        details_layout.addRow("Port:", self.port_label)
        details_layout.addRow("Protocol:", self.protocol_label)
        details_layout.addRow("RTSP URL:", self.rtsp_label)

        details_group.setLayout(details_layout)
        layout.addWidget(details_group)

        # Connect selected
        self.connect_selected_btn = QPushButton("Connect camera")
        layout.addWidget(self.connect_selected_btn)

        # Horizontal line separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Serial connection group
        serial_group = QGroupBox("Serial Connection")
        serial_layout = QFormLayout()

        # COM Port Row with buttons
        com_port_layout = QHBoxLayout()
        self.serial_combo = QComboBox()
        self.refresh_ports()

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setToolTip("Refresh")
        self.refresh_btn.setFixedWidth(40)

        com_label = QLabel("COM:")
        com_label.setFixedWidth(53)
        com_port_layout.addWidget(com_label)
        com_port_layout.addWidget(self.serial_combo)
        com_port_layout.addWidget(self.refresh_btn)
        serial_layout.addRow(com_port_layout)

        # Protocol selection
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["Pelnet", "Pelco-D"])
        serial_layout.addRow("Protocol:", self.protocol_combo)

        # Baud rate selection
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        serial_layout.addRow("BaudRate:", self.baud_combo)

        # Connection status
        self.serial_status = QLabel("Disconnected")
        self.serial_status.setStyleSheet("color: red; font-weight: bold;")
        serial_layout.addRow("Status:", self.serial_status)

        # Connection buttons
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setFixedWidth(100)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setFixedWidth(100)

        connection_layout = QHBoxLayout()
        connection_layout.addWidget(self.connect_btn)
        connection_layout.addWidget(self.disconnect_btn)
        serial_layout.addRow(connection_layout)

        serial_group.setLayout(serial_layout)
        layout.addWidget(serial_group)

        layout.addStretch()
        self.setLayout(layout)
        self.update_connection_combo()
        self.update_connection_details()

    def connect_signals(self):
        """Connect all UI signals to their handlers"""
        self.add_btn.clicked.connect(self.main_window.add_connection)
        self.edit_btn.clicked.connect(self.main_window.edit_connection)
        self.del_btn.clicked.connect(self.main_window.delete_connection)
        self.conn_combo.currentIndexChanged.connect(self.update_connection_details)
        self.connect_selected_btn.clicked.connect(self.main_window.connect_to_selected)
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn.clicked.connect(self.connect_serial)
        self.disconnect_btn.clicked.connect(self.disconnect_serial)

    def connect_serial(self):
        """Handle serial connection"""
        port = self.serial_combo.currentText()
        baud = int(self.baud_combo.currentText())
        protocol = self.protocol_combo.currentText().lower()

        if self.main_window.serial_handler.connect(port, baud, protocol):
            self.update_serial_ui(True)
        else:
            self.serial_status.setText("Connection Failed")
            self.serial_status.setStyleSheet("color: red; font-weight: bold;")

    def disconnect_serial(self):
        """Handle serial disconnection"""
        self.main_window.serial_handler.disconnect()
        self.update_serial_ui(False)

    def update_serial_ui(self, connected):
        """Update UI based on connection state"""
        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)
        if connected:
            self.serial_status.setText("Connected")
            self.serial_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.serial_status.setText("Disconnected")
            self.serial_status.setStyleSheet("color: red; font-weight: bold;")

    def update_button_states(self):
        """Update button states based on current connection status"""
        is_connected = self.main_window.serial_handler.is_connected()
        self.connect_btn.setEnabled(not is_connected)
        self.disconnect_btn.setEnabled(is_connected)
        self.update_serial_ui(is_connected)

    def refresh_ports(self):
        """Refresh the list of available COM ports"""
        self.serial_combo.clear()
        ports = self.main_window.serial_handler.list_ports()
        if ports:
            self.serial_combo.addItems(ports)
            if len(ports) == 1:  # Auto-select if only one port
                self.serial_combo.setCurrentIndex(0)
        else:
            self.serial_combo.addItem("None")

    def update_connection_combo(self):
        """Update the camera connections dropdown"""
        current_text = self.conn_combo.currentText() if self.conn_combo.currentIndex() != -1 else None
        self.conn_combo.clear()

        for conn in self.main_window.connections:
            self.conn_combo.addItem(conn.get("ip", "-") + "  :  " + conn.get("name", "Unnamed"))

        # Try to restore previous selection if possible
        if current_text:
            index = self.conn_combo.findText(current_text)
            if index >= 0:
                self.conn_combo.setCurrentIndex(index)
        elif self.conn_combo.count() > 0:  # Select first item if nothing was selected
            self.conn_combo.setCurrentIndex(0)

    def update_connection_details(self):
        """Update the connection details display"""
        if not self.main_window.connections:  # If no connections exist
            self.clear_connection_details()
            return

        idx = self.conn_combo.currentIndex()
        # If no selection or invalid index, default to first connection
        if idx == -1 or idx >= len(self.main_window.connections):
            idx = 0

        conn = self.main_window.connections[idx]
        self.name_label.setText(conn.get("name", "-"))
        self.ip_label.setText(conn.get("ip", "-"))
        self.port_label.setText(str(conn.get("port", "-")))
        self.protocol_label.setText(conn.get("protocol", "-"))
        rtsp_map = conn.get("rtsp_urls", {})
        if isinstance(rtsp_map, dict) and rtsp_map:
            rtsp_text = "\n".join(f"{k}: {v}" for k, v in rtsp_map.items())
        else:
            rtsp_text = "-"
        self.rtsp_label.setText(rtsp_text)

    def clear_connection_details(self):
        """Clear the connection details display"""
        self.name_label.setText("-")
        self.ip_label.setText("-")
        self.port_label.setText("-")
        self.protocol_label.setText("-")
        self.rtsp_label.setText("-")