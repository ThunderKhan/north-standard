import unittest

from north_standard.canonical import canonical_json, canonical_sha256


class CanonicalTests(unittest.TestCase):
    def test_mapping_order_does_not_change_hash(self) -> None:
        left = {"b": 2, "a": 1, "nested": {"z": 9, "y": 8}}
        right = {"nested": {"y": 8, "z": 9}, "a": 1, "b": 2}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(canonical_sha256(left), canonical_sha256(right))

    def test_hash_is_sha256_hex(self) -> None:
        digest = canonical_sha256({"contract": "north-standard"})
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(ch in "0123456789abcdef" for ch in digest))


if __name__ == "__main__":
    unittest.main()
