"""Align two versions of a document and diff the clauses that changed.

Alignment is deterministic: the document's own numbering first, then text
similarity for clauses that were renumbered. Only the pairs that actually differ
are ever sent to a model, which keeps a comparison cheap and keeps the *what*
changed separate from the *why it matters*.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Final

from rapidfuzz import fuzz, process

from app.domain.enums import ChangeKind
from app.domain.models import Clause
from app.domain.normalize import normalize

#: Similarity above which two unlabelled clauses are treated as the same clause.
ALIGN_THRESHOLD: Final = 75

#: Similarity above which an aligned pair counts as unchanged apart from wording.
UNCHANGED_THRESHOLD: Final = 99.5


@dataclass(frozen=True, slots=True)
class AlignedPair:
    """Two clauses that correspond, or one clause with no counterpart."""

    change: ChangeKind
    before: Clause | None
    after: Clause | None

    @property
    def label(self) -> str:
        """The clause label to show, preferring the newer version's."""
        for clause in (self.after, self.before):
            if clause is not None and clause.label:
                return clause.label
        for clause in (self.after, self.before):
            if clause is not None:
                return clause.heading or clause.id
        return ""


@dataclass(frozen=True, slots=True)
class DiffToken:
    """A run of words shared, added or removed between two texts."""

    kind: ChangeKind
    text: str


def align(before: list[Clause], after: list[Clause]) -> list[AlignedPair]:
    """Pair up the clauses of two versions of a document.

    Args:
        before: Clauses of the earlier version.
        after: Clauses of the later version.

    Returns:
        One pair per clause of either version, in the order of the later
        version, with removed clauses appended where they were.
    """
    by_label = {clause.label: clause for clause in before if clause.label}
    unmatched = list(before)
    pairs: list[AlignedPair] = []

    for clause in after:
        match = by_label.get(clause.label) if clause.label else None
        if match is None:
            match = _closest(clause, unmatched)
        if match is None:
            pairs.append(AlignedPair(ChangeKind.ADDED, None, clause))
            continue
        if match in unmatched:
            unmatched.remove(match)
        pairs.append(AlignedPair(_classify(match, clause), match, clause))

    pairs.extend(AlignedPair(ChangeKind.REMOVED, clause, None) for clause in unmatched)
    return pairs


def _closest(clause: Clause, candidates: list[Clause]) -> Clause | None:
    """Find the most similar unmatched clause, if any is similar enough."""
    if not candidates:
        return None
    texts = [normalize(candidate.text) for candidate in candidates]
    result = process.extractOne(
        normalize(clause.text), texts, scorer=fuzz.token_set_ratio, score_cutoff=ALIGN_THRESHOLD
    )
    return candidates[result[2]] if result else None


def _classify(before: Clause, after: Clause) -> ChangeKind:
    """Decide whether an aligned pair changed in substance."""
    if normalize(before.text) == normalize(after.text):
        return ChangeKind.UNCHANGED
    score = fuzz.ratio(normalize(before.text), normalize(after.text))
    return ChangeKind.UNCHANGED if score >= UNCHANGED_THRESHOLD else ChangeKind.CHANGED


def word_diff(before: str, after: str) -> list[DiffToken]:
    """Diff two texts word by word.

    Args:
        before: Text of the earlier version.
        after: Text of the later version.

    Returns:
        Tokens in reading order. The frontend renders additions as ``<ins>`` and
        removals as ``<del>``, each with visually hidden wording, so the change
        is never signalled by colour alone.
    """
    before_words = before.split()
    after_words = after.split()
    matcher = SequenceMatcher(a=before_words, b=after_words, autojunk=False)
    tokens: list[DiffToken] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"delete", "replace"}:
            tokens.append(DiffToken(ChangeKind.REMOVED, " ".join(before_words[i1:i2])))
        if tag in {"insert", "replace"}:
            tokens.append(DiffToken(ChangeKind.ADDED, " ".join(after_words[j1:j2])))
        if tag == "equal":
            tokens.append(DiffToken(ChangeKind.UNCHANGED, " ".join(before_words[i1:i2])))

    return [token for token in tokens if token.text]


def count_changes(pairs: list[AlignedPair]) -> dict[str, int]:
    """Tally the alignment by change kind, for the table caption."""
    counts = dict.fromkeys((kind.value for kind in ChangeKind), 0)
    for pair in pairs:
        counts[pair.change.value] += 1
    return counts
