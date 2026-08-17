
---

# PHASE 1 — FOUNDATION

**Classification: IMPLEMENTED**

| Area | Status | Evidence |
|------|--------|----------|
| Database foundation | IMPLEMENTED | `app/database/database.py` (SQLAlchemy 2.0 engine, `Database`, `session_scope`, `new_session`, `dispose`, `dispose_all_databases`) |
| SQLite | IMPLEMENTED | Local `data/hotel.db` via `Paths().database_file`; `PRAGMA foreign_keys=ON` on every connection |
| ORM models | IMPLEMENTED | `app/database/models/__init__.py` registers 11 models: Room, Guest, Booking, BookingCharge, BookingSource, Payment, Invoice, AuditLog, HotelSetting, BookingStatusHistory, RoomStatusHistory |
| Schema migrations | IMPLEMENTED | `app/database/migrations.py` — idempotent `ALTER TABLE` + `create_all` (Phase 1 room columns, Phase 4 discount, Phase 7 payment indexes) |
| Application structure | IMPLEMENTED | `main.py` (`initialize_application` + `main`), package layout `app/{core,database,services,ui}`, `tests/` |
| Configuration | IMPLEMENTED | `app/core/config.py` (default settings + 11 default rooms), `app/core/constants.py` (hotel info, enums, status colors) |
| Path management | IMPLEMENTED | `app/core/paths.py` — centralized `Paths`; `NCS_APP_DATA` override; packaged-build handling |
| Logging | IMPLEMENTED | `app/core/logging_config.py` → `logs/application.log` |
| Basic UI shell | IMPLEMENTED | `main.py` stylesheet, `MainWindow` + `Sidebar` navigation, placeholder page |
| Initial hotel configuration | IMPLEMENTED | Startup seeds settings, 11 rooms (AC 202–207, Non-AC 208–212), 9 booking sources — idempotent |
| Admin-password placeholder | IMPLEMENTED | Settings carry `admin_password_set=false`, `admin_password_hash` empty at start |

---

# PHASE 2 — ROOMS + RECEPTION DASHBOARD

**Classification: IMPLEMENTED**

| Area | Status | Evidence |
|------|--------|----------|
| Room management | IMPLEMENTED | `app/services/room_service.py` — `get_rooms`, `get_all_rooms`, `get_room`, `get_room_by_number`, `update_room_notes`, `set_room_active` |
| Room types | IMPLEMENTED | `RoomType` enum (`AC`, `Non-AC`); `DEFAULT_ROOMS` (202–207 AC, 208–212 Non-AC) |
| Room statuses | IMPLEMENTED | `RoomStatus` enum: VACANT / OCCUPIED / CLEANING / RESERVED / MAINTENANCE; advisory transition map `ALLOWED_TRANSITIONS` |
| Status colors + text | IMPLEMENTED | `constants.ROOM_STATUS_COLORS` (green/red/amber/blue/gray) rendered as colored pills by `widgets/status_badge.py` |
| Status history | IMPLEMENTED | `RoomStatusHistory` model + `room_service.get_status_history`; every change recorded (`changed_by` defaults to "Reception") |
| Room status board | IMPLEMENTED | `ui/pages/rooms_page.py` (room-card grid) and dashboard board; `widgets/room_card.py` (clickable hover card, tooltip) |
| Reception dashboard | IMPLEMENTED | `ui/pages/dashboard_page.py` — today's check-ins, today's check-outs, occupancy counts, room board, upcoming bookings, quick actions |
| Quick navigation | IMPLEMENTED | Sidebar items Dashboard / Rooms / Check-in / Check-out etc.; `main_window._quick_action` |

---

# PHASE 3 — GUESTS + BOOKINGS

**Classification: IMPLEMENTED**

