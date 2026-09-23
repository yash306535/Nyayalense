"""Indexes over the packaged law data.

Lookups are pure data. A model is never asked what a section maps to, so a
mapping shown to a user is exactly what the source document said, and a section
that is not in the data returns nothing rather than a plausible guess.
"""

import re
from dataclasses import dataclass, field
from typing import Final

from rapidfuzz import fuzz, process

from app.domain.enums import ChangeType, LawAct, ReviewStatus
from app.domain.laws.models import LawMapping, LawReference, LawTransition, Provision

_WORD_RE: Final = re.compile(r"[\w']+")

#: Trailing punctuation a title ends with that a question rarely echoes, so it
#: is stripped before scoring rather than counted against the match.
_TRAILING_PUNCTUATION: Final = re.compile("[.\\-–—,;:]+$")

#: English filler words dropped before topic matching, so "What counts as
#: cheating under the law?" is scored on "cheating" alone. English only, which
#: is a real limit: a Hindi or Marathi question falls back to matching on the
#: whole sentence, the same as a query that happens to have no filler words.
_STOPWORDS: Final = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "what",
        "which",
        "who",
        "whom",
        "when",
        "where",
        "why",
        "how",
        "can",
        "could",
        "do",
        "does",
        "did",
        "will",
        "would",
        "should",
        "of",
        "to",
        "for",
        "in",
        "on",
        "at",
        "by",
        "with",
        "under",
        "about",
        "and",
        "or",
        "not",
        "no",
        "it",
        "this",
        "that",
        "these",
        "those",
        "i",
        "my",
        "me",
        "you",
        "your",
        "someone",
        "anyone",
        "law",
        "laws",
    }
)

#: Words shorter than this rarely carry enough of a topic to score on alone.
MIN_KEYWORD_LENGTH: Final = 3

#: Similarity above which a mistyped section number is offered as a suggestion.
SUGGESTION_THRESHOLD: Final = 70

MAX_SUGGESTIONS: Final = 5

#: Similarity above which a free-text word counts as naming a provision's own
#: title, rather than coincidentally overlapping a few letters of it. High,
#: because a false match here shows a user the wrong law.
TOPIC_MATCH_THRESHOLD: Final = 90

MAX_TOPIC_MATCHES: Final = 6

#: Clauses handed to the model for one general legal question. Capped so the
#: prompt stays small and the answer stays about what was actually asked.
MAX_LEGAL_QA_CLAUSES: Final = 8


def _keywords(text: str) -> str:
    """Reduce a query to its content words, casefolded and space-joined."""
    words = [word.casefold() for word in _WORD_RE.findall(text)]
    kept = [word for word in words if word not in _STOPWORDS and len(word) >= MIN_KEYWORD_LENGTH]
    return " ".join(kept) if kept else text.casefold()


def _stripped(title: str) -> str:
    """A title's own words, casefolded, with its closing punctuation dropped."""
    return _TRAILING_PUNCTUATION.sub("", title).strip().casefold()


@dataclass(frozen=True, slots=True)
class MappingHit:
    """A mapping found by a lookup, and which direction it was found from."""

    mapping: LawMapping
    matched_old: bool

    @property
    def is_reverse(self) -> bool:
        """True when the query named a provision in the new code."""
        return not self.matched_old


