"""Minimal CLI: agiofit <fit-profile.json> <cut-profile.json> [disclosure_level]

With no level given, the profile's own default_level applies, and result_only if it has none.
"""

import json
import sys

from .match import load_fit_profile, load_cut_profile, recommend


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    level = argv[2] if len(argv) > 2 else None
    profile = load_fit_profile(argv[0])
    garment = load_cut_profile(argv[1])
    report = recommend(profile, garment, disclosure_level=level)
    print(json.dumps(report.to_json(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
