"""Display bounded policy sections from already extracted teaching documents, never auth data."""

import argparse
import json
import re
from pathlib import Path

from campus.config import load_config
from campus.security import redact
from campus.store import Store, single

store = Store(load_config(home=Path.cwd() / ".campus").db)
parser = argparse.ArgumentParser()
parser.add_argument("--downloads", action="store_true")
parser.add_argument("--formulas", action="store_true")
args = parser.parse_args()
try:
    if args.downloads:
        from campus.artifacts import read_document

        for path in (Path.cwd() / ".campus" / "downloads").glob("*.pdf"):
            text = read_document(path)
            if args.formulas:
                lines = text.splitlines()
                selected = set()
                for i, line in enumerate(lines):
                    if re.search(
                        r"(?i)(?:nota final|m[eé]dia|peso|[PMN]F\s*=|\bP[12]\b|aprovad|pontua|escala|0\s*a\s*10)",
                        line,
                    ):
                        selected.update(range(max(0, i - 1), min(len(lines), i + 3)))
                print(
                    json.dumps(
                        {
                            "document_hash": path.stem,
                            "formula_lines": [redact(lines[i]) for i in sorted(selected)][:90],
                        },
                        ensure_ascii=True,
                    )
                )
                continue
            positions = [
                m.start()
                for m in re.finditer(
                    r"(?i)(?:procedimentos de avalia|crit[eé]rios de avalia|m[eé]dia final|MF\s*=|recupera[çc][aã]o)",
                    text,
                )
            ]
            if positions:
                start = next((p for p in positions if p > len(text) / 3), positions[0])
                print(
                    json.dumps(
                        {
                            "document_hash": path.stem,
                            "policy_section": redact(text[max(0, start - 100) : start + 10000]),
                        },
                        ensure_ascii=True,
                    )
                )
    for document in store.entities("document"):
        if single(document, "purpose") != "teaching_policy_candidate":
            continue
        text = single(document, "text", "")
        positions = [
            m.start()
            for m in re.finditer(
                r"(?i)(?:procedimentos de avalia|crit[eé]rios de avalia|m[eé]dia final|MF\s*=|avalia[çc][aã]o|recupera[çc][aã]o)",
                text,
            )
        ]
        start = next((p for p in positions if p > len(text) / 3), max(0, len(text) - 6000))
        print(
            json.dumps(
                {
                    "document": document["id"],
                    "course": single(document, "course"),
                    "characters": len(text),
                    "policy_section": redact(text[max(0, start - 100) : start + 10000]),
                },
                ensure_ascii=True,
            )
        )
finally:
    store.close()
