import os
import sys
import time
import math
from typing import Dict, List

import cv2
import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QFont, QAction, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QFileDialog, QStackedWidget, QMainWindow, QSizePolicy
)


# -----------------------------
# Per-stream capture worker
# -----------------------------
class VideoWorker(QThread):
    frame_ready = Signal(int, np.ndarray)         # (stream_id, frame BGR)
    status = Signal(int, bool, str)               # (stream_id, ok, message)
    error = Signal(int, str)                      # (stream_id, message)

    def __init__(self, stream_id: int, url: str, parent: QObject | None = None):
        super().__init__(parent)
        self.stream_id = stream_id
        self.url = url
        self._running = False
        self._cap = None

        # Tuneables
        self._max_failures = 50
        self._sleep_between_loops_ms = 1

    def _open(self) -> bool:
        try:
            # Try FFMPEG first
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.url)

            if not cap.isOpened():
                self.status.emit(self.stream_id, False, "Failed to open")
                return False

            self._cap = cap
            self.status.emit(self.stream_id, True, "Connected")
            return True
        except Exception as e:
            self.error.emit(self.stream_id, f"Open error: {e}")
            return False

    def run(self):
        self._running = True
        backoff = 0.5

        while self._running:
            if not self._cap or not self._cap.isOpened():
                if not self._open():
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 5.0)
                    continue
                backoff = 0.5

            failures = 0
            while self._running and self._cap and self._cap.isOpened():
                grabbed = self._cap.grab()
                if not grabbed:
                    failures += 1
                    if failures >= self._max_failures:
                        self.status.emit(self.stream_id, False, "Too many grab() failures")
                        break
                    time.sleep(0.01)
                    continue

                ok, frame = self._cap.retrieve()
                if not ok or frame is None:
                    failures += 1
                    if failures >= self._max_failures:
                        self.status.emit(self.stream_id, False, "Too many retrieve() failures")
                        break
                    time.sleep(0.01)
                    continue

                if failures:
                    failures = 0

                self.frame_ready.emit(self.stream_id, frame)
                self.msleep(self._sleep_between_loops_ms)

            # Close & retry
            if self._cap and self._cap.isOpened():
                self._cap.release()
            self._cap = None
            time.sleep(0.5)

        # cleanup
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = None

    def stop(self):
        self._running = False
        self.wait(1500)


