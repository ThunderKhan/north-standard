#!/usr/bin/env python3
"""Run a ground-truth-labelled Mode R campaign from a manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from north_standard.recorded_campaign import (
    campaign_summary,
    run_campaign,
    validate_campaign_manifest,
    write_campaign_results,
)
from north_standard.recorded_real import load_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = load_json(manifest_path)
    validate_campaign_manifest(manifest)
    rows = run_campaign(manifest, base_dir=manifest_path.parent)
    raw_path, summary_path = write_campaign_results(rows, args.output_dir)
    print(json.dumps(campaign_summary(rows), indent=2, sort_keys=True))
    print(f"raw_trials={raw_path}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
