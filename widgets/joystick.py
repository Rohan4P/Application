from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush, QPen
import math


class JoystickWidget(QWidget):
    position_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.center = QPointF(0, 0)
        self.handle_position = QPointF(0, 0)
        self.mouse_down = False
        self.setFocusPolicy(Qt.StrongFocus)

        self.base_radius = 0
        self.handle_radius = 0
        self.current_direction = None

    def resizeEvent(self, event):
        self.center = QPointF(self.width() / 2, self.height() / 2)
        self.base_radius = min(self.width(), self.height()) * 0.30
        self.handle_radius = self.base_radius * 0.35
        self.handle_position = self.center
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # --- Draw base circle ---
        painter.setPen(QPen(QColor(80, 80, 80), 2))
        painter.setBrush(QBrush(QColor(50, 50, 50)))
        painter.drawEllipse(self.center, self.base_radius, self.base_radius)

        # --- Draw 8 wedge buttons around ---
        directions = [
            ("up", -90),
            ("up_right", -45),
            ("right", 0),
            ("down_right", 45),
            ("down", 90),
            ("down_left", 135),
            ("left", 180),
            ("up_left", -135),
        ]

        button_outer = self.base_radius * 1.35
        self.button_inner = self.base_radius * 1.05

        for name, angle in directions:
            start_angle = angle - 22.5
            end_angle = angle + 22.5

            path = self.create_sector_path(self.center, self.button_inner, button_outer,
                                           math.radians(start_angle),
                                           math.radians(end_angle))

            if self.current_direction == name:
                painter.setBrush(QColor(100, 180, 255, 200))
            else:
                painter.setBrush(QColor(150, 150, 150, 100))

            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.drawPath(path)

        # --- Draw joystick handle ---
        painter.setPen(QPen(QColor(100, 160, 220), 2))
        painter.setBrush(QBrush(QColor(70, 130, 180)))
        painter.drawEllipse(self.handle_position, self.handle_radius, self.handle_radius)

    # def mousePressEvent(self, event):
    #     if event.button() == Qt.LeftButton:
    #         direction = self.detect_direction_button(event.position())
    #         if direction:
    #             self.current_direction = direction
    #             self.emit_direction(direction)
    #             self.update()
    #         else:
    #             self.mouse_down = True
    #             self.update_handle_position(event.position())
    #             self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            direction = self.detect_direction_button(event.position())
            if direction:
                self.current_direction = direction
                self.emit_direction(direction)

                # Optional: snap handle slightly toward wedge (visual feedback)
                snap_distance = self.button_inner * 0.7  # inside edge
                angle_map = {
                    "up": -90, "up_right": -45, "right": 0, "down_right": 45,
                    "down": 90, "down_left": 135, "left": 180, "up_left": -135
                }
                angle = math.radians(angle_map[direction])
                self.handle_position = QPointF(
                    self.center.x() + snap_distance * math.cos(angle),
                    self.center.y() + snap_distance * math.sin(angle)
                )
                self.update()
            else:
                # Drag joystick
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
            self.current_direction = None
            self.handle_position = self.center
            self.position_changed.emit(0, 0)
            self.update()

    def update_handle_position(self, pos):
        dx = pos.x() - self.center.x()
        dy = pos.y() - self.center.y()
        distance = math.hypot(dx, dy)

        # limit handle travel inside button ring
        self.button_inner = self.base_radius * 1.05
        max_distance = self.button_inner - self.handle_radius

        if distance > max_distance:
            dx = dx * max_distance / distance
            dy = dy * max_distance / distance

        self.handle_position = QPointF(self.center.x() + dx, self.center.y() + dy)
        normalized_x = dx / max_distance
        normalized_y = dy / max_distance
        self.position_changed.emit(normalized_x, normalized_y)

    def detect_direction_button(self, pos):
        dx = pos.x() - self.center.x()
        dy = pos.y() - self.center.y()
        distance = math.hypot(dx, dy)

        if self.base_radius * 1.05 <= distance <= self.base_radius * 1.35:
            angle = math.degrees(math.atan2(dy, dx))
            if angle < -180:
                angle += 360
            if angle > 180:
                angle -= 360

            mapping = {
                "up": (-112.5, -67.5),
                "up_right": (-67.5, -22.5),
                "right": (-22.5, 22.5),
                "down_right": (22.5, 67.5),
                "down": (67.5, 112.5),
                "down_left": (112.5, 157.5),
                "left": (157.5, -157.5),
                "up_left": (-157.5, -112.5),
            }

            for name, (a1, a2) in mapping.items():
                if a1 < a2 and a1 <= angle <= a2:
                    return name
                if a1 > a2 and (angle >= a1 or angle <= a2):
                    return name
        return None

    def emit_direction(self, direction):
        step = 1.0
        mapping = {
            "up": (0, -step),
            "down": (0, step),
            "left": (-step, 0),
            "right": (step, 0),
            "up_left": (-step, -step),
            "up_right": (step, -step),
            "down_left": (-step, step),
            "down_right": (step, step),
        }
        if direction in mapping:
            x, y = mapping[direction]
            self.position_changed.emit(x, y)

    def create_sector_path(self, center, inner_r, outer_r, start_angle, end_angle):
        """Create a wedge (sector ring) between two radii"""
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.moveTo(center.x() + inner_r * math.cos(start_angle),
                    center.y() + inner_r * math.sin(start_angle))
        # inner arc
        path.arcTo(QRectF(center.x() - inner_r, center.y() - inner_r,
                          2 * inner_r, 2 * inner_r),
                   -math.degrees(start_angle), -(math.degrees(end_angle - start_angle)))
        # outer arc
        path.lineTo(center.x() + outer_r * math.cos(end_angle),
                    center.y() + outer_r * math.sin(end_angle))
        path.arcTo(QRectF(center.x() - outer_r, center.y() - outer_r,
                          2 * outer_r, 2 * outer_r),
                   -math.degrees(end_angle), math.degrees(end_angle - start_angle))
        path.closeSubpath()
        return path
