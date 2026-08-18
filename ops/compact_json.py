#!/usr/bin/env python3
"""compact_json.py — compact serialization for the public ledger files.

Partner-approved 2026-08-18 ("All changes approved"): the ledger was growing
too fast in pretty-print form (~10 lines per payment row). This serializer
writes valid JSON with exactly ONE line per entry inside known list fields:

  {
    "ledger": "Mutual Aid Registry",
    "members": [
      {"member_no": 1, "name": "Glint", ...},
      {"member_no": 2, "name": "Sylvia", ...}
    ],
    "updated": "2026-08-18T06:38:38Z"
  }

JSON semantics are unchanged — every existing reader (json.load anywhere,
members' links, claim tools) keeps working. What changes is the diff shape:
a new payment is exactly 1 added line, and whole-file API writes shrink ~4x.

Usage:
    from compact_json import dumps_compact
    text = dumps_compact(doc, list_keys=("members", "entry_parts", ...))
"""
import json

DEFAULT_LIST_KEYS = ("members", "entry_parts", "premium_parts", "dues", "claims")


def _enc(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ": "))


def dumps_compact(doc, list_keys=DEFAULT_LIST_KEYS):
    """Serialize `doc` as valid JSON with one dict per line inside list fields."""
    items = list(doc.items())
    lines = ["{"]
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if k in list_keys and isinstance(v, list):
            lines.append(f'  "{k}": [')
            for j, entry in enumerate(v):
                ecomma = "," if j < len(v) - 1 else ""
                lines.append("    " + _enc(entry) + ecomma)
            lines.append("  ]" + comma)
        else:
            lines.append("  " + _enc({k: v})[1:-1] + comma)
    lines.append("}")
    return "\n".join(lines) + "\n"
