from __future__ import annotations

import logging
import re as stdre
from dataclasses import dataclass, field
from typing import Iterable

import orjson

log = logging.getLogger(__name__)

COLUMNS = [
    "plant_species",
    "genes",
    "modification_type",
    "engineering_type",
    "gene_construct",
    "phenotype",
    "mechanism",
    "doi",
    "pmcid",
]

_MODEL_FIELDS = COLUMNS + ["evidence_quote"]

EXTRACTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "plant_species":     {"type": "string", "minLength": 1},
                    "genes":             {"type": "string", "minLength": 1},
                    "modification_type": {"type": "string", "minLength": 1},
                    "engineering_type": {
                        "type": "string",
                        "enum": [
                            "single-gene engineering",
                            "multi-gene engineering",
                            "NA",
                        ],
                    },
                    "gene_construct": {"type": "string", "minLength": 1},
                    "phenotype":      {"type": "string", "minLength": 1},
                    "mechanism":      {"type": "string", "minLength": 1},
                    "doi":            {"type": "string", "minLength": 1},
                    "pmcid": {
                        "type": "string",
                        "pattern": r"^PMC[0-9]+(\.[0-9]+)?$",
                    },
                    "evidence_quote": {
                        "type": "string",
                        "minLength": 20,
                        "maxLength": 1200,
                    },
                },
                "required": _MODEL_FIELDS,
                "additionalProperties": False,
            },
        },
    },
    "required": ["rows"],
    "additionalProperties": False,
}

_FENCE_RE = stdre.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", stdre.IGNORECASE)

def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()

def _slice_outer_json(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None

_UNICODE_FOLD = str.maketrans({
    "–": "-",  "—": "-",  "−": "-",
    "“": '"',  "”": '"',
    "‘": "'",  "’": "'",
    " ": " ",
    " ": " ",
    " ": " ",
    "…": "...",
})

_WS_RUN = stdre.compile(r"\s+")

def _normalize_for_match(s: str) -> str:
    if not s:
        return ""
    s = s.translate(_UNICODE_FOLD)
    s = _WS_RUN.sub(" ", s).strip()
    return s.lower()

def verify_evidence(quote: str, body: str) -> tuple[bool, str]:
    if not quote or len(quote.strip()) < 20:
        return False, "quote too short (<20 chars)"

    nq = _normalize_for_match(quote)
    nb = _normalize_for_match(body)
    if not nb:
        return False, "empty body"

    if nq in nb:
        return True, "strict"

    n = len(nq)
    if n < 60:
        return False, "no strict match; too short for chunked"
    third = n // 3
    chunks = [
        nq[0:third].strip(),
        nq[third:2 * third].strip(),
        nq[2 * third:].strip(),
    ]
    hits = sum(1 for c in chunks if len(c) >= 15 and c in nb)
    if hits >= 2:
        return True, f"chunked ({hits}/3)"

    return False, f"no match ({hits}/3 chunks present)"

@dataclass
class ParsedExtraction:
    rows: list[dict]
    raw_text: str
    parse_error: str | None
    n_rejected_evidence: int = 0
    evidence_diags: list[str] = field(default_factory=list)

def parse_extraction(raw: str, body: str | None = None) -> ParsedExtraction:
    text = _strip_fences(raw)

    obj = None
    err = None
    try:
        obj = orjson.loads(text)
    except orjson.JSONDecodeError as e:
        sliced = _slice_outer_json(text)
        if sliced is not None:
            try:
                obj = orjson.loads(sliced)
            except orjson.JSONDecodeError as e2:
                err = f"json parse failed even after slice: {e2}"
        else:
            err = f"json parse failed and no balanced object found: {e}"

    if obj is None:
        return ParsedExtraction(rows=[], raw_text=raw, parse_error=err)

    raw_rows = obj.get("rows", []) if isinstance(obj, dict) else []
    if not isinstance(raw_rows, list):
        return ParsedExtraction(
            rows=[], raw_text=raw,
            parse_error=f"'rows' is not a list (got {type(raw_rows).__name__})",
        )

    cleaned: list[dict] = []
    diags: list[str] = []
    n_reject = 0
    for r in raw_rows:
        if not isinstance(r, dict):
            continue
        row = _normalize_row(r)
        quote = _clean_cell(r.get("evidence_quote"))
        row["_evidence_quote"] = quote

        if body is None:
            row["_evidence_ok"] = None
            row["_evidence_diag"] = "verification disabled (no body provided)"
        else:
            ok, diag = verify_evidence(quote, body)
            row["_evidence_ok"] = bool(ok)
            row["_evidence_diag"] = diag
            diags.append(diag)
            if not ok:
                n_reject += 1

        cleaned.append(row)

    return ParsedExtraction(
        rows=cleaned, raw_text=raw, parse_error=None,
        n_rejected_evidence=n_reject, evidence_diags=diags,
    )

_BAD_WHITESPACE_RE = stdre.compile(r"[\t\r\n\v\f]+")
_MULTI_WS_RE = stdre.compile(r"  +")

def _clean_cell(v) -> str:
    if v is None:
        return "NA"
    if not isinstance(v, str):
        try:
            v = orjson.dumps(v).decode("utf-8")
        except Exception:
            v = str(v)
    v = _BAD_WHITESPACE_RE.sub(" ", v)
    v = _MULTI_WS_RE.sub(" ", v).strip()
    return v if v else "NA"

def _normalize_row(row: dict) -> dict:
    return {col: _clean_cell(row.get(col)) for col in COLUMNS}

def public_row(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}

def tsv_header() -> str:
    return "\t".join(COLUMNS)

def render_rows_tsv(rows: Iterable[dict]) -> str:
    lines = ["\t".join(r[c] for c in COLUMNS) for r in rows]
    return "\n".join(lines)

@dataclass
class GateResult:
    qualifies: bool
    reason: str
    parse_error: str | None = None

def parse_gate(raw: str) -> GateResult:
    text = _strip_fences(raw)
    try:
        obj = orjson.loads(text)
    except orjson.JSONDecodeError:
        sliced = _slice_outer_json(text)
        if sliced is None:
            return GateResult(qualifies=False, reason="(unparseable gate reply)",
                              parse_error="json parse failed and no balanced object")
        try:
            obj = orjson.loads(sliced)
        except orjson.JSONDecodeError as e:
            return GateResult(qualifies=False, reason="(unparseable gate reply)",
                              parse_error=f"json parse failed after slice: {e}")
    qualifies = bool(obj.get("qualifies", False)) if isinstance(obj, dict) else False
    reason = str(obj.get("reason", "")) if isinstance(obj, dict) else ""
    return GateResult(qualifies=qualifies, reason=reason or "(no reason given)")

GATE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "qualifies": {"type": "boolean"},
        "reason":    {"type": "string", "maxLength": 200},
    },
    "required": ["qualifies", "reason"],
    "additionalProperties": False,
}
