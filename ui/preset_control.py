# app/ui/preset_control.py
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QLabel, QPushButton, QComboBox, QSpinBox, QFrame, QSizePolicy)
from PySide6.QtCore import Qt
from ui.collapsible_box import CollapsibleBox


class PresetButton(QPushButton):
    """Custom button that automatically handles text display"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumSize(80, 30)  # Increased minimum size

    def set_full_text(self, text):
        self._full_text = text
        super().setText(text)  # Always show full text
        self.setToolTip(text)

        # Calculate if text would be truncated
        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(text)
        if text_width > self.width():
            # If text is too long, set a fixed minimum width
            self.setMinimumWidth(text_width + 10)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-check text width on resize
        if self._full_text:
            metrics = self.fontMetrics()
            text_width = metrics.horizontalAdvance(self._full_text)
            if text_width > self.width():
                self.setMinimumWidth(text_width + 10)

class PresetControlSection(CollapsibleBox):
    def __init__(self, main_window):
        super().__init__("Presets")
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)  # Reduce spacing between elements

        # ───── Combined Preset Control Section ─────
        main_group = QGroupBox()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)

        # Top row - Direct preset controls
        top_row = QHBoxLayout()

        self.direct_spin = QSpinBox()
        self.direct_spin.setRange(1, 255)
        self.direct_spin.setFixedWidth(60)
        top_row.addWidget(self.direct_spin)

        self.call_btn = QPushButton("Call")
        self.call_btn.setFixedWidth(50)
        self.set_btn = QPushButton("Set")
        self.set_btn.setFixedWidth(50)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setFixedWidth(50)

        top_row.addWidget(self.call_btn)
        top_row.addWidget(self.set_btn)
        top_row.addWidget(self.clear_btn)
        top_row.addStretch()
        main_layout.addLayout(top_row)

        # Add separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        main_layout.addWidget(separator)

        # Middle section - Preset manager
        # Type filter
        type_row = QHBoxLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Positional (1-79)", "Functional (80-255)"])
        self.type_combo.setCurrentIndex(1)
        type_row.addWidget(self.type_combo)
        type_row.addStretch()
        main_layout.addLayout(type_row)

        # Preset selection row
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(80)
        preset_row.addWidget(self.preset_combo, 1)  # Allow combo box to expand

        self.preset_call_btn = QPushButton("Call")
        self.preset_call_btn.setFixedWidth(50)
        self.preset_set_btn = QPushButton("Set")
        self.preset_set_btn.setFixedWidth(50)
        self.preset_clear_btn = QPushButton("Clear")
        self.preset_clear_btn.setFixedWidth(50)

        preset_row.addWidget(self.preset_call_btn)
        preset_row.addWidget(self.preset_set_btn)
        preset_row.addWidget(self.preset_clear_btn)
        main_layout.addLayout(preset_row)

        # Preset buttons grid
        grid_frame = QFrame()
        grid_layout = QGridLayout(grid_frame)
        grid_layout.setSpacing(5)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setColumnStretch(2, 1)
        self.preset_buttons = []

        for i in range(9):
            btn = PresetButton("N/A")  # Using our custom button
            self.preset_buttons.append(btn)
            grid_layout.addWidget(btn, i // 3, i % 3)

        main_layout.addWidget(grid_frame)

        # Management buttons
        bottom_row = QHBoxLayout()
        self.add_preset_btn = QPushButton("+ Add")
        self.edit_preset_btn = QPushButton("✎ Edit")
        self.del_preset_btn = QPushButton("✖ Del")

        bottom_row.addWidget(self.add_preset_btn)
        bottom_row.addWidget(self.edit_preset_btn)
        bottom_row.addWidget(self.del_preset_btn)
        bottom_row.addStretch()

        main_layout.addLayout(bottom_row)
        main_group.setLayout(main_layout)
        layout.addWidget(main_group)

        # Set main collapsible layout
        self.setContentLayout(layout)
        self.update_preset_ui()

    def connect_signals(self):
        self.type_combo.currentIndexChanged.connect(self.update_preset_ui)
        self.call_btn.clicked.connect(self.main_window.call_direct_preset)
        self.set_btn.clicked.connect(self.main_window.set_direct_preset)
        self.clear_btn.clicked.connect(self.main_window.clear_direct_preset)

        for btn in self.preset_buttons:
            btn.clicked.connect(lambda _, b=btn: self.main_window.activate_preset_button(b))

        self.preset_call_btn.clicked.connect(self.main_window.call_selected_preset)
        self.preset_set_btn.clicked.connect(self.main_window.set_selected_preset)
        self.preset_clear_btn.clicked.connect(self.main_window.clear_selected_preset)
        self.add_preset_btn.clicked.connect(self.main_window.add_new_preset)
        self.edit_preset_btn.clicked.connect(self.main_window.edit_selected_preset)
        self.del_preset_btn.clicked.connect(self.main_window.delete_selected_preset)

    def update_preset_ui(self):
        """Update UI based on selected preset type"""
        self.update_preset_combo()
        self.update_preset_buttons()

    def update_preset_combo(self):
        """Update the preset dropdown"""
        self.preset_combo.clear()
        preset_type = self.type_combo.currentIndex()
        min_val, max_val = (1, 79) if preset_type == 0 else (80, 255)

        for preset in self.main_window.presets:
            if min_val <= preset['number'] <= max_val:
                self.preset_combo.addItem(f"{preset['number']}: {preset['name']}")

    def update_preset_buttons(self):
        """Update the quick preset buttons"""
        preset_type = self.type_combo.currentIndex()
        min_val, max_val = (1, 79) if preset_type == 0 else (80, 255)

        filtered = [p for p in self.main_window.presets if min_val <= p['number'] <= max_val]

        for i, btn in enumerate(self.preset_buttons):
            if i < len(filtered):
                preset = filtered[i]
                btn.set_full_text(preset['name'])  # Use our custom text handling
                btn.setProperty('preset_num', preset['number'])
                btn.setEnabled(True)
            else:
                btn.setText("N/A")
                btn.setToolTip("")
                btn.setProperty('preset_num', -1)
                btn.setEnabled(False)