| Area | Status | Evidence |
|------|--------|----------|
| Guest management | IMPLEMENTED | `app/services/guest_service.py` — create/update/search/history; `ui/dialogs/guest_form_dialog.py` |
| Guest fields | IMPLEMENTED | Name, mobile, alternate, address, city, state, country, ID type, ID number, adults, children, special notes — only name + mobile required |
| ID types | IMPLEMENTED | `constants.ID_TYPES`: Aadhaar, Passport, Driving License, Voter ID, PAN, Other |
| ID masking | IMPLEMENTED | `app/ui/formatters.py:mask_id_number` (keeps last 4 digits); used in `GuestDetailsDialog` |
| Booking creation | IMPLEMENTED | `booking_service.create_reservation`; `ui/dialogs/booking_form_dialog.py` |
| Walk-in | IMPLEMENTED | `booking_service.create_walkin` (immediate check-in, room occupied); `ui/dialogs/walkin_dialog.py` (guest → room → rate → payment → check-in) |
| Booking source | IMPLEMENTED | `booking_source_service.py` + `BookingSource` table; 9 defaults; historical source references never deleted (disable-only) |
| Booking numbers | IMPLEMENTED | `NCS-B-<YEAR>-000001`, restart-safe, never reused (`generate_booking_number`) |
| Check-in | IMPLEMENTED | `booking_service.check_in_booking` (only reserved/new; occupies room; optional date/time override) |
| Check-out | IMPLEMENTED | `booking_service.check_out_booking` (records `actual_check_out_at`, starts room cleaning) |
| Cancellation | IMPLEMENTED | `booking_service.cancel_booking` — booking is NOT deleted; stores `cancelled_at`, `cancellation_reason`, `cancelled_by`; frees room if no other reservation |
| No-show | IMPLEMENTED | `booking_service.mark_no_show` — NOT deleted; stores `no_show_at`, `no_show_reason`; frees room |
| Guest history | IMPLEMENTED | `guest_service.get_guest_booking_history`; shown in `GuestDetailsDialog` |
| Availability | IMPLEMENTED | `booking_service.is_room_available` — date-range overlap check; boundary rule: same-day checkout/check-in allowed |
| Booking search / filters | IMPLEMENTED | `search_bookings` (name/mobile/room/booking no), `filter_bookings` (status/period/date) |
| Today's activity | IMPLEMENTED | `get_today_check_ins`, `get_today_check_outs`, `get_upcoming_bookings` (next N days), `get_active_booking_for_room` |
| Booking status history | IMPLEMENTED | `BookingStatusHistory` model + `booking_service.get_booking_status_history`; shown in `BookingDetailsDialog` |
| Manual rates & charges | IMPLEMENTED | `room_rate`, `extra_person_charge`, `early_check_in_charge`, `late_check_out_charge` on the booking (manual entry) |

---

# PHASE 4 — PAYMENTS + FINANCIALS

**Classification: IMPLEMENTED**

| Area | Status | Evidence |
|------|--------|----------|
| Payments | IMPLEMENTED | `app/services/financial_service.py:record_payment`; `Payment` model (date, amount, method, reference, notes, status) |
| Payment methods | IMPLEMENTED | Cash / UPI / QR / Other (`PaymentMethod`) |
| Partial payments | IMPLEMENTED | Multiple payments per booking; any amount ≤ remaining balance accepted |
| Overpayment guard | IMPLEMENTED | `OverPaymentError` when amount exceeds remaining balance |
| Payment status | IMPLEMENTED | Derived `PaymentStatus` PAID / PARTIAL / UNPAID (never stored; `get_payment_status`) |
| Remaining balance | IMPLEMENTED | `get_financial_summary().remaining` = grand_total − total_paid |
| Financial calculations | IMPLEMENTED | `get_financial_summary`: nights, derived room charge (rate × nights), manual charges, subtotal, discount, GST (0 while disabled), grand total, paid, remaining |
| Manual charges | IMPLEMENTED | `add_charge`/`remove_charge` — Extra Mattress / Miscellaneous / Other / extra ROOM; `ChargeType` |
| Discount | IMPLEMENTED | `set_discount` (0 ≤ discount ≤ subtotal) |
| Payment history | IMPLEMENTED | `get_payment_history`, `list_payments` (search + status/date filters); `ui/pages/payments_page.py` |
| Payment reversal/refund | IMPLEMENTED | `reverse_payment` — record kept (status → refunded), never deleted; `reversal_reason` stored |
| Today's collected total | IMPLEMENTED | `get_today_payment_total`, `get_payment_period_total` |
| Money safety | IMPLEMENTED | All money as `Decimal` via `app/services/money.py`; Indian grouping `₹` formatting in `formatters.format_money` |
| Add-payment UI | IMPLEMENTED | `ui/dialogs/add_payment_dialog.py`; reverse from `BookingDetailsDialog` |

---

# PHASE 5 — INVOICE + BILLING

**Classification: IMPLEMENTED**

