"""Stylesheet của cửa sổ chính: chủ đề sáng/tối, màu nhấn và cỡ chữ."""

THEMES = ("light", "dark")
DEFAULT_ACCENT = "#d61718"
ACCENT_HOVER = {"#d61718": "#b51515", "#2864c5": "#1f4fa8", "#168578": "#106b60"}
PALETTES = {
    "light": {
        "bg": "#f3f5f8", "surface": "#ffffff", "text": "#202633",
        "muted": "#687386", "border": "#dce2ea", "alternate": "#f5f7fa",
        "selected_row": "#e2e6eb", "hover_row": "#f0f2f4",
    },
    "dark": {
        "bg": "#171a21", "surface": "#222733", "text": "#edf0f6",
        "muted": "#aab3c2", "border": "#394252", "alternate": "#1d222c",
        "selected_row": "#39414d", "hover_row": "#2b313c",
    },
}


def normalize_appearance(theme, accent):
    """Chặn giá trị lạ (cấu hình cũ hoặc sửa tay) về bộ choices hợp lệ."""
    if theme not in THEMES:
        theme = "light"
    if accent not in ACCENT_HOVER:
        accent = DEFAULT_ACCENT
    return theme, accent


def read_appearance(settings):
    """Bốn thuộc tính giao diện đang lưu trong SettingsStore."""
    theme, accent = normalize_appearance(settings.get("theme", "light"),
                                        settings.get("accent", DEFAULT_ACCENT))
    return {"theme": theme, "accent": accent,
            "font_size": settings.get_int("font_size", 9),
            "compact": settings.get_bool("compact", False)}


def build_stylesheet(theme="light", accent="#d61718", font_size=9, compact=False):
    """
    QSS cho toàn cửa sổ.

    Widget tĩnh vẫn định kiểu theo objectName; chỉ có nền/chữ/màu nhấn đổi theo chủ đề.
    """
    theme, accent = normalize_appearance(theme, accent)
    palette = PALETTES[theme]
    accent_hover = ACCENT_HOVER[accent]
    row_padding = 4 if compact else 9
    bg = palette["bg"]
    surface = palette["surface"]
    text = palette["text"]
    muted = palette["muted"]
    border = palette["border"]
    alternate = palette["alternate"]
    selected_row = palette["selected_row"]
    hover_row = palette["hover_row"]
    return f"""
        QMainWindow, QWidget {{ background: {bg}; color: {text}; font-size: {font_size}pt; }}
        QToolBar {{ background: {surface}; border: 0; padding: 10px; spacing: 8px; }}
        QTabWidget::pane {{ background: {bg}; border: 0; }}
        QTabBar::tab {{ background: {surface}; color: {muted}; padding: 10px 18px; margin-right: 4px; border: 1px solid {border}; border-bottom: 0; border-top-left-radius: 7px; border-top-right-radius: 7px; }}
        QTabBar::tab:selected {{ color: {accent}; font-weight: 700; background: {bg}; }}
        QFrame {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
        QFrame#statCard {{ background: {alternate}; }}
        QLabel#statCaption {{ background: transparent; color: {muted}; font-size: 8pt; font-weight: 600; }}
        QLabel#statValueTotal, QLabel#statValueActive, QLabel#statValueInactive, QLabel#statValueUnchecked {{ background: transparent; font-size: 16pt; font-weight: 800; }}
        QLabel#statValueTotal {{ color: {accent}; }}
        QLabel#statValueActive {{ color: #28a745; }}
        QLabel#statValueInactive {{ color: #dc3545; }}
        QLabel#statValueUnchecked {{ color: {muted}; }}
        QLabel#emptyState {{ background: transparent; color: {muted}; font-size: 12pt; font-weight: 600; padding: 24px; }}
        QLabel#inputPreview {{ background: transparent; color: {muted}; font-size: 9pt; font-weight: 600; }}
        QLabel#statsChip {{ background: transparent; color: {muted}; font-size: 10pt; }}
        QPushButton {{ background: #b8fff5; color: #102322; border: 1px solid #3ff2d7; padding: 8px 13px; border-radius: 6px; font-weight: 600; }}
        QPushButton:hover {{ background: #93f7e9; border-color: #20ccb7; color: #102322; }}
        QPushButton:pressed {{ background: #72ead8; }}
        QPushButton#actionAdd, QPushButton#actionClear, QPushButton#actionCheck, QPushButton#actionExport, QPushButton#actionImport {{ padding: 6px 12px; border-radius: 6px; font-weight: 700; border: none; color: white; }}
        QPushButton#actionAdd {{ background: #d61718; }}
        QPushButton#actionAdd:hover {{ background: #b51515; }}
        QPushButton#actionImport {{ background: #4a90d9; }}
        QPushButton#actionImport:hover {{ background: #3a7bc8; }}
        QPushButton#actionClear {{ background: #6c757d; }}
        QPushButton#actionClear:hover {{ background: #5a6268; }}
        QPushButton#actionCheck {{ background: #28a745; }}
        QPushButton#actionCheck:hover {{ background: #218838; }}
        QPushButton#actionExport {{ background: #2864c5; }}
        QPushButton#actionExport:hover {{ background: #1f4fa8; }}
        QPushButton#toolInput, QPushButton#toolCheckAll, QPushButton#toolDelete {{ color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 700; }}
        QPushButton#toolInput {{ background: {accent}; }}
        QPushButton#toolInput:hover {{ background: {accent_hover}; }}
        QPushButton#toolCheckAll {{ background: #28a745; }}
        QPushButton#toolCheckAll:hover {{ background: #218838; }}
        QPushButton#toolDelete {{ background: #dc3545; }}
        QPushButton#toolDelete:hover {{ background: #c82333; }}
        QLineEdit, QTextEdit, QComboBox {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 6px; padding: 7px; selection-background-color: {accent}; }}
        QTextEdit#activityLog {{ font-size: 8pt; }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{ border: 2px solid {accent}; }}
        QTableWidget {{ background: {surface}; alternate-background-color: {alternate}; color: {text}; gridline-color: {border}; border: 1px solid {border}; outline: none; selection-background-color: {selected_row}; selection-color: {text}; }}
        QHeaderView::section {{ background: {alternate}; color: {text}; padding: {row_padding}px; border: 0; border-bottom: 2px solid {border}; font-weight: 700; }}
        QTableWidget::item {{ padding: {row_padding}px; border-bottom: 1px solid {border}; }}
        QTableWidget::item:selected, QTableWidget::item:selected:hover {{ background: {selected_row}; color: {text}; border: 0; }}
        QTableWidget::item:hover {{ background: {hover_row}; color: {text}; }}
        QTableWidget::item:focus {{ outline: none; border: 0; }}
        QGroupBox {{ border: 1px solid {border}; border-radius: 7px; margin-top: 12px; padding: 12px 8px 8px; font-weight: 600; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
        QStatusBar {{ background: {surface}; color: {muted}; border-top: 1px solid {border}; }}
        QProgressBar {{ background: {alternate}; border: 0; border-radius: 5px; text-align: center; }}
        QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
        QMenu {{ background: {surface}; color: {text}; border: 1px solid {border}; }}
        QMenu::item:selected {{ background: {accent}; color: white; }}
    """
