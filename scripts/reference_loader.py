"""Parse reference questions from config/reference_questions.md."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REFERENCE_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "reference_questions.md"
)


@dataclass(frozen=True)
class ReferenceQuestion:
    """One row from the reference questions table."""

    number: int
    question_ref: str
    question: str
    question_type: str
    human_label: str


def load_reference_questions(path: Path | None = None) -> list[ReferenceQuestion]:
    """Parse the markdown table in reference_questions.md.

    Description:
        Reads canonical question_ref (Q1..Q8), question text, and
        question_type from the pipe-delimited table.

    Input:
        path: Optional override; defaults to config/reference_questions.md.

    Output:
        Ordered list of ReferenceQuestion rows.

    When to use:
        Batch runner initialization.

    When not to use:
        N/A.
    """
    md_path = path or REFERENCE_PATH
    text = md_path.read_text(encoding="utf-8")
    rows: list[ReferenceQuestion] = []

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        num_cell = cells[0]
        if not re.fullmatch(r"\d+", num_cell):
            continue
        number = int(num_cell)
        question = cells[1]
        question_type = cells[2]
        human_label = cells[3] if len(cells) > 3 else ""
        rows.append(
            ReferenceQuestion(
                number=number,
                question_ref=f"Q{number}",
                question=question,
                question_type=question_type,
                human_label=human_label,
            )
        )

    return sorted(rows, key=lambda r: r.number)
