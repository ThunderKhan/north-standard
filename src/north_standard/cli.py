"""Small CLI for exercising the Step-1 verifier slice."""

from __future__ import annotations

import argparse
import json

from .simulator import Scenario, simulate_scenario
from .verifier import verify


def main() -> int:
    parser = argparse.ArgumentParser(prog="north-standard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    simulate = subparsers.add_parser("simulate", help="run a built-in synthetic scenario")
    simulate.add_argument("scenario", choices=[scenario.value for scenario in Scenario])

    args = parser.parse_args()

    if args.command == "simulate":
        contract, bundle = simulate_scenario(args.scenario)
        result = verify(contract, bundle)
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
