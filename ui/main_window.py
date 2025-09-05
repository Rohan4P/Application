import contextlib
import os
import threading
import time
from PySide6.QtWidgets import QMainWindow, QTabWidget, QSplitter, QMessageBox, QLabel, QPushButton, QVBoxLayout, \
    QDialog, QGroupBox, QGridLayout, QApplication, QFileDialog, QHBoxLayout, QLineEdit, QGraphicsOpacityEffect, QWidget, \
    QSizePolicy, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from components.video_stream import RTSPVideoStream
from components.ptz_controller import PTZController
from components.serial_manager import SerialHandler
from ui.control_tab import ControlTab
from ui.connection_tab import ConnectionTab
from ui.dialogs import ConnectionDialog, PresetDialog
from ui.discovery_widget import DiscoveryWidget
from utils.settings import load_connections, save_connections, load_presets, save_presets
from license.license_manager import LicenseManager
from lib.pelco import *
import core_config

# Status message timeout
INFO_TIMEOUT = 3000  # 3 Seconds
WARNING_TIMEOUT = 5000  # 5 Seconds
ERROR_TIMEOUT = 7000  # 7 Seconds


class VMSMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Octagon Node - Video Management Tool")
        self.setMinimumSize(1200, 800)

        self.license_manager = LicenseManager("license/public.pem", "license/license.lic")

        self.create_menu_bar()

        # check License()

        # Initialize components
        # self.init_components()
        # self.init_ui()
        # self.connect_signals()

        # UI
        self.control_panel_width = 350
        self.panel_collapsed = False

        # Start monitoring thread
        self._monitoring = False
        self._monitor_thread = None

        self._check_license_validity()

        # Initialize key states
        self.setFocusPolicy(Qt.StrongFocus)  # Ensure window can receive key events
        self.setFocus()  #
        self.active_controls = {'pan': 0, 'tilt': 0, 'zoom': 0, 'focus': 0}
        self.key_state_lock = threading.Lock()  # Thread-safe access to key states

    def init_components(self):
        """Initialize all major components"""
        self.video_stream = RTSPVideoStream(self)

        self.ptz_controller = PTZController()
        self.ptz_controller.set_address_provider(
            lambda: self.control_tab.camera_control.address_input.value()
        )

        defaults = {'serialCom': 'COM3', 'protocol': 'pelnet', 'baud': 9600}
        self.serial_handler = SerialHandler(defaults)
        self.serial_handler.register_keyboard_subscriber(self.ptz_controller.handle_pelco_keyboard_command)

        # Load saved data
        self.connections = load_connections()
        self.presets = load_presets()
        self.current_connection_index = -1

        self._pelco_device = PelcoDevice()

    def _check_license_validity(self):
        result = self.license_manager.load_license()

        if result["status"] in ["valid_permanent", "valid_temporary"]:
            print("✅ License OK:", result["status"])
            self.unlock_ui()  # allow UI
            # self.start_position_monitor()
        else:
            print("❌ License error:", result["status"])
            if result["status"] == "expired":
                QMessageBox.warning(self, "License Expired", "Your license has expired.")
            else:
                QMessageBox.critical(self, "License Invalid", f"Problem: {result['status']}")
            self.lock_ui()  # block UI

    def lock_ui(self):
        """Restrict UI when license is missing/invalid/expired"""
        # Remove central widget
        self.takeCentralWidget()

        # Disable all menus except Info
        for action in self.menuBar().actions():
            if action.menu().title() != "&Info":
                action.setEnabled(False)
            else:
                action.setEnabled(True)

    def unlock_ui(self):
        """Enable UI when license is valid"""
        # Restore main UI
        self.init_components()
        self.init_ui()
        self.connect_signals()

        # Enable all menus
        for action in self.menuBar().actions():
            action.setEnabled(True)

    def refresh_license_status(self, dialog):
        dialog.accept()
        self._check_license_validity()  # re-check license
        self.show_license_info()

    def show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Disclaimer")
        dialog.setMinimumWidth(400)
        dialog.setMaximumWidth(500)
        dialog.setSizeGripEnabled(False)  # remove resize handle
        dialog.setStyleSheet("""
            QDialog {
                background-color: #f9f9f9;
            }
            QLabel {
                font-size: 13px;
                color: #333333;
            }
            QPushButton {
                padding: 5px 12px;
                font-weight: bold;
                border-radius: 4px;
                background-color: #2196f3;  /* blue shade */
                color: white;
            }
            QPushButton:hover {
                background-color: #1976d2;  /* darker blue on hover */
            }
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 8px;
                padding: 10px;
                background-color: white;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        # --- About Content ---
        label = QLabel(core_config.ABOUT_TEXT)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)

        # --- OK Button ---
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        ok_btn.setFixedWidth(80)
        ok_btn.setDefault(True)
        layout.addWidget(ok_btn, alignment=Qt.AlignCenter)

        dialog.exec()

    def show_license_info(self):
        result = self.license_manager.load_license()
        device_id = self.license_manager.get_device_id()

        dialog = QDialog(self)
        dialog.setWindowTitle("License Management")
        dialog.setMinimumWidth(450)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #fafafa;
                border-radius: 8px;
            }
            QLabel {
                font-size: 13px;
                color: #333;
            }
            QPushButton {
                padding: 6px 14px;
                border-radius: 6px;
                font-weight: 500;
            }
            QPushButton#primary {
                background-color: #2196f3;
                color: white;
            }
            QPushButton#success {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton#warn {
                background-color: #FF9800;
                color: white;
            }
            QPushButton#secondary {
                background-color: #9C27B0;
                color: white;
            }
            QLineEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: #fff;
            }
            QFrame[frameShape="4"] { /* Styled panels */
                border: 1px solid #ddd;
                border-radius: 8px;
                background-color: white;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)

        # --- Card Helper ---
        def make_card(title: str):
            card = QFrame()
            card.setFrameShape(QFrame.StyledPanel)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            vbox = QVBoxLayout(card)
            vbox.setSpacing(6)
            vbox.addWidget(QLabel(f"<b>{title}</b>"))
            return card, vbox

        # --- License Status ---
        status_card, status_layout = make_card("License Status")

        status = result["status"]
        if status in ["valid_permanent", "valid_temporary"]:
            lic = result["license"]
            license_type = lic.get("license_type", "N/A")
            issued = lic.get("issued", "N/A")
            expires = lic.get("expires", "—") if license_type == "temporary" else "—"

            grid = QGridLayout()
            grid.addWidget(QLabel("Status:"), 0, 0)
            status_val = QLabel(f"{status.replace('_', ' ').capitalize()} ({license_type})")
            status_val.setStyleSheet("color: green; font-weight: bold;")
            status_val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(status_val, 0, 1)

            grid.addWidget(QLabel("Issued:"), 1, 0)
            grid.addWidget(QLabel(issued), 1, 1)

            grid.addWidget(QLabel("Expires:"), 2, 0)
            grid.addWidget(QLabel(expires), 2, 1)

            status_layout.addLayout(grid)
        else:
            error_lbl = QLabel(status.replace('_', ' ').capitalize())
            error_lbl.setStyleSheet("color: red; font-weight: bold;")
            status_layout.addWidget(error_lbl)

        layout.addWidget(status_card)

        # --- Device ID ---
        device_card, device_layout = make_card("Device ID")

        device_layout.addWidget(QLabel("Your Device ID (Provide this to generate a license):"))

        # Inline layout for device ID + copy button
        device_id_layout = QHBoxLayout()
        device_id_field = QLineEdit(device_id)
        device_id_field.setReadOnly(True)
        device_id_field.setToolTip("Copy this ID and provide it to your software vendor to generate a license")
        device_id_layout.addWidget(device_id_field)

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("secondary")
        copy_btn.clicked.connect(lambda: self.copy_to_clipboard(device_id))
        device_id_layout.addWidget(copy_btn)
        device_layout.addLayout(device_id_layout)

        layout.addWidget(device_card)

        # --- License Upload ---
        upload_card, upload_layout = make_card("License Update")

        # Horizontal layout for file path + select button + upload button
        file_layout = QHBoxLayout()

        license_path_field = QLineEdit()
        license_path_field.setReadOnly(True)
        file_layout.addWidget(license_path_field)

        select_btn = QPushButton("Select File")
        select_btn.setObjectName("secondary")

        def select_file():
            path, _ = QFileDialog.getOpenFileName(dialog, "Select License File", "",
                                                  "License Files (*.lic);;All Files (*)")
            if path:
                license_path_field.setText(path)

        select_btn.clicked.connect(select_file)
        file_layout.addWidget(select_btn)

        upload_btn = QPushButton("Upload")
        upload_btn.setObjectName("success")
        upload_btn.clicked.connect(lambda: self.upload_license(dialog, license_path_field.text()))
        file_layout.addWidget(upload_btn)

        upload_layout.addLayout(file_layout)
        layout.addWidget(upload_card)

        # --- Bottom Buttons ---
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("warn")
        refresh_btn.clicked.connect(lambda: self.refresh_license_status(dialog))
        bottom_layout.addWidget(refresh_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("primary")
        ok_btn.clicked.connect(dialog.accept)
        ok_btn.setDefault(True)
        bottom_layout.addWidget(ok_btn)

        layout.addLayout(bottom_layout)

        dialog.exec()

    def upload_license(self, parent_dialog, file_path = ""):
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                parent_dialog,
                "Select License File",
                "",
                "License Files (*.lic);;All Files (*)"
            )

        if file_path:
            result = self.license_manager.install_license(file_path)

            if result["success"]:
                QMessageBox.information(
                    parent_dialog,
                    "Success",
                    result["message"] + "\nPlease restart the application for changes to take effect."
                )
                parent_dialog.accept()
            else:
                QMessageBox.critical(
                    parent_dialog,
                    "Error",
                    result["message"]
                )

    def copy_to_clipboard(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        QMessageBox.information(self, "Copied", "Device ID copied to clipboard!")

    def init_ui(self):
        """Initialize the main UI components"""
        # Main splitter (video on left, controls on right)
        self.main_splitter = QSplitter(Qt.Horizontal)

        # --- video panel ---
        self.video_panel = self.video_stream.get_video_widget()
        self.video_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_splitter.addWidget(self.video_stream)

        # --- control panel with its own container ---
        self.panel_container = QWidget()
        self.panel_container.setFixedWidth(self.control_panel_width)
        self.panel_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        panel_layout = QVBoxLayout(self.panel_container)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # toggle button (initially on panel)
        self.toggle_btn = QPushButton("◀")
        self.toggle_btn.setFixedSize(25, 30)
        self.toggle_btn.setStyleSheet("""
                       QPushButton {
                           background: #444;
                           color: white;
                           border: none;
                       }
                       QPushButton:hover {
                           background: #666;
                       }
                   """)

        # control tabs
        self.control_tabs = QTabWidget()
        self.control_tab = ControlTab(self)
        self.connection_tab = ConnectionTab(self)
        self.control_tabs.addTab(self.control_tab, "Controls")
        self.control_tabs.addTab(self.connection_tab, "Connections")

        panel_layout.addWidget(self.toggle_btn, alignment=Qt.AlignLeft)
        panel_layout.addWidget(self.control_tabs)

        self.main_splitter.addWidget(self.panel_container)
        self.main_splitter.setSizes([self.width() - self.control_panel_width, self.control_panel_width])

        self.setCentralWidget(self.main_splitter)
        self.statusBar().showMessage("Ready", INFO_TIMEOUT)

        # opacity effect for when button floats on video
        self.opacity_effect = QGraphicsOpacityEffect()
        self.opacity_effect.setOpacity(0.3)
        self.toggle_btn.setGraphicsEffect(self.opacity_effect)

        self.toggle_btn.enterEvent = lambda e: self.opacity_effect.setOpacity(1.0)
        self.toggle_btn.leaveEvent = lambda e: self.opacity_effect.setOpacity(0.3)

        # Discovery tab
        self.discovery_tab = DiscoveryWidget(self)
        self.control_tabs.addTab(self.discovery_tab, "Discover")

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
        self.fullscreen_action = view_menu.addAction("FullScreen")
        self.fullscreen_action.setShortcut("F11")

        # Record menu
        self.record_menu = self.menuBar().addMenu("Record")
        self.start_record = self.record_menu.addAction("Start ●")
        self.start_record.setShortcut("Ctrl+R")
        self.pause_record = self.record_menu.addAction("Pause ||")
        self.pause_record.setShortcut("Ctrl+P")
        self.pause_record.setEnabled(False)
        self.resume_record = self.record_menu.addAction("Resume ▶")
        self.resume_record.setShortcut("Ctrl+M")
        self.resume_record.setEnabled(False)
        self.stop_record = self.record_menu.addAction("Stop X")
        self.stop_record.setShortcut("Ctrl+S")
        self.stop_record.setEnabled(False)
        self.save_as_record_file = self.record_menu.addAction("Save As...")

        # info menu
        info_menu = self.menuBar().addMenu("&Info")
        self.about_action = info_menu.addAction("About")
        self.about_action.triggered.connect(self.show_about)
        self.license_action = info_menu.addAction("License")
        self.license_action.triggered.connect(self.show_license_info)

    def connect_signals(self):
        """Connect all signals and slots"""
        # Connect tab signals
        self.control_tab.connect_signals()
        self.connection_tab.connect_signals()

        # Connect UI signals
        self.toggle_btn.clicked.connect(self.toggle_control_panel)
        self.main_splitter.splitterMoved.connect(lambda pos, index: self._position_toggle_button())

        # Connect menu actions
        self.toggle_controls_action.triggered.connect(self.toggle_control_panel)
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)

        self.start_record.triggered.connect(self.video_stream.start_recording)
        self.pause_record.triggered.connect(self.video_stream.pause_recording)
        self.resume_record.triggered.connect(self.video_stream.resume_recording)
        self.stop_record.triggered.connect(self.video_stream.stop_recording)
        self.save_as_record_file.triggered.connect(self.video_stream.save_as_record_file)

    # ================= Discovery Methods =================
    def start_discovery(self):
        self.discovery_tab.start_scan()

    def stop_discovery(self):
        self.discovery_tab.stop_scan()

    def connect_to_device(self, items):
        ip = items.text(0)
        name = items.text(1)
        self.statusBar().showMessage(f"Connecting to {ip} ...")

        # Switch to Connection tab
        idx = self.control_tabs.indexOf(self.connection_tab)
        if idx != -1:
            self.control_tabs.setCurrentIndex(idx)

        # Set IP and auto-connect
        self.connection_tab.set_ip_and_connect(ip, name)

    # ================= PTZ Control Methods =================
    def on_joystick_moved(self, x, y):
        """Handle joystick movement"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
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
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        speed = 100  # Fixed speed for now
        if direction == "wide":
            self.ptz_controller.zoom_wide(speed)
            self.statusBar().showMessage(f"Zooming wide at speed {speed}", INFO_TIMEOUT)
        elif direction == "tele":
            self.ptz_controller.zoom_tele(speed)
            self.statusBar().showMessage(f"Zooming tele at speed {speed}", INFO_TIMEOUT)
        else:  # stop
            self.ptz_controller.zoom_stop()
            self.statusBar().showMessage("Zoom stopped", INFO_TIMEOUT)

    def focus_control(self, direction):
        """Handle focus control commands"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        speed = 100  # Fixed speed for now
        if direction == "near":
            self.ptz_controller.focus_near(speed)
            self.statusBar().showMessage(f"Focusing near at speed {speed}", INFO_TIMEOUT)
        elif direction == "far":
            self.ptz_controller.focus_far(speed)
            self.statusBar().showMessage(f"Focusing far at speed {speed}", INFO_TIMEOUT)
        else:  # stop
            self.ptz_controller.focus_stop()
            self.statusBar().showMessage("Focus stopped", INFO_TIMEOUT)

    def set_absolute_pan(self):
        """Set absolute pan position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        position = self.control_tab.ptz_control.pan_spin.value()
        speed = self.control_tab.ptz_control.pan_speed_spin.value()
        self.ptz_controller.set_pan(position, speed)
        self.statusBar().showMessage(f"Setting absolute pan to {position}°", INFO_TIMEOUT)

    def set_absolute_tilt(self):
        """Set absolute tilt position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        position = self.control_tab.ptz_control.tilt_spin.value()
        speed = self.control_tab.ptz_control.tilt_speed_spin.value()
        self.ptz_controller.set_tilt(position, speed)
        self.statusBar().showMessage(f"Setting absolute tilt to {position}°", INFO_TIMEOUT)

    def set_absolute_zoom(self):
        """Set absolute zoom position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        position = self.control_tab.ptz_control.zoom_spin.value()
        self.ptz_controller.set_zoom(position)
        self.statusBar().showMessage(f"Setting zoom position to {position}", INFO_TIMEOUT)

    def set_absolute_focus(self):
        """Set absolute focus position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        position = self.control_tab.ptz_control.focus_spin.value()
        self.ptz_controller.set_focus(position)
        self.statusBar().showMessage(f"Setting focus position to {position}")

    def toggle_auto_focus(self):
        """Toggle auto focus mode"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        auto_focus = self.control_tab.ptz_control.auto_focus_btn.isChecked()
        self.ptz_controller.set_auto_focus(auto_focus)

        if auto_focus:
            self.statusBar().showMessage("Auto focus enabled", INFO_TIMEOUT)
        else:
            self.statusBar().showMessage("Auto focus disabled", INFO_TIMEOUT)

    def one_push_focus(self):
        """Execute one-push focus"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        self.ptz_controller.execute_focus()
        self.statusBar().showMessage("execute auto focus", INFO_TIMEOUT)

    def go_to_home(self):
        """Move to home position"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        self.ptz_controller.goto_home()
        self.statusBar().showMessage("Moving to home position", INFO_TIMEOUT)

    # ================= Preset Control Methods =================
    def call_direct_preset(self):
        """Call a preset directly by number"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        preset_num = self.control_tab.preset_control.direct_spin.value()
        self.ptz_controller.goto_preset(preset_num)
        self.statusBar().showMessage(f"Moving to Preset {preset_num}", INFO_TIMEOUT)

    def set_direct_preset(self):
        """Set a preset directly by number"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        preset_num = self.control_tab.preset_control.direct_spin.value()
        self.ptz_controller.set_preset(preset_num)
        self.statusBar().showMessage(f"Setting preset {preset_num}", INFO_TIMEOUT)

    def clear_direct_preset(self):
        """Clear a preset directly by number"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        preset_num = self.control_tab.preset_control.direct_spin.value()
        self.ptz_controller.clear_preset(preset_num)
        self.statusBar().showMessage(f"Clearing preset {preset_num}", INFO_TIMEOUT)

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
            self.statusBar().showMessage(f"[WARNING] Preset {preset_num} not found in dropdown!", WARNING_TIMEOUT)
        preset = next((p for p in self.presets if p['number'] == preset_num), None)
        if preset:
            self.ptz_controller.goto_preset(preset_num)
            self.statusBar().showMessage(f"Moving to {preset['name']} (Preset {preset_num})")

    def call_selected_preset(self):
        """Call the currently selected preset from dropdown"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        preset_text = self.control_tab.preset_control.preset_combo.currentText()
        if preset_text:
            preset_num = int(preset_text.split(":")[0])
            self.ptz_controller.goto_preset(preset_num)
            self.statusBar().showMessage(f"Moving to {preset_text}", INFO_TIMEOUT)

    def set_selected_preset(self):
        """Set the currently selected preset from dropdown"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        preset_text = self.control_tab.preset_control.preset_combo.currentText()
        if preset_text:
            preset_num = int(preset_text.split(":")[0])
            self.ptz_controller.set_preset(preset_num)
            self.statusBar().showMessage(f"Setting preset {preset_text}", INFO_TIMEOUT)

    def clear_selected_preset(self):
        """Clear the currently selected preset from dropdown"""
        if not self.ptz_controller.is_connected():
            self.statusBar().showMessage("Not connected to camera", WARNING_TIMEOUT)
            return

        preset_text = self.control_tab.preset_control.preset_combo.currentText()
        if preset_text:
            preset_num = int(preset_text.split(":")[0])
            self.ptz_controller.clear_preset(preset_num)
            self.statusBar().showMessage(f"Clearing preset {preset_num}", INFO_TIMEOUT)

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
        self.control_tab.camera_control.update_camera_combo()
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
    def focus_on_camera(self, index):
        if hasattr(self, 'video_stream') and self.video_stream:
            self.video_stream.focus_on_camera(index)
            print(f"Focused on camera {index + 1}", self.control_tab.camera_control.camera_combo.count())
            if index < self.control_tab.camera_control.camera_combo.count():
                self.control_tab.camera_control.camera_combo.setCurrentIndex(index)

            self.statusBar().showMessage(f"Focused on camera {index + 1}", INFO_TIMEOUT)

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
            rtsp_urls = connection.get("rtsp_urls", {})

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
                self.statusBar().showMessage(f"Connected to {ip}:{port}", INFO_TIMEOUT)

                # Set available streams for grid view
                self.video_stream.available_streams = list(rtsp_urls.values())

                # Set stream buttons
                self.video_stream.set_stream_buttons(rtsp_urls)

                # Connect to the first stream by default
                default_stream = rtsp_urls.get("visible") or next(iter(rtsp_urls.values()), None)
                if default_stream:
                    self.video_stream.connect(default_stream)
            else:
                self.statusBar().showMessage(f"Failed to connect to {ip}:{port}", ERROR_TIMEOUT)

    def disconnect_camera(self):
        """Disconnect from current camera"""
        self.video_stream.disconnect()
        self.ptz_controller.disconnect()
        # self.clear_all_controls()
        self.control_tab.camera_control.status_label.setText("Disconnected")
        self.control_tab.camera_control.status_label.setStyleSheet("color: red;")
        self.control_tab.camera_control.connect_btn.setEnabled(True)
        self.control_tab.camera_control.disconnect_btn.setEnabled(False)
        self.current_connection_index = -1
        self.statusBar().showMessage("Disconnected from camera", INFO_TIMEOUT)
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
                self.statusBar().showMessage(f"Selected {stream_type} stream: {rtsp_url}", INFO_TIMEOUT)

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
        self._update_ptz_display("all", "None")
        self.statusBar().showMessage("Position monitoring stopped", INFO_TIMEOUT)

    def toggle_position_updates(self, enabled):
        """Toggle position monitoring"""
        if enabled:
            self.start_position_monitor()
        else:
            self.stop_position_monitor()

    def _position_monitor_loop(self):
        while self._monitoring and hasattr(self, 'ptz_controller'):
            try:
                if not self.ptz_controller.is_connected():
                    self._update_ptz_display(axis='all', value="None")
                    time.sleep(1)
                    continue

                self.ptz_controller.get_pan(self._safe_callback_wrapper('pan'))
                self.ptz_controller.get_tilt(self._safe_callback_wrapper('tilt'))
                self.ptz_controller.get_zoom(self._safe_callback_wrapper('zoom'))
                self.ptz_controller.get_focus(self._safe_callback_wrapper('focus'))

                time.sleep(0.75)

            except Exception as e:
                self.statusBar().showMessage(f"[ERROR] Position monitor error: {e}", ERROR_TIMEOUT)
                time.sleep(0.75)

    def _safe_callback_wrapper(self, axis):
        """Create a safe callback that handles errors"""
        def wrapper(packet):
            try:
                resp = self._pelco_device.ingest(packet)
                if packet:
                    if packet[3] == 0x59:  # parse Pan
                        self._update_ptz_display(axis='pan', value=str(resp[0]['data']))
                    elif packet[3] == 0x5B:  # parse Tilt
                        self._update_ptz_display(axis='tilt', value=str(resp[0]['data']))
                    elif packet[3] == 0x5D:  # parse Zoom
                        self._update_ptz_display(axis='zoom', value=str(resp[0]['data']))
                    elif packet[3] == 0x63:  # parse Focus
                        self._update_ptz_display(axis='focus', value=str(resp[0]['data']))
                else:
                    self._update_ptz_display(axis, "None")
            except Exception as e:
                print(f"Callback error for {axis}: {e}")
                self._update_ptz_display(axis, "None")
        return wrapper

    def _update_ptz_display(self, axis='all', value="None"):
        if axis in ['pan', 'all']:
            self.control_tab.ptz_control.pan_label.setText(value)
        if axis in ['tilt', 'all']:
            self.control_tab.ptz_control.tilt_label.setText(value)
        if axis in ['zoom', 'all']:
            self.control_tab.ptz_control.zoom_label.setText(value)
        if axis in ['focus', 'all']:
            self.control_tab.ptz_control.focus_label.setText(value)

    def _position_toggle_button(self):
        """Position toggle button depending on panel state."""
        if self.panel_collapsed:
            self.toggle_btn.setText("◀")
        else:
            self.toggle_btn.setText("▶")

        parent = self.video_panel
        self.toggle_btn.setParent(parent)
        self.toggle_btn.show()
        self.toggle_btn.raise_()

        # calculate position
        btn_w, btn_h = self.toggle_btn.width(), self.toggle_btn.height()
        parent_rect = parent.rect()

        x = parent_rect.width() - btn_w
        y = (parent_rect.height() - btn_h) // 2

        self.toggle_btn.move(x, y)

    # ================= Window Events =================
    def closeEvent(self, event):
        """Handle window close event"""
        self.stop_position_monitor()
        self.video_stream.disconnect()
        self.ptz_controller.disconnect()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # check if button is already created
        if self.toggle_btn:
            self._position_toggle_button()

    def showEvent(self, event):
        super().showEvent(event)
        # check if button is already created
        if self.toggle_btn:
            self._position_toggle_button()

    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        self.showFullScreen() if not self.isFullScreen() else self.showNormal()

    def toggle_control_panel(self):
        """Collapse/expand control tab with animation, and move button accordingly."""

        self.panel_collapsed = not self.panel_collapsed

        sizes = self.main_splitter.sizes()
        if sizes[1] > 0:
            self.control_panel_width = sizes[1]
            self.main_splitter.setSizes([self.width(), 0])
        else:
            # width = getattr(self, 'control_panel_width', 300)
            self.panel_container.show()
            self.main_splitter.setSizes([self.width() - self.control_panel_width, self.control_panel_width])

        self._position_toggle_button()

    # ==================== Keyboard ==================
    """
       Keyboard Controls:
       ------------------
       Arrow Keys:
           ← = Pan Left
           → = Pan Right
           ↑ = Tilt Up
           ↓ = Tilt Down
           H = Move to Home Position

       Zoom:
           Z = Zoom In (Tele)
           X = Zoom Out (Wide)

       Focus:
           F = Focus Far
           N = Focus Near

       Presets:
           1–9 = GOTO Preset Positions

       Other:
           
       """

    def keyPressEvent(self, event):
        print(event.key())
        if event.isAutoRepeat():
            return
        key = event.key()

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Z, Qt.Key.Key_X, Qt.Key.Key_F, Qt.Key.Key_N):
            if key == Qt.Key.Key_Left:
                self.active_controls['pan'] = -1
            elif key == Qt.Key.Key_Right:
                self.active_controls['pan'] = 1
            elif key == Qt.Key.Key_Up:
                self.active_controls['tilt'] = 1
            elif key == Qt.Key.Key_Down:
                self.active_controls['tilt'] = -1
            elif key == Qt.Key.Key_Z:
                self.active_controls['zoom'] = 1
            elif key == Qt.Key.Key_X:
                self.active_controls['zoom'] = -1
            elif key == Qt.Key.Key_F:
                self.active_controls['focus'] = 1
            elif key == Qt.Key.Key_N:
                self.active_controls['focus'] = -1
            self._update_ptz_controls()

        elif key == Qt.Key.Key_H:
            self.ptz_controller.goto_home()
        elif Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            self.ptz_controller.goto_preset(key - Qt.Key.Key_0)

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Z, Qt.Key.Key_X, Qt.Key.Key_F, Qt.Key.Key_N):
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                self.active_controls['pan'] = 0
            elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self.active_controls['tilt'] = 0
            elif key in (Qt.Key.Key_Z, Qt.Key.Key_X):
                self.active_controls['zoom'] = 0
            elif key in (Qt.Key.Key_F, Qt.Key.Key_N):
                self.active_controls['focus'] = 0
            self._update_ptz_controls()

    def _update_ptz_controls(self):
        speed = self.control_tab.ptz_control.speed_slider.value()
        pan, tilt = self.active_controls['pan'] * speed, self.active_controls['tilt'] * speed
        zoom, focus = self.active_controls['zoom'], self.active_controls['focus']

        if pan or tilt:
            self.ptz_controller.pan_tilt(pan, tilt)
        elif zoom == 1:
            self.ptz_controller.zoom_tele()
        elif zoom == -1:
            self.ptz_controller.zoom_wide()
        elif focus == 1:
            self.ptz_controller.focus_far()
        elif focus == -1:
            self.ptz_controller.focus_near()
        else:
            self.ptz_controller.stop()

    def clear_all_controls(self):
        """Clear all active controls"""
        with self.key_state_lock or contextlib.nullcontext():
            for key in self.active_controls:
                self.active_controls[key] = 0
            if self.ptz_controller:
                self.ptz_controller.stop()