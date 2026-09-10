# Provision

Smart household food inventory and pantry management system powering automated batch tracking, First Expired First Out (FEFO) consumption logic, and household decision intelligence.

---

## Project Structure

```text
Provision/
├── backend/                      # FastAPI + SQLAlchemy 2.0 REST API (PostgreSQL / SQLite fallback)
├── frontend/                     # Native SwiftUI iOS application (Xcode project)
└── provision_reference_screens/  # Extracted Stitch/Figma UI reference screens
```

---

## Getting Started

### Backend Setup & Execution

From the repository root:

```bash
# 1. Enter backend directory
cd backend

# 2. Sync dependencies
uv sync

# 3. Run automated tests
uv run pytest

# 4. Start local development server (defaults to http://127.0.0.1:8000)
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Interactive OpenAPI Swagger Docs: `http://localhost:8000/docs`

---

### Frontend Setup & Execution

Open the iOS project in Xcode:

```bash
open frontend/frontend.xcodeproj
```

- **Deployment Target:** iOS 26.5+ (Swift 6 / SwiftUI)
- **Architecture:** MVVM with reactive `ObservableObject` ViewModels and native async/await networking.
- **Simulator Execution:** Defaults to `http://127.0.0.1:8000/api/v1`.
- **Physical Device Execution:** Set your development Mac's local LAN IP in `APIEnvironment.localDeviceHost` (`Core/APIClient.swift`). Local HTTP communication is permitted via `NSAllowsLocalNetworking`.

---

## Project Status

This repository is currently at **approximately 50% completion for the iOS Development midterm project**:
- Complete backend domain model, FEFO consumption engine, analytics, and 21 passing pytest tests.
- Complete frontend core UI architecture: 5-tab pantry navigation (`Home`, `Inventory`, `Scan`, `Shopping`, `Analytics`), product detail, and FEFO batch consumption flows.
- **Midterm Scope Note:** Camera-based `AVFoundation` barcode capture, receipt OCR, and `VisionKit` text recognition are intentionally simulated prototypes at this stage and reserved for the final project.
