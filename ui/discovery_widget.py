import socket
import time
import threading
import queue
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QProgressBar,
    QLabel, QTreeWidget, QTreeWidgetItem, QSplitter, QTextEdit, QMenu, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont


SEARCH_PACKET = b'>SEARCH_OCTAGON\r\n'
TRANSMITTING_DISCOVERY_PORT = 54529
RECEIVING_DISCOVERY_PORT = 54528
DISCOVERY_PORT = 8888
RECV_BUFFER = 1024
RECV_TIMEOUT = 0.1
RANGE_TIMEOUT = 5
BROADCAST_TIMEOUT = 5


class DiscoveryWorker(QThread):
    result_found = Signal(dict)
    progress_updated = Signal(int, str)
    finished = Signal()

    def __init__(self, stop_event: threading.Event):
        super().__init__()
        self.stop_event = stop_event

    def run(self):
        """Perform broadcast discovery"""
        hosts = self.get_hosts()
        total_hosts = len(hosts)
        TOTAL_TIMEOUT = RANGE_TIMEOUT + BROADCAST_TIMEOUT * total_hosts
        start_time = time.time()
        address = []

        for i, host in enumerate(hosts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.bind((host, RECEIVING_DISCOVERY_PORT))
                    sock.settimeout(RECV_TIMEOUT)
                    sock.sendto(SEARCH_PACKET, ('<broadcast>', TRANSMITTING_DISCOVERY_PORT))

                    host_start_time = time.time()
                    while not self.stop_event.is_set():
                        elapsed_time = time.time() - host_start_time

                        progress = int(((i + elapsed_time / BROADCAST_TIMEOUT) / total_hosts) * 100)
                        progress = min(progress, 100)
                        self.progress_updated.emit(progress, f"Scanning ({progress}%) ...")

                        if elapsed_time >= BROADCAST_TIMEOUT:
                            break

                        try:
                            data, addr = sock.recvfrom(RECV_BUFFER)
                            tokens = data.decode().lstrip('<').rstrip('\r\n').split('|')
                            response = dict(
                                host=addr[0],
                                hardware=tokens[0],
                                uptime=tokens[1],
                                model=tokens[2],
                                projectCode=tokens[3],
                                systemSerial=tokens[4],
                                boardSerial=tokens[5],
                                octagonService=self.service_code_to_string(tokens[6]),
                                webpanelService=self.service_code_to_string(tokens[7]),
                                bridgeService=self.service_code_to_string(tokens[8]),
                                nginxService=self.service_code_to_string(tokens[9]),
                                octagonVersion=tokens[10],
                                webpanelVersion=tokens[11],
                                apiVersion=tokens[12],
                                bridgeVersion=tokens[13],
                            )
                            self.result_found.emit(response)
                            address.append(addr)
                        except socket.timeout:
                            continue
            except Exception as e:
                print(f"Error during scan: {e}")

        self.progress_updated.emit(100, "Scan complete")
        self.finished.emit()

    def get_hosts(self):
        interfaces = socket.getaddrinfo(host=socket.gethostname(), port=None, family=socket.AF_INET)
        return [ip[-1][0] for ip in interfaces]

    def service_code_to_string(self, service_code):
        if not service_code:
            return ''
        active_state = 'ACTIVE' if service_code[0] == 'Y' else 'INACTIVE'
        service_state = 'ENABLED' if service_code[1] == 'E' else 'DISABLED'
        return f"{active_state}"

class DiscoveryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Network Discovery")
        self.stop_event = threading.Event()
        self.worker = None
        self.parent = parent

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Buttons + progress
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.start_btn = QPushButton("🔍 Scan")
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(12)

        self.status_label = QLabel("Ready")

        top_bar.addWidget(self.start_btn)
        top_bar.addWidget(self.stop_btn)
        top_bar.addWidget(self.progress, stretch=1)
        top_bar.addWidget(self.status_label)

        layout.addLayout(top_bar)

        # --- Splitter ---
        splitter = QSplitter(Qt.Vertical)

        # Tree (summary table)
        self.table = QTreeWidget()
        self.table.setColumnCount(3)
        self.table.setHeaderLabels(["IP Address", "Project", "Serial"])
        self.table.setAlternatingRowColors(True)
        self.table.setRootIsDecorated(False)
        self.table.header().setStretchLastSection(True)
        self.table.header().setDefaultSectionSize(120)
        splitter.addWidget(self.table)

        # Details Panel (monospaced)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setFont(QFont("Courier", 10))
        self.details.setStyleSheet("background-color: #f5f5f5;")
        splitter.addWidget(self.details)
        splitter.setSizes([300, 200])  # default size ratio

        layout.addWidget(splitter)

        # --- Connections ---
        self.start_btn.clicked.connect(self.start_scan)
        self.stop_btn.clicked.connect(self.stop_scan)
        self.table.itemDoubleClicked.connect(self.show_details)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

    def start_scan(self):
        self.table.clear()
        self.details.clear()
        self.stop_event.clear()
        self.worker = DiscoveryWorker(self.stop_event)
        self.worker.result_found.connect(self.add_result)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.finished.connect(self.scan_finished)
        self.worker.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("Scanning...")

    def stop_scan(self):
        self.stop_event.set()
        self.status_label.setText("Stopping...")
        self.stop_btn.setEnabled(False)

    def scan_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Finished")

    def update_progress(self, value, text):
        self.progress.setValue(value)
        self.status_label.setText(text)

    def add_result(self, response):
        item = QTreeWidgetItem([
            response.get("host", ""),
            response.get("projectCode", ""),
            response.get("systemSerial", ""),
            response.get("model", ""),
            response.get("uptime", ""),
            response.get("hardware", ""),
            response.get("boardSerial", ""),
            response.get("octagonService", ""),
            response.get("webpanelService", ""),
            response.get("bridgeService", ""),
            response.get("nginxService", ""),
            response.get("octagonVersion", ""),
            response.get("webpanelVersion", ""),
            response.get("apiVersion", ""),
            response.get("bridgeVersion", ""),
        ])
        item.setData(0, Qt.UserRole, response)  # store full dict
        self.table.addTopLevelItem(item)

    def show_details(self, item):
        response = item.data(0, Qt.UserRole)
        response = {key: value for key, value in response.items() if value}
        if not response:
            return
        text = "\n".join(f"{k}: {v}" for k, v in response.items())
        self.details.setText(text)

    def show_context_menu(self, position):
        item = self.table.itemAt(position)
        if not item:
            return

        menu = QMenu()
        connect_action = menu.addAction("Connect")
        action = menu.exec_(self.table.viewport().mapToGlobal(position))

        if action == connect_action:
            # OctagonService is column index 7 (0-based)
            services = item.data(0, Qt.UserRole) or {}
            octagon_status = services.get("octagonService", "")

            if octagon_status.strip().lower() == "active":
                # Call parent connect_to_device with the host (column 0)
                if hasattr(self.parent, "connect_to_device"):
                    self.parent.connect_to_device(item)
            else:
                QMessageBox.warning(
                    self,
                    "Connection not allowed",
                    "OctagonService must be Active to connect."
                )
