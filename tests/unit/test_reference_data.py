"""The packaged data files, and the loaders that refuse a bad one."""

import json
from pathlib import Path

import pytest
from app.config import DATA_DIR
from app.domain.checklists import MAX_ITEMS, MIN_ITEMS, Checklist
from app.domain.enums import DocType, Language, ResourceCategory, Role
from app.domain.glossary import Glossary
from app.domain.resources import ResourceDirectory
from app.errors import DataFileError, NotFoundError
from app.services.registry import Registry, load_registry


def checklists() -> list[Checklist]:
    return [
        Checklist.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((DATA_DIR / "checklists").glob("*.json"))
    ]


# ---------------------------------------------------------------- checklists


def test_there_is_a_checklist_for_every_document_type() -> None:
    assert {checklist.doc_type for checklist in checklists()} == set(DocType)


def test_every_checklist_is_the_right_size() -> None:
    for checklist in checklists():
        assert MIN_ITEMS <= len(checklist.items) <= MAX_ITEMS


def test_every_item_says_what_to_look_for_and_what_to_ask() -> None:
    for checklist in checklists():
        for item in checklist.items:
            assert item.look_for
            assert item.why_it_matters
            assert item.question_to_ask


def test_every_checklist_states_that_it_is_not_legal_rules() -> None:
    for checklist in checklists():
        assert "not legal rules" in checklist.note.casefold()


def test_every_checklist_offers_questions_scenarios_and_lists() -> None:
    for checklist in checklists():
        assert checklist.suggested_questions
        assert checklist.scenarios
        assert checklist.facts_to_have_ready
        assert checklist.documents_to_bring


def test_items_can_be_narrowed_to_a_role() -> None:
    rental = next(c for c in checklists() if c.doc_type is DocType.RENTAL_LEAVE_LICENCE)
    tenant_items = rental.for_role(Role.TENANT)
    landlord_items = rental.for_role(Role.LANDLORD)
    assert len(tenant_items) > len(landlord_items)


def test_the_prompt_lines_name_every_relevant_item() -> None:
    rental = next(c for c in checklists() if c.doc_type is DocType.RENTAL_LEAVE_LICENCE)
    lines = rental.as_prompt_lines(Role.TENANT)
    for item in rental.for_role(Role.TENANT):
        assert f"- {item.id}:" in lines


def test_a_checklist_with_too_few_items_is_refused() -> None:
    with pytest.raises(ValueError, match="checklist items"):
        Checklist.model_validate(
            {
                "doc_type": "nda",
                "title": "t",
                "items": [
                    {
                        "id": "a",
                        "title": "t",
                        "look_for": "l",
                        "why_it_matters": "w",
                        "question_to_ask": "q",
                    }
                ],
            }
        )


# ---------------------------------------------------------------- glossary


def test_the_glossary_defines_every_term_in_all_three_languages() -> None:
    glossary = Glossary.model_validate(json.loads((DATA_DIR / "glossary.json").read_text("utf-8")))
    for entry in glossary.entries:
        assert set(entry.meaning) == set(Language), entry.term


def test_a_glossary_term_is_found_by_its_aliases() -> None:
    glossary = Glossary.model_validate(json.loads((DATA_DIR / "glossary.json").read_text("utf-8")))
    assert glossary.find("non compete") is not None
    assert glossary.find("NON-COMPETE") is not None
    assert glossary.find("not a legal term at all") is None


def test_terms_present_in_a_clause_are_detected() -> None:
    glossary = Glossary.model_validate(json.loads((DATA_DIR / "glossary.json").read_text("utf-8")))
    found = {
        entry.term for entry in glossary.present_in("The Licensee shall indemnify the Licensor.")
    }
    assert {"indemnify", "licensee", "licensor"} <= found