| Area | Status | Evidence |
|------|--------|----------|
| Invoices | IMPLEMENTED | `Invoice` model (number, booking, date, financials, status, snapshot, pdf path) |
| Invoice numbering | IMPLEMENTED | `NCS-INV-2026-000001`, persistent + unique + restart-safe (`invoice_service.generate_invoice_number`) |
| Invoice lifecycle | IMPLEMENTED | DRAFT → FINALIZED (immutable) / CANCELLED (draft only) — `create_draft_invoice`, `finalize_invoice`, `cancel_invoice` |
| Duplicate-finalized guard | IMPLEMENTED | `DuplicateFinalizedInvoiceError` |
| Invoice snapshot | IMPLEMENTED | `build_snapshot` freezes guest/room/stay/line items/money into `snapshot_json`; finalized invoices read only the snapshot — later edits never rewrite them |
| Invoice service | IMPLEMENTED | `get_or_create_draft_invoice`, `refresh_draft_snapshot`, `get_invoices_for_booking`, `get_finalized_invoice_for_booking` |
| Invoice PDF | IMPLEMENTED | `app/services/invoice_pdf.py` (ReportLab A4, ₹ via TrueType font, logo); `generate_pdf`, `regenerate_pdf`; stored in `invoices/` — separate from reports |
| Invoice preview | IMPLEMENTED | `widgets/invoice_preview_widget.py`; shared render model with the PDF (`build_render_model`) |
| Invoice content | IMPLEMENTED | Hotel info, invoice no/date, guest, mobile, address, room, room type, source, check-in/out, nights, charges, subtotal, discount, total, paid, remaining, payment status + method |
| Invoice history/filters | IMPLEMENTED | `filter_invoices` (search + payment/invoice status + today/week/month/custom); `ui/pages/invoices_page.py` |
| Billing at checkout | IMPLEMENTED | Booking must be CHECKED_OUT before invoicing; invoiceable-state validation |
| GST | IMPLEMENTED (disabled) | GST figures always 0; never printed — property has no GST |

---

# PHASE 6 — ADMIN + REPORTS

**Classification: IMPLEMENTED**

| Area | Status | Evidence |
|------|--------|----------|
| Admin authentication | IMPLEMENTED | `app/services/security_service.py`; `AdminLoginDialog`; `main_window._require_login` — ONLY admin pages require login; reception is login-free |
| Password hashing | IMPLEMENTED | PBKDF2-HMAC-SHA256, per-password 16-byte salt, 210,000 iterations; plaintext never stored (`hash_password` / `verify_password`) |
| First-run setup | IMPLEMENTED | `initialize_admin_password` (no default, no backdoor; refuses overwrite) |
| Password change | IMPLEMENTED | `change_admin_password` (current-password check + min 8 chars + confirm) |
| Failed-login protection | IMPLEMENTED | 5 failed attempts → 30 s lockout (`ADMIN_MAX_FAILED_ATTEMPTS`, `ADMIN_LOCKOUT_SECONDS`) |
| Session handling | IMPLEMENTED | `AdminSession` in-memory inactivity timeout (default 15 min); auto-expiry + message on activity check |
| Logout | IMPLEMENTED | Sidebar Logout; audit logged |
| Admin dashboard | IMPLEMENTED | `ui/pages/admin_dashboard_page.py` — today's check-ins/outs, occupied/vacant/cleaning/reserved, revenue today/week/month/year, collected/outstanding/paid/partial/unpaid, booking-source + payment-method charts, 7-day revenue/booking trends |
| Analytics service | IMPLEMENTED | `app/services/analytics_service.py` — revenue (payment-date based, never double-counted), outstanding, payment overview, source analytics, occupancy (room-night based), room-type report, room performance, booking trend |
| Custom date range | IMPLEMENTED | Revenue/reports accept custom from/to |
| Reports | IMPLEMENTED | `app/services/report_service.py` — Financial, Booking Sources, Occupancy, Booking Trend (presentation-agnostic `ReportData`) |
| Export CSV / Excel / PDF | IMPLEMENTED | `app/services/report_export.py` — CSV (UTF-8-sig), openpyxl workbook, ReportLab PDF; written to `reports/` — separate from invoice PDFs |
| Admin settings | IMPLEMENTED | `ui/pages/admin_settings_page.py` + `admin_settings_service.py` — hotel name/description/address/phone/email, website (validated), logo, admin password, session timeout, booking sources |
| Logo | IMPLEMENTED | Upload / replace / remove (PNG/JPG/JPEG/GIF); copied into `assets/`; old file cleaned |
| Booking source management | IMPLEMENTED | Admin add + enable/disable (disable-only, historical references retained) |
| Audit log | IMPLEMENTED | `app/services/audit_service.py` + `ui/pages/admin_audit_page.py` — login, logout, password change, settings change, source add/disable, logo change, report generation; passwords/secrets never logged |
| Report generation audit | IMPLEMENTED | `ACTION_REPORT_GENERATED` hook used by reports page |
---

