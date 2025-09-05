import os
import threading

import cv2
import numpy as np
from PySide6.QtWidgets import (QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
                               QWidget, QMessageBox, QFileDialog, QGridLayout,
                               QStackedWidget, QSpinBox, QSizePolicy)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QMutex, QMutexLocker
from PySide6.QtGui import QImage, QPixmap, QPainter, QFont
import time
import re


class VideoWorker(QThread):
    frame_ready = Signal(int, np.ndarray)
    connection_status = Signal(bool, str)
    error_occurred = Signal(str)
    active_frame_ready = Signal(np.ndarray)

    def __init__(self):
        super().__init__()
        self._running = False
        self._caps = {}
        self._urls = {}
        self._mutex = QMutex()
        self._active_stream_id = 0
        self._stream_locks = {}

        # Recording attributes
        self._recording_path = None
        self._recording = False
        self._paused = False
        self._writer = None
        self._output_file = None
        self._fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._fps = 20.0
        self._frame_size = None

    def set_url(self, stream_id, url):
        with QMutexLocker(self._mutex):
            self._urls[stream_id] = url

    def set_active_stream(self, stream_id):
        with QMutexLocker(self._mutex):
            self._active_stream_id = stream_id

    def add_stream(self, stream_id, url):
        self.set_url(stream_id, url)
        if stream_id not in self._stream_locks:
            self._stream_locks[stream_id] = threading.Lock()

    def remove_stream(self, stream_id):
        with QMutexLocker(self._mutex):
            if stream_id in self._caps:
                if self._caps[stream_id] and self._caps[stream_id].isOpened():
                    self._caps[stream_id].release()
                del self._caps[stream_id]
            if stream_id in self._urls:
                del self._urls[stream_id]
            if stream_id in self._stream_locks:
                del self._stream_locks[stream_id]

    def run(self):
        self._running = True
        while self._running:
            try:
                # Process all streams
                stream_ids = list(self._urls.keys())
                for stream_id in stream_ids:
                    if not self._running:
                        break

                    if stream_id not in self._caps or not self._caps.get(stream_id) or not self._caps[
                        stream_id].isOpened():
                        self._connect(stream_id)

                    if stream_id in self._caps and self._caps[stream_id] and self._caps[stream_id].isOpened():
                        self._process_stream(stream_id)

                self.msleep(10)
            except Exception as e:
                self.error_occurred.emit(f"Error: {e}")
                time.sleep(1)

    def _connect(self, stream_id):
        url = self._urls.get(stream_id, "")

        if not url or url == "":
            return False

        try:
            # Use optimized parameters
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FPS, 30)

            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(url)

            if cap.isOpened():
                with QMutexLocker(self._mutex):
                    self._caps[stream_id] = cap
                self.connection_status.emit(True, f"Connected to stream {stream_id}")
                return True
            else:
                self.connection_status.emit(False, f"Failed to connect to stream {stream_id}")
                return False

        except Exception as e:
            self.error_occurred.emit(f"Connection error: {str(e)}")
            return False

    def start_recording(self, filename: str):
        if self._recording:
            return

        with QMutexLocker(self._mutex):
            if self._active_stream_id not in self._caps or not self._caps[self._active_stream_id].isOpened():
                raise RuntimeError("Cannot start recording: no active stream")

            self._frame_size = (
                int(self._caps[self._active_stream_id].get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._caps[self._active_stream_id].get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
            self._output_file = filename
            self._writer = cv2.VideoWriter(filename, self._fourcc, self._fps, self._frame_size)
            if not self._writer.isOpened():
                raise RuntimeError("Failed to initialize VideoWriter")
            self._recording = True
            self._paused = False

    def pause_recording(self):
        with QMutexLocker(self._mutex):
            if self._recording:
                self._paused = True

    def resume_recording(self):
        with QMutexLocker(self._mutex):
            if self._recording and self._paused:
                self._paused = False

    def stop_recording(self):
        if not self._recording:
            return

        with QMutexLocker(self._mutex):
            self._recording = False
            if self._writer:
                self._writer.release()
                self._writer = None

    def _process_stream(self, stream_id):
        try:
            if stream_id not in self._caps or not self._caps[stream_id] or not self._caps[stream_id].isOpened():
                return

            cap = self._caps[stream_id]

            grabbed = cap.grab()
            if not grabbed:
                return

            ok, frame = cap.retrieve()
            if not ok or frame is None:
                return

            # Emit frame for grid view
            self.frame_ready.emit(stream_id, frame)

            # Emit for main view if this is the active stream
            if stream_id == self._active_stream_id:
                self.active_frame_ready.emit(frame)

                # Handle recording
                if self._recording and not self._paused and self._writer:
                    self._writer.write(frame)

        except Exception as e:
            self.error_occurred.emit(f"Stream {stream_id} error: {str(e)}")

    def _cleanup(self):
        with QMutexLocker(self._mutex):
            for stream_id, cap in self._caps.items():
                if cap and cap.isOpened():
                    cap.release()
            self._caps.clear()
            self._urls.clear()

        if self._writer:
            self._writer.release()
        self._writer = None

    def stop(self):
        self._running = False
        self._cleanup()
        self.wait(2000)


class VideoGridWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(2)
        self.setLayout(self.grid_layout)
        self.video_widgets = []

    def setup_grid(self, rows, cols):
        # Clear existing widgets
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        self.video_widgets = []
        self.rows = rows
        self.cols = cols

        # Create video widgets for each grid cell
        for row in range(rows):
            for col in range(cols):
                video_widget = QLabel()
                video_widget.setAlignment(Qt.AlignCenter)
                video_widget.setText(f"Camera {row * cols + col + 1}")
                video_widget.setStyleSheet("""
                    QLabel {
                        background-color: #1e293b; 
                        color: white; 
                        border: 2px solid #334155;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                    QLabel:hover {
                        border: 2px solid #60a5fa;
                    }
                """)
                video_widget.setMinimumSize(200, 150)
                video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

                # Store the index in a closure to avoid late binding issues
                index = row * cols + col
                video_widget.mousePressEvent = lambda event, idx=index: self.cell_clicked(idx)

                self.grid_layout.addWidget(video_widget, row, col)
                self.video_widgets.append(video_widget)

    def cell_clicked(self, index):
        # Handle cell click to focus on a specific camera
        if self.parent and hasattr(self.parent, 'focus_on_camera'):
            self.parent.focus_on_camera(index)

    def update_frame(self, index, frame):
        # Update a specific cell with a new frame
        if index < len(self.video_widgets):
            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_frame.shape
                bytes_per_line = ch * w
                q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(q_img)

                # Scale to fit the cell while maintaining aspect ratio
                self.video_widgets[index].setPixmap(
                    pixmap.scaled(
                        self.video_widgets[index].width(),
                        self.video_widgets[index].height(),
                        Qt.IgnoreAspectRatio,  # Fill the entire cell
                        Qt.SmoothTransformation
                    )
                )
            except Exception as e:
                print(f"Error updating grid cell {index}: {e}")


class RTSPVideoStream(QWidget):  # Fixed: Now inherits from QWidget
    def __init__(self, parent=None):
        super().__init__(parent)  # Fixed: Proper parent initialization
        self.parent = parent
        self.worker = VideoWorker()
        self.grid_widget = VideoGridWidget(self)  # Fixed: Pass self as parent
        self._setup_ui()
        self._connect_signals()
        self.available_streams = []
        self.available_stream_names = []
        self.grid_mode = False
        self.stream_buttons = []
        self.current_stream_index = 0

    def _setup_ui(self):
        # Main video label for single view
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("No video stream connected")
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #1e293b; 
                color: white; 
                border-radius: 8px;
                font-size: 14px;
            }
        """)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Stacked widget to switch between single and grid view
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.video_label)
        self.stacked_widget.addWidget(self.grid_widget)

        # View mode toggle button
        self.view_toggle_btn = QPushButton("Grid View")
        self.view_toggle_btn.setCheckable(True)
        self.view_toggle_btn.clicked.connect(self.toggle_view_mode)

        # Grid configuration controls
        grid_config_layout = QHBoxLayout()
        grid_config_layout.addWidget(QLabel("Grid:"))

        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 4)
        self.rows_spin.setValue(2)
        self.rows_spin.valueChanged.connect(self.update_grid_layout)
        grid_config_layout.addWidget(QLabel("Rows:"))
        grid_config_layout.addWidget(self.rows_spin)

        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 4)
        self.cols_spin.setValue(2)
        self.cols_spin.valueChanged.connect(self.update_grid_layout)
        grid_config_layout.addWidget(QLabel("Columns:"))
        grid_config_layout.addWidget(self.cols_spin)

        # Stream switcher buttons
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(5)

        # Main layout
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.stacked_widget, 1)  # Priority 1 for expansion

        # Control layout at bottom
        control_layout = QHBoxLayout()
        control_layout.addWidget(self.view_toggle_btn)
        control_layout.addLayout(grid_config_layout)
        control_layout.addStretch()
        control_layout.addLayout(self.button_layout)

        self.layout.addLayout(control_layout)
        self.setLayout(self.layout)  # Fixed: Set layout on self

    def _extract_stream_name(self, rtsp_url):
        """Extract meaningful name from RTSP URL"""
        try:
            if 'channel=' in rtsp_url:
                match = re.search(r'channel=(\d+)', rtsp_url)
                if match:
                    return f"Ch{match.group(1)}"

            if 'stream=' in rtsp_url:
                match = re.search(r'stream=(\d+)', rtsp_url)
                if match:
                    return f"Strm{match.group(1)}"

            path_parts = rtsp_url.split('/')
            for part in reversed(path_parts):
                if part and not part.startswith('rtsp:') and '=' not in part:
                    return part[:15]

            return "Cam"
        except:
            return "Stream"

    def toggle_view_mode(self, checked):
        self.grid_mode = checked
        if checked:
            self.stacked_widget.setCurrentIndex(1)
            self.view_toggle_btn.setText("Single View")
            self.update_grid_layout()
        else:
            self.stacked_widget.setCurrentIndex(0)
            self.view_toggle_btn.setText("Grid View")

    def update_grid_layout(self):
        if not self.grid_mode:
            return

        rows = self.rows_spin.value()
        cols = self.cols_spin.value()
        self.grid_widget.setup_grid(rows, cols)

        max_streams = rows * cols

        for i in range(max_streams):
            if i < len(self.available_streams):
                self.worker.add_stream(i, self.available_streams[i])
            else:
                self.worker.add_stream(i, "")

        current_streams = len(self.worker._urls)
        for i in range(max_streams, current_streams):
            self.worker.remove_stream(i)

    def focus_on_camera(self, index):
        if index < len(self.available_streams):
            self.current_stream_index = index
            self.worker.set_active_stream(index)
            self._switch_to_stream(index)
            self.stacked_widget.setCurrentIndex(0)
            self.view_toggle_btn.setChecked(False)
            self.view_toggle_btn.setText("Grid View")
            self.grid_mode = False
            self.set_active_button(index)

    def _switch_to_stream(self, stream_id):
        """Switch to a specific stream"""
        if stream_id < len(self.available_streams):
            stream_url = self.available_streams[stream_id]

            # Ensure worker is running
            if not self.worker.isRunning():
                self.worker.start()

            # Set the active stream
            self.worker.set_active_stream(stream_id)

            # Update the URL for the main connection
            self.worker.set_url(0, stream_url)

    def _on_stream_button_clicked(self, stream_id):
        """Handle stream button clicks"""
        print(f"Stream button clicked: {stream_id}")
        if stream_id < len(self.available_streams):
            self.current_stream_index = stream_id
            self.worker.set_active_stream(stream_id)
            self._switch_to_stream(stream_id)

            # Update button states
            for i, btn in enumerate(self.stream_buttons):
                btn.setChecked(i == stream_id)

    def _connect_signals(self):
        self.worker.frame_ready.connect(self._update_grid_frame)
        self.worker.active_frame_ready.connect(self._update_main_frame)
        self.worker.connection_status.connect(self._update_connection_status)
        self.worker.error_occurred.connect(self._handle_error)

    def get_video_widget(self):
        return self  # Fixed: Return self since we're now a QWidget

    def connect(self, rtsp_url):
        """Main connect method"""
        try:
            self.video_label.setText("Connecting to stream...")

            # Stop if already running
            if self.worker.isRunning():
                self.worker.stop()
                self.worker.wait()

            # Add to available streams if not already there
            if rtsp_url not in self.available_streams:
                self.available_streams = [rtsp_url]
                stream_name = self._extract_stream_name(rtsp_url)
                self.available_stream_names = [stream_name]

            self.current_stream_index = 0
            self.worker.set_active_stream(0)
            self.worker.set_url(0, rtsp_url)
            self.worker.start()

            return True
        except Exception as e:
            self._handle_error(f"Connection error: {str(e)}")
            return False

    def disconnect(self):
        if self.worker.isRunning():
            self.worker.stop()
        if hasattr(self.worker, 'stop_recording'):
            self.worker.stop_recording()
        self.video_label.setText("No video stream connected")

    def set_active_button(self, stream_id):
        for i, btn in enumerate(self.stream_buttons):
            btn.setChecked(i == stream_id)

    @Slot(int, np.ndarray)
    def _update_grid_frame(self, stream_id, frame):
        if self.grid_mode:
            self.grid_widget.update_frame(stream_id, frame)

    @Slot(np.ndarray)
    def _update_main_frame(self, frame):
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)

            if hasattr(self.worker, '_recording') and self.worker._recording:
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                if not self.worker._paused:
                    painter.setPen(Qt.red)
                    painter.setFont(QFont("Arial", 18, QFont.Bold))
                    painter.drawText(pixmap.width() - 120, 30, "REC ●")
                else:
                    painter.setPen(Qt.yellow)
                    painter.setFont(QFont("Arial", 18, QFont.Bold))
                    painter.drawText(pixmap.width() - 150, 30, "PAUSED ⏸")
                painter.end()

            self.video_label.setPixmap(
                pixmap.scaled(
                    self.video_label.width(),
                    self.video_label.height(),
                    Qt.IgnoreAspectRatio,  # Fill the entire space
                    Qt.SmoothTransformation
                )
            )
        except Exception as e:
            self._handle_error(f"Frame error: {str(e)}")

    @Slot(bool, str)
    def _update_connection_status(self, success, message):
        if not success:
            self.video_label.setText(message)

    @Slot(str)
    def _handle_error(self, message):
        self.video_label.setText(message)
        if self.parent:
            print(message)

    def set_stream_buttons(self, rtsp_urls):
        """Set available streams with meaningful names from RTSP keys"""
        # Clear existing buttons
        for i in reversed(range(self.button_layout.count())):
            widget = self.button_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        self.stream_buttons.clear()
        self.available_streams = []
        self.available_stream_names = []

        # Extract streams from dictionary
        if isinstance(rtsp_urls, dict):
            for key, url in rtsp_urls.items():
                self.available_streams.append(url)
                self.available_stream_names.append(key.capitalize())
        else:
            self.available_streams = list(rtsp_urls)
            for url in self.available_streams:
                self.available_stream_names.append(self._extract_stream_name(url))

        # Create buttons
        for i, (stream_name, stream_url) in enumerate(zip(self.available_stream_names, self.available_streams)):
            btn = QPushButton(stream_name)
            btn.setCheckable(True)
            btn.setToolTip(stream_url)
            btn.setMinimumWidth(80)
            btn.clicked.connect(lambda checked, idx=i: self._on_stream_button_clicked(idx))
            self.button_layout.addWidget(btn)
            self.stream_buttons.append(btn)

        # Select the first stream by default
        if self.stream_buttons:
            self.stream_buttons[0].setChecked(True)

        if self.grid_mode:
            self.update_grid_layout()

    # Recording methods remain the same...

    # --- Recording controls ---
    def start_recording(self):
        if not self.worker.isRunning():
            self._handle_error("Stream not active. Cannot record.")
            return
        try:
            # Make sure base exists
            if not hasattr(self.worker, "_recording_base") or not self.worker._recording_base:
                if not self.save_as_record_file():
                    return  # user cancelled

            # Generate indexed filename (_1, _2, ...)
            new_filename = self._next_recording_filename()
            self.worker._recording_path = new_filename
            self.worker.start_recording(new_filename)

            if self.parent:
                self.parent.start_record.setEnabled(False)
                self.parent.pause_record.setEnabled(True)
                self.parent.resume_record.setEnabled(False)
                self.parent.stop_record.setEnabled(True)
                self.parent.statusBar().showMessage(f"Recording started: {new_filename}")

        except Exception as e:
            self._handle_error(str(e))

    def pause_recording(self):
        if self.worker.isRunning():
            self.worker.pause_recording()
            if self.parent:
                self.parent.start_record.setEnabled(False)
                self.parent.pause_record.setEnabled(False)
                self.parent.resume_record.setEnabled(True)
                self.parent.stop_record.setEnabled(True)
                self.parent.statusBar().showMessage("Recording paused")

    def resume_recording(self):
        if self.worker.isRunning():
            self.worker.resume_recording()
            if self.parent:
                self.parent.start_record.setEnabled(True)
                self.parent.pause_record.setEnabled(True)
                self.parent.resume_record.setEnabled(False)
                self.parent.stop_record.setEnabled(True)
                self.parent.statusBar().showMessage("Recording resumed")

    def stop_recording(self):
        if self.worker.isRunning():
            self.worker.stop_recording()
            if self.parent:
                self.parent.start_record.setEnabled(True)
                self.parent.pause_record.setEnabled(False)
                self.parent.resume_record.setEnabled(False)
                self.parent.stop_record.setEnabled(False)
                self.parent.statusBar().showMessage("Recording stopped")

    def save_as_record_file(self):
        """Explicitly reset base filename (but don’t increment yet)"""
        filename, _ = QFileDialog.getSaveFileName(
            caption="Save Recording As",
            dir=f"recording_{time.strftime('%Y%m%d_%H%M%S')}.mp4",
            filter="MP4 Files (*.mp4);;AVI Files (*.avi)"
        )
        if not filename:
            return False

        base_dir = os.path.dirname(filename)
        base_name, ext = os.path.splitext(os.path.basename(filename))
        if not ext:
            ext = ".mp4"

        # store these so next recordings can reuse them
        self.worker._recording_dir = base_dir
        self.worker._recording_base = base_name
        self.worker._recording_ext = ext
        self.worker._recording_index = 0  # reset to 0 so first recording will be _1
        return True

    def _next_recording_filename(self):
        """Generate next indexed filename"""
        if not hasattr(self.worker, "_recording_base") or not self.worker._recording_base:
            if not self.save_as_record_file():
                return None

        self.worker._recording_index += 1
        return os.path.join(
            self.worker._recording_dir,
            f"{self.worker._recording_base}_{self.worker._recording_index}{self.worker._recording_ext}"
        )
