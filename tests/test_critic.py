"""Critic autograder — load-bearing cascade gates.

Cascade thresholds pinned 2026-06-05 against the reference 4-stage
cascade (answer-key.md §4.1): per-class precision and recall measure
1.00/1.00 across supported, entailed-only, and contradicted on the
40-claim eval set. Pins 0.90/0.90/0.60/0.75 leave a generous margin so
partial cascade implementations earn class-by-class credit (Stage 1+3
catches supported + contradicted but tanks entailed recall).
"""
from __future__ import annotations

import ast
import hashlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.eval_set import (
    EVAL_SET,
    SUPPORTED_CLAIMS,
    ENTAILED_CLAIMS,
    CONTRADICTED_CLAIMS,
)


# ---------------------------------------------------------------------------
# learner_notes.md must be touched (rubric-graded deliverable)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_UNMODIFIED_LEARNER_NOTES_MD5 = "9f491e688e6cf570710b9e95a7717ba4"


def test_learner_notes_modified():
    """Sentinel: `learner_notes.md` is a TA-rubric-graded deliverable.
    A submission whose `learner_notes.md` is byte-identical to the
    starter template has not been filled in.
    """
    notes = _REPO_ROOT / "learner_notes.md"
    assert notes.exists(), "learner_notes.md is missing from the submission"
    h = hashlib.md5(notes.read_bytes()).hexdigest()
    assert h != _UNMODIFIED_LEARNER_NOTES_MD5, (
        "learner_notes.md is the unmodified starter template. Replace each "
        "bullet question with a narrative answer before resubmitting."
    )
from critic.verify import verify_claim


# ─── Fixture-shape gates ─────────────────────────────────────────────


def test_load_fixture(driver):
    """The fixture loader (run as a workflow step before pytest) must
    have produced the expected node and relationship counts."""
    with driver.session() as s:
        n_nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        n_rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    assert n_nodes == 31, f"Expected 31 nodes, got {n_nodes}"
    assert n_rels == 48, f"Expected 48 relationships, got {n_rels}"


def test_entity_id_uniqueness(driver):
    """Identity Discipline: no duplicate :Entity ids in the loaded graph."""
    with driver.session() as s:
        rows = list(s.run(
            "MATCH (n:Entity) WITH n.id AS id, count(*) AS c "
            "WHERE c > 1 RETURN id, c"
        ))
    assert rows == [], f"Duplicate :Entity ids found: {rows}"


# ─── Cascade gates ───────────────────────────────────────────────────


def _predict(driver, claims: list[dict]) -> list[str]:
    """Run verify_claim on every (claim, label) entry and return the
    predicted verdict labels in order."""
    return [verify_claim(driver, e["claim"]).verdict for e in claims]


def _precision_recall(predictions: list[str], golds: list[str], target: str) -> tuple[float, float]:
    """Per-class precision and recall for one verdict label."""
    tp = sum(1 for p, g in zip(predictions, golds) if p == target and g == target)
    fp = sum(1 for p, g in zip(predictions, golds) if p == target and g != target)
    fn = sum(1 for p, g in zip(predictions, golds) if p != target and g == target)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


def test_supported_precision_recall(driver):
    """Stage 1 of the cascade must catch all supported claims with both
    high precision and high recall."""
    all_preds = _predict(driver, EVAL_SET)
    all_golds = [e["label"] for e in EVAL_SET]
    precision, recall = _precision_recall(all_preds, all_golds, "supported")
    assert precision >= 0.90, f"supported precision {precision:.3f} < 0.90"
    assert recall >= 0.90, f"supported recall {recall:.3f} < 0.90"


def test_entailed_only_recall(driver):
    """The hard class — Stage 2 must catch entailed-only claims via
    [:SUBCLASS_OF*0..]. A learner who only implements Stage 1 will
    miss these and recall drops to 0."""
    all_preds = _predict(driver, EVAL_SET)
    all_golds = [e["label"] for e in EVAL_SET]
    _, recall = _precision_recall(all_preds, all_golds, "entailed")
    assert recall >= 0.60, f"entailed recall {recall:.3f} < 0.60"


def test_contradicted_precision(driver):
    """Stage 3 must not false-accuse. A learner who maps
    'anything-not-supported' to contradicted will tank precision here."""
    all_preds = _predict(driver, EVAL_SET)
    all_golds = [e["label"] for e in EVAL_SET]
    precision, _ = _precision_recall(all_preds, all_golds, "contradicted")
    assert precision >= 0.75, f"contradicted precision {precision:.3f} < 0.75"


# ─── Production-discipline gate: parameterized Cypher ────────────────


def test_verify_uses_parameterized_cypher():
    """AST inspection — `critic/verify.py` must not f-string-interpolate
    any claim component (subject_id, predicate, object_id) into a Cypher
    string. f-string interpolation of claim data is the silent-failure
    mode shown in the Reading (apostrophes break parses; attacker-
    controlled subject ids could inject destructive Cypher)."""
    path = os.path.join(os.path.dirname(__file__), "..", "critic", "verify.py")
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)

    BAD_NAMES = {"subject_id", "object_id"}
    offenses: list[str] = []

    for node in ast.walk(tree):
        # JoinedStr is the AST node for an f-string literal.
        if isinstance(node, ast.JoinedStr):
            # Collect the names referenced inside the f-string.
            referenced: set[str] = set()
            for v in node.values:
                if isinstance(v, ast.FormattedValue):
                    for sub in ast.walk(v):
                        if isinstance(sub, ast.Name):
                            referenced.add(sub.id)
            if BAD_NAMES & referenced:
                offenses.append(
                    f"line {node.lineno}: f-string interpolates {sorted(BAD_NAMES & referenced)}"
                )

    assert not offenses, (
        "verify.py must use parameterized Cypher ($param) — never "
        "f-string-interpolate claim components into Cypher strings. "
        "Offenses:\n  " + "\n  ".join(offenses)
    )


# ─── Unmodified-starter sentinel ─────────────────────────────────────


def test_starter_unmodified_fails(driver):
    """Sentinel — running verify_claim on an unmodified starter must
    raise (the cascade is not yet wired up). The presence of a working
    implementation removes this failure naturally.

    Guards the Unmodified Starter Failure Rule: if this test passes
    silently on the unmodified starter, the autograder is defective."""
    try:
        result = verify_claim(driver, ("recipe:001", "OF_CUISINE", "cuisine:sichuan"))
    except NotImplementedError:
        # Expected when the starter is unmodified.
        pytest.fail(
            "Starter not yet implemented — verify_claim raised NotImplementedError "
            "as expected. Implement the cascade in critic/verify.py."
        )
    except Exception as e:
        # Any other exception during exploration is also a "not done" signal.
        pytest.fail(
            f"verify_claim raised {type(e).__name__}: {e}. Implement the cascade "
            "in critic/verify.py."
        )
    # If we got here, the function returned — let downstream gates judge correctness.
    assert result is not None
