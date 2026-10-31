# KEMS Library Portal — Kasturba English Medium School

A school library borrowing register built with **Flask**, using SQLite for local development or **Neon PostgreSQL** for a persistent hosted deployment. It records which student borrowed which book, when it was borrowed, an optional expected return date, and when it was returned.

## Features

- First-run setup for the librarian account and password hashing.
- Maintain a class-wise student register for Classes 6–12 and divisions A–D.\n- Sort students by class, division and roll number; open an individual student history.\n- Link every new borrowing record to a registered student.\n- Track book-summary status as pending, submitted or not needed.\n- Export class student registers to CSV.
- Automatically records the borrowing date and time.
- Search records by book, student, class or roll number.
- Filter currently borrowed, returned and all records.
- Return workflow preserves the original borrowing entry.
- Edit corrections and view activity history.
- Dashboard counts for total records, currently borrowed, overdue and returned.
- CSV export; SQLite backup is available in local SQLite mode. Hosted PostgreSQL deployments should use Neon backups and CSV exports.
- Responsive interface for computers, tablets and phones.
- CSRF protection, parameterized SQL, database indexes, and security headers.

## Requirements

- Python 3.10 or newer (Python 3.11+ recommended).
- Windows, macOS or Linux.
- Internet access is needed only to install dependencies. The app can run locally afterward.

## Quick start — Windows

1. Download or clone this repository and open the project folder in Command Prompt.
2. Create a virtual environment:

   ```bat
   py -3 -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:

   ```bat
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Start the app:

   ```bat
   run_windows.bat
   ```

5. Open http://127.0.0.1:8000 and create the first librarian account. Use a unique password with at least 12 characters.

You can also start the server manually with `waitress-serve --listen=127.0.0.1:8000 app:app`.

## Share it on school Wi-Fi / LAN

Only do this with school approval and on a trusted network. Run `run_windows_lan.bat` on the host computer, find its local IPv4 address, then open `http://HOST-IP:8000` from another device on the same network. Do not configure router port forwarding or expose this first version directly to the public internet. The local-network version uses HTTP; public deployment requires HTTPS and additional hardening.

## Accounts and admin commands

The first visit to `/setup` creates the initial librarian account. To create another librarian from the terminal:

```bash
flask --app app create-admin
```

To check database integrity:

```bash
flask --app app check-db
```

To reset a librarian password:

```bash
flask --app app reset-password
```

Do not share librarian credentials with students.

## Data storage and privacy

Without `DATABASE_URL`, SQLite stores data in `instance/library.db`; a generated session signing key is stored in `instance/secret_key`. With `DATABASE_URL`, application records are stored in Neon PostgreSQL. These local files are intentionally ignored by Git. The database contains student names and borrowing history and must be treated as confidential school data. Do not commit the `instance` folder or share backups publicly.

Optional environment variables:

- `DATABASE_URL`: Neon PostgreSQL connection string. Prefer the pooled connection string (`-pooler`) for the hosted Flask service. When set, the app creates/uses the PostgreSQL schema automatically. The PostgreSQL driver is installed from `requirements.txt`.
- `LIBRARY_DATABASE`: path to an alternate SQLite database for local development.
- `APP_SECRET_KEY`: secret key provided by the administrator; otherwise a random key is generated and saved locally.
- `LIBRARY_TIMEZONE`: timezone for recorded dates; defaults to `Asia/Kolkata`.
- `COOKIE_SECURE=1`: use only after HTTPS is configured; do not enable for local HTTP.

## Backups and restore

1. Export CSV from **Records** for a portable copy of borrowing records.
2. For SQLite mode, use **Download backup** to download a full database backup.
3. For Neon PostgreSQL, configure and test Neon backups/restore options in the Neon console; the SQLite backup endpoint is not a PostgreSQL dump.
4. Keep backups on separate school-approved storage in a secure location and periodically test restoring them.

To restore a SQLite backup, stop the server, preserve the current database, replace `instance/library.db`, and restart. Never overwrite a live database while the app is running. CSV is useful for spreadsheets but is not a full database backup.

## Good operating practices

1. Confirm student details before saving.
2. Use a consistent class format (for example, always `10-A`).
3. Record each physical book as a separate borrowing entry.
4. Mark a book returned only after it has physically been handed back.
5. Correct individual records using the edit screen rather than deleting the database.
6. This version tracks student records and borrowing transactions; it does not yet provide a full book catalogue or shelf locations. The class division options are currently A–D and should be adjusted if the school uses a different division scheme.
7. Availability is only accurate if the librarian updates returns.
8. Get school approval before digitizing paper registers, and store only the student data the school has authorized.

## Project layout

```text
app.py
requirements.txt
run_windows.bat
run_windows_lan.bat
START_HERE.txt
static/
  app.js
  style.css
templates/
tests/
  test_app.py
```

## Run tests

```bash
python -m unittest discover -s tests -v
```

The tests should use a temporary database, not the live library database.


## Neon / Render deployment

1. Create a Neon project and keep its database password private. If a connection string has been shared, rotate the database password first.
2. In Neon, copy the pooled connection string with connection pooling enabled.
3. In Render → your web service → **Environment**, add `DATABASE_URL` with that connection string. Do not commit it to GitHub or put it in frontend code.
4. Keep `APP_SECRET_KEY` set to a long, random secret and use HTTPS so secure cookies can be enabled with `COOKIE_SECURE=1`.
5. After deployment, open the site and create the first librarian account if the PostgreSQL database is empty. Test with a dummy borrowing record before entering real school data.

The app creates PostgreSQL tables automatically but does not automatically import existing records from an old SQLite database. Export/plan a migration before switching if you already have records you need to preserve. Confirm school approval and privacy requirements before entering real student data.
