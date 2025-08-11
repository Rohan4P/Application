import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from ui.main_window import VMSMainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon("icons/Infiniti.png"))
    window = VMSMainWindow()
    window.show()
    sys.exit(app.exec())
