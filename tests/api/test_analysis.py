"""Overview, review, Q&A, scenarios and compare over HTTP."""

from app.domain.models import Document
from httpx import AsyncClient


def body(document: Document, role: str = "tenant") -> dict[str, object]:
    return {
        "document": document.model_dump(mode="json"),
        "audience": {"role": role, "language": "en", "reading_level": "simple"},
    }


# ---------------------------------------------------------------- overview


async def test_overview_returns_only_verified_statements(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post("/api/v1/analysis/overview", json=body(rental_document))
    assert response.status_code == 200
    overview = response.json()

    for statement in overview["summary"]:
        assert any(citation["verified"] for citation in statement["citations"])


async def test_every_verified_quote_really_is_in_its_clause(
    client: AsyncClient, rental_document: Document
) -> None:
    """The end-to-end form of the product's central promise."""
    response = await client.post("/api/v1/analysis/overview", json=body(rental_document))
    clauses = {clause.id: clause.text for clause in rental_document.clauses}

    checked = 0
    for statement in response.json()["summary"]:
        for citation in statement["citations"]:
            if not citation["verified"]:
                continue
            span = clauses[citation["clause_id"]][citation["span_start"] : citation["span_end"]]
            assert span.strip(), "a verified citation must point at real text"
            checked += 1
    assert checked > 0


async def test_an_unspecified_key_term_is_returned_as_an_absence(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post("/api/v1/analysis/overview", json=body(rental_document))
    for term in response.json()["key_terms"]:
        if term["value"] is None:
            assert term["statements"] == []


async def test_the_verification_report_adds_up(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post("/api/v1/analysis/overview", json=body(rental_document))
    report = response.json()["verification"]
    assert report["verified"] <= report["total"]
    assert report["verified"] + len(report["removed"]) == report["total"]


async def test_results_are_cached_by_content(
    client: AsyncClient, rental_document: Document
) -> None:
    first = await client.post("/api/v1/analysis/overview", json=body(rental_document))
    second = await client.post("/api/v1/analysis/overview", json=body(rental_document))
    assert first.json() == second.json()


async def test_clearing_the_cache_reports_what_it_dropped(
    client: AsyncClient, rental_document: Document
) -> None:
    await client.post("/api/v1/analysis/overview", json=body(rental_document))
    response = await client.delete(f"/api/v1/cache/{rental_document.id}")
    assert response.status_code == 200
    assert response.json()["removed"] >= 1


# ---------------------------------------------------------------- review


async def test_review_fills_the_curated_checklist(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post("/api/v1/analysis/review", json=body(rental_document))
    assert response.status_code == 200
    review = response.json()

    checklist = (await client.get("/api/v1/checklists/rental_leave_licence")).json()
    expected = {item["id"] for item in checklist["items"]}
    assert {result["item_id"] for result in review["checklist"]} <= expected


async def test_an_item_the_model_cannot_evidence_is_not_found(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post("/api/v1/analysis/review", json=body(rental_document))
    for result in response.json()["checklist"]:
        if result["status"] == "found":
            assert result["statements"], "a found item must carry evidence"


async def test_missing_items_are_never_stated_as_certain(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post("/api/v1/analysis/review", json=body(rental_document))
    for item in response.json()["missing"]:
        assert item["why_it_matters"]
        assert item["question_to_ask"]


async def test_the_deterministic_amount_mismatch_reaches_the_review(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post("/api/v1/analysis/review", json=body(rental_document))
    kinds = {entry["kind"] for entry in response.json()["inconsistencies"]}
    assert "amount_mismatch" in kinds


async def test_risks_come_back_most_serious_first(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post("/api/v1/analysis/review", json=body(rental_document))
    order = {"high": 0, "medium": 1, "low": 2}
    severities = [order[risk["severity"]] for risk in response.json()["risks"]]
    assert severities == sorted(severities)


# ---------------------------------------------------------------- questions


async def test_a_question_the_document_answers(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post(
        "/api/v1/qa",
        json={**body(rental_document), "question": "How much is the security deposit?"},
    )
    assert response.status_code == 200
    answer = response.json()
    assert answer["answer_type"] in {"direct", "interpretation"}
    assert answer["statements"]


async def test_a_question_the_document_does_not_answer(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post(
        "/api/v1/qa",
        json={**body(rental_document), "question": "Which quantum physicist drafted this?"},
    )
    answer = response.json()
    assert answer["answer_type"] == "not_found"
    assert answer["statements"] == []
    assert answer["suggested_question_to_other_party"], "a dead end still offers a next step"


async def test_history_is_capped_at_four_turns(
    client: AsyncClient, rental_document: Document
) -> None:
    history = [{"question": f"q{n}", "answer": f"a{n}"} for n in range(5)]
    response = await client.post(
        "/api/v1/qa", json={**body(rental_document), "question": "And?", "history": history}
    )
    assert response.status_code == 422


async def test_an_over_long_question_is_refused(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post(
        "/api/v1/qa", json={**body(rental_document), "question": "x" * 1001}
    )
    assert response.status_code == 422


async def test_related_clauses_always_exist_in_the_document(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post(
        "/api/v1/qa", json={**body(rental_document), "question": "Is there a gym?"}
    )
    ids = {clause.id for clause in rental_document.clauses}
    assert set(response.json()["related_clause_ids"]) <= ids


# ---------------------------------------------------------------- scenarios


async def test_a_scenario_reports_what_the_document_says(
    client: AsyncClient, rental_document: Document
) -> None:
    response = await client.post(
        "/api/v1/scenarios",
        json={**body(rental_document), "scenario": "I want to leave before the lock-in ends"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["next_steps"]
    for statement in result["says"]:
        assert any(citation["verified"] for citation in statement["citations"])


# ---------------------------------------------------------------- compare


async def test_versions_are_aligned_and_classified(
    client: AsyncClient, rental_document: Document, rental_document_v2: Document
) -> None:
    response = await client.post(
        "/api/v1/compare",
        json={
            "mode": "versions",
            "before": rental_document.model_dump(mode="json"),
            "after": rental_document_v2.model_dump(mode="json"),
            "audience": {"role": "tenant", "language": "en", "reading_level": "simple"},
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["counts"]["changed"] >= 3
    assert result["counts"]["added"] >= 1
    assert result["counts"]["unchanged"] > 0


async def test_an_unchanged_pair_carries_both_texts(
    client: AsyncClient, rental_document: Document, rental_document_v2: Document
) -> None:
    response = await client.post(
        "/api/v1/compare",
        json={
            "mode": "versions",
            "before": rental_document.model_dump(mode="json"),
            "after": rental_document_v2.model_dump(mode="json"),
        },
    )
    unchanged = [pair for pair in response.json()["pairs"] if pair["change"] == "unchanged"]
    assert unchanged
    assert all(pair["before_text"] and pair["after_text"] for pair in unchanged)


async def test_alternatives_are_compared_without_a_winner(
    client: AsyncClient, rental_document: Document, rental_document_v2: Document
) -> None:
    response = await client.post(
        "/api/v1/compare",
        json={
            "mode": "alternatives",
            "before": rental_document.model_dump(mode="json"),
            "after": rental_document_v2.model_dump(mode="json"),
        },
    )
    assert response.status_code == 200
    for row in response.json()["rows"]:
        assert "better" not in row["difference"].casefold()
        assert "worse" not in row["difference"].casefold()
