# Stretch Tue — Learner Notes

## Design decisions

In `verify_claim`, I implemented the critic as a four-stage cascade where the first matching stage returns immediately.

For Stage 1, I handled direct support first. For relationship predicates such as `USES_INGREDIENT`, `OF_CUISINE`, `BY_AUTHOR`, and `REQUIRES_TECHNIQUE`, I used directed Cypher `MATCH` queries from the subject entity to the object entity. For the `type` predicate, I treated the direct case as the reflexive depth-0 case where `subject_id == object_id`.

For Stage 2, I used a separate variable-length `SUBCLASS_OF` query with depth at least one: `[:SUBCLASS_OF*1..]`. I chose this instead of using `[:SUBCLASS_OF*0..]` because Stage 1 already handles the depth-0 reflexive case. Keeping Stage 2 at depth >= 1 makes the distinction between `supported` and `entailed` clearer.

For Stage 3, I fetched the subject and object labels once per verification call using the provided `_labels_of` helper. I did not cache labels across calls because the fixture is small and the implementation is easier to reason about. The schema constraints are only applied to relationship predicates in `SCHEMA_CONSTRAINTS`; the `type` predicate is skipped because it is governed by the `SUBCLASS_OF` hierarchy.

I considered using one generic Cypher query with the relationship type inserted dynamically, but I avoided interpolating claim values into Cypher. Subject and object ids are always passed as parameters. I also kept the confidence values exactly as specified by the cascade: `1.0` for supported, `0.7` for entailed, `0.8` for contradicted, and `0.5` for unsupported.

## Eval-set behavior

I ran the local autograder with:

`pytest tests/ -v`

The critic passed the eval gates. The observed behavior matched the expected four-stage cascade.

| Class        | Precision | Recall |
| ------------ | --------: | -----: |
| supported    |      1.00 |   1.00 |
| entailed     |         - |   1.00 |
| contradicted |      1.00 |      - |

The hardest class conceptually was `entailed`, because it requires walking the `SUBCLASS_OF` hierarchy instead of only checking direct edges. A direct-exists-only critic would miss these claims completely.

No individual claim surprised me after inspecting the cascade. The main thing to watch was the direction of `SUBCLASS_OF`: the traversal must go from the subject toward the object.

## Abstention boundary

The critic should return `unsupported` when the graph does not directly support the claim, does not entail it through the hierarchy, and does not show a domain/range schema violation. This follows the open-world assumption: the graph may simply not contain enough information to decide.

Over-flagging a claim as `contradicted` is worse than abstaining because `contradicted` makes a stronger statement. It says the claim is structurally impossible according to the schema, not just missing from the graph. If the critic marks unknown claims as contradictions, it becomes overconfident and less trustworthy.

## Optional — M8 router warm-up

I skipped the optional M8 router warm-up because my M8 stretch router was not part of this repository branch. The M9 KG critic still works as a standalone verifier through `verify_claim(driver, claim)`.
