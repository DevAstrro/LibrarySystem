from __future__ import annotations

import csv
import hmac
import io
import os
import re
import secrets
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from flask import (
    Flask, abort, flash, g, make_response, redirect,
    render_template, request, send_file, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # PostgreSQL is optional for local SQLite development.
    psycopg = None
    dict_row = None

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DEFAULT_DB = INSTANCE_DIR / "library.db"
LOCAL_TZ = ZoneInfo(os.environ.get("LIBRARY_TIMEZONE", "Asia/Kolkata"))


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ).replace(microsecond=0)


def timestamp_now() -> str:
    return local_now().isoformat()


def get_database_path() -> Path:
    configured = os.environ.get("LIBRARY_DATABASE")
    path = Path(configured).expanduser() if configured else DEFAULT_DB
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_or_create_secret_key() -> str:
    """Persist a random signing key so sessions survive ordinary restarts."""
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    key_path = INSTANCE_DIR / "secret_key"
    try:
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as key_file:
            key_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    return key_path.read_text(encoding="utf-8").strip()


def connect_db(path: Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path or get_database_path()), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database(path: Path | None = None) -> None:
    with connect_db(path) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_title TEXT NOT NULL,
                student_name TEXT NOT NULL DEFAULT '',
                class_name TEXT NOT NULL,
                roll_number TEXT NOT NULL DEFAULT '',
                borrowed_at TEXT NOT NULL,
                due_date TEXT NOT NULL DEFAULT '',
                returned_at TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_by INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(loan_id) REFERENCES loans(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_loans_borrowed_at ON loans(borrowed_at);
            CREATE INDEX IF NOT EXISTS idx_loans_returned_at ON loans(returned_at);
            CREATE INDEX IF NOT EXISTS idx_loans_class_roll ON loans(class_name, roll_number);
            CREATE INDEX IF NOT EXISTS idx_loans_book_title ON loans(book_title);
            CREATE INDEX IF NOT EXISTS idx_audit_loan_id ON audit_logs(loan_id);
        """)


class HybridRow(dict):
    """Mapping row that also supports SQLite-style numeric indexing."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid
    def fetchone(self):
        return self._cursor.fetchone()
    def fetchall(self):
        return self._cursor.fetchall()
    @property
    def rowcount(self):
        return self._cursor.rowcount


class PostgresConnection:
    def __init__(self, raw):
        self.raw = raw
    def execute(self, sql, params=()):
        query = sql.replace(" COLLATE NOCASE", "").replace(" LIKE ", " ILIKE ")
        query = query.replace("?", "%s")
        returning_id = bool(re.match(r"\s*INSERT\s+INTO\s+(users|loans|audit_logs)\b", query, re.I)) and "RETURNING" not in query.upper()
        if returning_id:
            query = query.rstrip().rstrip(";") + " RETURNING id"
        cur = self.raw.cursor()
        cur.execute(query, params)
        lastrowid = None
        if returning_id:
            row = cur.fetchone()
            if row:
                lastrowid = row["id"]
        return PostgresCursor(cur, lastrowid)
    def commit(self):
        self.raw.commit()
    def rollback(self):
        self.raw.rollback()
    def close(self):
        self.raw.close()


def connect_postgres(url: str) -> PostgresConnection:
    if psycopg is None:
        raise RuntimeError("PostgreSQL support is missing. Install dependencies from requirements.txt.")
    raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    return PostgresConnection(raw)


def initialize_postgres(url: str) -> None:
    connection = connect_postgres(url)
    try:
        statements = [
            """CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS loans (
                id BIGSERIAL PRIMARY KEY, book_title TEXT NOT NULL, student_name TEXT NOT NULL DEFAULT '',
                class_name TEXT NOT NULL, roll_number TEXT NOT NULL DEFAULT '', borrowed_at TEXT NOT NULL,
                due_date TEXT NOT NULL DEFAULT '', returned_at TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
                created_by BIGINT NOT NULL REFERENCES users(id), updated_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS audit_logs (
                id BIGSERIAL PRIMARY KEY, loan_id BIGINT REFERENCES loans(id), user_id BIGINT REFERENCES users(id),
                action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_loans_borrowed_at ON loans(borrowed_at)",
            "CREATE INDEX IF NOT EXISTS idx_loans_returned_at ON loans(returned_at)",
            "CREATE INDEX IF NOT EXISTS idx_loans_class_roll ON loans(class_name, roll_number)",
            "CREATE INDEX IF NOT EXISTS idx_loans_book_title ON loans(book_title)",
            "CREATE INDEX IF NOT EXISTS idx_audit_loan_id ON audit_logs(loan_id)",
        ]
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_path=str(INSTANCE_DIR), instance_relative_config=False)
    supplied_config = test_config or {}
    app.config.update(
        SECRET_KEY=supplied_config.get("SECRET_KEY") or os.environ.get("APP_SECRET_KEY") or get_or_create_secret_key(),
        DATABASE=str(supplied_config.get("DATABASE") or get_database_path()),
        DATABASE_URL=os.environ.get("DATABASE_URL", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    app.config.update(supplied_config)
    use_postgres = bool(app.config.get("DATABASE_URL")) and not ("DATABASE" in supplied_config)
    app.config["USE_POSTGRES"] = use_postgres
    if use_postgres:
        initialize_postgres(app.config["DATABASE_URL"])
    else:
        Path(app.config["DATABASE"]).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        initialize_database(Path(app.config["DATABASE"]))

    def db():
        if "db" not in g:
            g.db = connect_postgres(app.config["DATABASE_URL"]) if app.config["USE_POSTGRES"] else connect_db(Path(app.config["DATABASE"]))
        return g.db

    @app.teardown_appcontext
    def close_db(_error: BaseException | None = None) -> None:
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    def csrf_token() -> str:
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def csrf_protect() -> None:
        if request.method == "POST":
            supplied = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                abort(400, description="The form expired or could not be verified. Please go back and try again.")

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'"
        return response

    def login_required(view: Callable):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                return redirect(url_for("login", next=request.path))
            # A signed cookie can outlive a reset/replaced SQLite database on
            # ephemeral hosts. Never trust a session unless its user still exists.
            user = db().execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
            if user is None:
                session.clear()
                user_count = db().execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
                return redirect(url_for("setup" if user_count == 0 else "login"))
            session["username"] = user["username"]
            return view(*args, **kwargs)
        return wrapped

    def log_action(loan_id: int | None, action: str, details: str = "") -> None:
        db().execute(
            "INSERT INTO audit_logs (loan_id, user_id, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (loan_id, session.get("user_id"), action, details[:500], timestamp_now()),
        )

    def clean(value: str, maximum: int) -> str:
        return " ".join((value or "").strip().split())[:maximum]

    @app.context_processor
    def inject_user():
        return {"current_username": session.get("username", ""), "today_date": local_now().date().isoformat()}

    @app.route("/")
    def index():
        count = db().execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        return redirect(url_for("dashboard" if session.get("user_id") else ("login" if count else "setup")))

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if db().execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]:
            return redirect(url_for("login"))
        if request.method == "POST":
            username = clean(request.form.get("username", ""), 32)
            password = request.form.get("password", "")
            confirmation = request.form.get("confirm_password", "")
            if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username):
                flash("Use 3–32 letters, numbers, dots, dashes or underscores for the username.", "error")
            elif len(password) < 12:
                flash("Use a password with at least 12 characters.", "error")
            elif len(password) > 200:
                flash("Password is too long.", "error")
            elif password != confirmation:
                flash("The passwords do not match.", "error")
            else:
                try:
                    cursor = db().execute(
                        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                        (username, generate_password_hash(password), timestamp_now()),
                    )
                    db().commit()
                    session.clear()
                    session["user_id"] = cursor.lastrowid
                    session["username"] = username
                    session.permanent = True
                    return redirect(url_for("dashboard"))
                except Exception as exc:
                    if not isinstance(exc, sqlite3.IntegrityError) and not (psycopg and isinstance(exc, psycopg.IntegrityError)):
                        raise
                    db().rollback()
                    flash("That username is already in use.", "error")
        return render_template("setup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = clean(request.form.get("username", ""), 32)
            password = request.form.get("password", "")
            user = db().execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session.permanent = True
                next_url = request.args.get("next", "")
                if next_url.startswith("/") and not next_url.startswith("//"):
                    return redirect(next_url)
                return redirect(url_for("dashboard"))
            flash("Incorrect username or password.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        stats = db().execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN returned_at = '' THEN 1 ELSE 0 END) AS active,
                   SUM(CASE WHEN returned_at <> '' THEN 1 ELSE 0 END) AS returned,
                   SUM(CASE WHEN returned_at = '' AND due_date <> '' AND due_date < ? THEN 1 ELSE 0 END) AS overdue,
                   SUM(CASE WHEN returned_at = '' AND due_date = ? THEN 1 ELSE 0 END) AS due_today
            FROM loans
        """, (local_now().date().isoformat(), local_now().date().isoformat())).fetchone()
        recent = db().execute("SELECT * FROM loans ORDER BY id DESC LIMIT 6").fetchall()
        return render_template("dashboard.html", stats=stats, recent=recent)

    @app.route("/loans")
    @login_required
    def loans():
        query = clean(request.args.get("q", ""), 100)
        status = request.args.get("status", "active")
        clauses, params = [], []
        if status == "active":
            clauses.append("returned_at = ''")
        elif status == "returned":
            clauses.append("returned_at <> ''")
        if query:
            clauses.append("(book_title LIKE ? OR student_name LIKE ? OR class_name LIKE ? OR roll_number LIKE ?)")
            term = f"%{query}%"
            params.extend([term] * 4)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        records = db().execute(f"SELECT * FROM loans{where} ORDER BY id DESC LIMIT 500", params).fetchall()
        return render_template("loans.html", loans=records, query=query, status=status)

    @app.route("/loans/new", methods=["GET", "POST"])
    @login_required
    def new_loan():
        if request.method == "POST":
            title = clean(request.form.get("book_title", ""), 180)
            student = clean(request.form.get("student_name", ""), 100)
            class_name = clean(request.form.get("class_name", ""), 40)
            roll = clean(request.form.get("roll_number", ""), 30)
            due = clean(request.form.get("due_date", ""), 10)
            notes = clean(request.form.get("notes", ""), 300)
            if not due:
                due = (local_now().date() + timedelta(days=14)).isoformat()
            if not title or not class_name or not (student or roll):
                abort(400, description="Book title, class, and at least the student's name or roll number are required.")
            if due:
                try:
                    date.fromisoformat(due)
                except ValueError:
                    abort(400, description="Enter a valid expected return date.")
            now = timestamp_now()
            cursor = db().execute("""
                INSERT INTO loans (book_title, student_name, class_name, roll_number, borrowed_at, due_date, notes, created_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, student, class_name, roll, now, due, notes, session["user_id"], now))
            loan_id = cursor.lastrowid
            log_action(loan_id, "borrowed", f"Borrowed by {student or 'student'} / {class_name} / {roll}")
            db().commit()
            flash("Borrowing record saved.", "success")
            return redirect(url_for("loan_detail", loan_id=loan_id))
        return render_template("new_loan.html", values={"due_date": (local_now().date() + timedelta(days=14)).isoformat()})

    @app.route("/loans/<int:loan_id>")
    @login_required
    def loan_detail(loan_id: int):
        record = db().execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not record:
            abort(404)
        history = db().execute("SELECT * FROM audit_logs WHERE loan_id = ? ORDER BY id DESC", (loan_id,)).fetchall()
        return render_template("loan_detail.html", loan=record, history=history)

    @app.route("/loans/<int:loan_id>/return", methods=["POST"])
    @login_required
    def return_loan(loan_id: int):
        record = db().execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not record:
            abort(404)
        if record["returned_at"]:
            flash("This book has already been marked as returned.", "error")
        else:
            now = timestamp_now()
            result = db().execute("UPDATE loans SET returned_at = ?, updated_at = ? WHERE id = ? AND returned_at = ''", (now, now, loan_id))
            if result.rowcount:
                log_action(loan_id, "returned", "Book marked as returned")
                db().commit()
                flash("Book marked as returned.", "success")
            else:
                db().rollback()
                flash("The record changed before the return could be saved. Refresh and check its status.", "error")
        return redirect(url_for("loan_detail", loan_id=loan_id))

    @app.route("/loans/<int:loan_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_loan(loan_id: int):
        record = db().execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not record:
            abort(404)
        if request.method == "POST":
            title = clean(request.form.get("book_title", ""), 180)
            student = clean(request.form.get("student_name", ""), 100)
            class_name = clean(request.form.get("class_name", ""), 40)
            roll = clean(request.form.get("roll_number", ""), 30)
            due = clean(request.form.get("due_date", ""), 10)
            notes = clean(request.form.get("notes", ""), 300)
            if not title or not class_name or not (student or roll):
                abort(400, description="Book title, class, and at least the student's name or roll number are required.")
            if due:
                try:
                    date.fromisoformat(due)
                except ValueError:
                    abort(400, description="Enter a valid expected return date.")
            details = "Record details corrected by librarian"
            db().execute("""
                UPDATE loans SET book_title=?, student_name=?, class_name=?, roll_number=?, due_date=?, notes=?, updated_at=? WHERE id=?
            """, (title, student, class_name, roll, due, notes, timestamp_now(), loan_id))
            log_action(loan_id, "edited", details)
            db().commit()
            flash("Record updated. The original borrowing and return history was preserved.", "success")
            return redirect(url_for("loan_detail", loan_id=loan_id))
        return render_template("edit_loan.html", loan=record)

    @app.route("/export.csv")
    @login_required
    def export_csv():
        status = request.args.get("status", "all")
        if status == "active":
            condition = "WHERE returned_at = ''"
        elif status == "returned":
            condition = "WHERE returned_at <> ''"
        else:
            condition = ""
        records = db().execute(f"SELECT id, book_title, student_name, class_name, roll_number, borrowed_at, due_date, returned_at, notes FROM loans {condition} ORDER BY id DESC").fetchall()
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Record ID", "Book", "Student", "Class", "Roll number", "Borrowed at", "Due date", "Returned at", "Notes"])
        for row in records:
            writer.writerow([row[key] for key in row.keys()])
        response = make_response("\ufeff" + output.getvalue())
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = "attachment; filename=library-records.csv"
        return response

    @app.route("/backup.sqlite")
    @login_required
    def download_backup():
        if app.config["USE_POSTGRES"]:
            flash("PostgreSQL is connected. Use Export CSV for a portable records backup.", "warning")
            return redirect(url_for("loans", status="all"))
        temp = tempfile.NamedTemporaryFile(prefix="library-backup-", suffix=".sqlite", delete=False)
        temp.close()
        source = connect_db(Path(app.config["DATABASE"]))
        destination = sqlite3.connect(temp.name)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return send_file(temp.name, as_attachment=True, download_name=f"library-backup-{local_now().date().isoformat()}.sqlite", mimetype="application/vnd.sqlite3")

    @app.route("/audit")
    @login_required
    def audit():
        entries = db().execute("""
            SELECT a.*, l.book_title, u.username FROM audit_logs a
            LEFT JOIN loans l ON l.id = a.loan_id LEFT JOIN users u ON u.id = a.user_id
            ORDER BY a.id DESC LIMIT 300
        """).fetchall()
        return render_template("audit.html", entries=entries)

    @app.cli.command("check-db")
    def check_db_command():
        if app.config["USE_POSTGRES"]:
            db().execute("SELECT 1")
            result = "PostgreSQL connection OK"
        else:
            result = db().execute("PRAGMA integrity_check").fetchone()[0]
        print(result)
        if result != "ok" and result != "PostgreSQL connection OK":
            raise SystemExit(1)

    @app.cli.command("create-admin")
    def create_admin_command():
        import getpass
        username = input("New librarian username: ").strip()
        password = getpass.getpass("New password (12+ characters): ")
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username) or len(password) < 12:
            raise SystemExit("Invalid username or password length.")
        db().execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)", (username, generate_password_hash(password), timestamp_now()))
        db().commit()
        print("Librarian account created.")

    @app.cli.command("reset-password")
    def reset_password_command():
        import getpass
        username = input("Librarian username: ").strip()
        password = getpass.getpass("New password (12+ characters): ")
        if len(password) < 12:
            raise SystemExit("Password must be at least 12 characters.")
        result = db().execute("UPDATE users SET password_hash = ? WHERE username = ? COLLATE NOCASE", (generate_password_hash(password), username))
        db().commit()
        if not result.rowcount:
            raise SystemExit("Username not found.")
        print("Password reset.")

    return app


app = create_app()

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="127.0.0.1", port=8000)
