"""Replay recorded model answers against an explicit, offline rubric."""

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path


class EvaluationError(ValueError):
    """Invalid dataset or response mapping; errors do not echo their contents."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_):
    raise EvaluationError("non-finite JSON constant")


def _finite(value):
    if type(value) is float and not math.isfinite(value):
        raise EvaluationError("non-finite number")
    if type(value) is str:
        value.encode("utf-8")
    if type(value) is dict:
        for key, item in value.items():
            _finite(key)
            _finite(item)
    if type(value) is list:
        for item in value:
            _finite(item)


def _load(text):
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
        _finite(value)
        return value
    except (ValueError, RecursionError, UnicodeError):
        raise EvaluationError("invalid JSON input") from None


def _normalize(text):
    return " ".join(text.casefold().split())


def _validate_cases(cases):
    if type(cases) is not list or not 1 <= len(cases) <= 1000:
        raise EvaluationError("dataset must contain 1 to 1000 cases")
    seen = set()
    for case in cases:
        if type(case) is not dict or set(case) != {"id", "prompt", "checks"}:
            raise EvaluationError("invalid case fields")
        name = case["id"]
        if type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name) or name in seen:
            raise EvaluationError("invalid or duplicate case ID")
        seen.add(name)
        if type(case["prompt"]) is not str or not case["prompt"].strip():
            raise EvaluationError("prompt must be nonempty text")
        checks = case["checks"]
        if type(checks) is not dict or not checks or set(checks) - {"contains_all", "forbids_any", "json_fields"}:
            raise EvaluationError("invalid checks")
        for key, rule in checks.items():
            if key == "json_fields":
                if type(rule) is not dict or not rule or any(type(k) is not str or type(v) not in (str, int, float, bool, type(None)) for k, v in rule.items()):
                    raise EvaluationError("invalid JSON field checks")
            elif type(rule) is not list or not rule or any(type(v) is not str or not v.strip() for v in rule):
                raise EvaluationError("text checks must contain nonempty strings")
    return seen


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def evaluate(cases, responses):
    """Return a deterministic report. A missing answer counts as a failed case.

    Text checks are substring heuristics, not semantic or factual judges.
    JSON field checks compare top-level primitive values with exact types.
    """
    names = _validate_cases(cases)
    if type(responses) is not dict or set(responses) - names:
        raise EvaluationError("unknown response IDs or invalid response mapping")
    try:
        _finite(cases)
        _finite(responses)
        fingerprints = (_fingerprint(cases), _fingerprint(responses))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise EvaluationError("inputs must be finite JSON values") from None
    rows = []
    for case in cases:
        name = case["id"]
        failures = []
        if name not in responses:
            failures.append("missing_response")
        elif type(responses[name]) is not str:
            failures.append("response_not_text")
        elif len(responses[name].encode("utf-8")) > 65536:
            failures.append("response_too_large")
        else:
            response = responses[name]
            normalized = _normalize(response)
            checks = case["checks"]
            if "contains_all" in checks and any(_normalize(word) not in normalized for word in checks["contains_all"]):
                failures.append("required_text_missing")
            if "forbids_any" in checks and any(_normalize(word) in normalized for word in checks["forbids_any"]):
                failures.append("forbidden_text")
            if "json_fields" in checks:
                try:
                    data = _load(response)
                    expected = checks["json_fields"]
                    if type(data) is not dict or any(key not in data or type(data[key]) is not type(value) or data[key] != value for key, value in expected.items()):
                        failures.append("json_field_mismatch")
                except EvaluationError:
                    failures.append("invalid_json_response")
        rows.append({"id": name, "passed": not failures, "failures": failures})
    passed = sum(row["passed"] for row in rows)
    return {"format_version": 1, "dataset_sha256": fingerprints[0], "responses_sha256": fingerprints[1], "total": len(rows), "passed": passed, "pass_rate": passed / len(rows), "cases": rows}


def _read(path):
    with Path(path).open("rb") as source:
        raw = source.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise EvaluationError("input file exceeds 2 MiB")
    return _load(raw.decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", help="JSON dataset: id, prompt and checks")
    parser.add_argument("responses", help="JSON object mapping case IDs to answer text")
    args = parser.parse_args()
    try:
        report = evaluate(_read(args.cases), _read(args.responses))
    except (EvaluationError, OSError, UnicodeError):
        print("Invalid dataset, answers, or unreadable input file.", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
