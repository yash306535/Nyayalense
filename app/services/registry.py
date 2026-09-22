"""Load and validate every packaged data file, once, at startup.

A malformed checklist or an unsourced law row must stop the process, not reach a
user. Validating here means the rest of the application can treat this data as
already correct, and adding a checklist, a resource or a letter template needs
no code change at all.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.domain.checklists import Checklist
from app.domain.enums import DocType, LawAct
from app.domain.glossary import Glossary
from app.domain.laws.lookup import LawIndex
from app.domain.laws.models import LawTransition, Provision
from app.domain.resources import ResourceDirectory
from app.errors import DataFileError, NotFoundError

logger = logging.getLogger(__name__)

CHECKLISTS_DIR = DATA_DIR / "checklists"
SAMPLES_DIR = DATA_DIR / "samples"
LAW_MAPPINGS_DIR = DATA_DIR / "laws" / "mappings"
LAW_TEXTS_DIR = DATA_DIR / "laws" / "texts"


@dataclass(frozen=True, slots=True)
class Sample:
    """One built-in fictional document."""

    id: str
    title: str
    description: str
    text: str


@dataclass
class Registry:
    """Everything loaded from ``app/data`` and held for the process's lifetime."""

    checklists: dict[DocType, Checklist] = field(default_factory=dict)
    glossary: Glossary = field(default_factory=lambda: Glossary(entries=[]))
    resources: ResourceDirectory = field(default_factory=lambda: ResourceDirectory(entries=[]))
    samples: dict[str, Sample] = field(default_factory=dict)
    laws: LawIndex = field(default_factory=LawIndex)

    def checklist(self, doc_type: DocType) -> Checklist:
        """Return the checklist for a document type.

        Raises:
            NotFoundError: No checklist is packaged for that type.
        """
        checklist = self.checklists.get(doc_type)
        if checklist is None:
            raise NotFoundError(f"No checklist is available for '{doc_type.value}'.")
        return checklist

    def sample(self, sample_id: str) -> Sample:
        """Return a built-in sample.

        Raises:
            NotFoundError: There is no sample with that id.
        """
        sample = self.samples.get(sample_id)
        if sample is None:
            raise NotFoundError("That sample does not exist.")
        return sample


#: Titles and one-line descriptions for the built-in samples.
_SAMPLE_META: dict[str, tuple[str, str]] = {
    "leave-licence-v1": (
        "Rental agreement",
        "A leave and licence agreement with a one-sided lock-in and a deposit written two ways.",
    ),
    "leave-licence-v2": (
        "Rental agreement, revised",
        "The same agreement after four changes. Use it with Compare.",
    ),
    "offer-letter-bond": (
        "Job offer with a service bond",
        "An offer letter with a bond, a clawback and a line addressed to AI assistants.",
    ),
    "legal-notice-old-sections": (
        "Legal notice citing old sections",
        "A notice that cites IPC, CrPC and Evidence Act sections replaced in 2024.",
    ),
}


def _read_json(path: Path) -> Any:
    """Read one JSON file.

    Raises:
        DataFileError: The file is missing or is not valid JSON.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DataFileError(f"Data file missing: {path.name}") from error
    except json.JSONDecodeError as error:
        raise DataFileError(f"Data file is not valid JSON: {path.name}") from error


def _load_checklists() -> dict[DocType, Checklist]:
    """Load every checklist and confirm one exists for each document type.

    Raises:
        DataFileError: A file fails its schema, or a document type has none.
    """
    checklists: dict[DocType, Checklist] = {}
    for path in sorted(CHECKLISTS_DIR.glob("*.json")):
        try:
            checklist = Checklist.model_validate(_read_json(path))
        except ValueError as error:
            raise DataFileError(f"{path.name} does not match the checklist schema.") from error
        checklists[checklist.doc_type] = checklist

    missing = [doc_type.value for doc_type in DocType if doc_type not in checklists]
    if missing:
        raise DataFileError(f"No checklist for: {', '.join(missing)}")
    return checklists


def _load_samples() -> dict[str, Sample]:
    """Load the built-in fictional documents."""
    samples: dict[str, Sample] = {}
    for path in sorted(SAMPLES_DIR.glob("*.txt")):
        title, description = _SAMPLE_META.get(path.stem, (path.stem, ""))
        samples[path.stem] = Sample(
            id=path.stem,
            title=title,
            description=description,
            text=path.read_text(encoding="utf-8"),
        )
    return samples


def _load_laws() -> LawIndex:
    """Load law transitions and stored provision texts.

    Raises:
        DataFileError: A file fails its schema.
    """
    index = LawIndex()
    for path in sorted(LAW_MAPPINGS_DIR.glob("*.json")):
        try:
            index.transitions.append(LawTransition.model_validate(_read_json(path)))
        except ValueError as error:
            raise DataFileError(f"{path.name} does not match the law-transition schema.") from error

    for path in sorted(LAW_TEXTS_DIR.glob("*.json")):
        payload = _read_json(path)
        try:
            for entry in payload:
                provision = Provision.model_validate(entry)
                index.provisions[provision.key] = provision
        except (ValueError, TypeError) as error:
            raise DataFileError(f"{path.name} does not match the provision schema.") from error

    _check_acts_are_known(index)
    return index.build()


def _check_acts_are_known(index: LawIndex) -> None:
    """Confirm every act named in the data is one the parser recognises.

    Raises:
        DataFileError: A row names an act with no parser support, which would
            make the row unreachable from any search.
    """
    known = set(LawAct)
    for transition in index.transitions:
        if transition.old_act not in known or transition.new_act not in known:
            raise DataFileError(f"Transition '{transition.id}' names an unknown act.")


def load_registry() -> Registry:
    """Load and validate every packaged data file.

    Returns:
        The loaded registry.

    Raises:
        DataFileError: Any file is missing or fails its schema.
    """
    registry = Registry(
        checklists=_load_checklists(),
        glossary=Glossary.model_validate(_read_json(DATA_DIR / "glossary.json")),
        resources=ResourceDirectory.model_validate(_read_json(DATA_DIR / "resources.json")),
        samples=_load_samples(),
        laws=_load_laws(),
    )
    logger.info(
        "data_loaded",
        extra={
            "checklists": len(registry.checklists),
            "glossary_terms": len(registry.glossary.entries),
            "resources": len(registry.resources.entries),
            "samples": len(registry.samples),
            **registry.laws.counts(),
        },
    )
    return registry