# PHASE 7 — RECEPTION WORKFLOW + UI/UX

**Classification: IMPLEMENTED** (with the partial items listed below)

| Area | Status | Evidence |
|------|--------|----------|
| Reception workflow | IMPLEMENTED | Dashboard → bookings → check-in/check-out/payments/invoices via sidebar + quick actions (`main_window._quick_action`) |
| Walk-in workflow | IMPLEMENTED | `WalkInDialog` — guest → room → rate → payment → check-in in one dialog |
| Booking workflow | IMPLEMENTED | `BookingFormDialog` — guest, room (availability-filtered), check-in/out date+time, source, rates, notes, optional advance payment |
| Advance payment at booking | IMPLEMENTED | `create_reservation`/`create_walkin` record optional advance payment (`_record_advance_payment`) |
| Check-in / Check-out access | IMPLEMENTED | Sidebar Check-in (reserved) / Check-out (checked-in) filters; actions in `BookingDetailsDialog` |
| Room status transitions | IMPLEMENTED | Check-in occupies, check-out → cleaning, cancel/no-show frees room; manual correction allowed |
| Search | IMPLEMENTED | `GlobalSearchDialog` (Ctrl+K) via `search_global` — guest name/mobile, booking number, room number; bookings page + guests page search |
| Upcoming bookings | IMPLEMENTED | `get_upcoming_bookings`; dashboard "upcoming" table |
| Payment workflow | IMPLEMENTED | Add payment dialog + reverse; payments page filters; booking details financial summary |
| Invoice access | IMPLEMENTED | Invoices page, `InvoiceDialog` (preview, finalize, PDF open/print/regenerate) |
| Booking details | IMPLEMENTED | `BookingDetailsDialog` — full booking view, charges, payments, actions, status history |
| Guest details | IMPLEMENTED | `GuestDetailsDialog` — guest info, masked ID, booking history |
| Room details | IMPLEMENTED | `RoomDetailsDialog` — status change, notes, active toggle, status history |
| UI/UX polish | IMPLEMENTED | `app/ui/styles.py` QSS theme; `status_badge`, `summary_card`, `empty_state`, `room_card`, `financial_summary`, `bar_chart`, `flow_layout` widgets |
| Keyboard shortcuts | PARTIAL | Only global **Ctrl+K** (global search); no other shortcuts |
| Validation / error handling | IMPLEMENTED | Service-level validators (guest, booking, charge, payment, website) surfaced as friendly dialogs; safe errors written to log |
| Booking status history | IMPLEMENTED | `BookingStatusHistory` recorded on create/check-in/check-out/cancel/no-show; shown in details dialog |
| Room status history | IMPLEMENTED | `RoomStatusHistory` recorded on every room change |
| Payments page queries | IMPLEMENTED | `PaymentsPage` with period/status/search filters |
| ID masking | IMPLEMENTED | `mask_id_number` used in guest details display |

---

# PHASE 8 — BACKUP, RESTORE & DATA SAFETY

**Classification: IMPLEMENTED**

