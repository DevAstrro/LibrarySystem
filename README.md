# School Library Desk

A locally hosted school library borrowing register built with **Flask** and **SQLite**. It records which student borrowed which book, when it was borrowed, an optional expected return date, and when it was returned.

## Features

- First-run setup for the librarian account and password hashing.
- Record book title, student name, class/section and roll number.
- Automatically records the borrowing date and time.
- Search records by book, student, class or roll number.
- Filter currently borrowed, returned and all records.
- Return workflow preserves the original borrowing entry.
- Edit corrections and view activity history.
- Dashboard counts for total records, currently borrowed, overdue and returned.
- CSV export and downloadable SQLite database backup.
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

By default, SQLite stores data in `instance/library.db`; a generated session signing key is stored in `instance/secret_key`. These files are intentionally ignored by Git. The database contains student names and borrowing history and must be treated as confidential school data. Do not commit the `instance` folder or share backups publicly.

Optional environment variables:

- `LIBRARY_DATABASE`: path to an alternate SQLite database.
- `APP_SECRET_KEY`: secret key provided by the administrator; otherwise a random key is generated and saved locally.
- `LIBRARY_TIMEZONE`: timezone for recorded dates; defaults to `Asia/Kolkata`.
- `COOKIE_SECURE=1`: use only after HTTPS is configured; do not enable for local HTTP.

## Backups and restore

1. Sign in and use **Records → Database backup** to download a full SQLite backup.
2. Keep a copy on separate school-approved storage in a secure location.
3. Periodically test restoring a backup to a separate test database.

To restore a verified backup, stop the server, preserve the current database, replace `instance/library.db` with the backup, and restart the server. Never overwrite the live database while the app is running. CSV is useful for spreadsheets but is not a full database backup.

## Good operating practices

1. Confirm student details before saving.
2. Use a consistent class format (for example, always `10-A`).
3. Record each physical book as a separate borrowing entry.
4. Mark a book returned only after it has physically been handed back.
5. Correct individual records using the edit screen rather than deleting the database.
6. This version tracks borrowing transactions; it does not yet provide the full catalogue or shelf locations.
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
