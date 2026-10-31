import os
import re
import tempfile
import unittest

from app import create_app


class LibrarySystemTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test-library.sqlite")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret-key", "DATABASE": self.db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def csrf(self, response):
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match, "CSRF token should be present on forms")
        return match.group(1).decode()

    def setup_librarian(self):
        response = self.client.get("/setup")
        token = self.csrf(response)
        response = self.client.post("/setup", data={
            "csrf_token": token,
            "username": "librarian",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Library", response.data)

    def test_setup_creates_librarian_and_dashboard(self):
        self.setup_librarian()
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Library overview", response.data)

    def test_can_record_and_search_borrowed_book(self):
        self.setup_librarian()
        response = self.client.get("/students/new")
        token = self.csrf(response)
        response = self.client.post("/students/new", data={
            "csrf_token": token,
            "full_name": "Anaya",
            "class_grade": "10",
            "division": "A",
            "roll_number": "23",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/loans/new")
        token = self.csrf(response)
        response = self.client.post("/loans/new", data={
            "csrf_token": token,
            "book_title": "Wings of Fire",
            "student_id": "1",
            "summary_status": "pending",
            "due_date": "",
            "notes": "",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Wings of Fire", response.data)
        response = self.client.get("/loans?q=Anaya&status=active")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Wings of Fire", response.data)

    def test_records_require_login(self):
        response = self.client.get("/loans")
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/login", response.headers.get("Location", ""))

    def test_post_without_csrf_is_rejected(self):
        response = self.client.post("/setup", data={
            "username": "librarian",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        })
        self.assertEqual(response.status_code, 400)

    def test_static_assets_are_cacheable(self):
        response = self.client.get("/static/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("max-age=3600", response.headers.get("Cache-Control", ""))
        self.assertGreater(len(response.data), 0)


if __name__ == "__main__":
    unittest.main()
