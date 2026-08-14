"""Shared Qt stylesheets and color definitions.

The design targets a modern, professional hotel-front-desk / PMS
application: a single light theme, consistent design tokens, strong text
contrast, clean white cards on a light background, and status badges that
never rely on color alone.

All colors are centralized here. Widgets reuse object names and dynamic
properties defined by this stylesheet, so pages stay consistent without
duplicating styles.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
COLORS = {
    # Brand
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_pressed": "#1E40AF",
    "navy": "#0F172A",
    "navy_2": "#172554",
    # Surfaces
    "bg": "#F8FAFC",
    "surface": "#FFFFFF",
    "surface_hover": "#F1F5F9",
    "border": "#E2E8F0",
    "border_strong": "#CBD5E1",
    # Text
    "text": "#0F172A",
    "text_secondary": "#64748B",
    "text_muted": "#94A3B8",
    "text_header": "#334155",
    # Semantic
    "success": "#16A34A",
    "warning": "#F59E0B",
    "danger": "#DC2626",
    "info": "#0284C7",
    "purple": "#7C3AED",
    "orange": "#F97316",
    # Sidebar
    "sidebar_bg": "#FFFFFF",
    "sidebar_text": "#0F172A",
    "sidebar_hover": "#F1F5F9",
    "sidebar_active": "#2563EB",
    "sidebar_section": "#334155",
}

# Soft tint backgrounds + dark readable foregrounds for status badges and
# table cells. Keyed by lowercase status value (matches persisted values).
# The dark foreground guarantees WCAG-style contrast on the light tint.
STATUS_TINTS: dict[str, tuple[str, str]] = {
    # Room statuses
    "vacant": ("#DCFCE7", "#15803D"),
    "occupied": ("#FEE2E2", "#B91C1C"),
    "reserved": ("#DBEAFE", "#1E40AF"),
    "cleaning": ("#FEF3C7", "#B45309"),
    # Booking statuses
    "new": ("#F1F5F9", "#475569"),
    "checked-in": ("#DBEAFE", "#1E40AF"),
    "checked-out": ("#DCFCE7", "#15803D"),
    "cancelled": ("#FEE2E2", "#B91C1C"),
    "no-show": ("#EDE9FE", "#6D28D9"),
    "deleted": ("#FEE2E2", "#B91C1C"),
    # Payment (booking-level) statuses
    "paid": ("#DCFCE7", "#15803D"),
    "partial": ("#FEF3C7", "#B45309"),
    "unpaid": ("#FEE2E2", "#B91C1C"),
    # Payment-record statuses
    "completed": ("#DCFCE7", "#15803D"),
    "refunded": ("#FEF3C7", "#B45309"),
    "reversed": ("#FEE2E2", "#B91C1C"),
    # Invoice statuses
    "draft": ("#F1F5F9", "#475569"),
    "finalized": ("#DCFCE7", "#15803D"),
}

_FALLBACK_TINT = ("#F1F5F9", "#475569")


def status_tint(status: str) -> tuple[str, str]:
    """Return ``(background, foreground)`` for a status value.

    Unknown statuses fall back to a neutral slate tint. The pair always
    provides strong readable contrast.
    """
    return STATUS_TINTS.get(str(status).strip().lower(), _FALLBACK_TINT)


def solid_status_color(status: str) -> str:
    """Return the saturated brand color for a status (for accents/dots)."""
    solid = {
        "vacant": "#16A34A",
        "occupied": "#DC2626",
        "reserved": "#2563EB",
        "cleaning": "#D97706",
        "new": "#64748B",
        "checked-in": "#2563EB",
        "checked-out": "#16A34A",
        "cancelled": "#6B7280",
        "no-show": "#7C3AED",
        "paid": "#16A34A",
        "partial": "#D97706",
        "unpaid": "#DC2626",
        "completed": "#16A34A",
        "refunded": "#D97706",
        "reversed": "#DC2626",
        "draft": "#64748B",
        "finalized": "#16A34A",
    }
    return solid.get(str(status).strip().lower(), "#64748B")


APP_STYLESHEET = f"""
* {{
    font-family: "Inter", "Segoe UI", Arial, sans-serif;
    font-size: 14px;
    color: {COLORS["text"]};
}}