def test_a_meaning_falls_back_to_english() -> None:
    glossary = Glossary.model_validate(json.loads((DATA_DIR / "glossary.json").read_text("utf-8")))
    entry = glossary.entries[0]
    assert entry.meaning_in(Language.MR)


# ---------------------------------------------------------------- resources


def directory() -> ResourceDirectory:
    return ResourceDirectory.model_validate(
        json.loads((DATA_DIR / "resources.json").read_text("utf-8"))
    )


def test_every_resource_names_its_source_and_the_date_it_was_checked() -> None:
    for entry in directory().entries:
        assert entry.source_url.startswith("https://")
        assert entry.verified_on


def test_every_resource_link_is_https() -> None:
    for entry in directory().entries:
        if entry.contact.url:
            assert entry.contact.url.startswith("https://")


def test_phone_numbers_are_dialable() -> None:
    for entry in directory().entries:
        if entry.contact.phone:
            assert entry.contact.phone.replace(" ", "").replace("-", "").lstrip("+").isdigit()


def test_free_legal_aid_is_always_offered() -> None:
    relevant = directory().relevant(doc_type=None, situations=set(), limit=3)
    assert relevant[0].category is ResourceCategory.LEGAL_AID


def test_cyber_crime_surfaces_for_online_fraud() -> None:
    relevant = directory().relevant(doc_type=None, situations={"online_fraud"}, limit=3)
    assert any(entry.category is ResourceCategory.CYBER_CRIME for entry in relevant)


def test_consumer_routes_surface_for_an_insurance_policy() -> None:
    relevant = directory().relevant(doc_type=DocType.INSURANCE_POLICY, situations=set(), limit=4)
    assert any(entry.category is ResourceCategory.CONSUMER for entry in relevant)


def test_a_resource_with_no_way_to_reach_it_is_refused() -> None:
    with pytest.raises(ValueError, match="URL or a phone"):
        ResourceDirectory.model_validate(
            {
                "entries": [
                    {
                        "id": "x",
                        "name": "X",
                        "category": "legal_aid",
                        "purpose": {"en": "x"},
                        "contact": {},
                        "source_url": "https://example.gov.in",
                        "verified_on": "2026-01-01",
                    }
                ]
            }
        )


def test_an_http_link_is_refused() -> None:
    with pytest.raises(ValueError, match="pattern"):
        ResourceDirectory.model_validate(
            {
                "entries": [
                    {
                        "id": "x",
                        "name": "X",
                        "category": "legal_aid",
                        "purpose": {"en": "x"},
                        "contact": {"url": "http://insecure.example"},
                        "source_url": "https://example.gov.in",
                        "verified_on": "2026-01-01",
                    }
                ]
            }
        )


# ---------------------------------------------------------------- the registry


def test_the_registry_loads_everything(registry: Registry) -> None:
    assert len(registry.checklists) == len(DocType)
    assert registry.glossary.entries
    assert registry.resources.entries
    assert len(registry.samples) == 4
    assert registry.laws.counts()["mappings"] > 50


def test_asking_for_an_unknown_sample_raises(registry: Registry) -> None:
    with pytest.raises(NotFoundError):
        registry.sample("nope")


def test_a_missing_data_file_stops_the_process(tmp_path: Path) -> None:
    from app.services import registry as module

    original = module.CHECKLISTS_DIR
    module.CHECKLISTS_DIR = tmp_path
    try:
        with pytest.raises(DataFileError, match="No checklist for"):
            load_registry.__wrapped__() if hasattr(
                load_registry, "__wrapped__"
            ) else module._load_checklists()
    finally:
        module.CHECKLISTS_DIR = original


def test_invalid_json_stops_the_process(tmp_path: Path) -> None:
    from app.services import registry as module

    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    original = module.CHECKLISTS_DIR
    module.CHECKLISTS_DIR = tmp_path
    try:
        with pytest.raises(DataFileError, match="not valid JSON"):
            module._load_checklists()
    finally:
        module.CHECKLISTS_DIR = original
