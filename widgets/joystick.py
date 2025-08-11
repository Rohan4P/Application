from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QLinearGradient


class JoystickWidget(QWidget):
    position_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(150, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.center = QPointF(0, 0)
        self.handle_position = QPointF(0, 0)
        self.mouse_down = False
        self.setFocusPolicy(Qt.StrongFocus)

    def resizeEvent(self, event):
        self.center = QPointF(self.width() / 2, self.height() / 2)
        self.handle_position = self.center
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        base_radius = min(self.width(), self.height()) * 0.40
        handle_radius = base_radius * 0.35

        # Draw base circle
        base_gradient = QLinearGradient(
            self.center.x() - base_radius,
            self.center.y() - base_radius,
            self.center.x() + base_radius,
            self.center.y() + base_radius
        )
        base_gradient.setColorAt(0, QColor(60, 60, 60))
        base_gradient.setColorAt(1, QColor(30, 30, 30))

        painter.setPen(QPen(QColor(80, 80, 80), 2))
        painter.setBrush(QBrush(base_gradient))
        painter.drawEllipse(self.center, base_radius, base_radius)

        # Draw outer ring
        painter.setPen(QPen(QColor(100, 100, 100, 180), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(self.center, base_radius * 0.75, base_radius * 0.75)
        painter.drawEllipse(self.center, base_radius * 0.55, base_radius * 0.55)

        # Draw crosshairs
        painter.setPen(QPen(QColor(120, 120, 120, 120), 1))
        painter.drawLine(
            QPointF(self.center.x() - base_radius, self.center.y()),
            QPointF(self.center.x() + base_radius, self.center.y())
        )
        painter.drawLine(
            QPointF(self.center.x(), self.center.y() - base_radius),
            QPointF(self.center.x(), self.center.y() + base_radius)
        )

        # Draw cardinal points
        painter.setPen(QPen(QColor(200, 200, 200, 150), 1))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        # North
        painter.drawText(
            QRectF(self.center.x() - 10, self.center.y() - base_radius - 20, 20, 20),
            Qt.AlignCenter,
            "N"
        )

        # East
        painter.drawText(
            QRectF(self.center.x() + base_radius + 5, self.center.y() - 10, 20, 20),
            Qt.AlignCenter,
            "E"
        )

        # South
        painter.drawText(
            QRectF(self.center.x() - 10, self.center.y() + base_radius + 5, 20, 20),
            Qt.AlignCenter,
            "S"
        )

        # West
        painter.drawText(
            QRectF(self.center.x() - base_radius - 20, self.center.y() - 10, 20, 20),
            Qt.AlignCenter,
            "W"
        )

        # Draw handle with gradient
        handle_gradient = QLinearGradient(
            self.handle_position.x() - handle_radius,
            self.handle_position.y() - handle_radius,
            self.handle_position.x() + handle_radius,
            self.handle_position.y() + handle_radius
        )
        handle_gradient.setColorAt(0, QColor(70, 130, 180))  # Steel blue
        handle_gradient.setColorAt(1, QColor(30, 80, 120))

        painter.setPen(QPen(QColor(100, 160, 220), 2))
        painter.setBrush(QBrush(handle_gradient))
        painter.drawEllipse(self.handle_position, handle_radius, handle_radius)

        # Draw handle highlight
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 60))
        painter.drawEllipse(
            QPointF(self.handle_position.x() - handle_radius * 0.25,
                    self.handle_position.y() - handle_radius * 0.25),
            handle_radius * 0.35,
            handle_radius * 0.35
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.mouse_down = True
            self.update_handle_position(event.position())
            self.update()

    def mouseMoveEvent(self, event):
        if self.mouse_down:
            self.update_handle_position(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.mouse_down = False
            # Reset to center
            self.handle_position = self.center
            self.position_changed.emit(0, 0)
            self.update()

    def update_handle_position(self, pos):
        # Calculate vector from center
        dx = pos.x() - self.center.x()
        dy = pos.y() - self.center.y()

        # Calculate distance from center
        distance = (dx ** 2 + dy ** 2) ** 0.5

        # Limit to base circle
        max_distance = min(self.width(), self.height()) * 0.45 - 10

        if distance > max_distance:
            dx = dx * max_distance / distance
            dy = dy * max_distance / distance

        # Update handle position
        self.handle_position = QPointF(self.center.x() + dx, self.center.y() + dy)

        # Emit normalized position (-1 to 1)
        normalized_x = dx / max_distance
        normalized_y = dy / max_distance
        self.position_changed.emit(normalized_x, normalized_y)

    def keyPressEvent(self, event):
        # Allow keyboard control of joystick
        step = 0.8  # 30% movement
        up, down, left, right = False, False, False, False
        if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            if event.key() == Qt.Key_Up:
                up = True
            elif event.key() == Qt.Key_Down:
                down = True
            elif event.key() == Qt.Key_Left:
                left = True
            elif event.key() == Qt.Key_Right:
                right = True
            self.position_changed.emit((right - left) * step, (up - down) * step)
        # if event.key() == Qt.Key_Up:
        #     self.position_changed.emit(0, -step)
        # elif event.key() == Qt.Key_Down:
        #     self.position_changed.emit(0, step)
        # elif event.key() == Qt.Key_Left:
        #     self.position_changed.emit(-step, 0)
        # elif event.key() == Qt.Key_Right:
        #     self.position_changed.emit(step, 0)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # Reset on key release for arrow keys
        if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            self.position_changed.emit(0, 0)
        else:
            super().keyReleaseEvent(event)