QMainWindow, QWidget#AppRoot {{
    background: {COLORS["bg"]};
}}

QWidget {{
    background: transparent;
}}

QToolTip {{
    background: {COLORS["navy"]};
    color: #FFFFFF;
    border: none;
    padding: 6px 8px;
    font-size: 13px;
}}

/* ------------------------------------------------------------------ scrollbars */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS["border_strong"]};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS["text_secondary"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS["border_strong"]};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {COLORS["text_secondary"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

/* ------------------------------------------------------------------ sidebar */
#Sidebar {{
    background: {COLORS["sidebar_bg"]};
    border-right: 1px solid {COLORS["border"]};
}}

#SidebarBrand {{
    color: #000000;
    font-size: 17px;
    font-weight: 700;
    background: transparent;
}}

#SidebarBrandLogo {{
    color: #000000;
    font-size: 26px;
    background: transparent;
}}

#SidebarScroll, #SidebarScroll QWidget#SidebarScrollContent {{
    background: {COLORS["sidebar_bg"]};
    border: none;
}}

#SidebarScroll QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}

#SidebarScroll QScrollBar::handle:vertical {{
    background: #334155;
    border-radius: 4px;
    min-height: 30px;
}}

#SidebarScroll QScrollBar::handle:vertical:hover {{
    background: #475569;
}}

#SidebarScroll QScrollBar::add-line:vertical,
#SidebarScroll QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
}}

#SidebarScroll QScrollBar::add-page:vertical,
#SidebarScroll QScrollBar::sub-page:vertical {{
    background: none;
}}

#SidebarBrandSub {{
    color: {COLORS["sidebar_section"]};
    font-size: 11.5px;
    font-weight: 500;
    background: transparent;
}}

QLabel[sidebarSection="true"] {{
    color: {COLORS["sidebar_section"]};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.4px;
    padding: 16px 16px 6px 16px;
    background: {COLORS["sidebar_bg"]};
}}

QPushButton#NavButton {{
    background: transparent;
    color: {COLORS["sidebar_text"]};
    border: none;
    border-radius: 8px;
    text-align: left;
    padding: 9px 14px;
    margin: 1px 10px;
    font-size: 14px;
    font-weight: 700;
}}

QPushButton#NavButton:hover {{
    background: {COLORS["sidebar_hover"]};
    color: {COLORS["sidebar_text"]};
}}

QPushButton#NavButton:checked {{
    background: {COLORS["sidebar_active"]};
    color: #FFFFFF;
    font-weight: 800;
}}

QPushButton#SidebarLogout {{
    background: transparent;
    color: {COLORS["sidebar_text"]};
    border: 1px solid {COLORS["sidebar_hover"]};
    border-radius: 8px;
    margin: 4px 0 0 0;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 700;
    text-align: left;
}}

QPushButton#SidebarLogout:hover {{
    background: {COLORS["sidebar_hover"]};
    color: {COLORS["sidebar_text"]};
}}

QPushButton#SidebarLogout:disabled {{
    color: {COLORS["text_muted"]};
    border-color: {COLORS["sidebar_hover"]};
    background: transparent;
}}

#SidebarFooter {{
    background: {COLORS["sidebar_bg"]};
    border-top: 1px solid {COLORS["border"]};
    border-radius: 8px;
}}

QLabel[sidebarDot="true"] {{
    background: {COLORS["success"]};
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}}

QLabel[sidebarRole="true"] {{
    color: {COLORS["text"]};
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}}

QLabel[sidebarStatus="true"] {{
    color: {COLORS["sidebar_section"]};
    font-size: 11.5px;
    background: transparent;
}}

/* ------------------------------------------------------------------ top header */
#TopHeader {{
    background: {COLORS["surface"]};
    border-bottom: 1px solid {COLORS["border"]};
}}

