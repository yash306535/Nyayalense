"""The old-to-new law lookup, and the guarantees around the data behind it."""

import json
from pathlib import Path

import pytest
from app.config import DATA_DIR
from app.domain.enums import ChangeType, LawAct, ReviewStatus
from app.domain.laws.lookup import LawIndex
from app.domain.laws.models import LawMapping, LawTransition, Provision, ProvisionRef, Source
from app.services.registry import Registry
from httpx import AsyncClient

MAPPINGS_DIR = DATA_DIR / "laws" / "mappings"
TEXTS_DIR = DATA_DIR / "laws" / "texts"


def transitions() -> list[LawTransition]:
    return [
        LawTransition.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(MAPPINGS_DIR.glob("*.json"))
    ]


def packaged_provisions() -> list[Provision]:
    return [
        Provision.model_validate(entry)
        for path in sorted(TEXTS_DIR.glob("*.json"))
        for entry in json.loads(path.read_text(encoding="utf-8"))
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


def _mapping(*, verified: bool, section: str = "420") -> LawMapping:
    return LawMapping(
        old=ProvisionRef(act=LawAct.IPC, section=section, title="Cheating"),
        new=[ProvisionRef(act=LawAct.BNS, section="318", title="Cheating")],
        change_type=ChangeType.RENUMBERED,
        source=Source(document="test fixture"),
        review_status=ReviewStatus.VERIFIED if verified else ReviewStatus.EXTRACTED,
        verified_on="2026-09-23" if verified else None,
    )


def _index(*mappings: LawMapping) -> LawIndex:
    transition = LawTransition(
        id="ipc_bns",
        old_act=LawAct.IPC,
        new_act=LawAct.BNS,
        old_act_name="Indian Penal Code, 1860",
        new_act_name="Bharatiya Nyaya Sanhita, 2023",
        in_force_from="2024-07-01",
        source_note="test fixture",
        mappings=list(mappings),
    )
    return LawIndex(transitions=[transition]).build()


def test_an_unreviewed_row_is_hidden_by_default() -> None:
    """A row still marked 'extracted' does not count unless asked for."""
    from app.domain.laws.references import parse_query

    index = _index(_mapping(verified=False))
    reference = parse_query("IPC 420")
    assert reference is not None
    assert index.lookup(reference, include_unreviewed=False) == []
    assert len(index.lookup(reference, include_unreviewed=True)) == 1


def test_a_verified_row_shows_by_default() -> None:
    """Once a row is marked verified, it needs no flag to appear."""
    from app.domain.laws.references import parse_query

    index = _index(_mapping(verified=True))
    reference = parse_query("IPC 420")
    assert reference is not None
    assert len(index.lookup(reference, include_unreviewed=False)) == 1


async def test_every_packaged_mapping_has_been_reviewed(client: AsyncClient) -> None:
    """The packaged data ships reviewed, so a lookup needs no special flag."""
    body = (await client.get("/api/v1/laws/lookup", params={"q": "IPC 420"})).json()
    assert body["mappings"] != []
    assert all(m["review_status"] == "verified" for m in body["mappings"])


async def test_an_unparseable_query_returns_nothing_rather_than_a_guess(
    client: AsyncClient,
) -> None:
    body = (await client.get("/api/v1/laws/lookup", params={"q": "hello there"})).json()
    assert body["reference"] is None
    assert body["mappings"] == []
    assert body["suggestions"] == []


# ---------------------------------------------------------------- topic search


def test_search_by_topic_finds_a_mapping_by_its_own_title() -> None:
    """A word naming no act, like 'cheating', still finds the row."""
    index = _index(_mapping(verified=True))
    hits = index.search_by_topic("cheating", include_unreviewed=False)
    assert [hit.mapping.old.section for hit in hits] == ["420"]


def test_search_by_topic_works_on_a_full_question_not_just_a_bare_word() -> None:
    """Filler words are dropped before scoring, so a whole sentence still matches."""
    index = _index(_mapping(verified=True))
    hits = index.search_by_topic("What counts as cheating under the law?", include_unreviewed=False)
    assert len(hits) == 1


def test_search_by_topic_finds_nothing_for_an_unrelated_word() -> None:
    index = _index(_mapping(verified=True))
    assert index.search_by_topic("photosynthesis", include_unreviewed=False) == []


def test_search_by_topic_matches_a_title_on_the_new_side_alone() -> None:
    """A row whose old title shares no word with the query is found by its new one."""
    renamed = LawMapping(
        old=ProvisionRef(act=LawAct.IPC, section="124A", title="Sedition"),
        new=[ProvisionRef(act=LawAct.BNS, section="152", title="Endangering sovereignty")],
        change_type=ChangeType.MODIFIED,
        source=Source(document="test fixture"),
        review_status=ReviewStatus.VERIFIED,
        verified_on="2026-09-23",
    )
    index = _index(_mapping(verified=True), renamed)
    hits = index.search_by_topic("sovereignty", include_unreviewed=False)
    assert [hit.mapping.old.section for hit in hits] == ["124A"]


def test_search_by_topic_hides_an_unreviewed_row_by_default() -> None:
    index = _index(_mapping(verified=False))
    assert index.search_by_topic("cheating", include_unreviewed=False) == []
    assert len(index.search_by_topic("cheating", include_unreviewed=True)) == 1


async def test_a_topic_query_reaches_the_lookup_endpoint(client: AsyncClient) -> None:
    """The same endpoint a citation uses also answers a plain topic."""
    body = (await client.get("/api/v1/laws/lookup", params={"q": "cheating"})).json()
    assert body["reference"] is None
    assert body["mappings"] != []
    assert any(m["old"]["act"] == "ipc" for m in body["mappings"])


def test_matching_provisions_resolves_real_stored_text() -> None:
    """A topic match with stored text on both sides yields real clauses to answer from."""
    index = _index(_mapping(verified=True))
    index.provisions["ipc:420"] = Provision(
        act=LawAct.IPC,
        section="420",
        title="Cheating",
        text="Whoever cheats shall be punished.",
        source=Source(document="test fixture"),
        review_status=ReviewStatus.VERIFIED,
        verified_on="2026-09-23",
    )
    matched = index.matching_provisions("cheating")
    assert [provision.key for provision in matched] == ["ipc:420"]


def test_matching_provisions_skips_a_match_with_no_stored_text() -> None:
    """A topic match is not enough on its own: there has to be text to quote."""
    index = _index(_mapping(verified=True))
    assert index.matching_provisions("cheating") == []


# ---------------------------------------------------------------- general legal Q&A


async def test_a_legal_question_answers_from_matched_sections(client: AsyncClient) -> None:
    body = (
        await client.post("/api/v1/laws/qa", json={"question": "What is the punishment for rape?"})
    ).json()
    assert body["matched"] != []
    assert {p["act"] for p in body["matched"]} >= {"ipc", "bns"}
    assert body["answer"]["answer_type"] in {"direct", "interpretation"}
    assert body["answer"]["verification"]["verified"] > 0
    for statement in body["answer"]["statements"]:
        assert statement["citations"]
        assert all(citation["verified"] for citation in statement["citations"])


async def test_a_legal_question_with_no_topic_match_is_not_found(client: AsyncClient) -> None:
    body = (
        await client.post(
            "/api/v1/laws/qa", json={"question": "asdkjh qlwkejr nonsense zztelevision"}
        )
    ).json()
    assert body["matched"] == []
    assert body["answer"]["answer_type"] == "not_found"
    assert body["answer"]["statements"] == []


async def test_an_empty_legal_question_is_refused(client: AsyncClient) -> None:
    response = await client.post("/api/v1/laws/qa", json={"question": ""})
    assert response.status_code == 422


async def test_an_empty_query_is_refused(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/laws/lookup", params={"q": ""})).status_code == 422


def test_every_packaged_provision_matches_the_schema() -> None:
    """Statutory text is never written from memory, only copied from a source."""
    assert len(packaged_provisions()) > 0


def test_every_packaged_provision_has_been_reviewed() -> None:
    """Every stored text has been checked against the India Code page it cites."""
    assert [
        provision.key
        for provision in packaged_provisions()
        if provision.review_status is not ReviewStatus.VERIFIED or not provision.verified_on
    ] == []


def test_a_provision_cannot_claim_verified_without_a_date() -> None:
    """Extraction alone can never produce this state: the schema forbids it."""
    with pytest.raises(ValueError, match="verified provision must carry"):
        Provision(
            act=LawAct.IPC,
            section="420",
            title="Cheating",
            text="Whoever cheats.",
            source=Source(document="test fixture"),
            review_status=ReviewStatus.VERIFIED,
        )


def test_every_packaged_provision_cites_india_code() -> None:
    """Every stored text carries the public page it can be checked against."""
    assert [
        provision.key
        for provision in packaged_provisions()
        if not provision.source.url.startswith("https://indiacode.gov.in/")
    ] == []


def test_no_crpc_text_is_packaged() -> None:
    """The only copy India Code still publishes is a scan too degraded to quote.

    Rather than show a user a sentence that reads ``Code ot Criminai
    .Procedure``, CrPC sections ship with no stored text at all.
    """
    assert [p.key for p in packaged_provisions() if p.act is LawAct.CRPC] == []


def test_a_stored_text_rides_along_with_its_unreviewed_mapping() -> None:
    """A provision text carries no review flag of its own: it is only ever
    shown attached to a mapping row, so hiding the row hides the text too.
    """
    index = _index(_mapping(verified=False))
    index.provisions["ipc:420"] = Provision(
        act=LawAct.IPC,
        section="420",
        title="Cheating",
        text="Whoever cheats.",
        source=Source(document="test fixture"),
    )
    from app.domain.laws.references import parse_query
    from app.services.laws import lookup

    reference = parse_query("IPC 420")
    assert reference is not None
    found = lookup("IPC 420", index, include_unreviewed=False)
    assert found.mappings == []
    assert found.provisions == {}


async def test_a_lookup_shows_the_reviewed_text_by_default(client: AsyncClient) -> None:
    """The packaged data ships reviewed, so its stored text needs no flag either."""
    body = (await client.get("/api/v1/laws/lookup", params={"q": "IPC 420"})).json()
    assert "ipc:420" in body["provisions"]


def test_both_sides_of_a_reviewed_mapping_carry_their_text(registry: Registry) -> None:
    """With both texts stored, the word-level diff switches on by itself."""
    from app.services.laws import lookup, provision_diff

    found = lookup("IPC 420", registry.laws, include_unreviewed=True)
    mapping = found.mappings[0]
    old = found.provisions[mapping.old.key]
    new = found.provisions[mapping.new[0].key]

    assert "dishonestly induces the person deceived" in old.text
    assert provision_diff(old, new) != []


def test_a_crpc_lookup_still_offers_the_new_text_alone(registry: Registry) -> None:
    """A missing old text is a gap, not a failure: the new side still shows."""
    from app.services.laws import lookup

    found = lookup("CrPC 154", registry.laws, include_unreviewed=True)
    mapping = found.mappings[0]
    assert mapping.old.key not in found.provisions
    assert found.provisions[mapping.new[0].key].text


async def test_comparing_without_stored_texts_generates_no_explanation(
    client: AsyncClient,
) -> None:
    """CrPC has no stored text on the old side, so there is nothing to diff."""
    response = await client.post("/api/v1/laws/compare", json={"act": "crpc", "section": "154"})
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

    # BNS 318 (cheating) consolidates several IPC cheating provisions, so the
    # reverse lookup is a superset check: 420 must be among them, not the whole set.
    reverse = registry.laws.lookup(parse_query("BNS 318"), include_unreviewed=True)
    assert "420" in {hit.mapping.old.section for hit in reverse}
    assert all(hit.is_reverse for hit in reverse)


def test_a_mistyped_section_query_returns_plausible_suggestions(registry: Registry) -> None:
    from app.domain.laws.references import parse_query

    # A one-digit-off typo of a real section (420), among other real
    # neighbours. The closest numeric match must be offered, not just any
    # candidate that happens to share characters with the query.
    suggestions = registry.laws.suggest(parse_query("IPC 421"))
    assert suggestions
    assert all(key.startswith("ipc:") for key in suggestions)
    assert "ipc:420" in suggestions


def test_suggestions_are_ranked_by_numeric_closeness_not_string_overlap(
    registry: Registry,
) -> None:
    """429 sits between real sections 426-431; a distant coincidental string
    match like "29" must never outrank a numerically close real section.
    """
    from app.domain.laws.references import parse_query

    suggestions = registry.laws.suggest(parse_query("IPC 429"))
    assert suggestions
    assert "ipc:29" not in suggestions
    sections = [int(key.split(":")[1]) for key in suggestions]
    assert all(abs(section - 429) <= 5 for section in sections)


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
