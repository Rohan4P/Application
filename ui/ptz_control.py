# ui/ptz_control.py
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QDoubleSpinBox,
    QLabel, QSlider, QPushButton, QFrame, QCheckBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from widgets.joystick import JoystickWidget
from ui.collapsible_box import CollapsibleBox


class PTZControlSection(CollapsibleBox):
    def __init__(self, main_window):
        super().__init__("PTZ Control")
        self.main_window = main_window
        self.init_ui()
        self.connect_signals()

    def init_ui(self):
        """Initialize the PTZ control UI"""
        layout = QVBoxLayout()

        # Absolute position controls
        abs_group = QGroupBox()
        abs_layout = QGridLayout()
        abs_layout.setHorizontalSpacing(10)
        abs_layout.setVerticalSpacing(6)

        # Pan control + speed input
        # position labels
        self.pan_label = QLabel("None")
        self.tilt_label = QLabel("None")
        self.zoom_label = QLabel("None")
        self.focus_label = QLabel("None")

        self.update_checkbox = QCheckBox("Polling Position")
        self.update_checkbox.setChecked(False)

        abs_layout.addWidget(QLabel("Pan:"), 1, 0)
        abs_layout.addWidget(self.pan_label, 1, 1)
        self.pan_spin = QDoubleSpinBox()
        self.pan_spin.setRange(0, 360)
        self.pan_spin.setToolTip("Pan: 0.00 - 360.00")
        abs_layout.addWidget(self.pan_spin, 1, 2)
        self.pan_speed_spin = QDoubleSpinBox()
        self.pan_speed_spin.setToolTip("Pan Abs Speed")
        self.pan_speed_spin.setRange(1, 100)
        self.pan_speed_spin.setValue(100)
        abs_layout.addWidget(self.pan_speed_spin, 1, 3)
        self.pan_set_btn = QPushButton("Set")
        abs_layout.addWidget(self.pan_set_btn, 1, 4)

        # Tilt control + speed input
        abs_layout.addWidget(QLabel("Tilt:"), 2, 0)
        abs_layout.addWidget(self.tilt_label, 2, 1)
        self.tilt_spin = QDoubleSpinBox()
        self.tilt_spin.setRange(-90, 90)
        self.tilt_spin.setToolTip("Tilt: -90.00 - 90.00")
        abs_layout.addWidget(self.tilt_spin, 2, 2)
        self.tilt_speed_spin = QDoubleSpinBox()
        self.tilt_speed_spin.setToolTip("Tilt Abs Speed")
        self.tilt_speed_spin.setRange(1, 100)
        self.tilt_speed_spin.setValue(100)
        abs_layout.addWidget(self.tilt_speed_spin, 2, 3)
        self.tilt_set_btn = QPushButton("Set")
        abs_layout.addWidget(self.tilt_set_btn, 2, 4)

        # Zoom control
        abs_layout.addWidget(QLabel("Zoom:"), 3, 0)
        abs_layout.addWidget(self.zoom_label, 3, 1)
        self.zoom_spin = QDoubleSpinBox()
        self.zoom_spin.setRange(0, 100)
        self.zoom_spin.setToolTip("Zoom: 0.00 - 100.00%")
        abs_layout.addWidget(self.zoom_spin, 3, 2)
        self.zoom_set_btn = QPushButton("Set")
        abs_layout.addWidget(self.zoom_set_btn, 3, 4)

        # Focus control
        abs_layout.addWidget(QLabel("Focus:"), 4, 0)
        abs_layout.addWidget(self.focus_label, 4, 1)
        self.focus_spin = QDoubleSpinBox()
        self.focus_spin.setRange(0, 100)
        self.focus_spin.setToolTip("Focus: 0.00 - 100.00%")
        abs_layout.addWidget(self.focus_spin, 4, 2)
        self.focus_set_btn = QPushButton("Set")
        abs_layout.addWidget(self.focus_set_btn, 4, 4)

        abs_group.setLayout(abs_layout)

        layout.addWidget(self.update_checkbox)
        layout.addWidget(abs_group)

        # Create container for joystick + lens controls
        joystick_lens_container = QWidget()
        joystick_lens_layout = QHBoxLayout(joystick_lens_container)
        joystick_lens_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Joystick Control Group (left side)
        joystick_group = QGroupBox()
        joystick_layout = QVBoxLayout()

        self.joystick = JoystickWidget()
        self.joystick.setMinimumSize(120, 120)
        joystick_layout.addWidget(self.joystick)

        # Speed control (keep existing)
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setValue(50)
        self.speed_label = QLabel("50")
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_label)
        joystick_layout.addLayout(speed_layout)

        joystick_group.setLayout(joystick_layout)
        joystick_lens_layout.addWidget(joystick_group)

        # 2. Lens Controls Group (right side) - IMPROVED DESIGN
        lens_group = QGroupBox()
        lens_layout = QVBoxLayout()
        lens_layout.setSpacing(10)

        # Main control grid with better styling
        control_grid = QGridLayout()
        control_grid.setSpacing(8)
        control_grid.setContentsMargins(5, 5, 5, 5)

        self.zoom_tele_btn = QPushButton()
        self.zoom_tele_btn.setIcon(QIcon("icons/zoom_in.png"))
        self.zoom_tele_btn.setIconSize(QSize(20, 20))
        self.zoom_tele_btn.setToolTip("Zoom In")
        self.zoom_tele_btn.setFixedSize(30, 30)

        self.zoom_wide_btn = QPushButton()
        self.zoom_wide_btn.setIcon(QIcon("icons/zoom_out.png"))
        self.zoom_wide_btn.setIconSize(QSize(20, 20))
        self.zoom_wide_btn.setToolTip("Zoom Out")
        self.zoom_wide_btn.setFixedSize(30, 30)

        control_grid.addWidget(self.zoom_wide_btn, 0, 0)
        control_grid.addWidget(self.zoom_tele_btn, 0, 1)

        # Focus Controls with label
        self.focus_near_btn = QPushButton()
        self.focus_near_btn.setIcon(QIcon("icons/focus_near.png"))
        self.focus_near_btn.setIconSize(QSize(20, 20))
        self.focus_near_btn.setToolTip("Focus Near")
        self.focus_near_btn.setFixedSize(30, 30)

        self.focus_far_btn = QPushButton()
        self.focus_far_btn.setIcon(QIcon("icons/focus_far.png"))
        self.focus_far_btn.setIconSize(QSize(20, 20))
        self.focus_far_btn.setToolTip("Focus Far")
        self.focus_far_btn.setFixedSize(30, 30)

        control_grid.addWidget(self.focus_near_btn, 1, 0)
        control_grid.addWidget(self.focus_far_btn, 1, 1)

        # Iris Controls with label
        self.iris_close_btn = QPushButton()
        self.iris_close_btn.setIcon(QIcon("icons/iris_close.png"))
        self.iris_close_btn.setIconSize(QSize(20, 20))
        self.iris_close_btn.setToolTip("Iris Close")
        self.iris_close_btn.setFixedSize(30, 30)

        self.iris_open_btn = QPushButton()
        self.iris_open_btn.setIcon(QIcon("icons/iris_open.png"))
        self.iris_open_btn.setIconSize(QSize(20, 20))
        self.iris_open_btn.setToolTip("Iris Open")
        self.iris_open_btn.setFixedSize(30, 30)

        control_grid.addWidget(self.iris_close_btn, 2, 0)
        control_grid.addWidget(self.iris_open_btn, 2, 1)

        # AF and 1-Push
        self.auto_focus_btn = QPushButton("ZT")
        self.auto_focus_btn.setCheckable(True)
        self.auto_focus_btn.setFixedSize(30, 30)

        self.one_push_btn = QPushButton("AF")
        self.one_push_btn.setFixedSize(30, 30)

        control_grid.addWidget(self.auto_focus_btn, 3, 0)
        control_grid.addWidget(self.one_push_btn, 3, 1)

        lens_layout.addLayout(control_grid)

        # Home Button with better styling
        home_layout = QHBoxLayout()
        self.home_btn = QPushButton()
        self.home_btn.setIcon(QIcon("icons/home.jpg"))
        self.home_btn.setIconSize(QSize(20, 20))
        self.home_btn.setToolTip("Home Position")
        self.home_btn.setFixedSize(40, 40)
        home_layout.addWidget(self.home_btn)
        lens_layout.addLayout(home_layout, Qt.AlignCenter)

        lens_group.setLayout(lens_layout)
        joystick_lens_layout.addWidget(lens_group)

        # Add the container to main layout
        layout.addWidget(joystick_lens_container)

        self.setContentLayout(layout)

    def connect_signals(self):
        """Connect all signals to main_window methods"""
        # Joystick signals
        self.joystick.position_changed.connect(self.main_window.on_joystick_moved)

        # Speed slider
        self.speed_slider.valueChanged.connect(
            lambda val: self.speed_label.setText(str(val))
        )

        # Zoom buttons
        self.zoom_wide_btn.pressed.connect(
            lambda: self.main_window.zoom_control("wide"))
        self.zoom_wide_btn.released.connect(
            lambda: self.main_window.zoom_control("stop"))
        self.zoom_tele_btn.pressed.connect(
            lambda: self.main_window.zoom_control("tele"))
        self.zoom_tele_btn.released.connect(
            lambda: self.main_window.zoom_control("stop"))

        # Focus buttons
        self.focus_near_btn.pressed.connect(
            lambda: self.main_window.focus_control("near"))
        self.focus_near_btn.released.connect(
            lambda: self.main_window.focus_control("stop"))
        self.focus_far_btn.pressed.connect(
            lambda: self.main_window.focus_control("far"))
        self.focus_far_btn.released.connect(
            lambda: self.main_window.focus_control("stop"))

        # Auto focus
        self.auto_focus_btn.clicked.connect(self.main_window.toggle_auto_focus)
        self.one_push_btn.clicked.connect(self.main_window.one_push_focus)

        # Home button
        self.home_btn.clicked.connect(self.main_window.go_to_home)

        # Absolute position controls
        self.pan_set_btn.clicked.connect(self.main_window.set_absolute_pan)
        self.tilt_set_btn.clicked.connect(self.main_window.set_absolute_tilt)
        self.zoom_set_btn.clicked.connect(self.main_window.set_absolute_zoom)
        self.focus_set_btn.clicked.connect(self.main_window.set_absolute_focus)

        # Position polling
        self.update_checkbox.toggled.connect(self.main_window.toggle_position_updates)