#HeaderGreeting {{
    font-size: 16px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

#HeaderSubtitle {{
    font-size: 12.5px;
    color: {COLORS["text_secondary"]};
}}

#HeaderDate {{
    font-size: 13px;
    font-weight: 600;
    color: {COLORS["text"]};
}}

#HeaderDateSub {{
    font-size: 12px;
    color: {COLORS["text_secondary"]};
}}

QLineEdit#HeaderSearch {{
    background: {COLORS["bg"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}}

QLineEdit#HeaderSearch:focus {{
    border-color: {COLORS["primary"]};
    background: {COLORS["surface"]};
}}

/* ------------------------------------------------------------------ content */
#PageTitle {{
    font-size: 27px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

#PageSubtitle {{
    font-size: 14px;
    color: {COLORS["text_secondary"]};
}}

#SectionHeading {{
    font-size: 17px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

#HotelNameLabel {{
    font-size: 20px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

#ClockLabel {{
    font-size: 15px;
    font-weight: 600;
    color: {COLORS["text"]};
}}

#DateLabel {{
    font-size: 13px;
    color: {COLORS["text_secondary"]};
}}

/* ------------------------------------------------------------------ cards */
#Card {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
}}

#DetailsCard {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
}}

#Card:hover, #DetailsCard:hover {{
    border-color: {COLORS["border_strong"]};
}}

QLabel[cardTitle="true"] {{
    color: {COLORS["text_secondary"]};
    font-size: 13px;
    font-weight: 500;
}}

QLabel[cardValue="true"] {{
    color: {COLORS["text"]};
    font-size: 28px;
    font-weight: 700;
}}

QLabel[cardSubtext="true"] {{
    color: {COLORS["text_muted"]};
    font-size: 12px;
}}

QLabel[cardIcon="true"] {{
    font-size: 20px;
    background: transparent;
}}

QLabel[cardAccent="true"] {{
    border-radius: 5px;
    min-width: 6px;
    max-width: 6px;
    min-height: 48px;
    max-height: 48px;
}}

/* ------------------------------------------------------------------ buttons */
QPushButton {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 14px;
}}

QPushButton:hover {{
    background: {COLORS["bg"]};
    border-color: {COLORS["text_muted"]};
}}

QPushButton:pressed {{
    background: {COLORS["surface_hover"]};
}}

QPushButton:disabled {{
    background: {COLORS["surface_hover"]};
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border"]};
}}

/* Primary */
QPushButton#ActionButton, QPushButton#QuickActionButton {{
    background: {COLORS["primary"]};
    color: #FFFFFF;
    border: 1px solid {COLORS["primary"]};
    font-weight: 600;
}}

QPushButton#ActionButton:hover, QPushButton#QuickActionButton:hover {{
    background: {COLORS["primary_hover"]};
    border-color: {COLORS["primary_hover"]};
}}

QPushButton#ActionButton:pressed, QPushButton#QuickActionButton:pressed {{
    background: {COLORS["primary_pressed"]};
    border-color: {COLORS["primary_pressed"]};
}}

QPushButton#ActionButton:disabled, QPushButton#QuickActionButton:disabled {{
    background: {COLORS["surface_hover"]};
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border"]};
}}

/* Secondary */
QPushButton#SecondaryButton {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border_strong"]};
    font-weight: 500;
}}

QPushButton#SecondaryButton:hover {{
    background: {COLORS["bg"]};
    border-color: {COLORS["text_muted"]};
}}

QPushButton#SecondaryButton:pressed {{
    background: {COLORS["surface_hover"]};
}}

/* Small in-table action button */
QPushButton#SmallActionButton {{
    background: {COLORS["primary"]};
    color: #FFFFFF;
    border: 1px solid {COLORS["primary"]};
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 12px;
}}

QPushButton#SmallActionButton:hover {{
    background: {COLORS["primary_hover"]};
    border-color: {COLORS["primary_hover"]};
}}

