"""Aligning two versions of a document, and diffing what changed."""

from app.domain.diff import align, count_changes, word_diff
from app.domain.enums import ChangeKind
from app.domain.models import Clause


def clause(clause_id: str, label: str, text: str) -> Clause:
    return Clause(id=clause_id, label=label, text=text)


BEFORE = [
    clause("C1", "3", "Rent shall increase by 5% each year."),
    clause("C2", "4", "The lock-in is 11 months."),
    clause("C3", "5", "Parking is provided at no extra cost."),
]
AFTER = [
    clause("C1", "3", "Rent shall increase by 10% each year."),
    clause("C2", "4", "The lock-in is 11 months."),
    clause("C4", "6", "The premises shall not be painted without consent."),
]


def kinds() -> dict[str, ChangeKind]:
    return {pair.label: pair.change for pair in align(BEFORE, AFTER)}


def test_a_changed_clause_is_classified_as_changed() -> None:
    assert kinds()["3"] is ChangeKind.CHANGED


def test_an_identical_clause_is_classified_as_unchanged() -> None:
    assert kinds()["4"] is ChangeKind.UNCHANGED


def test_a_new_clause_is_classified_as_added() -> None:
    assert kinds()["6"] is ChangeKind.ADDED


def test_a_dropped_clause_is_classified_as_removed() -> None:
    assert kinds()["5"] is ChangeKind.REMOVED


def test_clauses_align_by_label_first() -> None:
    pair = next(pair for pair in align(BEFORE, AFTER) if pair.label == "3")
    assert pair.before is not None
    assert pair.before.id == "C1"


def test_a_renumbered_clause_still_aligns_by_similarity() -> None:
    before = [clause("C1", "3", "Rent shall increase by 5% each year without exception.")]
    after = [clause("C1", "9", "Rent shall increase by 5% each year without exception.")]
    assert align(before, after)[0].change is ChangeKind.UNCHANGED


def test_whitespace_only_differences_are_not_a_change() -> None:
    before = [clause("C1", "3", "Rent  shall   increase.")]
    after = [clause("C1", "3", "Rent shall increase.")]
    assert align(before, after)[0].change is ChangeKind.UNCHANGED


def test_counts_cover_every_kind() -> None:
    counts = count_changes(align(BEFORE, AFTER))
    assert counts == {"added": 1, "removed": 1, "changed": 1, "unchanged": 1}


def test_an_empty_earlier_version_makes_everything_added() -> None:
    pairs = align([], AFTER)
    assert all(pair.change is ChangeKind.ADDED for pair in pairs)


def test_an_empty_later_version_makes_everything_removed() -> None:
    pairs = align(BEFORE, [])
    assert all(pair.change is ChangeKind.REMOVED for pair in pairs)


def test_a_pair_label_prefers_the_later_version() -> None:
    before = [clause("C1", "3", "Some clause text that is long enough to align.")]
    after = [clause("C1", "9", "Some clause text that is long enough to align.")]
    assert align(before, after)[0].label == "9"


def test_a_pair_falls_back_to_the_heading_when_there_is_no_label() -> None:
    before = [Clause(id="C1", heading="Rent", text="Rent is payable monthly always.")]
    after = [Clause(id="C1", heading="Rent", text="Rent is payable quarterly always.")]
    assert align(before, after)[0].label == "Rent"


# ---------------------------------------------------------------- word diff


def test_word_diff_marks_what_was_replaced() -> None:
    tokens = word_diff("Rent increases by 5% each year.", "Rent increases by 10% each year.")
    assert (ChangeKind.REMOVED, "5%") in [(token.kind, token.text) for token in tokens]
    assert (ChangeKind.ADDED, "10%") in [(token.kind, token.text) for token in tokens]


def test_word_diff_keeps_the_unchanged_words() -> None:
    tokens = word_diff("Rent increases by 5%.", "Rent increases by 10%.")
    assert any(token.kind is ChangeKind.UNCHANGED for token in tokens)


def test_word_diff_of_identical_text_has_no_changes() -> None:
    tokens = word_diff("Same text here.", "Same text here.")
    assert all(token.kind is ChangeKind.UNCHANGED for token in tokens)


def test_word_diff_reports_appended_words_as_added() -> None:
    tokens = word_diff("Rent is due.", "Rent is due monthly.")
    added = " ".join(token.text for token in tokens if token.kind is ChangeKind.ADDED)
    assert "monthly." in added


def test_word_diff_produces_no_empty_tokens() -> None:
    tokens = word_diff("", "Something new appeared.")
    assert all(token.text for token in tokens)
