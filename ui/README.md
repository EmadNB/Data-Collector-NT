# Django country + zone selector

## What this is
- A Django website where **all countries start red** on a map.
- When you **activate** a country from a list, it becomes **green** on the map.
- After activating a country, you can select **zones** (your provided codes) for that country.
- Selections are stored in the **session** and exposed via a small JSON API so you can reuse them “for something”.

## Setup (Windows / PowerShell)

Create and activate a venv (recommended):

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run migrations (this also seeds your countries/zones):

```bash
python manage.py migrate
```

Start server:

```bash
python manage.py runserver
```

Open:
- Main UI: `http://127.0.0.1:8000/`
- Current selection JSON: `http://127.0.0.1:8000/api/selection/`

## Where to add your “something”
Use the selection JSON from:
- `GET /api/selection/`

Or read it server-side from session key:
- `request.session["country_zone_selection"]`

