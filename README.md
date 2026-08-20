# Nashik Comfort Stay — Hotel Management System

A local-first, offline-first Windows desktop application for **Nashik Comfort Stay**,
a small luxury-room stay property in Nashik.

## Purpose

A complete hotel management system covering the full reception workflow — room
management, guest management, bookings, check-in/check-out, payments, invoicing,
admin analytics, reports and automatic backups. Everything runs locally on a
single machine; no internet connection or server is required.

## Features

- **Reception dashboard** — live room board, today's check-ins/check-outs,
  occupancy counts, upcoming bookings and one-click quick actions.
- **Rooms** — room-card grid with status badges (Vacant / Occupied / Reserved /
  Cleaning / Maintenance), AC & Non-AC types, notes and status history.
- **Guests** — add, edit, view and search guests; ID masking; per-guest booking
  history.
- **Bookings** — reservations and walk-ins; advance payment; manual rates,
  extra-person and early/late check charges; availability checks; booking
  numbers that are never reused.
- **Check-in / Check-out** — lifecycle with status history; check-out blocks
  until the balance is settled, applies an editable late check-out charge when
  the guest leaves late, records the actual check-out time and marks the room
  for cleaning.
- **Payments** — cash / UPI / QR / other; partial payments; discounts; payment
  reversal (records kept, never deleted).
- **Invoices** — draft → finalize → PDF (ReportLab); print / open / re-generate;
  cancelled drafts retained in history. GST is disabled (property has none).
- **Admin** — password-protected (PBKDF2, no default password, no backdoor):
  revenue KPIs, booking-source and payment-method charts, financial / source /
  occupancy / booking-trend reports with CSV/Excel/PDF export, hotel settings
  and logo, booking-source management, full audit log.
- **Backup & data safety** — `.ncsbackup` packages (database + invoices + logo)
  via the SQLite online-backup API, integrity-verified, with safe restore,
  retention and automatic daily/weekly backups.

## Technology stack

- Python 3.11+
- PySide6 (Qt for Python)
- SQLAlchemy 2.x
- SQLite (local database, `hotel.db`)
- ReportLab (invoice PDFs), openpyxl (Excel exports)
- pytest

## Windows EXE (end users)

### Running the application

1. Copy `NashikComfortStay.exe` to the Windows computer.
2. Double-click the EXE.
3. The application creates its local data automatically.
4. No Python installation is required.
5. No internet connection is required for normal operation.

### Data location

`%LOCALAPPDATA%\NashikComfortStay\`

(e.g. `C:\Users\<User>\AppData\Local\NashikComfortStay\`)

The database, backups, invoices, reports, logs and the uploaded hotel logo
are stored here — **outside** the EXE.

**IMPORTANT:** Do not delete this folder unless you intentionally want to
remove the hotel's local data.

### Backups

Use the application's **Backup & Restore** feature regularly (Admin →
Backup & Restore). Backups are saved to
`Documents\Nashik Comfort Stay\Backups`.

Each computer has its own local hotel database. To move data to another
computer, create a backup on one machine and restore it on the other
(Admin → Backup & Restore → Restore).

### Notes for end users

- An unsigned, locally built EXE may trigger a Windows SmartScreen
  "unknown publisher" warning. This is normal for internally built
  software; choose "More info" → "Run anyway" when you trust the source.
- Reception screens need no login; Admin screens require the admin
  password, which is set on first use.

## For developers

### Installation

### 1. Create a virtual environment

```powershell
python -m venv .venv
```

### 2. Activate it

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## Test

```powershell
python -m pytest
```

Tests use temporary SQLite databases in `tmp_path` and never touch production
data. Run a headless smoke check with:

```powershell
python scripts/smoke_run.py
```

### Building the Windows EXE

A reproducible build script runs the tests, the smoke test, then builds the
one-file windowed EXE and assembles the `release/` directory:

```powershell
python scripts/build_windows.py
```

Requirements: `pyinstaller` installed in the virtual environment
(`.venv\Scripts\python.exe -m pip install pyinstaller`).

- Primary deliverable: `release\NashikComfortStay.exe` (one-file, windowed,
  no console window).
- Portable/ONEDIR troubleshooting build: `NashikComfortStayPortable.spec`
  (output in `dist\NashikComfortStayPortable\`).
- The build never touches production data or `%LOCALAPPDATA%\NashikComfortStay\`.

## Data locations

Writable application data (database, backups, invoices, reports, logs) is
resolved through the centralized path manager in `app/core/paths.py`:

- Development mode: stored under the project root (`data/`, `backups/`, ...).
- Packaged build: `%LOCALAPPDATA%\NashikComfortStay\`.
- Override for testing/CI: set the `NCS_APP_DATA` environment variable.

The SQLite database file is `data/hotel.db`.

## Notes

- The 11 standard rooms (AC 202–207, Non-AC 208–212) are seeded automatically
  on first run. Room rates are **not** hard-coded; they are entered manually per
  booking.
- A 12th guest/property room is intentionally not seeded; Admin can add rooms
  via the settings architecture.
- OTA bookings from **Agoda, FabHotels, MakeMyTrip and Goibibo** (not
  Booking.com) can be marked **Paid Online** when the guest already prepaid the
  OTA. For such bookings the Room Rate and Extra Person fields are hidden (the
  hotel records nothing for the room) and only Early Check-in / Late Check-out
  charges can be added. Bookings can also be left as **Pay at Hotel**.
- A reservation whose check-in is in the future does **not** mark the room as
  "Reserved" — the room stays available so it can still be used before the
  check-in date (the reservation still blocks its own dates).
- GST is **disabled** and remains disabled (the property has no GST) — GST
  figures are always zero and never printed.
- Reception is login-free; only Admin pages require a password. The admin
  password is set on first use (stored as a PBKDF2 hash, never plaintext).
- Backups are intentionally **not** encrypted — a documented design choice for
  a local, offline, single-machine application.