QPushButton#SmallActionButton:pressed {{
    background: {COLORS["primary_pressed"]};
}}

QPushButton#SmallActionButton:disabled {{
    background: {COLORS["border_strong"]};
    border-color: {COLORS["border_strong"]};
    color: {COLORS["text_muted"]};
}}

/* Small in-table danger button */
QPushButton#DangerSmallButton {{
    background: transparent;
    color: {COLORS["danger"]};
    border: 1px solid {COLORS["danger"]};
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 12px;
}}

QPushButton#DangerSmallButton:hover {{
    background: {COLORS["danger"]};
    color: #FFFFFF;
}}

QPushButton#DangerSmallButton:pressed {{
    background: #B91C1C;
    border-color: #B91C1C;
    color: #FFFFFF;
}}

/* Danger */
QPushButton#DangerButton {{
    background: {COLORS["danger"]};
    color: #FFFFFF;
    border: 1px solid {COLORS["danger"]};
    font-weight: 600;
}}

QPushButton#DangerButton:hover {{
    background: #B91C1C;
    border-color: #B91C1C;
}}

QPushButton#DangerButton:pressed {{
    background: #991B1B;
    border-color: #991B1B;
}}

/* Success */
QPushButton#SuccessButton {{
    background: {COLORS["success"]};
    color: #FFFFFF;
    border: 1px solid {COLORS["success"]};
    font-weight: 600;
}}

QPushButton#SuccessButton:hover {{
    background: #15803D;
    border-color: #15803D;
}}

QPushButton#SuccessButton:pressed {{
    background: #166534;
    border-color: #166534;
}}

/* Quick action colour variants (dashboard) */
QPushButton#QuickActionButton[kind="primary"] {{
    background: {COLORS["primary"]};
    border-color: {COLORS["primary"]};
}}
QPushButton#QuickActionButton[kind="primary"]:hover {{
    background: {COLORS["primary_hover"]};
    border-color: {COLORS["primary_hover"]};
}}
QPushButton#QuickActionButton[kind="success"] {{
    background: {COLORS["success"]};
    border-color: {COLORS["success"]};
}}
QPushButton#QuickActionButton[kind="success"]:hover {{
    background: #15803D;
    border-color: #15803D;
}}
QPushButton#QuickActionButton[kind="checkin"] {{
    background: {COLORS["purple"]};
    border-color: {COLORS["purple"]};
}}
QPushButton#QuickActionButton[kind="checkin"]:hover {{
    background: #6D28D9;
    border-color: #6D28D9;
}}
QPushButton#QuickActionButton[kind="checkout"] {{
    background: {COLORS["orange"]};
    border-color: {COLORS["orange"]};
}}
QPushButton#QuickActionButton[kind="checkout"]:hover {{
    background: #EA580C;
    border-color: #EA580C;
}}
QPushButton#QuickActionButton[kind="info"] {{
    background: {COLORS["info"]};
    border-color: {COLORS["info"]};
}}
QPushButton#QuickActionButton[kind="info"]:hover {{
    background: #0369A1;
    border-color: #0369A1;
}}
QPushButton#QuickActionButton[kind="invoice"] {{
    background: #6366F1;
    border-color: #6366F1;
}}
QPushButton#QuickActionButton[kind="invoice"]:hover {{
    background: #4F46E5;
    border-color: #4F46E5;
}}

/* ------------------------------------------------------------------ filter chips */
QPushButton#FilterChip {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 14px;
    padding: 5px 14px;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton#FilterChip:hover {{
    border-color: {COLORS["primary"]};
    color: {COLORS["primary"]};
    background: {COLORS["surface"]};
}}

QPushButton#FilterChip:checked {{
    background: {COLORS["primary"]};
    color: #FFFFFF;
    border-color: {COLORS["primary"]};
    font-weight: 600;
}}

QPushButton#FilterChip:checked:hover {{
    background: {COLORS["primary_hover"]};
    border-color: {COLORS["primary_hover"]};
}}