# -----------------------------
# Grid widget (previews only)
# -----------------------------
class VideoGridWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setSpacing(2)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.cells: Dict[int, QLabel] = {}   # stream_id -> QLabel

    def _make_label(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignCenter)
        lab.setStyleSheet("""
            QLabel {
                background-color: #1e293b;
                color: white;
                border: 2px solid #334155;
                border-radius: 4px;
                font-size: 12px;
            }
            QLabel:hover { border: 2px solid #60a5fa; }
        """)
        lab.setMinimumSize(160, 120)
        lab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return lab

    def set_streams(self, stream_ids: List[int], names: Dict[int, str]):
        # Clear grid
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.cells.clear()

        n = len(stream_ids)
        if n == 0:
            return

        rows = int(math.ceil(math.sqrt(n)))
        cols = int(math.ceil(n / rows))

        for idx, sid in enumerate(stream_ids):
            r, c = divmod(idx, cols)
            label = self._make_label(names.get(sid, f"Cam {sid}"))
            self.grid.addWidget(label, r, c)
            self.cells[sid] = label

    def set_click_handler(self, handler):
        # Assign mousePressEvent with bound stream_id
        for sid, lab in self.cells.items():
            lab.mousePressEvent = (lambda ev, s=sid: handler(s))

    def update_frame(self, stream_id: int, frame_bgr: np.ndarray):
        lab = self.cells.get(stream_id)
        if not lab:
            return
        try:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg)
            # Fill cell (ignore aspect ratio to fully occupy)
            lab.setPixmap(pix.scaled(lab.width(), lab.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            # Keep cell text on error
            print(f"Grid update error [{stream_id}]: {e}")


# -----------------------------
# Main video widget (single + grid)
# -----------------------------
class RTSPVideoStream(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # UI elements
        self.single_label = QLabel("No video stream connected")
        self.single_label.setAlignment(Qt.AlignCenter)
        self.single_label.setStyleSheet("""
            QLabel {
                background-color: #0f172a;
                color: white;
                border-radius: 8px;
                font-size: 14px;
            }
        """)
        self.single_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.grid_widget = VideoGridWidget(self)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.single_label)  # index 0
        self.stack.addWidget(self.grid_widget)   # index 1

        # Bottom controls: stream buttons + view toggle
        self.view_btn = QPushButton("Grid View")
        self.view_btn.setCheckable(True)
        self.view_btn.clicked.connect(self._toggle_view)

        self.buttons_bar = QHBoxLayout()
        self.buttons_bar.setSpacing(6)

        bar = QHBoxLayout()
        bar.addWidget(self.view_btn)
        bar.addStretch()
        bar.addLayout(self.buttons_bar)

        layout = QVBoxLayout(self)
        layout.addWidget(self.stack, 1)
        layout.addLayout(bar)

        # State
        self.workers: Dict[int, VideoWorker] = {}
        self.stream_urls: Dict[int, str] = {}
        self.stream_names: Dict[int, str] = {}
        self.active_stream_id: int | None = None

        # Recording state (active stream only)
        self._writer: cv2.VideoWriter | None = None
        self._recording = False
        self._paused = False
        self._rec_base_dir = ""
        self._rec_base_name = ""
        self._rec_ext = ".mp4"
        self._rec_index = 0
        self._fps = 20.0
        self._last_raw_frame: np.ndarray | None = None  # latest raw BGR from active worker

        # Blink timer for REC dot
        self._blink = False
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.start(500)

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+R"), self, self.start_recording)
        QShortcut(QKeySequence("Ctrl+P"), self, self.pause_recording)
        QShortcut(QKeySequence("Ctrl+M"), self, self.resume_recording)
        QShortcut(QKeySequence("Ctrl+S"), self, self.stop_recording)

    # ---------- Streams ----------
    def set_streams(self, urls: List[str] | Dict[str, str]):
        """Accepts a list of RTSP URLs or a dict {name: url}."""
        # Stop and clear existing
        self._stop_all_workers()

        self.stream_urls.clear()
        self.stream_names.clear()
        self.workers.clear()

        if isinstance(urls, dict):
            items = list(urls.items())
            for i, (name, url) in enumerate(items):
                self.stream_urls[i] = url
                self.stream_names[i] = name
        else:
            for i, url in enumerate(urls):
                self.stream_urls[i] = url
                self.stream_names[i] = self._infer_name(url)

        # Create workers
        for sid, url in self.stream_urls.items():
            w = VideoWorker(sid, url, self)
            w.frame_ready.connect(self._on_frame)
            w.status.connect(self._on_status)
            w.error.connect(self._on_error)
            self.workers[sid] = w
            w.start()

        # Build buttons & grid
        self._rebuild_stream_buttons()
        self._rebuild_grid()

        # Pick active 0 by default
        if self.stream_urls:
            self.set_active_stream(0)

    def _infer_name(self, rtsp_url: str) -> str:
        # Try extracting the last significant path segment
        parts = [p for p in rtsp_url.split('/') if p and not p.startswith("rtsp")]
        if parts:
            tail = parts[-1].split('?')[0]
            return tail[:16]
        return "Camera"

    def _rebuild_stream_buttons(self):
        # Clear
        while self.buttons_bar.count():
            item = self.buttons_bar.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        # Build
        for sid in sorted(self.stream_urls.keys()):
            btn = QPushButton(self.stream_names.get(sid, f"Cam {sid}"))
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, s=sid: self.set_active_stream(s))
            btn.setMinimumWidth(90)
            self.buttons_bar.addWidget(btn)

        self._refresh_button_checks()

    def _refresh_button_checks(self):
        # Apply checked state to match active_stream_id
        idx = 0
        for i in range(self.buttons_bar.count()):
            w = self.buttons_bar.itemAt(i).widget()
            if isinstance(w, QPushButton):
                sid = sorted(self.stream_urls.keys())[idx]
                w.setChecked(sid == self.active_stream_id)
                idx += 1

    def _rebuild_grid(self):
        ids = sorted(self.stream_urls.keys())
        self.grid_widget.set_streams(ids, self.stream_names)
        self.grid_widget.set_click_handler(self._on_grid_click)

    def _on_grid_click(self, stream_id: int):
        self.set_active_stream(stream_id)
        # switch to single view
        if self.view_btn.isChecked():
            self.view_btn.setChecked(False)
            self._toggle_view(False)

    def _toggle_view(self, checked: bool):
        self.stack.setCurrentIndex(1 if checked else 0)
        self.view_btn.setText("Single View" if checked else "Grid View")

    def set_active_stream(self, stream_id: int):
        if stream_id not in self.stream_urls:
            return
        self.active_stream_id = stream_id
        self._refresh_button_checks()

    def get_video_widget(self):
        return self  # Fixed: Return self since we're now a QWidget

    # ---------- Frame handling ----------
    def _on_frame(self, stream_id: int, frame_bgr: np.ndarray):
        # Grid preview (always)
        if self.stack.currentIndex() == 1:
            self.grid_widget.update_frame(stream_id, frame_bgr)

        # Single preview (only active)
        if stream_id == self.active_stream_id:
            # keep raw for recording
            self._last_raw_frame = frame_bgr

            # Build preview pixmap
            try:
                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                pix = QPixmap.fromImage(qimg)

                # Draw overlays only on preview
                if self._recording:
                    pix = self._draw_overlay(pix)

                self.single_label.setPixmap(
                    pix.scaled(self.single_label.width(), self.single_label.height(),
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            except Exception as e:
                self._on_error(stream_id, f"Preview error: {e}")

            # Write to file if recording & not paused (write raw frame)
            if self._recording and not self._paused and self._writer is not None:
                try:
                    self._writer.write(self._last_raw_frame)
                except Exception as e:
                    self._on_error(stream_id, f"Write error: {e}")

    def _draw_overlay(self, pix: QPixmap) -> QPixmap:
        # Renders right-aligned REC/PAUSE indicators. No Unicode symbols; draw shapes.
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(QFont("Arial", 18, QFont.Bold))

        margin = 14
        text = "PAUSE" if self._paused else "REC"
        metrics = p.fontMetrics()
        tw = metrics.horizontalAdvance(text)
        th = metrics.height()

        x = pix.width() - tw - margin - 26  # room for icon
        y = th + margin // 2

        # Text
        p.setPen(Qt.white)
        p.drawText(x, y, text)

        # Icon
        if self._paused:
            # Yellow pause icon (two bars)
            p.setPen(Qt.NoPen)
            p.setBrush(Qt.yellow)
            bx = x - 26
            by = y - th + 4
            bar_w, bar_h, gap = 6, th - 6, 6
            p.drawRect(bx, by, bar_w, bar_h)
            p.drawRect(bx + bar_w + gap, by, bar_w, bar_h)
        else:
            # Blinking red dot
            p.setPen(Qt.NoPen)
            p.setBrush(Qt.red if self._blink else Qt.transparent)
            cx = x - 16
            cy = y - th // 2 + 3
            p.drawEllipse(cx, cy, 12, 12)

        p.end()
        return pix

    def _toggle_blink(self):
        self._blink = not self._blink

    def _on_status(self, stream_id: int, ok: bool, msg: str):
        if not ok and stream_id == self.active_stream_id:
            self.single_label.setText(f"[{self.stream_names.get(stream_id, stream_id)}] {msg}")

    def _on_error(self, stream_id: int, msg: str):
        print(f"[{stream_id}] {msg}")
        if stream_id == self.active_stream_id:
            self.single_label.setText(msg)

    def set_stream_buttons(self, stream_urls):
        """Public method to replace stream list and rebuild buttons"""
        self.available_streams = stream_urls
        self._rebuild_stream_buttons()

    # ---------- Recording ----------
    def _ensure_save_base(self) -> bool:
        if not self._rec_base_dir or not self._rec_base_name:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Recording As",
                f"recording_{time.strftime('%Y%m%d_%H%M%S')}.mp4",
                "MP4 Files (*.mp4);;AVI Files (*.avi)"
            )
            if not filename:
                return False
            base_dir = os.path.dirname(filename)
            base, ext = os.path.splitext(os.path.basename(filename))
            if not ext:
                ext = ".mp4"
            self._rec_base_dir = base_dir
            self._rec_base_name = base
            self._rec_ext = ext
            self._rec_index = 0
        return True

    def _next_filename(self) -> str:
        self._rec_index += 1
        return os.path.join(
            self._rec_base_dir, f"{self._rec_base_name}_{self._rec_index}{self._rec_ext}"
        )

    def start_recording(self):
        if self._recording:
            return
        if self.active_stream_id is None:
            self.single_label.setText("No active stream to record.")
            return
        if not self._ensure_save_base():
            return
        # We’ll create writer on first valid frame (when _last_raw_frame is ready)
        # but often we already have one.
        if self._last_raw_frame is None:
            # Try waiting a tick for a frame
            QApplication.processEvents()

        filename = self._next_filename()
        # Determine frame size safely
        if self._last_raw_frame is not None:
            h, w = self._last_raw_frame.shape[:2]
            size = (w, h)
        else:
            # fallback (will likely fix itself next frame)
            size = (1280, 720)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v") if self._rec_ext.lower() == ".mp4" else cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(filename, fourcc, self._fps, size)
        if not writer.isOpened():
            self.single_label.setText("Failed to open writer.")
            return

        self._writer = writer
        self._recording = True
        self._paused = False
        self.single_label.setToolTip(f"Recording to {filename}")

    def pause_recording(self):
        if self._recording:
            self._paused = True

    def resume_recording(self):
        if self._recording and self._paused:
            self._paused = False

    def stop_recording(self):
        if not self._recording:
            return
        try:
            if self._writer:
                self._writer.release()
        finally:
            self._writer = None
            self._recording = False
            self._paused = False
            self.single_label.setToolTip("")

    # ---------- Cleanup ----------
    def _stop_all_workers(self):
        for w in list(self.workers.values()):
            try:
                w.stop()
            except Exception:
                pass
        self.workers.clear()

    def closeEvent(self, ev):
        self.stop_recording()
        self._stop_all_workers()
        return super().closeEvent(ev)