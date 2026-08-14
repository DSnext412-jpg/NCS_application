"""Sidebar navigation for the main window.

Modern navy sidebar with brand header, section labels, icon + label nav
buttons and a reception/front-desk status footer. Admin items remain
password protected by the main window.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import APP_NAME
from app.core.paths import Paths

MAIN_ITEMS: tuple[tuple[str, str], ...] = (
    ("dashboard", "Dashboard"),
    ("rooms", "Rooms"),
    ("guests", "Guests"),
    ("bookings", "Bookings"),
    ("check_in", "Check-in"),
    ("check_out", "Check-out"),
    ("payments", "Payments"),
    ("invoices", "Invoices"),
)

ADMIN_ITEMS: tuple[tuple[str, str], ...] = (
    ("admin", "Admin Dashboard"),
    ("reports", "Reports"),
    ("settings", "Settings"),
    ("audit", "Audit Log"),
    ("backup", "Backup & Restore"),
)

NAV_ICONS: dict[str, str] = {
    "dashboard": "🏠",
    "rooms": "🛏️",
    "guests": "👤",
    "bookings": "📅",
    "check_in": "📥",
    "check_out": "📤",
    "payments": "💳",
    "invoices": "🧾",
    "admin": "🛡️",
    "reports": "📊",
    "settings": "⚙️",
    "audit": "📋",
    "backup": "💾",
}


class Sidebar(QWidget):
    navigation_requested = Signal(str)
    logout_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(238)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- scrollable content (brand + nav) ------------------------------
        scroll = QScrollArea()
        scroll.setObjectName("SidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        content.setObjectName("SidebarScrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # --- brand -------------------------------------------------------
        brand_box = QVBoxLayout()
        brand_box.setContentsMargins(18, 20, 18, 12)
        brand_box.setSpacing(2)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        brand_logo = QLabel()
        brand_logo.setObjectName("SidebarBrandLogo")
        brand_logo.setPixmap(self._hotel_logo_pixmap(40))
        brand_logo.setFixedSize(40, 40)
        brand_row.addWidget(brand_logo, 0, Qt.AlignmentFlag.AlignTop)
        brand_text = QLabel(APP_NAME)
        brand_text.setObjectName("SidebarBrand")
        brand_text.setWordWrap(True)
        brand_text.setMinimumWidth(0)
        brand_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        brand_row.addWidget(brand_text, 1)
        brand_box.addLayout(brand_row)
        brand_sub = QLabel("Hotel Management System")
        brand_sub.setObjectName("SidebarBrandSub")
        brand_sub.setWordWrap(True)
        brand_box.addWidget(brand_sub)
        content_layout.addLayout(brand_box)

        # --- MAIN section ------------------------------------------------
        content_layout.addWidget(self._section_label("MAIN"))
        self.main_group = QButtonGroup(self)
        self.main_group.setExclusive(True)
        for key, label in MAIN_ITEMS:
            button = self._make_button(key, label)
            self.main_group.addButton(button)
            content_layout.addWidget(button)

        # --- ADMIN section -----------------------------------------------
        content_layout.addWidget(self._section_label("ADMIN"))
        self.admin_group = QButtonGroup(self)
        self.admin_group.setExclusive(True)
        for key, label in ADMIN_ITEMS:
            button = self._make_button(key, label)
            self.admin_group.addButton(button)
            content_layout.addWidget(button)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # --- footer: reception status + logout ----------------------------
        footer = QWidget()
        footer.setObjectName("SidebarFooter")
        footer_box = QVBoxLayout(footer)
        footer_box.setContentsMargins(12, 10, 12, 10)
        footer_box.setSpacing(6)

        role_row = QHBoxLayout()
        role_row.setSpacing(8)
        dot = QLabel()
        dot.setProperty("sidebarDot", True)
        role_row.addWidget(dot)
        role = QLabel("Reception · Front Desk")
        role.setProperty("sidebarRole", True)
        role_row.addWidget(role)
        role_row.addStretch(1)
        footer_box.addLayout(role_row)

        status = QLabel("Online")
        status.setProperty("sidebarStatus", True)
        footer_box.addWidget(status)

        self.logout_button = QPushButton("Logout")
        self.logout_button.setObjectName("SidebarLogout")
        self.logout_button.setEnabled(False)
        self.logout_button.clicked.connect(self.logout_requested)
        footer_box.addWidget(self.logout_button)

        layout.addWidget(footer, 0, Qt.AlignmentFlag.AlignBottom)

        self._buttons: dict[str, QPushButton] = {}
        for key, _label in MAIN_ITEMS + ADMIN_ITEMS:
            self._buttons[key] = self._find_button(key)

    def _hotel_logo_pixmap(self, size: int) -> QPixmap:
        """Render the bundled monochrome hotel logo into a pixmap."""
        svg_path = Paths().source_assets_dir / "icons" / "hotel.svg"
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        if svg_path.exists():
            renderer = QSvgRenderer(str(svg_path))
            renderer.render(QPainter(pixmap))
        return pixmap

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("sidebarSection", True)
        return label

    def _make_button(self, key: str, label: str) -> QPushButton:
        button = QPushButton(f"{NAV_ICONS.get(key, '•')}   {label}")
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setProperty("navKey", key)
        button.clicked.connect(lambda checked=False, k=key: self.navigation_requested.emit(k))
        return button

    def _find_button(self, key: str) -> QPushButton:
        for group in (self.main_group, self.admin_group):
            for button in group.buttons():
                if button.property("navKey") == key:
                    return button
        raise KeyError(key)

    def select(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is None:
            return
        for group in (self.main_group, self.admin_group):
            for other in group.buttons():
                other.setChecked(other is button)

    def set_logged_in(self, logged_in: bool) -> None:
        self.logout_button.setEnabled(logged_in)
        self.logout_button.setText("Logout" if logged_in else "Login required")