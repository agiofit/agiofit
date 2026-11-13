"""Minimal CLI, in two forms.

    agiofit <fit-profile.json> <cut-profile.json> [disclosure_level]

With no level given, the profile's own default_level applies, and result_only if it has none.

    agiofit <fit-profile.json> <cut-profile.json> --request <match-request.json> [--authorise[=level]]

Answers a Match Request. --authorise says the person authorised the request, and
--authorise=level that they granted that level; the report is at the lower of the level asked and
the level granted. Without --authorise nothing is printed. The authorisation is an input, given by
whoever runs this: the tool applies it, and does not show that a person gave it.

What is printed on standard output is the report and nothing else. When there is no report, a
line on standard error says why, for whoever runs this and not for the verifier.
"""

import json
import sys

from .match import answer, load_fit_profile, load_cut_profile, recommend, request_problems


def _usage() -> int:
    print(__doc__.strip(), file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    request_path = None
    authorised: str | bool | None = None
    if "--request" in argv:
        at = argv.index("--request")
        if at + 1 >= len(argv):
            return _usage()
        request_path = argv[at + 1]
        del argv[at : at + 2]
    for arg in [a for a in argv if a == "--authorise" or a.startswith("--authorise=")]:
        authorised = True if arg == "--authorise" else arg.split("=", 1)[1]
        argv.remove(arg)
    if len(argv) < 2 or any(a.startswith("--") for a in argv):
        return _usage()
    if request_path is None and authorised is not None:
        return _usage()
    if request_path is not None and len(argv) > 2:
        return _usage()
    level = argv[2] if len(argv) > 2 else None
    profile = load_fit_profile(argv[0])
    garment = load_cut_profile(argv[1])
    if request_path is None:
        report = recommend(profile, garment, disclosure_level=level)
    else:
        request = json.loads(open(request_path, encoding="utf-8").read())
        report = answer(profile, garment, request, authorised=authorised)
        if report is None:
            why = request_problems(request, garment) or ["The request was not authorised."]
            print("No report. " + " ".join(why), file=sys.stderr)
            return 1
    # sent to a file, the report would otherwise take the console's code page, cp1252 on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(report.to_json(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