@dataclass
class LawIndex:
    """Every mapping and provision, indexed both ways.

    Built once at startup. Dictionary lookups keyed by ``act:section`` replace
    what would otherwise be a scan of several thousand rows per request.
    """

    transitions: list[LawTransition] = field(default_factory=list)
    provisions: dict[str, Provision] = field(default_factory=dict)
    _forward: dict[str, list[LawMapping]] = field(default_factory=dict, repr=False)
    _reverse: dict[str, list[LawMapping]] = field(default_factory=dict, repr=False)
    _keys: list[str] = field(default_factory=list, repr=False)

    @property
    def mappings(self) -> list[LawMapping]:
        """Every mapping row across every transition."""
        return [mapping for transition in self.transitions for mapping in transition.mappings]

    def build(self) -> "LawIndex":
        """Index the loaded transitions in both directions.

        Returns:
            This index, so the call can be chained after construction.
        """
        self._forward.clear()
        self._reverse.clear()
        for mapping in self.mappings:
            self._forward.setdefault(mapping.old.key, []).append(mapping)
            for counterpart in mapping.new:
                self._reverse.setdefault(counterpart.key, []).append(mapping)
        self._keys = sorted(set(self._forward) | set(self._reverse))
        return self

    def transition_for(self, act: LawAct) -> LawTransition | None:
        """Return the transition that involves an act, in either direction."""
        return next(
            (
                transition
                for transition in self.transitions
                if act in {transition.old_act, transition.new_act}
            ),
            None,
        )

    def lookup(self, reference: LawReference, *, include_unreviewed: bool) -> list[MappingHit]:
        """Find every mapping for a reference, in whichever direction applies.

        Args:
            reference: The parsed reference to look up.
            include_unreviewed: Whether rows still marked ``extracted`` count.

        Returns:
            The matching rows. Empty when the data does not cover this section.
        """
        hits = [
            MappingHit(mapping, matched_old=True)
            for mapping in self._forward.get(reference.key, [])
        ]
        hits.extend(
            MappingHit(mapping, matched_old=False)
            for mapping in self._reverse.get(reference.key, [])
        )
        return [hit for hit in hits if include_unreviewed or hit.mapping.is_reviewed]

    def search_by_topic(self, query: str, *, include_unreviewed: bool) -> list[MappingHit]:
        """Find mappings by what they are about, not by a citation.

        For a query like ``"What counts as cheating under the law?"`` that
        names no act, a citation parser finds nothing. This instead reduces the
        query to its content words -- dropping filler such as "what" and "the"
        -- and scores every mapping's own title on both the old and new side
        against them, order and extra words ignored. The threshold is high
        enough that an unrelated title never appears, at the cost of missing a
        paraphrase that shares none of the title's own words.

        Args:
            query: Free text, not expected to name an act or section.
            include_unreviewed: Whether rows still marked ``extracted`` count.

        Returns:
            Up to :data:`MAX_TOPIC_MATCHES` mappings, best match first.
        """
        keywords = _keywords(query)
        scored = []
        for mapping in self.mappings:
            if not include_unreviewed and not mapping.is_reviewed:
                continue
            titles = [mapping.old.title, *(ref.title for ref in mapping.new)]
            score = max(
                (fuzz.token_set_ratio(keywords, _stripped(title)) for title in titles if title),
                default=0.0,
            )
            if score >= TOPIC_MATCH_THRESHOLD:
                scored.append((score, mapping))
        scored.sort(key=lambda pair: (-pair[0], pair[1].old.key))
        return [MappingHit(mapping, matched_old=True) for _, mapping in scored[:MAX_TOPIC_MATCHES]]

    def matching_provisions(self, query: str) -> list[Provision]:
        """Find stored provision texts relevant to a general legal question.

        Built from :meth:`search_by_topic`, but resolved down to whichever
        matched sections actually have stored, reviewed text -- a topic match
        with nothing to quote is not useful to a grounded answer.

        Args:
            query: The reader's question, or the topic within it.

        Returns:
            Up to :data:`MAX_LEGAL_QA_CLAUSES` provisions, best match first.
        """
        found: dict[str, Provision] = {}
        for hit in self.search_by_topic(query, include_unreviewed=False):
            for reference in [hit.mapping.old, *hit.mapping.new]:
                if reference.key in found:
                    continue
                provision = self.provision(reference.act, reference.section)
                if provision is not None and provision.review_status is ReviewStatus.VERIFIED:
                    found[reference.key] = provision
            if len(found) >= MAX_LEGAL_QA_CLAUSES:
                break
        return list(found.values())[:MAX_LEGAL_QA_CLAUSES]

    def provision(self, act: LawAct, section: str) -> Provision | None:
        """Return the stored text of a section, when one is packaged."""
        return self.provisions.get(f"{act.value}:{section.upper()}")

    def suggest(self, reference: LawReference) -> list[str]:
        """Offer near matches for a section number that is not in the data.

        A mistyped section is almost always one wrong digit in an otherwise
        correct number, such as ``429`` for ``420``. Character-ratio scoring
        cannot tell that apart from a typo in a completely different position
        (``429`` versus ``129``): both share two of three characters and score
        identically, even though only one is numerically close. So a purely
        numeric, same-length query is ranked by numeric distance instead, and
        ratio scoring is kept only as the fallback for lettered sections such
        as ``498A``, where "distance" has no obvious meaning.

        Args:
            reference: The reference that found nothing.

        Returns:
            Up to :data:`MAX_SUGGESTIONS` keys that look like what was typed.
        """
        candidates = {
            key: key.split(":", 1)[1]
            for key in self._keys
            if key.startswith(f"{reference.act.value}:")
        }
        query = reference.section.upper()

        numeric = self._suggest_by_numeric_distance(candidates, query)
        if numeric:
            return numeric
        return self._suggest_by_ratio(candidates, query)

    @staticmethod
    def _suggest_by_numeric_distance(candidates: dict[str, str], query: str) -> list[str]:
        """Rank same-length, all-digit candidates by how close the number is."""
        if not query.isdigit():
            return []
        same_length_numeric = {
            key: int(value)
            for key, value in candidates.items()
            if value.isdigit() and len(value) == len(query)
        }
        if not same_length_numeric:
            return []
        ranked = sorted(same_length_numeric.items(), key=lambda item: abs(item[1] - int(query)))
        return [key for key, _ in ranked[:MAX_SUGGESTIONS]]

    @staticmethod
    def _suggest_by_ratio(candidates: dict[str, str], query: str) -> list[str]:
        """Fall back to character-ratio scoring, for lettered sections."""
        matches = process.extract(
            query,
            candidates,
            scorer=fuzz.ratio,
            limit=MAX_SUGGESTIONS,
            score_cutoff=SUGGESTION_THRESHOLD,
        )
        return [match[2] for match in matches]

    def changes(self, kind: ChangeType, *, include_unreviewed: bool) -> list[LawMapping]:
        """List the rows of one change type, for the browse lists.

        Args:
            kind: Which change type to list.
            include_unreviewed: Whether rows still marked ``extracted`` count.

        Returns:
            The matching rows.
        """
        return [
            mapping
            for mapping in self.mappings
            if mapping.change_type is kind and (include_unreviewed or mapping.is_reviewed)
        ]

    def counts(self) -> dict[str, int]:
        """Summarise the dataset, for the meta endpoint and the docs."""
        mappings = self.mappings
        return {
            "transitions": len(self.transitions),
            "mappings": len(mappings),
            "reviewed": sum(mapping.is_reviewed for mapping in mappings),
            "provision_texts": len(self.provisions),
        }


def visible_status(mapping: LawMapping) -> ReviewStatus:
    """Return the review status the UI must display for a row."""
    return mapping.review_status
