import threading
import time
from PySide6.QtWidgets import QMainWindow, QTabWidget, QSplitter, QMessageBox, QLabel, QPushButton, QVBoxLayout, QDialog
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from components.video_stream import RTSPVideoStream
from components.ptz_controller import PTZController
from components.serial_manager import SerialHandler
from ui.control_tab import ControlTab
from ui.connection_tab import ConnectionTab
from ui.dialogs import ConnectionDialog, PresetDialog
from utils.settings import load_connections, save_connections, load_presets, save_presets
from license.license_manager import LicenseManager
import core_config


class VMSMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Octagon Node - Video Management Tool")
        self.setMinimumSize(1200, 800)

        self.license_manager = LicenseManager("license/public.pem", "license/license.json")
        # check License()
        self._check_license_validity()

        # Initialize components
        self.init_components()
        self.init_ui()
        self.connect_signals()

        # Start monitoring thread
        self._monitoring = False
        self._monitor_thread = None
        self._position_callbacks = {
            'pan': self._update_pan_display,
            'tilt': self._update_tilt_display,
            'zoom': self._update_zoom_display,
            'focus': self._update_focus_display
        }
        self._last_update_time = time.time()
        self.start_position_monitor()

        # Initialize key states
        self.setFocusPolicy(Qt.StrongFocus)  # Ensure window can receive key events
        self.setFocus()  #
        self.active_commands = {
            'pan': None,  # Stores active pan command
            'tilt': None,  # Stores active tilt command
            'zoom': None,  # Stores active zoom command
            'focus': None  # Stores active focus command
        }
        self.key_state_lock = threading.Lock()  # Thread-safe access to key states

    def init_components(self):
        """Initialize all major components"""
        self.video_stream = RTSPVideoStream(self)
        defaults = {'serialCom': 'COM3', 'protocol': 'pelnet', 'baud': 9600}
        self.serial_handler = SerialHandler(defaults)
        self.serial_handler.register_keyboard_subscriber(self.handle_pelco_keyboard_command)
        self.ptz_controller = PTZController(self.serial_handler)
        self.ptz_controller.set_address_provider(
            lambda: self.control_tab.camera_control.address_input.value()
        )

        # Load saved data
        self.connections = load_connections()
        self.presets = load_presets()
        self.current_connection_index = -1

    def _check_license_validity(self):
        result = self.license_manager.load_license()
        if result["status"] == "expired":
            QMessageBox.warning(self, "License Expired", "Your temporary license has expired.")

        elif result["status"] in ["no_license", "invalid_signature", "hardware_mismatch"]:
            QMessageBox.critical(self, "License Invalid", f"Problem: {result['status']}")

        if result["status"].startswith("valid"):
            print("✅ License OK:", result["status"])
        else:
            print("❌ License error:", result["status"])

    def show_disclaimer(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Disclaimer")
        layout = QVBoxLayout(dialog)
        disclaimer = (
            "<b>App:</b> Octagon Node Software<br>"
            f"<b>Version:</b> {core_config.__version__}<br><br>"

            "<b>Support Options:</b><br>"
            "For support and additional information, please contact:<br>"
            "Ascendent Technology Group, Infiniti Division<br>"
            "<b>Contact:</b> INFO@INFINITIOPTICS.COM<br>"
            "Phone: 1-866-200-9191 / 1-250-426-8100<br><br>"

            "<b>Copyright & Ownership:</b><br>"
            "© Ascendent Technology Group<br>"
            "Date: [2025] – [2035]<br>"
            "Title: Ascendent Technology Group [2025] – [2035] All Rights Reserved<br><br>"

            "<b>Notice:</b><br>"
            "All information contained herein is, and remains, the property of Ascendent Technology Group and its suppliers (if any).<br><br>"

            "The intellectual and technical concepts contained herein are proprietary to Ascendent Technology Group and its suppliers "
            "and may be covered by U.S. and foreign patents (including patents in process), and are protected by trade secret or copyright law.<br><br>"

            "<b>Important:</b> Dissemination of this information or reproduction of this material is strictly forbidden "
            "unless prior written permission is obtained from Ascendent Technology Group."
        )
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(disclaimer)
        label.setWordWrap(True)
        layout.addWidget(label)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)

        dialog.exec_()

    def show_license_info(self):
        result = self.license_manager.load_license()

        dialog = QDialog(self)
        dialog.setWindowTitle("License Information")
        layout = QVBoxLayout(dialog)

        if result["status"] in ["valid_permanent", "valid_temporary"]:
            lic = result["license"]
            license_type = lic.get("license_type", "N/A")
            issued = lic.get("issued", "N/A")
            expires = lic.get("expires", "N/A") if license_type == "temporary" else "—"
            hardware = lic.get("hardware_info", {})

            info_text = (
                f"<b>Status:</b> Valid ({license_type})<br>"
                f"<b>Issued:</b> {issued}<br>"
                f"<b>Expires:</b> {expires}<br><br>"
                f"<b>Hardware:</b><br>"
                f"CPU ID: {hardware.get('cpu', 'N/A')}<br>"
                f"MB ID: {hardware.get('motherboard', 'N/A')}<br>"
                f"MAC: {hardware.get('mac', 'N/A')}"
            )
        else:
            info_text = f"<b>Status:</b> {result['status'].replace('_', ' ').capitalize()}"

        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(info_text)
        label.setWordWrap(True)
        layout.addWidget(label)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)

        dialog.exec()

    def init_ui(self):
        """Initialize the main UI components"""
        # Main splitter (video on left, controls on right)
        self.main_splitter = QSplitter(Qt.Horizontal)

        # Video panel
        self.video_panel = self.video_stream.get_video_widget()
        self.main_splitter.addWidget(self.video_panel)

        # Control tabs
        self.control_tabs = QTabWidget()
        self.control_tabs.setMinimumWidth(300)
        self.control_tabs.setMaximumWidth(400)

        # Create tabs
        self.control_tab = ControlTab(self)
        self.connection_tab = ConnectionTab(self)

        self.control_tabs.addTab(self.control_tab, "Controls")
        self.control_tabs.addTab(self.connection_tab, "Connections")

        self.main_splitter.addWidget(self.control_tabs)
        self.main_splitter.setSizes([700, 300])

        # Set as central widget
        self.setCentralWidget(self.main_splitter)

        # Create menu and status bar
        self.create_menu_bar()
        self.statusBar().showMessage("Ready")

    def create_menu_bar(self):
        """Create the main menu bar"""
        # File menu
        file_menu = self.menuBar().addMenu("&Action")
        self.exit_action = file_menu.addAction("Exit")
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)

        # View menu
        view_menu = self.menuBar().addMenu("&View")
        self.toggle_controls_action = view_menu.addAction("Toggle Control Panel")
        self.toggle_controls_action.setShortcut("Ctrl+T")
        self.fullscreen_action = view_menu.addAction("Fullscreen")
        self.fullscreen_action.setShortcut("F11")

        # info menu
        info_menu = self.menuBar().addMenu("&Info")
        # Disclaimer
        self.disclaimer_action = info_menu.addAction("Disclaimer")
        self.disclaimer_action.triggered.connect(self.show_disclaimer)
        # License
        self.license_action = info_menu.addAction("License")
        self.license_action.triggered.connect(self.show_license_info)

        # Camera menu
        # camera_menu = self.menuBar().addMenu("&Camera")
        # self.connect_action = camera_menu.addAction("Connect")
        # self.disconnect_action = camera_menu.addAction("Disconnect")

    def connect_signals(self):
        """Connect all signals and slots"""
        # Connect tab signals
        self.control_tab.connect_signals()
        self.connection_tab.connect_signals()

        # Connect menu actions
        self.toggle_controls_action.triggered.connect(self.toggle_control_panel)
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        # self.connect_action.triggered.connect(self.connect_to_camera)
        # self.disconnect_action.triggered.connect(self.disconnect_camera)

    # ================= PTZ Control Methods =================
    def on_joystick_moved(self, x, y):
        """Handle joystick movement"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        # Deadzone handling
        x = 0 if -0.1 < x < 0.1 else x
        y = 0 if -0.1 < y < 0.1 else y

        speed_factor = self.control_tab.ptz_control.speed_slider.value()
        pan_speed = int(x * speed_factor)
        tilt_speed = int(-y * speed_factor)  # Invert Y for natural control

        self.ptz_controller.pan_tilt(pan_speed, tilt_speed)

    def zoom_control(self, direction):
        """Handle zoom control commands"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        speed = 100  # Fixed speed for now
        if direction == "wide":
            self.ptz_controller.zoom_wide(speed)
            self.statusBar().showMessage(f"Zooming wide at speed {speed}")
        elif direction == "tele":
            self.ptz_controller.zoom_tele(speed)
            self.statusBar().showMessage(f"Zooming tele at speed {speed}")
        else:  # stop
            self.ptz_controller.zoom_stop()
            self.statusBar().showMessage("Zoom stopped")

    def focus_control(self, direction):
        """Handle focus control commands"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        speed = 100  # Fixed speed for now
        if direction == "near":
            self.ptz_controller.focus_near(speed)
            self.statusBar().showMessage(f"Focusing near at speed {speed}")
        elif direction == "far":
            self.ptz_controller.focus_far(speed)
            self.statusBar().showMessage(f"Focusing far at speed {speed}")
        else:  # stop
            self.ptz_controller.focus_stop()
            self.statusBar().showMessage("Focus stopped")

    def set_absolute_pan(self):
        """Set absolute pan position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        position = self.control_tab.ptz_control.pan_spin.value()
        speed = self.control_tab.ptz_control.pan_speed_spin.value()
        self.ptz_controller.set_pan(position, speed)
        self.statusBar().showMessage(f"Setting absolute pan to {position}°")

    def set_absolute_tilt(self):
        """Set absolute tilt position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        position = self.control_tab.ptz_control.tilt_spin.value()
        speed = self.control_tab.ptz_control.tilt_speed_spin.value()
        self.ptz_controller.set_tilt(position, speed)
        self.statusBar().showMessage(f"Setting absolute tilt to {position}°")

    def set_absolute_zoom(self):
        """Set absolute zoom position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        position = self.control_tab.ptz_control.zoom_spin.value()
        self.ptz_controller.set_zoom(position)
        self.statusBar().showMessage(f"Setting zoom position to {position}")

    def set_absolute_focus(self):
        """Set absolute focus position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        position = self.control_tab.ptz_control.focus_spin.value()
        self.ptz_controller.set_focus(position)
        self.statusBar().showMessage(f"Setting focus position to {position}")

    def toggle_auto_focus(self):
        """Toggle auto focus mode"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        auto_focus = self.control_tab.ptz_control.auto_focus_btn.isChecked()
        self.ptz_controller.set_auto_focus(auto_focus)

        if auto_focus:
            self.statusBar().showMessage("Auto focus enabled")
        else:
            self.statusBar().showMessage("Auto focus disabled")

    def one_push_focus(self):
        """Execute one-push focus"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        self.ptz_controller.execute_focus()
        self.statusBar().showMessage("One push auto focus triggered")

    def go_to_home(self):
        """Move to home position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        self.ptz_controller.goto_home()
        self.statusBar().showMessage("Moving to home position")

    # ================= Preset Control Methods =================
    def call_direct_preset(self):
        """Call a preset directly by number"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        preset_num = self.control_tab.preset_control.direct_spin.value()
        self.ptz_controller.goto_preset(preset_num)
        self.statusBar().showMessage(f"Moving to Preset {preset_num}")

    def set_direct_preset(self):
        """Set a preset directly by number"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        preset_num = self.control_tab.preset_control.direct_spin.value()
        self.ptz_controller.set_preset(preset_num)
        self.statusBar().showMessage(f"Setting preset {preset_num}")

    def clear_direct_preset(self):
        """Clear a preset directly by number"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        preset_num = self.control_tab.preset_control.direct_spin.value()
        self.ptz_controller.clear_preset(preset_num)
        self.statusBar().showMessage(f"Clearing preset {preset_num}")

    def activate_preset_button(self, button):
        """Activate a preset from button click"""
        preset_num = button.property('preset_num')
        if preset_num == -1:
            return

        # Update dropdown
        preset_number_to_index = {
            int(self.control_tab.preset_control.preset_combo.itemText(i).split(":")[0]): i
            for i in range(self.control_tab.preset_control.preset_combo.count())
        }

        if preset_num in preset_number_to_index:
            self.control_tab.preset_control.preset_combo.setCurrentIndex(preset_number_to_index[preset_num])
        else:
            print(f"[WARN] Preset {preset_num} not found in combo box!")
        # Find and activate preset
        preset = next((p for p in self.presets if p['number'] == preset_num), None)
        if preset:
            self.ptz_controller.goto_preset(preset_num)
            self.statusBar().showMessage(f"Moving to {preset['name']} (Preset {preset_num})")

    def call_selected_preset(self):
        """Call the currently selected preset from dropdown"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        preset_text = self.control_tab.preset_control.preset_combo.currentText()
        if preset_text:
            preset_num = int(preset_text.split(":")[0])
            self.ptz_controller.goto_preset(preset_num)
            self.statusBar().showMessage(f"Moving to {preset_text}")

    def set_selected_preset(self):
        """Set the currently selected preset from dropdown"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        preset_text = self.control_tab.preset_control.preset_combo.currentText()
        if preset_text:
            preset_num = int(preset_text.split(":")[0])
            self.ptz_controller.set_preset(preset_num)
            self.statusBar().showMessage(f"Setting preset {preset_text}")

    def clear_selected_preset(self):
        """Clear the currently selected preset from dropdown"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera")
            return

        preset_text = self.control_tab.preset_control.preset_combo.currentText()
        if preset_text:
            preset_num = int(preset_text.split(":")[0])
            self.ptz_controller.clear_preset(preset_num)
            self.statusBar().showMessage(f"Clearing preset {preset_num}")

    def add_new_preset(self):
        """Add a new preset with dialog"""
        preset_type = self.control_tab.preset_control.type_combo.currentIndex()
        dialog = PresetDialog(self, preset_type=preset_type)
        if dialog.exec():
            preset_data = dialog.get_preset_data()
            preset_num = preset_data["number"]

            # Validate number range
            if (preset_type == 0 and not (1 <= preset_num <= 79)) or \
                    (preset_type == 1 and not (80 <= preset_num <= 255)):
                QMessageBox.warning(self, "Warning",
                                    "Preset number out of range for selected type!")
                return

            # Check for duplicates
            if any(p for p in self.presets if p["number"] == preset_num):
                QMessageBox.warning(self, "Warning", "Preset number already exists!")
                return

            self.presets.append(preset_data)
            save_presets(self.presets)
            self.control_tab.preset_control.update_preset_ui()

    def edit_selected_preset(self):
        """Edit selected preset with dialog"""
        preset_text = self.control_tab.preset_control.preset_combo.currentText()
        if not preset_text:
            return

        preset_num = int(preset_text.split(":")[0])
        preset_name = preset_text.split(": ")[1] if ": " in preset_text else f"Preset {preset_num}"
        preset_type = 0 if preset_num <= 79 else 1

        dialog = PresetDialog(self, preset_num, preset_name, preset_type)
        if dialog.exec():
            preset_data = dialog.get_preset_data()
            new_num = preset_data["number"]

            # Validate range
            if (preset_type == 0 and not (1 <= new_num <= 79)) or \
                    (preset_type == 1 and not (80 <= new_num <= 255)):
                QMessageBox.warning(self, "Warning",
                                    "Preset number must stay in original type range!")
                return

            # Check for duplicates (if number changed)
            if new_num != preset_num and any(p for p in self.presets if p["number"] == new_num):
                QMessageBox.warning(self, "Warning", "New preset number already exists!")
                return

            # Update the preset
            for i, preset in enumerate(self.presets):
                if preset["number"] == preset_num:
                    self.presets[i] = preset_data
                    break

            save_presets(self.presets)
            self.control_tab.preset_control.update_preset_ui()

    def delete_selected_preset(self):
        """Delete selected preset with confirmation"""
        preset_text = self.control_tab.preset_control.preset_combo.currentText()
        if not preset_text:
            return

        preset_num = int(preset_text.split(":")[0])
        preset_name = preset_text.split(": ")[1] if ": " in preset_text else f"Preset {preset_num}"

        reply = QMessageBox.question(
            self, "Delete Preset",
            f"Delete {preset_name} (Preset {preset_num})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.presets = [p for p in self.presets if p["number"] != preset_num]
            save_presets(self.presets)
            self.control_tab.preset_control.update_preset_ui()

    # ================= Connection Management =================
    def add_connection(self):
        """Add new connection with dialog"""
        dialog = ConnectionDialog(self)
        if dialog.exec():
            connection_data = dialog.get_connection_data()
            self.connections.append(connection_data)
            save_connections(self.connections)
            self.control_tab.camera_control.update_camera_combo()
            self.connection_tab.update_connection_combo()

    def edit_connection(self):
        """Edit selected connection with dialog"""
        current_index = self.connection_tab.conn_combo.currentIndex()
        if 0 <= current_index < len(self.connections):
            dialog = ConnectionDialog(self, self.connections[current_index])
            if dialog.exec():
                self.connections[current_index] = dialog.get_connection_data()
                save_connections(self.connections)
                self.control_tab.camera_control.update_camera_combo()
                self.connection_tab.update_connection_combo()
                self.connection_tab.update_connection_details()

    def delete_connection(self):
        """Delete selected connection with confirmation"""
        current_index = self.connection_tab.conn_combo.currentIndex()
        if 0 <= current_index < len(self.connections):
            conn_name = self.connections[current_index].get("name", "Unnamed")

            reply = QMessageBox.question(
                self, "Delete Connection",
                f"Delete connection '{conn_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                del self.connections[current_index]
                save_connections(self.connections)
                self.control_tab.camera_control.update_camera_combo()
                self.connection_tab.update_connection_combo()

                if self.connections:
                    self.connection_tab.conn_combo.setCurrentIndex(0)
                else:
                    self.connection_tab.clear_connection_details()

    def connect_to_selected(self):
        """Connect to selected camera"""
        current_index = self.connection_tab.conn_combo.currentIndex()
        if 0 <= current_index < len(self.connections):
            self.control_tabs.setCurrentIndex(0)  # Switch to control tab
            self.control_tab.camera_control.camera_combo.setCurrentIndex(current_index)
            self.connect_to_camera()

    def handle_serial_connect(self):
        """Handle serial connection button click"""
        if self.serial_handler.is_connected():
            self.serial_handler.disconnect()
            self.connection_tab.connect_btn.setText("Connect")
            QMessageBox.information(self, "Serial", "Disconnected.")
        else:
            port = self.connection_tab.serial_combo.currentText()
            baud = 9600
            protocol = 'pelnet'

            success = self.serial_handler.connect(port, baud, protocol)
            if success:
                self.connection_tab.connect_btn.setText("Disconnect")
                QMessageBox.information(self, "Serial", f"Connected to {port}.")
            else:
                QMessageBox.critical(self, "Serial", f"Failed to connect to {port}.")

    # ================= Camera Control Methods =================
    def connect_to_camera(self):
        """Connect to currently selected camera"""
        current_index = self.control_tab.camera_control.camera_combo.currentIndex()
        if 0 <= current_index < len(self.connections):
            connection = self.connections[current_index]
            self.current_connection_index = current_index

            ip = connection.get("ip", "")
            port = connection.get("port", 8005)
            protocol = connection.get("protocol", "Pelco-D")
            address = connection.get("address", 1)
            rtsp_urls = connection.get("rtsp_urls", "")

            self.statusBar().showMessage(f"Connecting to {ip}:{port}...")

            # Connect PTZ controller
            success = self.ptz_controller.connect(
                ip=ip, port=port, protocol=protocol, address=address
            )

            if success:
                self.control_tab.camera_control.status_label.setText("Connected")
                self.control_tab.camera_control.status_label.setStyleSheet("color: green;")
                self.control_tab.camera_control.connect_btn.setEnabled(False)
                self.control_tab.camera_control.disconnect_btn.setEnabled(True)
                self.statusBar().showMessage(f"Connected to {ip}:{port}")

                # set stream buttons
                self.control_tab.camera_control.set_stream_buttons(rtsp_urls)

                # Connect video stream
                default_stream = rtsp_urls.get("visible") or next(iter(rtsp_urls.values()), None)
                if default_stream:
                    self.video_stream.connect(default_stream)
            else:
                self.statusBar().showMessage(f"Failed to connect to {ip}:{port}")

    def disconnect_camera(self):
        """Disconnect from current camera"""
        self.video_stream.disconnect()
        self.ptz_controller.disconnect()
        self.clear_all_controls()
        self.control_tab.camera_control.status_label.setText("Disconnected")
        self.control_tab.camera_control.status_label.setStyleSheet("color: red;")
        self.control_tab.camera_control.connect_btn.setEnabled(True)
        self.control_tab.camera_control.disconnect_btn.setEnabled(False)
        self.current_connection_index = -1
        self.statusBar().showMessage("Disconnected from camera")
        self.control_tab.camera_control.set_stream_buttons({})

    def previous_camera(self):
        """Select previous camera in list"""
        if self.control_tab.camera_control.camera_combo.count() > 0:
            current = self.control_tab.camera_control.camera_combo.currentIndex()
            new_index = (current - 1) % self.control_tab.camera_control.camera_combo.count()
            self.control_tab.camera_control.camera_combo.setCurrentIndex(new_index)

    def next_camera(self):
        """Select next camera in list"""
        if self.control_tab.camera_control.camera_combo.count() > 0:
            current = self.control_tab.camera_control.camera_combo.currentIndex()
            new_index = (current + 1) % self.control_tab.camera_control.camera_combo.count()
            self.control_tab.camera_control.camera_combo.setCurrentIndex(new_index)

    def update_stream_url(self, stream_type):
        """Update video stream URL based on selection"""
        current_index = self.control_tab.camera_control.camera_combo.currentIndex()
        if 0 <= current_index < len(self.connections):
            connection = self.connections[current_index]
            rtsp_url = connection.get("rtsp_url", "")

            if rtsp_url:
                # Modify URL based on stream type if needed
                # rtsp_url = rtsp_url.replace("visible", stream_type)
                self.video_stream.connect(rtsp_url)
                self.statusBar().showMessage(f"Selected {stream_type} stream: {rtsp_url}")

    # ================= Position Monitoring =================
    def start_position_monitor(self):
        """Start position monitoring thread"""
        if not self._monitoring:
            self._monitoring = True
            self._monitor_thread = threading.Thread(
                target=self._position_monitor_loop,
                daemon=True
            )
            self._monitor_thread.start()

    def stop_position_monitor(self):
        """Stop position monitoring thread"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join()
            self._monitor_thread = None
        self._update_all_displays("None")
        self.statusBar().showMessage("Position monitoring stopped")

    def toggle_position_updates(self, enabled):
        """Toggle position monitoring"""
        if enabled:
            self.start_position_monitor()
        else:
            self.stop_position_monitor()

    def _position_monitor_loop(self):
        """Thread-safe position monitoring with callback handling"""
        while self._monitoring and hasattr(self, 'ptz_controller'):
            try:
                if not self.ptz_controller.is_connected():
                    self._update_all_displays("None")
                    time.sleep(1)
                    continue

                # Get current timestamp for timeout checking
                start_time = time.time()

                # Request all positions with timeout protection
                self.ptz_controller.get_pan(self._safe_callback_wrapper('pan'))
                self.ptz_controller.get_tilt(self._safe_callback_wrapper('tilt'))
                self.ptz_controller.get_zoom(self._safe_callback_wrapper('zoom'))
                self.ptz_controller.get_focus(self._safe_callback_wrapper('focus'))

                # Calculate processing time and adjust sleep
                processing_time = time.time() - start_time
                sleep_time = max(0.1 - processing_time, 0.01)
                time.sleep(sleep_time)

            except Exception as e:
                print(f"Position monitor error: {e}")
                time.sleep(0.5)

    def _safe_callback_wrapper(self, axis):
        """Create a safe callback that handles errors"""

        def wrapper(data):
            try:
                if data and 'data' in data:
                    self._position_callbacks[axis](data)
                else:
                    self._position_callbacks[axis]({'data': 'NONE'})
            except Exception as e:
                print(f"Callback error for {axis}: {e}")
                self._position_callbacks[axis]({'data': 'NONE'})

        return wrapper

    def _update_all_displays(self, value):
        """Update all displays to the same value"""
        data = {'data': value}
        self._update_pan_display(data)
        self._update_tilt_display(data)
        self._update_zoom_display(data)
        self._update_focus_display(data)

    def _update_pan_display(self, data):
        """Update pan position display"""
        self.control_tab.ptz_control.pan_label.setText(f"{data['data']}°")

    def _update_tilt_display(self, data):
        """Update tilt position display"""
        self.control_tab.ptz_control.tilt_label.setText(f"{data['data']}°")

    def _update_zoom_display(self, data):
        """Update zoom position display"""
        self.control_tab.ptz_control.zoom_label.setText(str(data['data']))

    def _update_focus_display(self, data):
        """Update focus position display"""
        self.control_tab.ptz_control.focus_label.setText(str(data['data']))

    def handle_pelco_keyboard_command(self, message):
        print("Pelco keyboard command received:", message)

    # ================= Window Management =================
    def toggle_control_panel(self):
        """Toggle control panel visibility"""
        sizes = self.main_splitter.sizes()
        if sizes[1] > 0:  # Control panel visible
            self.control_panel_width = sizes[1]
            self.main_splitter.setSizes([1, 0])
        else:
            width = getattr(self, 'control_panel_width', 300)
            self.main_splitter.setSizes([self.width() - width, width])

    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        self.showFullScreen() if not self.isFullScreen() else self.showNormal()

    def closeEvent(self, event):
        """Handle window close event"""
        self.stop_position_monitor()
        self.video_stream.disconnect()
        self.ptz_controller.disconnect()
        event.accept()

    # ================== Keyboard ==================
    def keyPressEvent(self, event):
        """Handle keyboard presses for all controls"""
        if event.isAutoRepeat():  # Ignore auto-repeat events
            return

        if not self.ptz_controller.is_connected():
            return

        key = event.key()
        speed = self.control_tab.ptz_control.speed_slider.value()

        with self.key_state_lock:
            # Movement controls
            if key == Qt.Key.Key_Left:
                self.active_controls['pan'] = -1
            elif key == Qt.Key.Key_Right:
                self.active_controls['pan'] = 1
            elif key == Qt.Key.Key_Up:
                self.active_controls['tilt'] = 1
            elif key == Qt.Key.Key_Down:
                self.active_controls['tilt'] = -1

            # Zoom controls
            elif key == Qt.Key.Key_Z:
                self.active_controls['zoom'] = 1
            elif key == Qt.Key.Key_X:
                self.active_controls['zoom'] = -1

            # Focus controls
            elif key == Qt.Key.Key_F:
                self.active_controls['focus'] = 1
            elif key == Qt.Key.Key_N:
                self.active_controls['focus'] = -1

            # Home position
            elif key == Qt.Key.Key_H:
                self.ptz_controller.goto_home()

            # Preset keys (1-9)
            elif Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
                preset_num = key - Qt.Key.Key_0
                self.ptz_controller.goto_preset(preset_num)

            # Update all active controls
            self._update_all_controls()

    def keyReleaseEvent(self, event):
        """Handle key releases for all controls"""
        if event.isAutoRepeat():  # Ignore auto-repeat releases
            return

        key = event.key()

        with self.key_state_lock:
            # Movement controls
            if key == Qt.Key.Key_Left and self.active_controls['pan'] == -1:
                self.active_controls['pan'] = 0
            elif key == Qt.Key.Key_Right and self.active_controls['pan'] == 1:
                self.active_controls['pan'] = 0
            elif key == Qt.Key.Key_Up and self.active_controls['tilt'] == 1:
                self.active_controls['tilt'] = 0
            elif key == Qt.Key.Key_Down and self.active_controls['tilt'] == -1:
                self.active_controls['tilt'] = 0

            # Zoom controls
            elif key == Qt.Key.Key_Z and self.active_controls['zoom'] == 1:
                self.active_controls['zoom'] = 0
            elif key == Qt.Key.Key_X and self.active_controls['zoom'] == -1:
                self.active_controls['zoom'] = 0

            # Focus controls
            elif key == Qt.Key.Key_F and self.active_controls['focus'] == 1:
                self.active_controls['focus'] = 0
            elif key == Qt.Key.Key_N and self.active_controls['focus'] == -1:
                self.active_controls['focus'] = 0

            # Update all active controls
            self._update_all_controls()

    def _update_all_controls(self):
        """Update all active controls based on current state"""
        if not hasattr(self, 'ptz_controller') or not self.ptz_controller.is_connected():
            return

        speed = self.control_tab.ptz_control.speed_slider.value()

        # Calculate pan/tilt movement
        pan_speed = self.active_controls['pan'] * speed
        tilt_speed = self.active_controls['tilt'] * speed
        self.ptz_controller.pan_tilt(pan_speed, tilt_speed)

        # Handle zoom
        if self.active_controls['zoom'] == 1:
            self.ptz_controller.zoom_tele(speed)
        elif self.active_controls['zoom'] == -1:
            self.ptz_controller.zoom_wide(speed)
        else:
            self.ptz_controller.zoom_stop()

        # Handle focus
        if self.active_controls['focus'] == 1:
            self.ptz_controller.focus_far(speed)
        elif self.active_controls['focus'] == -1:
            self.ptz_controller.focus_near(speed)
        else:
            self.ptz_controller.focus_stop()

    def clear_all_controls(self):
        """Clear all active controls"""
        with self.key_state_lock:
            self.active_controls = {
                'pan': 0,
                'tilt': 0,
                'zoom': 0,
                'focus': 0
            }
            if hasattr(self, 'ptz_controller'):
                self.ptz_controller.pan_tilt(0, 0)
                self.ptz_controller.zoom_stop()
                self.ptz_controller.focus_stop()