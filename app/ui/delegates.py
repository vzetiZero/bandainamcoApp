"""Delegate vẽ cột Status thành badge bo tròn."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
)


STATUS_BADGE_COLORS = {
    "Hoạt động": "#28a745",
    "Không hoạt động": "#dc3545",
    "Chưa kiểm tra": "#8a94a6",
}

class StatusDelegate(QStyledItemDelegate):
    """Vẽ cột Status thành badge bo tròn thay vì chữ tô màu."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem()
        self.initStyleOption(opt, index)
        text = opt.text
        color = STATUS_BADGE_COLORS.get(text)
        if color is None:
            super().paint(painter, option, index)
            return
        opt.text = ""
        widget = option.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(option.font)
        width = painter.fontMetrics().horizontalAdvance(text) + 18
        height = min(option.rect.height() - 8, 22)
        rect = QRectF(option.rect.center().x() - width / 2,
                      option.rect.center().y() - height / 2, width, height)
        tint = QColor(color)
        tint.setAlpha(40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tint))
        painter.drawRoundedRect(rect, height / 2, height / 2)
        painter.setPen(QPen(QColor(color)))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
