"""OPTIONAL — M8 stretch query router warm-up."""

from critic.verify import verify_claim


def register_kg_branch(router, neo4j_driver) -> None:
    """Register the M9 KG critic as the KG verification branch.

    When the router classifies a query as "verify_claim", this branch
    extracts the structured claim tuple and sends it to verify_claim.
    """

    def kg_branch(query):
        # Expected shape from the reference:
        # query.payload["claim"] == (subject_id, predicate, object_id)

        if hasattr(query, "payload"):
            claim = query.payload["claim"]
        elif isinstance(query, dict):
            claim = query["payload"]["claim"]
        else:
            raise ValueError("Query must expose a payload containing a claim.")

        return verify_claim(neo4j_driver, claim)

    router.register("verify_claim", kg_branch)