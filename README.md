# 🏨 NASHIK COMFORT STAY
### A Complete Hotel Management System — Built for Real-World Reception Operations

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&pause=1000&color=D6AD65&center=true&vCenter=true&width=750&lines=Simplifying+Hotel+Management.;Designed+for+Real+Reception+Workflows.;Offline-First.+Reliable.+Practical." alt="Typing SVG" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/PySide6-Qt-41CD52?style=for-the-badge&logo=qt&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-Local%20Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLAlchemy-ORM-D71F00?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" />
</p>

<p align="center">
  <strong>A practical, offline-first hotel management solution designed to handle everyday hotel operations from a single Windows computer.</strong>
</p>

---

## ◈ Overview

**Nashik Comfort Stay** is a desktop-based Hotel Management System developed to simplify and organize the daily operations of a small hotel.

From managing rooms and guest records to handling reservations, check-ins, payments, invoices, reports and backups, the application brings essential reception and administrative workflows into one place.

Unlike cloud-dependent hotel platforms, this application follows a **local-first architecture**. Its database and operational files stay on the local computer, allowing normal operation without an internet connection.

### Core objectives

- Simplify daily reception operations.
- Maintain organized guest and booking records.
- Track room availability and housekeeping status.
- Manage payments, balances and invoices.
- Provide useful financial and occupancy reports.
- Keep hotel data locally accessible and backed up.

---

## ◈ System Architecture

```text
             NASHIK COMFORT STAY
             HOTEL MANAGEMENT
                     │
          ┌──────────┴──────────┐
          │                     │
     RECEPTION              ADMIN PANEL
          │                     │
   ┌──────┼──────┐        ┌──────┼──────┐
   │      │      │        │      │      │
 Rooms  Guests Bookings  Reports Finance Settings
   │      │      │        │      │      │
   └──────┴──────┴────────┴──────┴──────┘
                     │
              SERVICE LAYER
                     │
              SQLAlchemy ORM
                     │
                SQLite DB
                     │
          Local Files & Backups
```

---

## ◈ Key Features

### 🛎️ Reception Dashboard
- Live room availability overview.
- Today's check-ins and check-outs.
- Occupancy statistics.
- Upcoming reservations.
- Quick actions for common reception tasks.

### 🏠 Room Management
- Room-wise visual status board.
- AC and Non-AC room categories.
- Vacant, Occupied, Reserved, Cleaning and Maintenance statuses.
- Room notes and status history.
- Room availability tracking.

### 👤 Guest Management
- Create, update and search guest records.
- Guest contact and address details.
- Multiple identification document types.
- Masked ID numbers for safer display.
- Guest-wise booking history.

### 📅 Booking Management
- Advance reservations and walk-in bookings.
- Booking availability validation.
- Manual room rates and additional charges.
- Booking source tracking.
- Check-in and check-out workflows.
- Cancellation and no-show records.
- Unique booking numbers that are never reused.

### 💳 Payment Management
- Cash, UPI, QR and other payment methods.
- Full and partial payments.
- Paid, Partial and Unpaid status tracking.
- Discounts and additional charges.
- Payment history and reversal records.
- Outstanding balance calculation.

### 🧾 Invoice & Billing
- Draft and finalized invoices.
- Unique invoice numbering.
- PDF invoice generation.
- Invoice preview and history.
- Payment and balance details.
- Finalized invoice snapshots.
- GST disabled as per the property's requirements.

### 📊 Admin Dashboard & Analytics
- Password-protected administration.
- Revenue overview: daily, weekly, monthly and yearly.
- Occupancy and room performance analytics.
- Booking source statistics.
- Payment method statistics.
- Booking and revenue trends.
- Custom date-range reports.

### 📁 Reports & Data Safety
- Financial reports.
- Booking source reports.
- Occupancy reports.
- Booking trend reports.
- CSV, Excel and PDF exports.
- Local database backups.
- Backup integrity verification.
- Backup restoration and retention management.

---

## ◈ Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Core application logic |
| PySide6 | Desktop graphical interface |
| SQLAlchemy 2.x | Database ORM |
| SQLite | Local database |
| ReportLab | PDF invoices and reports |
| openpyxl | Excel exports |
| pytest | Automated testing |
| PyInstaller | Windows executable packaging |

---

## ◈ Project Structure

```text
NCS_application/
│
├── app/
│   ├── core/              # Configuration, constants and paths
│   ├── database/          # Database, models and migrations
│   ├── services/          # Business logic and operations
│   └── ui/                # Desktop interface
│
├── assets/
│   └── icons/
│
├── scripts/
│   ├── build_windows.py
│   ├── make_icon.py
│   └── smoke_run.py
│
├── tests/                 # Automated tests
│
├── main.py                # Application entry point
├── requirements.txt
├── NashikComfortStay.spec
├── PROJECT_PHASES.md
└── README.md
```

---

## ◈ Getting Started

### Prerequisites

- Windows
- Python 3.11 or later
- pip

### 1. Clone the repository

```bash
git clone https://github.com/DSnext412-jpg/NCS_application.git
```

```bash
cd NCS_application
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the application

```bash
python main.py
```

---

## ◈ Windows Executable

The project includes a Windows build script that runs tests and a smoke check before packaging the application.

```bash
python scripts/build_windows.py
```

The primary packaged application is generated at:

```text
release/
└── NashikComfortStay.exe
```

The executable is designed to run without requiring a separate Python installation.

**Local data location:**

```text
%LOCALAPPDATA%\NashikComfortStay\
```

The database, invoices, reports, logs, backups and hotel logo are stored outside the executable.

---

## ◈ Testing

Run the automated test suite:

```bash
python -m pytest
```

Run the headless application smoke check:

```bash
python scripts/smoke_run.py
```

Tests use temporary SQLite databases rather than the hotel's production data.

---

## ◈ Project Configuration

The application initializes the following standard rooms automatically:

| Room Numbers | Category | Count |
|---|---|---:|
| 202–207 | AC | 6 |
| 208–212 | Non-AC | 5 |
| **Total** | | **11** |

Other implementation details:

- Room rates are entered manually per booking.
- Reception access does not require login.
- Admin access requires a password configured on first use.
- Admin passwords are stored as PBKDF2 hashes.
- Booking and invoice records use persistent unique numbering.
- GST calculations and printing remain disabled.

---

## ◈ Engineering Principles

This project focuses on practical software engineering decisions:

- **Local-first:** Normal operation does not depend on a remote server.
- **Modular architecture:** UI, services, database and core logic are separated.
- **Data integrity:** Financial and booking records retain important history.
- **Security:** Admin authentication and password hashing.
- **Reliability:** Automated tests, smoke checks and verified backups.
- **Maintainability:** Structured modules and documented development phases.

---

## ◈ Development Documentation

For a detailed breakdown of the implementation, milestones and completed modules, see:

📘 [PROJECT_PHASES.md](PROJECT_PHASES.md)

---

## ◈ About the Project

Nashik Comfort Stay is a real-world-oriented software project built around the operational requirements of a hotel reception.

The goal was not simply to create a CRUD application, but to build a structured desktop system that handles interconnected workflows such as room availability, reservations, payments, billing, reporting and local data management.

---

<p align="center">
  <strong>Built with Python. Designed for real operations.</strong>
</p>

<p align="center">
  <a href="https://github.com/DSnext412-jpg">GitHub Profile</a> •
  <a href="https://dipak-sonawane.onrender.com/">Portfolio</a> •
  <a href="https://github.com/DSnext412-jpg/NCS_application">Repository</a>
</p>

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:171717,50:6B5635,100:D6AD65&height=110&section=footer" />
</p>
