import cv2
import numpy as np
import json
from PySide6.QtWidgets import (QLabel, QPushButton, QHBoxLayout,
                               QVBoxLayout, QWidget, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QMutex, QMutexLocker
from PySide6.QtGui import QImage, QPixmap
import time
import requests


class VideoWorker(QThread):
    frame_ready = Signal(np.ndarray)
    connection_status = Signal(bool, str)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._running = False
        self._cap = None
        self._url = ""
        self._mutex = QMutex()

    def set_url(self, url):
        with QMutexLocker(self._mutex):
            self._url = url

    def run(self):
        self._running = True

        try:
            with QMutexLocker(self._mutex):
                url = self._url

            if not url:
                self.error_occurred.emit("Empty URL provided")
                return

            self._cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            if not self._cap.isOpened():
                self.error_occurred.emit("Failed to open stream")
                return

            self.connection_status.emit(True, "Connected")

            while self._running and self._cap.isOpened():
                for _ in range(2):  # Skip frames to get latest
                    self._cap.grab()

                ret, frame = self._cap.retrieve()
                if not ret:
                    self.error_occurred.emit("Frame retrieval failed")
                    break

                self.frame_ready.emit(frame)

        except Exception as e:
            self.error_occurred.emit(f"Stream error: {str(e)}")
        finally:
            self._cleanup()

    def _cleanup(self):
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    def stop(self):
        self._running = False
        self.wait(500)  # Wait up to 500ms for thread to finish


class RTSPVideoStream:
    def __init__(self, parent=None, config_urls=None):
        self.parent = parent
        self.config_urls = config_urls or {}  # Fallback URLs if GET request fails
        self.worker = VideoWorker()
        self._setup_ui()
        self._connect_signals()
        self.stream_buttons = {}  # Stores stream buttons by name
        self.available_streams = {}  # Stores available stream URLs

    def _setup_ui(self):
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("No stream selected")
        self.video_label.setStyleSheet("""
            background-color: #1e293b; 
            color: white; 
            border-radius: 8px;
            font-size: 14px;
        """)

        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(5)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.video_label)
        self.layout.addLayout(self.button_layout)

    def discover_streams(self, api_url=None, auth=None):
        """Discover available streams via GET request or use configured URLs"""
        # Clear existing buttons
        self._clear_buttons()

        # Try to get streams from API endpoint first
        if api_url:
            try:
                response = requests.get(
                    api_url,
                    timeout=3,
                    auth=auth if auth else None
                )
                response.raise_for_status()
                self.available_streams = response.json()
            except Exception as e:
                print(f"API request failed: {e}")
                # Fall back to configured URLs
                self.available_streams = self.config_urls
        else:
            # Use configured URLs directly
            self.available_streams = self.config_urls

        # Create buttons for available streams
        for name, url in self.available_streams.items():
            self._add_stream_button(name, url)

        if not self.available_streams:
            self.video_label.setText("No streams available")

    def _clear_buttons(self):
        """Remove all stream buttons"""
        while self.button_layout.count():
            item = self.button_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.stream_buttons.clear()

    def _add_stream_button(self, name: str, url: str):
        """Add a new stream button"""
        if name in self.stream_buttons:
            return

        btn = QPushButton(name)
        btn.setCheckable(True)
        btn.setProperty('stream_url', url)
        btn.clicked.connect(self._on_stream_button_clicked)
        self.button_layout.addWidget(btn)
        self.stream_buttons[name] = btn

    def _on_stream_button_clicked(self):
        """Handle stream button clicks"""
        sender = self.sender()
        if not sender.isChecked():
            return

        stream_url = sender.property('stream_url')
        self.connect(stream_url)

        # Update other buttons to unchecked state
        for btn in self.stream_buttons.values():
            if btn != sender:
                btn.setChecked(False)

    def _connect_signals(self):
        self.worker.frame_ready.connect(self._update_frame)
        self.worker.connection_status.connect(self._update_connection_status)
        self.worker.error_occurred.connect(self._handle_error)

    def get_video_widget(self):
        container = QWidget()
        container.setLayout(self.layout)
        return container

    def connect(self, rtsp_url):
        """Connect to a stream without blocking the UI"""
        self.disconnect()  # Disconnect any existing stream first

        if not rtsp_url:
            self.video_label.setText("Invalid stream URL")
            return False

        self.video_label.setText("Connecting...")
        self.worker.set_url(rtsp_url)
        self.worker.start()
        return True

    def disconnect(self):
        """Disconnect from current stream"""
        if self.worker.isRunning():
            self.worker.stop()
        self.video_label.setText("Stream disconnected")

    @Slot(np.ndarray)
    def _update_frame(self, frame):
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)

            self.video_label.setPixmap(pixmap.scaled(
                self.video_label.width(),
                self.video_label.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        except Exception as e:
            self._handle_error(f"Frame display error: {str(e)}")

    @Slot(bool, str)
    def _update_connection_status(self, success, message):
        if not success:
            self.video_label.setText(message)

    @Slot(str)
    def _handle_error(self, message):
        self.video_label.setText(message)
        self.disconnect()
        if self.parent:
            QMessageBox.warning(self.parent, "Stream Error", message)