"""Admin login / first-run setup dialog.

If no admin password has been set yet (first run) the dialog walks the user
through creating one; otherwise it authenticates the existing password. The
dialog tracks failed attempts and enforces the temporary lockout enforced by
:mod:`app.services.security_service`.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.database.database import Database
from app.services import audit_service, security_service


class AdminLoginDialog(QDialog):
    def __init__(self, database: Database, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.database = database
        self.authenticated = False

        self.setWindowTitle("Admin Login")
        self.setModal(True)
        self.setMinimumWidth(380)

        self._build_ui()
        self._start_flow()

    # ------------------------------------------------------------------ ui

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        self.title_label = QLabel()
        self.title_label.setObjectName("PageTitle")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.info_label = QLabel()
        self.info_label.setProperty("detailLabel", True)
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        row = QHBoxLayout()
        row.addWidget(self._field_label("Password"))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.returnPressed.connect(self._submit)
        row.addWidget(self.password_edit, 1)
        layout.addLayout(row)

        self.confirm_row = QHBoxLayout()
        self.confirm_row.addWidget(self._field_label("Confirm"))
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.returnPressed.connect(self._submit)
        self.confirm_row.addWidget(self.confirm_edit, 1)
        layout.addLayout(self.confirm_row)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #dc2626;")
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(self.reject)
        self.submit_button = QPushButton("Login")
        self.submit_button.setObjectName("ActionButton")
        self.submit_button.clicked.connect(self._submit)
        button_row.addWidget(cancel)
        button_row.addWidget(self.submit_button)
        layout.addLayout(button_row)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("detailLabel", True)
        return label

    def _start_flow(self) -> None:
        with self.database.session_scope() as session:
            password_set = security_service.is_password_set(session)
        self.setting_up = not password_set
        self.password_edit.clear()
        self.confirm_edit.clear()
        self.error_label.clear()
        if self.setting_up:
            self.title_label.setText("Set Admin Password")
            self.info_label.setText(
                "This is the first time the Admin area is opened. Create a password "
                "(minimum 8 characters) that will be required for all Admin access."
            )
            self.confirm_row_visible(True)
            self.submit_button.setText("Set Password")
        else:
            self.title_label.setText("Admin Login")
            self.info_label.setText("Enter the admin password to continue.")
            self.confirm_row_visible(False)
            self.submit_button.setText("Login")
        self.password_edit.setFocus()

    def confirm_row_visible(self, visible: bool) -> None:
        for index in range(self.confirm_row.count()):
            widget = self.confirm_row.itemAt(index).widget()
            if widget is not None:
                widget.setVisible(visible)

    # --------------------------------------------------------------- submit

    def _submit(self) -> None:
        password = self.password_edit.text()
        with self.database.session_scope() as session:
            if self.setting_up:
                confirm = self.confirm_edit.text()
                if password != confirm:
                    self._show_error("Passwords do not match.")
                    return
                try:
                    security_service.initialize_admin_password(session, password)
                except security_service.PasswordAlreadySetError:
                    self._show_error("An admin password is already set.")
                    return
                except security_service.WeakPasswordError as exc:
                    self._show_error(str(exc))
                    return
                audit_service.log_action(
                    session,
                    audit_service.ACTION_ADMIN_LOGIN,
                    "Initial admin password created and first login.",
                )
                self.authenticated = True
                self.accept()
                return

            try:
                ok = security_service.verify_admin_password(session, password)
            except security_service.LoginLockedError as exc:
                self._show_error(str(exc))
                self.submit_button.setEnabled(False)
                self.password_edit.setEnabled(False)
                return
            if not ok:
                self._show_error("Incorrect password. Please try again.")
                self.password_edit.selectAll()
                return
            audit_service.log_action(
                session,
                audit_service.ACTION_ADMIN_LOGIN,
                "Admin logged in.",
            )
        self.authenticated = True
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
