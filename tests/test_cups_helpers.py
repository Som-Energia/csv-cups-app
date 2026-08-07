import unittest

from app.cups import canonicalize_api_cups, canonicalize_lookup_cups


class CupsHelperTests(unittest.TestCase):
    canonical_cups = "ES123456789012345678"
    extended_cups = canonical_cups + "0F"

    def test_api_canonicalization_accepts_20_and_22_characters(self):
        self.assertEqual(canonicalize_api_cups(self.canonical_cups), self.canonical_cups)
        self.assertEqual(canonicalize_api_cups(self.extended_cups), self.canonical_cups)

    def test_api_canonicalization_rejects_other_trimmed_lengths(self):
        for cups in ("", "ES123", self.canonical_cups + "XYZ"):
            with self.assertRaises(ValueError):
                canonicalize_api_cups(f"  {cups}  ")

    def test_lookup_canonicalization_preserves_partial_html_searches(self):
        self.assertEqual(canonicalize_lookup_cups(" ES123 "), "ES123")
        self.assertEqual(canonicalize_lookup_cups(self.extended_cups), self.canonical_cups)


if __name__ == "__main__":
    unittest.main()
