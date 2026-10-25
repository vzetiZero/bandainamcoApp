"""Delegate vẽ cột Status thành badge bo tròn."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
)

from app.ui.table_spec import PROGRESS_ROLE


STATUS_BADGE_COLORS = {
    "Hoạt động": "#28a745",
    "Không hoạt động": "#dc3545",
    "Chưa kiểm tra": "#8a94a6",
}

DEFAULT_PROGRESS_ACCENT = "#d61718"


class EmailProgressDelegate(QStyledItemDelegate):
    """
    Tô nền ô Email theo % đang xử lý của chính tài khoản đó và ghi % ở góc phải.

    Nhiều tài khoản chạy đồng thời nên thanh progress chung không nói được gì;
    mỗi dòng tự cho biết tài khoản của nó tới đâu.
    """

    def __init__(self, parent=None, accent=DEFAULT_PROGRESS_ACCENT):
        super().__init__(parent)
        self._accent = QColor(accent)

    def set_accent(self, color):
        """Theo màu nhấn của chủ đề đang chọn (sáng/tối)."""
        self._accent = QColor(color)

    def paint(self, painter, option, index):
        percent = index.data(PROGRESS_ROLE) or 0
        if not percent:
            super().paint(painter, option, index)
            return
        percent = max(1, min(100, int(percent)))

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        widget = option.widget
        style = widget.style() if widget else QApplication.style()
        # Vẽ nền (kể cả nền khi đang chọn) trước, rồi mới phủ bar lên trên.
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cell = opt.rect.adjusted(3, 3, -3, -3)
        fill = QRectF(cell)
        fill.setWidth(cell.width() * percent / 100)
        tint = QColor(self._accent)
        tint.setAlpha(90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tint))
        painter.drawRoundedRect(fill, 4, 4)

        painter.setFont(opt.font)
        label = f"{percent}%"
        label_width = painter.fontMetrics().horizontalAdvance(label) + 6
        palette = opt.palette
        text_color = palette.color(palette.currentColorGroup(), QPalette.ColorRole.Text)
        painter.setPen(QPen(text_color))
        text_rect = cell.adjusted(4, 0, -(label_width + 4), 0)
        shown = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight,
                                                 int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, shown)
        painter.setPen(QPen(self._accent.darker(120)))
        painter.drawText(cell, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, label)
        painter.restore()

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
