"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import (
    APP_TITLE,
    BookingStatus,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
)
from app.database.database import Database
from app.services import audit_service, security_service
from app.ui.dialogs.admin_login_dialog import AdminLoginDialog
from app.ui.pages.admin_audit_page import AdminAuditPage
from app.ui.pages.admin_backup_page import AdminBackupPage
from app.ui.pages.admin_dashboard_page import AdminDashboardPage
from app.ui.pages.admin_reports_page import AdminReportsPage
from app.ui.pages.admin_settings_page import AdminSettingsPage
from app.ui.pages.bookings_page import BookingsPage
from app.ui.pages.coming_soon_page import ComingSoonPage
from app.ui.pages.dashboard_page import ReceptionDashboardPage
from app.ui.pages.guests_page import GuestsPage
from app.ui.pages.invoices_page import InvoicesPage
from app.ui.pages.payments_page import PaymentsPage
from app.ui.pages.rooms_page import RoomsPage
from app.ui.sidebar import ADMIN_ITEMS, MAIN_ITEMS, Sidebar
from app.ui.top_header import TopHeader

PAGE_KEYS = {key for items in (MAIN_ITEMS, ADMIN_ITEMS) for key, _ in items}
PAGE_LABELS = {key: label for items in (MAIN_ITEMS, ADMIN_ITEMS) for key, label in items}
ADMIN_KEYS = {key for key, _ in ADMIN_ITEMS}


