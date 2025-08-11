import cv2
import numpy as np
from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QMessageBox
from PySide6.QtCore import Qt, QThread, Signal, Slot, QMutex, QMutexLocker
from PySide6.QtGui import QImage, QPixmap
import time

import requests
from typing import List, Dict

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
        self._max_reconnect_attempts = 5  # for example

    def set_url(self, url):
        with QMutexLocker(self._mutex):
            self._url = url

    def run(self):
        self._running = True
        self._reconnect_attempts = 0

        while self._running:
            try:
                self._connect()
                self._process_stream()
            except Exception as e:
                self.error_occurred.emit(f"Error: {str(e)}")
                self._running = False
                time.sleep(1)
            finally:
                self._cleanup()

    def _connect(self):
        with QMutexLocker(self._mutex):
            url = self._url

        if not url:
            raise ValueError("Empty URL provided")

        self._cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not self._cap.isOpened():
            raise ConnectionError("Failed to open stream")
        print("connecting")
        self.connection_status.emit(True, "Connected")
        self._reconnect_attempts = 0

    def _process_stream(self):
        while self._running and self._cap.isOpened():
            for _ in range(2):  # Skip frames to get latest
                self._cap.grab()

            ret, frame = self._cap.retrieve()
            if not ret:
                self._handle_disconnect()
                break

            self.frame_ready.emit(frame)

    def _handle_disconnect(self):
        self._reconnect_attempts += 1
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            self.connection_status.emit(False, "Disconnected")
        else:
            self.connection_status.emit(
                False,
                f"Reconnecting ({self._reconnect_attempts}/{self._max_reconnect_attempts})"
            )

    def _cleanup(self):
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    def stop(self):
        self._running = False
        self.wait(2000)


class RTSPVideoStream:
    def __init__(self, parent=None):
        self.parent = parent
        self.worker = VideoWorker()
        # self.camera_manager = CameraManager()
        self._setup_ui()
        self._connect_signals()
        self.available_streams = []  # Stores available stream URLs

    def _setup_ui(self):
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("No video stream connected")
        self.video_label.setStyleSheet("""
            background-color: #1e293b; 
            color: white; 
            border-radius: 8px;
            font-size: 14px;
        """)

        # Stream switcher buttons (will be populated dynamically)
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(5)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.video_label)
        self.layout.addLayout(self.button_layout)

    def _on_stream_button_clicked(self):
        """Handle stream button clicks"""
        sender = self.sender()
        if not sender.isChecked():
            return

        stream_url = sender.property('stream_url')
        self.connect(stream_url)

        # Update button states
        for i in range(self.button_layout.count()):
            btn = self.button_layout.itemAt(i).widget()
            btn.setChecked(btn == sender)

    def _connect_signals(self):
        self.worker.frame_ready.connect(self._update_frame)
        self.worker.connection_status.connect(self._update_connection_status)
        self.worker.error_occurred.connect(self._handle_error)

    def get_video_widget(self):
        container = QWidget()
        container.setLayout(self.layout)
        return container

    def connect(self, rtsp_url):
        try:
            self.video_label.setText("Connecting to stream...")
            if self.worker.isRunning():
                self.worker.stop()
                self.worker.wait()

            self.worker.set_url(rtsp_url)
            self.worker.start()
            return True
        except Exception as e:
            self._handle_error(f"Connection error: {str(e)}")
            return False

    def disconnect(self):
        if self.worker.isRunning():
            self.worker.stop()
        self.video_label.setText("No video stream connected")

    def set_active_button(self, stream_id):
        for i in range(1, 5):
            btn = self.button_layout.itemAt(i - 1).widget()
            btn.setChecked(i == stream_id)

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
            self._handle_error(f"Frame error: {str(e)}")

    @Slot(bool, str)
    def _update_connection_status(self, success, message):
        self.video_label.setText(message)

    @Slot(str)
    def _handle_error(self, message):
        self.video_label.setText(message)
        if self.parent:
            print(message)
            # QMessageBox.warning(self.parent, "Stream Error", message)