QPushButton#FilterButton {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton#FilterButton:hover {{
    border-color: {COLORS["primary"]};
    color: {COLORS["primary"]};
}}

QPushButton#FilterButton:checked {{
    background: {COLORS["primary"]};
    color: #FFFFFF;
    border-color: {COLORS["primary"]};
    font-weight: 600;
}}

/* ------------------------------------------------------------------ inputs */
QLineEdit, QTextEdit, QPlainTextEdit,
QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
QComboBox, QListWidget, QListView {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {COLORS["primary"]};
    selection-color: #FFFFFF;
    font-size: 14px;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTimeEdit:focus,
QComboBox:focus, QListWidget:focus {{
    border: 1px solid {COLORS["primary"]};
    background: {COLORS["surface"]};
}}

QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled, QTimeEdit:disabled,
QComboBox:disabled, QListWidget:disabled {{
    background: {COLORS["surface_hover"]};
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border"]};
}}

QLineEdit[readOnly="true"] {{
    background: {COLORS["surface_hover"]};
    color: {COLORS["text_secondary"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 26px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {COLORS["text_secondary"]};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    selection-background-color: {COLORS["primary"]};
    selection-color: #FFFFFF;
    outline: none;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QDateEdit::up-button, QTimeEdit::up-button {{
    background: transparent;
    border: none;
    width: 18px;
}}

QSpinBox::down-button, QDoubleSpinBox::down-button,
QDateEdit::down-button, QTimeEdit::down-button {{
    background: transparent;
    border: none;
    width: 18px;
}}

QDateEdit::drop-down, QTimeEdit::drop-down {{
    border: none;
    width: 24px;
}}

QCheckBox {{
    color: {COLORS["text"]};
    spacing: 8px;
    font-size: 14px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 5px;
    background: {COLORS["surface"]};
}}

QCheckBox::indicator:hover {{
    border-color: {COLORS["primary"]};
}}

QCheckBox::indicator:checked {{
    background: {COLORS["primary"]};
    border-color: {COLORS["primary"]};
    image: none;
}}

/* ------------------------------------------------------------------ tables */
QTableWidget, QTableView {{
    background: {COLORS["surface"]};
    alternate-background-color: {COLORS["bg"]};
    gridline-color: {COLORS["border"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    selection-background-color: #DBEAFE;
    selection-color: {COLORS["text"]};
    color: {COLORS["text"]};
    outline: none;
    font-size: 13.5px;
}}

QTableWidget::item, QTableView::item {{
    padding: 0 8px;
    border-bottom: 1px solid {COLORS["border"]};
    color: {COLORS["text"]};
}}

QTableWidget::item:hover, QTableView::item:hover {{
    background: {COLORS["bg"]};
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background: #DBEAFE;
    color: {COLORS["text"]};
}}

QHeaderView::section {{
    background: {COLORS["bg"]};
    color: {COLORS["text_header"]};
    font-weight: 700;
    font-size: 13px;
    padding: 9px 10px;
    border: none;
    border-right: 1px solid {COLORS["border"]};
    border-bottom: 1px solid {COLORS["border"]};
}}

QTableCornerButton::section {{
    background: {COLORS["bg"]};
    border: none;
}}

/* ------------------------------------------------------------------ tabs */
QTabWidget::pane {{
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    background: {COLORS["surface"]};
    top: -1px;
}}

QTabBar::tab {{
    background: {COLORS["bg"]};
    color: {COLORS["text_secondary"]};
    border: 1px solid {COLORS["border"]};
    padding: 9px 18px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 500;
}}

QTabBar::tab:selected {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    border-bottom-color: {COLORS["surface"]};
    font-weight: 700;
}}

QTabBar::tab:hover:!selected {{
    background: #FFFFFF;
    color: {COLORS["text"]};
}}

/* ------------------------------------------------------------------ dialogs */
QDialog {{
    background: {COLORS["surface"]};
}}

QMessageBox {{
    background: {COLORS["surface"]};
}}

QMessageBox QLabel {{
    color: {COLORS["text"]};
    font-size: 14px;
    min-width: 320px;
}}

QDialogButtonBox QPushButton {{
    min-width: 90px;
}}

QLabel[detailLabel="true"] {{
    color: {COLORS["text_secondary"]};
    font-size: 13px;
}}

QLabel[detailValue="true"] {{
    color: {COLORS["text"]};
    font-size: 14px;
    font-weight: 600;
}}

#DialogRoomNumber {{
    font-size: 24px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

/* ------------------------------------------------------------------ room cards */
#RoomCard {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
}}

#RoomCard:hover {{
    border: 2px solid {COLORS["primary"]};
}}

#RoomCard[availability="free"] {{
    background: #F0FDF4;
    border: 2px solid {COLORS["success"]};
}}

