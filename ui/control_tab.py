# ui/control_tab.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea
from PySide6.QtCore import Qt
from ui.camera_control import CameraControlSection
from ui.ptz_control import PTZControlSection
from ui.preset_control import PresetControlSection


class ControlTab(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        """Initialize the control tab UI"""
        # Create scroll area for controls
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        control_panel = QWidget()
        self.layout = QVBoxLayout(control_panel)

        # Add control sections
        self.camera_control = CameraControlSection(self.parent)
        self.ptz_control = PTZControlSection(self.parent)
        self.preset_control = PresetControlSection(self.parent)

        self.layout.addWidget(self.camera_control)
        self.layout.addWidget(self.ptz_control)
        self.layout.addWidget(self.preset_control)
        self.layout.addStretch()

        scroll.setWidget(control_panel)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

        # IMPORTANT: Set focus policy to ensure key events can propagate
        self.setFocusPolicy(Qt.NoFocus)
        scroll.setFocusPolicy(Qt.NoFocus)
        control_panel.setFocusPolicy(Qt.NoFocus)

    def connect_signals(self):
        """Connect all signals in child sections"""
        self.camera_control.connect_signals()
        self.ptz_control.connect_signals()
        self.preset_control.connect_signals()

    # REMOVE or MODIFY the keyPressEvent to allow event propagation
    def keyPressEvent(self, event):
        # Instead of capturing events, forward them to parent
        self.parent.keyPressEvent(event)
        event.accept()  # Mark event as handled