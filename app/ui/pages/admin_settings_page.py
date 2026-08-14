"""Admin Settings page.

Hotel identity/contact details, logo management, booking sources and admin
security (change password, session timeout). Only visible after admin login.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.database.database import Database
from app.services import (
    admin_settings_service,
    audit_service,
    security_service,
    settings_service,
)


class AdminSettingsPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Admin Settings")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Hotel information, logo, booking sources and admin security. "
            "Saved changes apply immediately."
        )
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(subtitle)

        container = QWidget()
        self._form_layout = QVBoxLayout(container)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.setSpacing(14)

        self._build_hotel_card()
        self._build_logo_card()
        self._build_sources_card()
        self._build_security_card()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def _card(self, heading: str) -> tuple[QWidget, QVBoxLayout]:
        card = QWidget()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        heading_label = QLabel(heading)
        heading_label.setObjectName("SectionHeading")
        layout.addWidget(heading_label)
        return card, layout

    def _field_row(self, layout: QVBoxLayout, label: str, widget: QWidget) -> None:
        label_widget = QLabel(label)
        label_widget.setProperty("detailLabel", True)
        layout.addWidget(label_widget)
        layout.addWidget(widget)

    def _build_hotel_card(self) -> None:
        card, layout = self._card("Hotel Information")
        self.hotel_name_edit = QLineEdit()
        self._field_row(layout, "Hotel Name *", self.hotel_name_edit)
        self.hotel_desc_edit = QLineEdit()
        self._field_row(layout, "Description", self.hotel_desc_edit)
        self.hotel_address_edit = QPlainTextEdit()
        self.hotel_address_edit.setMaximumHeight(70)
        self._field_row(layout, "Address", self.hotel_address_edit)
        self.hotel_phone_edit = QLineEdit()
        self._field_row(layout, "Phone", self.hotel_phone_edit)
        self.hotel_email_edit = QLineEdit()
        self._field_row(layout, "Email", self.hotel_email_edit)
        self.hotel_website_edit = QLineEdit()
        self._field_row(layout, "Website", self.hotel_website_edit)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        save = QPushButton("Save Hotel Information")
        save.setObjectName("ActionButton")
        save.clicked.connect(self._save_hotel)
        button_row.addWidget(save)
        layout.addLayout(button_row)
        self._form_layout.addWidget(card)

    def _build_logo_card(self) -> None:
        card, layout = self._card("Logo")
        self.logo_label = QLabel("No logo set.")
        self.logo_label.setProperty("detailLabel", True)
        layout.addWidget(self.logo_label)
        row = QHBoxLayout()
        upload = QPushButton("Upload Logo")
        upload.setObjectName("ActionButton")
        upload.clicked.connect(self._upload_logo)
        remove = QPushButton("Remove Logo")
        remove.setObjectName("SecondaryButton")
        remove.clicked.connect(self._remove_logo)
        row.addWidget(upload)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)
        self._form_layout.addWidget(card)

    def _build_sources_card(self) -> None:
        card, layout = self._card("Booking Sources")
        self.source_new_edit = QLineEdit()
        self.source_new_edit.setPlaceholderText("New source name, e.g. MakeMyTrip")
        add_row = QHBoxLayout()
        add_row.addWidget(self.source_new_edit, 1)
        add_button = QPushButton("Add Source")
        add_button.setObjectName("ActionButton")
        add_button.clicked.connect(self._add_source)
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        self.source_list_layout = QVBoxLayout()
        self.source_list_layout.setSpacing(4)
        layout.addLayout(self.source_list_layout)
        self._form_layout.addWidget(card)

    def _build_security_card(self) -> None:
        card, layout = self._card("Admin Security")
        self.current_password_edit = QLineEdit()
        self.current_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._field_row(layout, "Current Password", self.current_password_edit)
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._field_row(layout, "New Password (min 8 chars)", self.new_password_edit)
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._field_row(layout, "Confirm New Password", self.confirm_password_edit)
        change_button = QPushButton("Change Password")
        change_button.setObjectName("ActionButton")
        change_button.clicked.connect(self._change_password)
        layout.addWidget(change_button)

        timeout_row = QHBoxLayout()
        timeout_row.addWidget(self._label("Session Timeout (minutes)"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 1440)
        timeout_row.addWidget(self.timeout_spin)
        save_timeout = QPushButton("Save Timeout")
        save_timeout.setObjectName("SecondaryButton")
        save_timeout.clicked.connect(self._save_timeout)
        timeout_row.addWidget(save_timeout)
        timeout_row.addStretch(1)
        layout.addLayout(timeout_row)
        self._form_layout.addWidget(card)

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("detailLabel", True)
        return label

    # --------------------------------------------------------------- load

    def refresh(self) -> None:
        with self.database.session_scope() as session:
            hotel = settings_service.get_hotel_settings(session)
            sources = admin_settings_service.get_booking_sources(session)
            timeout = security_service.session_timeout_minutes(session)
            logo = admin_settings_service.get_logo_path(session)

        self.hotel_name_edit.setText(hotel["hotel_name"])
        self.hotel_desc_edit.setText(hotel["hotel_description"])
        self.hotel_address_edit.setPlainText(hotel["hotel_address"])
        self.hotel_phone_edit.setText(hotel["hotel_phone"])
        self.hotel_email_edit.setText(hotel["hotel_email"])
        self.hotel_website_edit.setText(hotel["hotel_website"])
        self.timeout_spin.setValue(timeout)
        self.logo_label.setText(f"Logo: {logo}" if logo else "No logo set.")
        self.current_password_edit.clear()
        self.new_password_edit.clear()
        self.confirm_password_edit.clear()
        self._render_sources(sources)

    def _render_sources(self, sources) -> None:  # noqa: ANN001
        while self.source_list_layout.count():
            item = self.source_list_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for source in sources:
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(10, 6, 10, 6)
            name = QLabel(source.name)
            name.setProperty("cardTitle", True)
            row.addWidget(name)
            status = QLabel("Active" if source.is_active else "Disabled")
            status.setStyleSheet(
                "color: #ffffff; background: #16a34a; padding: 2px 10px; border-radius: 9px;"
                if source.is_active
                else "color: #ffffff; background: #94a3b8; padding: 2px 10px; border-radius: 9px;"
            )
            row.addWidget(status)
            row.addStretch(1)
            toggle = QPushButton("Disable" if source.is_active else "Enable")
            toggle.setObjectName("SecondaryButton" if source.is_active else "ActionButton")
            toggle.clicked.connect(lambda checked=False, s=source: self._toggle_source(s.id, s.is_active))
            row.addWidget(toggle)
            self.source_list_layout.addWidget(row_widget)

    # --------------------------------------------------------------- save

    def _save_hotel(self) -> None:
        try:
            with self.database.session_scope() as session:
                admin_settings_service.update_hotel_info(
                    session,
                    name=self.hotel_name_edit.text(),
                    description=self.hotel_desc_edit.text(),
                    address=self.hotel_address_edit.toPlainText(),
                    phone=self.hotel_phone_edit.text(),
                    email=self.hotel_email_edit.text(),
                    website=self.hotel_website_edit.text(),
                )
                audit_service.log_action(
                    session,
                    audit_service.ACTION_SETTINGS_CHANGED,
                    "Updated hotel information.",
                )
        except admin_settings_service.ValidationError as exc:
            QMessageBox.warning(self, "Invalid Details", str(exc))
            return
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Hotel settings save failed")
            QMessageBox.critical(self, "Error", "Could not save hotel information.")
            return
        QMessageBox.information(self, "Saved", "Hotel information saved.")
        self.refresh()

    def _upload_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Logo Image",
            "",
            "Images (*.png *.jpg *.jpeg *.gif)",
        )
        if not path:
            return
        try:
            with self.database.session_scope() as session:
                admin_settings_service.upload_logo(session, path)
                audit_service.log_action(
                    session,
                    audit_service.ACTION_LOGO_CHANGED,
                    "Updated hotel logo.",
                )
        except admin_settings_service.ValidationError as exc:
            QMessageBox.warning(self, "Invalid Logo", str(exc))
            return
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Logo upload failed")
            QMessageBox.critical(self, "Error", "Could not upload the logo.")
            return
        self.refresh()

    def _remove_logo(self) -> None:
        with self.database.session_scope() as session:
            admin_settings_service.remove_logo(session)
            audit_service.log_action(
                session,
                audit_service.ACTION_LOGO_CHANGED,
                "Removed hotel logo.",
            )
        self.refresh()

    def _add_source(self) -> None:
        name = self.source_new_edit.text().strip()
        if not name:
            return
        try:
            with self.database.session_scope() as session:
                admin_settings_service.add_booking_source(session, name)
                audit_service.log_action(
                    session,
                    audit_service.ACTION_SOURCE_ADDED,
                    f"Added booking source {name!r}.",
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Source", str(exc))
            return
        self.source_new_edit.clear()
        self.refresh()

    def _toggle_source(self, source_id: int, currently_active: bool) -> None:
        active = not currently_active
        with self.database.session_scope() as session:
            source = admin_settings_service.set_booking_source_active(session, source_id, active)
            action = (
                audit_service.ACTION_SOURCE_ENABLED
                if active
                else audit_service.ACTION_SOURCE_DISABLED
            )
            audit_service.log_action(
                session,
                action,
                f"{'Enabled' if active else 'Disabled'} booking source {source.name!r}.",
            )
        self.refresh()

    def _change_password(self) -> None:
        try:
            with self.database.session_scope() as session:
                security_service.change_admin_password(
                    session,
                    current_password=self.current_password_edit.text(),
                    new_password=self.new_password_edit.text(),
                    confirm_password=self.confirm_password_edit.text(),
                )
                audit_service.log_action(session, audit_service.ACTION_PASSWORD_CHANGED, "Admin password changed.")
        except security_service.SecurityError as exc:
            QMessageBox.warning(self, "Password Change Failed", str(exc))
            return
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Password change failed")
            QMessageBox.critical(self, "Error", "Could not change the password.")
            return
        QMessageBox.information(self, "Changed", "Admin password updated.")
        self.current_password_edit.clear()
        self.new_password_edit.clear()
        self.confirm_password_edit.clear()

    def _save_timeout(self) -> None:
        minutes = self.timeout_spin.value()
        with self.database.session_scope() as session:
            security_service.set_session_timeout_minutes(session, minutes)
            audit_service.log_action(
                session,
                audit_service.ACTION_SETTINGS_CHANGED,
                f"Admin session timeout set to {minutes} minutes.",
            )
        QMessageBox.information(self, "Saved", "Session timeout updated.")