#RoomCard[availability="free"]:hover {{
    border: 2px solid #15803D;
}}

#RoomCard[availability="blocked"] {{
    background: #FEF2F2;
    border: 2px solid {COLORS["danger"]};
}}

#RoomCard[availability="blocked"]:hover {{
    border: 2px solid #B91C1C;
}}

QLabel[roomNumberPrefix="true"] {{
    font-size: 15px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

QLabel[roomNumber="true"] {{
    font-size: 30px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

QLabel[roomGuestName="true"] {{
    font-size: 13px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

QLabel[roomType="true"] {{
    font-size: 12px;
    color: {COLORS["text_secondary"]};
}}

QLabel[roomOccupant="true"] {{
    font-size: 12.5px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

QLabel[roomOccupantDetail="true"] {{
    font-size: 11px;
    color: {COLORS["text_secondary"]};
}}

QLabel[roomStatusText="true"] {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

/* ------------------------------------------------------------------ coming soon */
#ComingSoonTitle {{
    font-size: 24px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

#ComingSoonText {{
    font-size: 15px;
    color: {COLORS["text_secondary"]};
}}

/* ------------------------------------------------------------------ status bar */
QStatusBar {{
    background: {COLORS["surface"]};
    color: {COLORS["text_secondary"]};
    font-size: 13px;
    border-top: 1px solid {COLORS["border"]};
}}

QStatusBar::item {{
    border: none;
}}

/* ------------------------------------------------------------------ misc */
QGroupBox {{
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}}

QCalendarWidget QWidget {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    font-size: 13px;
}}

QCalendarWidget QToolButton {{
    background: {COLORS["surface"]};
    border: none;
    padding: 6px 10px;
    font-weight: 600;
    color: {COLORS["text"]};
}}

QCalendarWidget QAbstractItemView:enabled {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    selection-background-color: {COLORS["primary"]};
    selection-color: #FFFFFF;
}}
"""


def empty_state_stylesheet() -> str:
    """Styles for the empty-state placeholder widget."""
    return f"""
    QWidget#EmptyState {{
        background: {COLORS["surface"]};
        border: 1px dashed {COLORS["border_strong"]};
        border-radius: 10px;
    }}
    QLabel[emptyIcon="true"] {{
        font-size: 26px;
        background: transparent;
    }}
    QLabel[emptyTitle="true"] {{
        color: {COLORS["text"]};
        font-size: 15px;
        font-weight: 700;
    }}
    QLabel[emptySubtitle="true"] {{
        color: {COLORS["text_secondary"]};
        font-size: 13px;
    }}
    """


def status_badge_stylesheet(status: str, compact: bool = False) -> str:
    """Return the pill stylesheet for a status badge.

    Uses a soft tint background with dark, readable foreground text. Text
    always carries the meaning — colour is a reinforcement, never the only
    signal. ``compact`` produces a smaller pill for room cards.
    """
    background, foreground = status_tint(status)
    if compact:
        padding = "3px 8px"
        font_size = "11px"
    else:
        padding = "3px 12px"
        font_size = "12px"
    return f"""
        QLabel {{
            background-color: {background};
            color: {foreground};
            border: 1px solid {background};
            border-radius: 10px;
            padding: {padding};
            font-size: {font_size};
            font-weight: 600;
        }}
    """