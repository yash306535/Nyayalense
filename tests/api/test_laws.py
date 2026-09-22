"""The old-to-new law lookup, and the guarantees around the data behind it."""

import json
from pathlib import Path

import pytest
from app.config import DATA_DIR
from app.domain.enums import ChangeType, LawAct, ReviewStatus
from app.domain.laws.models import LawTransition
from app.services.registry import Registry
from httpx import AsyncClient

MAPPINGS_DIR = DATA_DIR / "laws" / "mappings"


def transitions() -> list[LawTransition]:
    return [
        LawTransition.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(MAPPINGS_DIR.glob("*.json"))
    ]


def all_mappings() -> list[object]:
    return [mapping for transition in transitions() for mapping in transition.mappings]


# ---------------------------------------------------------------- the data itself


def test_every_transition_file_matches_the_schema() -> None:
    assert len(transitions()) == 3


def test_the_three_criminal_law_transitions_are_covered() -> None:
    pairs = {(transition.old_act, transition.new_act) for transition in transitions()}
    assert pairs == {
        (LawAct.IPC, LawAct.BNS),
        (LawAct.CRPC, LawAct.BNSS),
        (LawAct.IEA, LawAct.BSA),
    }


def test_every_row_names_its_source() -> None:
    for mapping in all_mappings():
        assert mapping.source.document, f"{mapping.old.key} has no source"


def test_a_verified_row_always_carries_the_date_it_was_verified() -> None:
    for mapping in all_mappings():
        if mapping.review_status is ReviewStatus.VERIFIED:
            assert mapping.verified_on, f"{mapping.old.key} is verified with no date"


def test_old_sections_are_unique_within_a_transition() -> None:
    for transition in transitions():
        keys = [mapping.old.key for mapping in transition.mappings]
        assert len(set(keys)) == len(keys), f"{transition.id} has duplicate rows"


def test_the_new_codes_came_into_force_on_the_same_date() -> None:
    assert {transition.in_force_from for transition in transitions()} == {"2024-07-01"}


# ---------------------------------------------------------------- trap tests


def test_sedition_is_never_shown_as_a_simple_renumbering() -> None:
    """IPC 124A has no counterpart presented as a renumbering. This must hold."""
    row = next(m for m in all_mappings() if m.old.act is LawAct.IPC and m.old.section == "124A")
    assert row.change_type is ChangeType.NO_DIRECT_EQUIVALENT
    assert row.new == []
    assert row.note


@pytest.mark.parametrize("section", ["377", "497"])
def test_provisions_not_carried_forward_say_so(section: str) -> None:
    row = next(m for m in all_mappings() if m.old.act is LawAct.IPC and m.old.section == section)
    assert row.change_type is ChangeType.NO_DIRECT_EQUIVALENT
    assert row.new == []


def test_bns_302_is_not_murder() -> None:
    """A trap: BNS 302 is snatching, not murder. Murder is BNS 103."""
    reverse = [m for m in all_mappings() if any(new.section == "302" for new in m.new)]
    for mapping in reverse:
        assert "murder" not in mapping.old.title.casefold()


def test_murder_maps_to_the_right_new_section() -> None:
    row = next(m for m in all_mappings() if m.old.act is LawAct.IPC and m.old.section == "302")
    assert [new.section for new in row.new] == ["103"]


def test_cruelty_is_split_across_two_new_sections() -> None:
    row = next(m for m in all_mappings() if m.old.act is LawAct.IPC and m.old.section == "498A")
    assert row.change_type is ChangeType.SPLIT
    assert {new.section for new in row.new} == {"85", "86"}


# ---------------------------------------------------------------- the API


async def test_lookup_finds_a_mapping(client: AsyncClient, registry: Registry) -> None:
    response = await client.get("/api/v1/laws/lookup", params={"q": "IPC 420"})
    assert response.status_code == 200
    body = response.json()
    assert body["reference"]["section"] == "420"
    assert body["source_note"]
    assert body["when_each_applies"].startswith("The new codes came into force")
    del registry


async def test_unreviewed_rows_are_hidden_by_default(client: AsyncClient) -> None:
    """Every seed row is unreviewed, so the default deployment shows none."""
    body = (await client.get("/api/v1/laws/lookup", params={"q": "IPC 420"})).json()
    assert body["mappings"] == []


async def test_an_unparseable_query_returns_nothing_rather_than_a_guess(
    client: AsyncClient,
) -> None:
    body = (await client.get("/api/v1/laws/lookup", params={"q": "hello there"})).json()
    assert body["reference"] is None
    assert body["mappings"] == []
    assert body["suggestions"] == []


async def test_an_empty_query_is_refused(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/laws/lookup", params={"q": ""})).status_code == 422


async def test_no_provision_texts_are_packaged_yet(client: AsyncClient) -> None:
    """Statutory text is never written from memory; none ships until copied."""
    assert list((DATA_DIR / "laws" / "texts").glob("*.json")) == []
    body = (await client.get("/api/v1/laws/lookup", params={"q": "IPC 420"})).json()
    assert body["provisions"] == {}


async def test_comparing_without_stored_texts_generates_no_explanation(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/laws/compare", json={"act": "ipc", "section": "420"})
    assert response.status_code == 200
    body = response.json()
    assert body["diff"] == []
    assert body["what_changed"] is None


async def test_the_direct_provision_route_works(client: AsyncClient) -> None:
    response = await client.get("/api/v1/laws/ipc/420")
    assert response.status_code == 200
    assert response.json()["reference"]["section"] == "420"


async def test_browse_lists_require_a_known_kind(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/laws/changes", params={"kind": "nope"})).status_code == 422
    assert (await client.get("/api/v1/laws/changes", params={"kind": "removed"})).status_code == 200


def test_the_law_index_reads_in_both_directions(registry: Registry) -> None:
    from app.domain.laws.references import parse_query

    forward = registry.laws.lookup(parse_query("IPC 420"), include_unreviewed=True)
    assert [hit.mapping.new[0].section for hit in forward] == ["318"]

    reverse = registry.laws.lookup(parse_query("BNS 318"), include_unreviewed=True)
    assert {hit.mapping.old.section for hit in reverse} == {"415", "420"}
    assert all(hit.is_reverse for hit in reverse)


def test_a_mistyped_section_gets_suggestions(registry: Registry) -> None:
    from app.domain.laws.references import parse_query

    suggestions = registry.laws.suggest(parse_query("IPC 421"))
    assert "ipc:420" in suggestions


def test_a_data_file_that_breaks_its_schema_stops_the_process(tmp_path: Path) -> None:
    from app.errors import DataFileError
    from app.services import registry as registry_module

    bad = tmp_path / "broken.json"
    bad.write_text('{"id": "x", "old_act": "ipc"}', encoding="utf-8")

    original = registry_module.LAW_MAPPINGS_DIR
    registry_module.LAW_MAPPINGS_DIR = tmp_path
    try:
        with pytest.raises(DataFileError):
            registry_module._load_laws()
    finally:
        registry_module.LAW_MAPPINGS_DIR = original
