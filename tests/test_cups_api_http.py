import unittest

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


class EmptyQuery:
    def __init__(self):
        self.cups_lookup = None

    def filter(self, criterion):
        self.cups_lookup = criterion.right.value
        return self

    def order_by(self, *args):
        return self

    def limit(self, *args):
        return self

    def all(self):
        return []

    def first(self):
        return None


class EmptyDatabase:
    def __init__(self):
        self.queries = []

    def query(self, *args):
        query = EmptyQuery()
        self.queries.append(query)
        return query


class CupsApiHttpTests(unittest.TestCase):
    canonical_cups = "ES123456789012345678"
    extended_cups = canonical_cups + "0F"

    def setUp(self):
        self.db = EmptyDatabase()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()

    def test_valid_cups_are_accepted_by_every_cups_api_endpoint(self):
        for cups in (self.canonical_cups, self.extended_cups):
            with self.subTest(cups=cups, endpoint="records query"):
                self.assertEqual(self.client.get("/api/records", params={"cups": f" {cups} "}).status_code, 200)
            with self.subTest(cups=cups, endpoint="record"):
                self.assertEqual(self.client.get(f"/api/records/{cups}").status_code, 404)
            with self.subTest(cups=cups, endpoint="bono social"):
                self.assertEqual(self.client.get(f"/api/records/{cups}/bono-social").status_code, 404)
            with self.subTest(cups=cups, endpoint="consumptions"):
                self.assertEqual(self.client.get(f"/api/records/{cups}/consumptions").status_code, 200)

    def test_every_cups_path_endpoint_uses_the_canonical_database_lookup(self):
        endpoints = (
            ("record", lambda cups: f"/api/records/{cups}"),
            ("bono social", lambda cups: f"/api/records/{cups}/bono-social"),
            ("consumptions", lambda cups: f"/api/records/{cups}/consumptions"),
        )
        for cups, expected_cups in (
            (self.canonical_cups, self.canonical_cups),
            (self.extended_cups, self.canonical_cups),
        ):
            for endpoint_name, url_for_cups in endpoints:
                with self.subTest(cups=cups, endpoint=endpoint_name):
                    response = self.client.get(url_for_cups(cups))
                    self.assertIn(response.status_code, (200, 404))
                    self.assertEqual(self.db.queries[-1].cups_lookup, expected_cups)

    def test_22_character_query_uses_the_canonical_20_character_lookup(self):
        response = self.client.get("/api/records", params={"cups": self.extended_cups})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.queries[-1].cups_lookup, self.canonical_cups)

    def test_invalid_cups_lengths_return_422_from_every_cups_api_endpoint(self):
        for cups in ("E" * 19, "E" * 21, "E" * 23):
            for url in (
                "/api/records",
                f"/api/records/{cups}",
                f"/api/records/{cups}/bono-social",
                f"/api/records/{cups}/consumptions",
            ):
                with self.subTest(cups_length=len(cups), url=url):
                    response = (
                        self.client.get(url, params={"cups": cups})
                        if url == "/api/records"
                        else self.client.get(url)
                    )
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["detail"], "CUPS must contain exactly 20 or 22 characters.")

    def test_records_query_allows_omitted_cups_but_rejects_explicit_blank_values(self):
        response = self.client.get("/api/records")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.db.queries[-1].cups_lookup)

        for cups in ("", "   "):
            with self.subTest(cups=repr(cups)):
                response = self.client.get("/api/records", params={"cups": cups})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], "CUPS must contain exactly 20 or 22 characters.")

    def test_partial_html_search_remains_usable(self):
        response = self.client.get("/", params={"cups": "ES123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.queries[-1].cups_lookup, "%ES123%")
