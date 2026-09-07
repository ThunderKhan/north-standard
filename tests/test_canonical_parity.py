"""Cross-language canonical JSON and SHA-256 parity vectors."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest

from north_standard.canonical import canonical_json, canonical_sha256


class CanonicalParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("NORTH_STANDARD_CPP_CLI")
        cls.binary = Path(configured) if configured else Path("build/cpp/north-standard-cpp")
        if not cls.binary.exists():
            raise unittest.SkipTest(f"C++ verifier binary not found: {cls.binary}")
        cls.vectors = Path("fixtures/canonical_vectors.jsonl")

    def test_shared_vectors_match_cpp(self) -> None:
        lines = [
            line
            for line in self.vectors.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertGreaterEqual(len(lines), 6)

        for index, raw in enumerate(lines):
            with self.subTest(vector=index):
                value = json.loads(raw)
                expected_json = canonical_json(value)
                expected_hash = canonical_sha256(value)

                canonicalized = subprocess.run(
                    [str(self.binary), "canonicalize-json"],
                    input=raw,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.rstrip("\n")
                hashed = subprocess.run(
                    [str(self.binary), "hash-json"],
                    input=raw,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

                self.assertEqual(canonicalized, expected_json)
                self.assertEqual(hashed, expected_hash)


if __name__ == "__main__":
    unittest.main()
