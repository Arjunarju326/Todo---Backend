# Personal Task & Finance Organizer — Django Backend

Python Django REST Framework backend powered by PostgreSQL (`tododb`).

## Tech Stack

- **Framework**: Django 4.2+ & Django REST Framework (DRF)
- **Database**: PostgreSQL (`tododb`) via `psycopg2-binary`
- **Cloud Storage**: Google Cloud Storage (`django-storages`, `google-cloud-storage`)
- **CORS**: `django-cors-headers`

## Architecture & Directory Structure

```text
backend/
├── core/                  # Project configuration
│   ├── settings.py        # Database, CORS, DRF, and GCS settings
│   ├── urls.py            # Root URL dispatching
│   ├── wsgi.py
│   └── asgi.py
├── api/                   # Main API application
│   ├── models.py          # Relational models (Task, Transaction, Debt, Habit, etc.)
│   ├── serializers.py     # DRF serializers with camelCase & _id mappings
│   ├── views.py           # REST views handling business logic
│   ├── urls.py            # API routes
│   ├── admin.py           # Django admin registrations
│   └── migrations/        # Database schema migrations
├── manage.py
├── requirements.txt
├── .env.example
└── .env
```

## Setup & Running Locally

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and verify database credentials:

```bash
cp .env.example .env
```

### 3. Apply database migrations

```bash
python manage.py migrate
```

### 4. (Optional) Seed demo workspace data

```bash
python manage.py shell -c "from api.views import SeedView; from rest_framework.test import APIRequestFactory; factory = APIRequestFactory(); req = factory.post('/api/seed', {'force': True}, format='json'); res = SeedView.as_view()(req); print(res.data)"
```

### 5. Start the development server

```bash
python manage.py runserver 0.0.0.0:8000
```

The API will be available at `http://127.0.0.1:8000/api/`.

## API Endpoints

- `GET /api/dashboard` — Today's priorities, liabilities, learning, and 4 daily focus questions.
- `GET/POST/PUT/DELETE /api/tasks` — Tasks management with `today`, `overdue`, and `upcoming` filters.
- `GET/POST/PATCH/DELETE /api/finance` — Ledger transactions, debts, repayments, and budgets.
- `GET/POST/PATCH/DELETE /api/growth` — Learning milestones, hours tracking, and job application pipeline.
- `GET/POST/PATCH/DELETE /api/habits` — Habits, daily completion tracking, and streaks.
- `GET/POST/PATCH/DELETE /api/notes` — Quick capture inbox notes.
- `GET/PUT /api/settings` — User preferences, currency, and database latency.
- `POST /api/seed` — Seed or reset demo data.