| Area | Status | Evidence |
|------|--------|----------|
| Backup service | IMPLEMENTED | `app/services/backup_service.py` — `create_backup`, `verify_backup_file`, `restore_backup`, `delete_backup_file`, history, retention, auto-backup |
| Backup package format | IMPLEMENTED | `.ncsbackup` = ZIP archive: `hotel.db` + `metadata.json` + `invoices/*.pdf` + `assets/` logo; `BACKUP_VERSION=1`, `SCHEMA_VERSION=8` |
| Consistent snapshot | IMPLEMENTED | SQLite **online backup API** (`sqlite3.Connection.backup`), NOT a raw file copy — valid even mid-write; `PRAGMA integrity_check` + required-table validation before marking VERIFIED |
| Metadata safety | IMPLEMENTED | `metadata.json` carries app/backup/schema versions, created-at, reason, DB SHA-256 + size + table counts, file inventory, `"encrypted": false`. Passwords/authentication secrets are NEVER written into metadata (tested) |
| Restore safety | IMPLEMENTED | Validate → newer-schema block (`IncompatibleBackupError`) → **PreRestore safety backup** of current data → dispose all connections → extract+validate in data dir → atomic `os.replace` → reopen + re-verify → restore invoice PDFs + logo; on failure the previous DB is recovered from the safety backup |
| Restore of missing/corrupt DB | IMPLEMENTED | Works onto a deleted or damaged database (recovery path); history is never required to restore |
| Backup history | IMPLEMENTED | `BackupHistory` model + `get_backup_history` / `last_successful_backup`; failed backups recorded as FAILED and never counted successful |
| Retention | IMPLEMENTED | Keep newest N (default 30, admin-configurable); never deletes the newest; `_apply_retention` runs after each backup |
| Automatic backups | IMPLEMENTED | `is_auto_backup_due` (daily/weekly + `backup_last_success_at`) → `run_auto_backup`; non-blocking `AutoBackupWorker` (QThread) triggered at startup with a status-bar notification |
| Backup settings | IMPLEMENTED | `app/core/config.py` keys: location, auto-enabled, frequency, time, retention, last-success; admin page controls |
| Admin backup page | IMPLEMENTED | `app/ui/pages/admin_backup_page.py` — DB health, location change, Create Backup Now, Restore, Open Folder, automatic-backup settings, history table; gated by admin login (reception cannot reach it) |
| Restore dialog | IMPLEMENTED | `app/ui/dialogs/restore_backup_dialog.py` — file picker (`.ncsbackup`), preview (date/size/version/schema/status), strong warning, safe restore, restart prompt |
| Startup recovery | IMPLEMENTED | `main.py:_resolve_database_startup` — healthy → normal; missing → offer restore (or fresh DB); corrupt → force restore or exit; `_restore_and_continue` |
| Auditing | IMPLEMENTED | `audit_service` actions: backup created, restored, settings changed, location changed, auto changed |
| Reception stays login-free | IMPLEMENTED | Backup/restore is admin-only; no changes to reception pages |
| Backup location | IMPLEMENTED | Default `Documents\Nashik Comfort Stay\Backups` (never the install dir); admin-changeable with write probe; non-default folders auto-created |
| Dashboard hardening | IMPLEMENTED | Eager-loaded `guest`/`room` in today's check-ins/check-outs + upcoming bookings — fixes a latent `DetachedInstanceError` when a restore reintroduces bookings |
| No encryption (documented) | IMPLEMENTED | Metadata explicitly states `encrypted: false`; design decision documented in the service docstring |

---

# PHASE 9 - OTA PAID-ONLINE BOOKINGS

Booking sources **Agoda, FabHotels, MakeMyTrip and Goibibo** can be marked
**"Paid Online"** — the guest already prepaid the OTA, so the hotel records
nothing for the room. **Booking.com is deliberately excluded** (its bookings
are always collected at the hotel), as are Walk-in, Direct Call, Website,
Other.

- New `PaymentMethod.ONLINE` ("Online") added to the payment methods list.
- New `OTA_PAID_ONLINE_SOURCES` constant (`app/core/constants.py`).
- New `bookings.paid_online` boolean column (model + idempotent migration;
  included in the legacy table-rebuild path).
- `booking_service.create_reservation` / `create_walkin` accept
  `paid_online=True`; the booking is flagged `paid_online` and **no payment row
  is created** (the hotel records nothing for the room — the guest already paid
  the OTA; only Early Check-in / Late Check-out charges can apply at the hotel).
  Requesting paid-online for a non-OTA source raises `BookingValidationError`.
- New-Booking dialog shows a "Payment Arrangement" choice (Pay at Hotel /
  Paid Online) **only when an OTA source is selected**; while "Paid Online" is
  chosen the Room Rate and Extra Person fields are hidden (rate forced to 0)
  and the Advance Payment section is hidden — only Early Check-in / Late
  Check-out remain. Walk-in dialog unchanged (always Walk-in source).
- Booking Details shows "Payment Arrangement: Paid Online / Pay at Hotel"
  for OTA-sourced bookings only.
