"""Ingestion, samples and file validation over HTTP."""

import io
import zipfile

import pytest
from app.adapters.documents import DOCX_MARKER
from httpx import AsyncClient
from tests.conftest import sample_text

PROBLEM_JSON = "application/problem+json"


async def test_samples_are_listed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/samples")
    assert response.status_code == 200
    ids = {sample["id"] for sample in response.json()}
    assert ids == {
        "leave-licence-v1",
        "leave-licence-v2",
        "offer-letter-bond",
        "legal-notice-old-sections",
    }


async def test_every_sample_ingests(client: AsyncClient) -> None:
    for sample in (await client.get("/api/v1/samples")).json():
        response = await client.get(f"/api/v1/samples/{sample['id']}")
        assert response.status_code == 200, sample["id"]
        assert response.json()["document"]["clauses"]


async def test_an_unknown_sample_is_a_problem_document(client: AsyncClient) -> None:
    response = await client.get("/api/v1/samples/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["type"].endswith("/not-found")


async def test_pasted_text_is_segmented(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/documents/text",
        json={"text": "1. First clause here.\n2. Second clause here.", "title": "test"},
    )
    assert response.status_code == 200
    document = response.json()["document"]
    assert [clause["label"] for clause in document["clauses"]] == ["1", "2"]


async def test_empty_text_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/documents/text", json={"text": ""})
    assert response.status_code == 422


async def test_identifiers_are_masked_before_anything_else(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/documents/text",
        json={"text": "1. Contact the tenant on 9876543210 or at renter@example.com."},
    )
    document = response.json()["document"]
    text = " ".join(clause["text"] for clause in document["clauses"])
    assert "9876543210" not in text
    assert "renter@example.com" not in text
    assert {entry["kind"] for entry in document["masked"]} == {"phone", "email"}


async def test_old_law_references_are_detected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/samples/legal-notice-old-sections")
    references = response.json()["law_references"]
    found = {(reference["act"], reference["section"]) for reference in references}
    assert ("ipc", "420") in found
    assert ("crpc", "154") in found
    assert ("iea", "65B") in found


async def test_a_document_addressing_ai_raises_a_warning(client: AsyncClient) -> None:
    response = await client.get("/api/v1/samples/offer-letter-bond")
    assert "addresses_ai" in response.json()["document"]["warnings"]


async def test_the_deliberate_amount_mismatch_is_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/samples/leave-licence-v1")
    mismatches = response.json()["document"]["amount_mismatches"]
    assert len(mismatches) == 1
    assert mismatches[0]["digits_value"] == 60_000
    assert mismatches[0]["words_value"] == 65_000


async def test_roles_are_suggested_for_the_document_type(client: AsyncClient) -> None:
    response = await client.get("/api/v1/samples/leave-licence-v1")
    assert response.json()["suggested_roles"] == ["tenant", "landlord"]


# ---------------------------------------------------------------- uploads


async def test_a_text_file_uploads(client: AsyncClient) -> None:
    content = sample_text("leave-licence-v1").encode()
    response = await client.post(
        "/api/v1/documents", files={"file": ("agreement.txt", content, "text/plain")}
    )
    assert response.status_code == 200
    assert len(response.json()["document"]["clauses"]) > 10


async def test_an_unknown_format_is_refused_by_its_bytes(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/documents", files={"file": ("a.pdf", b"\x00\x01\x02not a pdf", "application/pdf")}
    )
    assert response.status_code == 415
    assert response.json()["type"].endswith("/unsupported-file-type")


async def test_a_zip_that_is_not_a_word_file_is_refused(client: AsyncClient) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "not a document")
    response = await client.post(
        "/api/v1/documents", files={"file": ("a.docx", buffer.getvalue(), "application/zip")}
    )
    assert response.status_code == 415


async def test_a_zip_bomb_is_refused(client: AsyncClient) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DOCX_MARKER, "<x/>")
        archive.writestr("word/document.xml", "0" * (40 * 1024 * 1024))
    response = await client.post(
        "/api/v1/documents", files={"file": ("bomb.docx", buffer.getvalue(), "application/zip")}
    )
    assert response.status_code == 413
    assert response.json()["type"].endswith("/document-too-large")


async def test_an_oversized_upload_is_refused_before_it_is_read(client: AsyncClient) -> None:
    oversized = b"%PDF-" + b"0" * (11 * 1024 * 1024)
    response = await client.post(
        "/api/v1/documents", files={"file": ("big.pdf", oversized, "application/pdf")}
    )
    assert response.status_code == 413


@pytest.mark.parametrize("clause_count", [0, 1501])
async def test_a_clause_map_outside_the_limits_is_refused(
    client: AsyncClient, clause_count: int
) -> None:
    clauses = [{"id": f"C{index}", "text": "text"} for index in range(clause_count)]
    response = await client.post(
        "/api/v1/analysis/overview",
        json={"document": {"id": "x", "doc_type": "general_contract", "clauses": clauses}},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------- glossary


async def test_the_glossary_is_served_in_every_language(client: AsyncClient) -> None:
    response = await client.get("/api/v1/glossary")
    assert response.status_code == 200
    entries = response.json()
    assert entries
    for entry in entries:
        assert set(entry["meaning"]) == {"en", "hi", "mr"}
        assert entry["term"]
