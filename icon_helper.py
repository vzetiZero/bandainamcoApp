"""
SVG Icon Helper for PySide6
Loads Lucide-style SVG icons as QIcon objects
"""
import os
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QSize, Qt


_ICON_CACHE = {}
_ICONS_DIR = os.path.join(os.path.dirname(__file__), "icons")


def load_svg_icon(name: str, size: int = 24, color: str = None) -> QIcon:
    """
    Load an SVG icon from the icons directory.
    
    Args:
        name: Icon filename without .svg extension (e.g., "plus", "trash")
        size: Icon size in pixels (default 24)
        color: Optional color override (CSS color string, e.g., "#d61718", "white")
    
    Returns:
        QIcon object
    """
    cache_key = (name, size, color)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]
    
    svg_path = os.path.join(_ICONS_DIR, f"{name}.svg")
    
    if not os.path.exists(svg_path):
        # Return empty icon if file not found
        return QIcon()
    
    renderer = QSvgRenderer(svg_path)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    
    if color:
        # Apply color tint by rendering to a temporary pixmap first
        temp_pixmap = QPixmap(size, size)
        temp_pixmap.fill(Qt.transparent)
        temp_painter = QPainter(temp_pixmap)
        temp_painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(temp_painter)
        temp_painter.end()
        
        # Apply color tint
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(0, 0, temp_pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(0, 0, size, size, QColor(color))
    else:
        renderer.render(painter)
    
    painter.end()
    
    icon = QIcon(pixmap)
    _ICON_CACHE[cache_key] = icon
    return icon


def get_icon(name: str, size: int = 24) -> QIcon:
    """Convenience function to load icon without color override."""
    return load_svg_icon(name, size)


# Pre-defined icon names for the application
class AppIcons:
    """Application icon constants"""
    PLUS = "plus"
    FOLDER_OPEN = "folder-open"
    CHECK = "check"
    TRASH = "trash"
    EDIT = "edit"
    COPY = "copy"
    DOWNLOAD = "download"
    X = "x"
    SETTINGS = "settings"
    MAIL = "mail"
