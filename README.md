# Provision

Smart household food inventory and pantry management system.

---

## Tech Stack

- **Frontend:** Swift + native SwiftUI (Deployment Target: iOS 26.5+)
- **Backend:** FastAPI + SQLAlchemy 2.0 + SQLite
- **Authentication:** JWT access tokens (HS256) + Argon2 password hashing (`pwdlib[argon2]`)
- **Token Storage:** Native iOS Keychain Services (`Security` framework)

---

## Project Structure

```text
Provision/
├── backend/                      # FastAPI + SQLite REST API
├── frontend/                     # Native SwiftUI iOS application (Xcode project)
└── provision_reference_screens/  # Design and reference exports
```

---

## Getting Started

### Backend Execution

From the repository root:

```bash
# 1. Enter backend directory
cd backend

# 2. Configure local environment variables
cp .env.example .env
# Set your local JWT_SECRET_KEY in .env

# 3. Sync dependencies
uv sync

# 4. Apply database migrations
uv run alembic upgrade head

# 5. Run automated test suite
uv run pytest

# 6. Start local development server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Interactive OpenAPI Swagger Docs: `http://localhost:8000/docs`

---

### Frontend Execution

Open the iOS project in Xcode:

```bash
open frontend/frontend.xcodeproj
```

- **Deployment Target:** iOS 26.5+
- **Frontend:** Native SwiftUI
- **Simulator Development:** Connects by default to `http://127.0.0.1:8000/api/v1`.
- **Physical Device Testing:** Set your development Mac's LAN IP in `APIEnvironment.localDeviceHost` (`frontend/Core/APIClient.swift`). Local HTTP traffic is permitted via `NSAllowsLocalNetworking`.

---

## Important Domain Limitation

> **Notice:** Provision currently authenticates access to a single shared household pantry. Per-user and multi-household data isolation is reserved for future development.

---

## Midterm Project Status (~50% Complete)

This project is intentionally at **approximately 50% completion** for the iOS Development midterm milestone:

### Implemented (Midterm Scope):
- User registration, login, and `/auth/me` verification with Argon2 password hashing.
- JWT access tokens stored in native iOS Keychain with automatic session restoration.
- Protected household pantry API: Catalog, Storage Locations, Inventory Batches, FEFO Consumption, Discard, Physical Count Adjustments, Shopping List, and Household Analytics.
- Native SwiftUI 5-tab app shell (`Home`, `Inventory`, `Scan`, `Shopping`, `Analytics`), user profile/logout sheet, and Product Detail with FEFO batch inspection.
- Prototype Scan UI simulation.

### Reserved for Final Project:
- Real camera and `AVFoundation` barcode scanning pipeline.
- `VisionKit` OCR for receipt intake and package expiration date extraction.
- Automatic inventory commit from live intake scanning.
- Offline-first local database caching (SwiftData / Core Data).
- Background expiration alert notifications.
