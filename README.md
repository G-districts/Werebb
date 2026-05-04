# Where Bazinc — Community Alert & Tracking Network

A Python/Flask PWA for community sighting reports, real-time alerts, and location tracking.

## Quick Start

```bash
pip install flask
python run.py
```

Open http://localhost:5000

**Default Admin Login:**
- Phone: `0000000000`
- Password: `admin123`
> ⚠️ Change these immediately via the database or admin console!

---

## Features

### For Users
- 📱 **PWA** — install to homescreen on iOS/Android
- 🗺 **Live Map** — see all confirmed sightings in real-time
- ⚑ **Report Sightings** — click map or use GPS to file a report
- 📍 **Share Location** — let admin know where you are
- 🔔 **Push Notifications** — receive alerts in real-time
- 🔐 **Phone-number accounts** — username IS your phone number

### For Admins
- 🖥 **Command Center** — full dashboard with live map
- 👁 **All Sightings** — review, confirm, or dismiss reports
- 📡 **Broadcast Alerts** — send high/medium/low severity alerts
- 🎯 **Area Targeting** — target alerts to a geographic radius
- 👤 **User Management** — approve, revoke, promote users
- ⚙ **App Settings** — change name, subject info, map defaults

### PWA Features
- Service Worker caching for offline use
- Push notification support
- Installable to homescreen
- Mobile-optimized UI

---

## Configuration

All settings are managed via the admin console (Settings tab):

| Setting | Description |
|---|---|
| App Name | Name shown throughout the app |
| Subject Name | Who is being tracked |
| Subject Description | Instructions shown to users |
| Map Center | Default lat/lng for the map |
| Allow Registration | Open or closed sign-ups |
| Require Approval | Manual user approval |

---

## Database

SQLite database at `wherebazinc.db` — auto-created on first run.

Tables: `users`, `sightings`, `alerts`, `alert_reads`, `settings`

---

## Deployment (Production)

```bash
pip install flask gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

For HTTPS (required for PWA on mobile), put behind nginx with SSL.