class MainWindow(QMainWindow):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database

        self.setWindowTitle(APP_TITLE)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        self.admin_session = None
        self.current_key = "dashboard"

        self.sidebar = Sidebar()
        self.dashboard_page = ReceptionDashboardPage(database)
        self.rooms_page = RoomsPage(database)
        self.guests_page = GuestsPage(database)
        self.bookings_page = BookingsPage(database)
        self.payments_page = PaymentsPage(database)
        self.invoices_page = InvoicesPage(database)
        self.coming_soon_page = ComingSoonPage()
        self.admin_dashboard_page = AdminDashboardPage(database)
        self.admin_reports_page = AdminReportsPage(database)
        self.admin_settings_page = AdminSettingsPage(database)
        self.admin_audit_page = AdminAuditPage(database)
        self.admin_backup_page = AdminBackupPage(database)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.rooms_page)
        self.pages.addWidget(self.guests_page)
        self.pages.addWidget(self.bookings_page)
        self.pages.addWidget(self.payments_page)
        self.pages.addWidget(self.invoices_page)
        self.pages.addWidget(self.coming_soon_page)
        self.pages.addWidget(self.admin_dashboard_page)
        self.pages.addWidget(self.admin_reports_page)
        self.pages.addWidget(self.admin_settings_page)
        self.pages.addWidget(self.admin_audit_page)
        self.pages.addWidget(self.admin_backup_page)

        central = QWidget()
        central.setObjectName("AppRoot")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)

        right_column = QWidget()
        right_column.setObjectName("AppContent")
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.header = TopHeader()
        right_layout.addWidget(self.header)
        right_layout.addWidget(self.pages, 1)
        layout.addWidget(right_column, 1)
        self.setCentralWidget(central)

        self.sidebar.navigation_requested.connect(self._navigate)
        self.sidebar.logout_requested.connect(self._logout)
        self.dashboard_page.quick_action_requested.connect(self._quick_action)
        self.header.search_requested.connect(self._open_global_search_with)
        self.sidebar.select("dashboard")

        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(30_000)
        self._lock_timer.timeout.connect(self._check_session)
        self._lock_timer.start()

        self._search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._search_shortcut.activated.connect(self._open_global_search)

        self.statusBar().showMessage("Ready")

    def _open_global_search(self) -> None:
        self._open_global_search_with("")

    def _open_global_search_with(self, query: str) -> None:
        from app.ui.dialogs.global_search_dialog import GlobalSearchDialog

        dialog = GlobalSearchDialog(self.database, parent=self)
        dialog.set_initial_query(query)
        dialog.exec()

    # ------------------------------------------------------------ navigation

    def _quick_action(self, action: str) -> None:
        key = {"checkin": "check_in", "checkout": "check_out"}.get(action, action)
        if key in ("check_in", "check_out", "payments", "invoices"):
            self.sidebar.select(key)
            self._navigate(key)
        else:
            self.dashboard_page.open_dialog(action)

    def _navigate(self, key: str) -> None:
        if key not in PAGE_KEYS:
            return
        self.current_key = key
        if key in ADMIN_KEYS:
            self._open_admin(key)
            return
        if key == "dashboard":
            self.pages.setCurrentWidget(self.dashboard_page)
            self.dashboard_page.refresh()
            self.statusBar().showMessage("Dashboard")
        elif key == "rooms":
            self.pages.setCurrentWidget(self.rooms_page)
            self.rooms_page.refresh()
            self.statusBar().showMessage("Rooms")
        elif key == "guests":
            self.pages.setCurrentWidget(self.guests_page)
            self.guests_page.refresh()
            self.statusBar().showMessage("Guests")
        elif key == "bookings":
            self.bookings_page.set_status_filter(None)
            self.pages.setCurrentWidget(self.bookings_page)
            self.statusBar().showMessage("Bookings")
        elif key == "check_in":
            self.bookings_page.set_status_filter(BookingStatus.RESERVED)
            self.pages.setCurrentWidget(self.bookings_page)
            self.statusBar().showMessage("Check-in — Reserved bookings")
        elif key == "check_out":
            self.bookings_page.set_status_filter(BookingStatus.CHECKED_IN)
            self.pages.setCurrentWidget(self.bookings_page)
            self.statusBar().showMessage("Check-out — Checked-in bookings")
        elif key == "payments":
            self.pages.setCurrentWidget(self.payments_page)
            self.payments_page.refresh()
            self.statusBar().showMessage("Payments")
        elif key == "invoices":
            self.pages.setCurrentWidget(self.invoices_page)
            self.invoices_page.refresh()
            self.statusBar().showMessage("Invoices")
        else:
            label = PAGE_LABELS[key]
            self.coming_soon_page.set_section(label)
            self.pages.setCurrentWidget(self.coming_soon_page)
            self.statusBar().showMessage(f"{label} — Coming Soon")

    # ----------------------------------------------------------- admin gate

    def _open_admin(self, key: str) -> None:
        if not self._require_login():
            self._back_to_reception()
            return
        if key == "admin":
            self.admin_dashboard_page.refresh()
            self.pages.setCurrentWidget(self.admin_dashboard_page)
            self.statusBar().showMessage("Admin Dashboard")
        elif key == "reports":
            self.admin_reports_page.refresh()
            self.pages.setCurrentWidget(self.admin_reports_page)
            self.statusBar().showMessage("Reports")
        elif key == "settings":
            self.admin_settings_page.refresh()
            self.pages.setCurrentWidget(self.admin_settings_page)
            self.statusBar().showMessage("Admin Settings")
        elif key == "audit":
            self.admin_audit_page.refresh()
            self.pages.setCurrentWidget(self.admin_audit_page)
            self.statusBar().showMessage("Audit Log")
        elif key == "backup":
            self.admin_backup_page.refresh()
            self.pages.setCurrentWidget(self.admin_backup_page)
            self.statusBar().showMessage("Backup & Data Safety")
        else:
            label = PAGE_LABELS[key]
            self.coming_soon_page.set_section(label)
            self.pages.setCurrentWidget(self.coming_soon_page)
            self.statusBar().showMessage(f"{label} — Coming Soon")
        if self.admin_session is not None:
            self.admin_session.touch()

    def _require_login(self) -> bool:
        if self.admin_session is not None and self.admin_session.is_active():
            self.admin_session.touch()
            return True
        dialog = AdminLoginDialog(self.database, parent=self)
        dialog.exec()
        if not dialog.authenticated:
            return False
        with self.database.session_scope() as session:
            timeout = security_service.session_timeout_minutes(session)
        self.admin_session = security_service.AdminSession(timeout_minutes=timeout)
        self.sidebar.set_logged_in(True)
        self.statusBar().showMessage("Admin session started")
        return True

    def _logout(self) -> None:
        if self.admin_session is not None:
            with self.database.session_scope() as session:
                audit_service.log_action(session, audit_service.ACTION_ADMIN_LOGOUT, "Admin logged out.")
            self.admin_session.logout()
            self.admin_session = None
        self.sidebar.set_logged_in(False)
        self._back_to_reception()
        self.statusBar().showMessage("Logged out")

    def _check_session(self) -> None:
        if self.admin_session is not None and not self.admin_session.is_active():
            with self.database.session_scope() as session:
                audit_service.log_action(
                    session,
                    audit_service.ACTION_ADMIN_LOGOUT,
                    "Admin session expired due to inactivity.",
                )
            self.admin_session = None
            self.sidebar.set_logged_in(False)
            if self.current_key in ADMIN_KEYS:
                self.statusBar().showMessage("Admin session expired — please log in again")
                QMessageBox.information(
                    self,
                    "Session Expired",
                    "Your admin session has expired. Please log in again to continue.",
                )
                self._back_to_reception()

    def _back_to_reception(self) -> None:
        self.sidebar.select("dashboard")
        self._navigate("dashboard")
