"""Every categorical value in the domain, as an enum.

Keeping these in one module means the API schema, the prompt builders, the
frontend labels and the tests all agree on the same closed sets.
"""

from enum import StrEnum


class Language(StrEnum):
    """UI and explanation language. Quotes always stay in the document's language."""

    EN = "en"
    HI = "hi"
    MR = "mr"


class ReadingLevel(StrEnum):
    """How much detail an explanation carries."""

    SIMPLE = "simple"
    DETAILED = "detailed"


class DocType(StrEnum):
    """Kinds of document NyayaLens has a checklist for."""

    RENTAL_LEAVE_LICENCE = "rental_leave_licence"
    EMPLOYMENT_OFFER = "employment_offer"
    LOAN_AGREEMENT = "loan_agreement"
    INSURANCE_POLICY = "insurance_policy"
    TERMS_OF_SERVICE = "terms_of_service"
    NDA = "nda"
    LEGAL_NOTICE = "legal_notice"
    GENERAL_CONTRACT = "general_contract"


class Role(StrEnum):
    """Which side of the document the user is on. Drives risk severity."""

    TENANT = "tenant"
    LANDLORD = "landlord"
    EMPLOYEE = "employee"
    EMPLOYER = "employer"
    BORROWER = "borrower"
    LENDER = "lender"
    POLICYHOLDER = "policyholder"
    CUSTOMER = "customer"
    NOTICE_RECIPIENT = "notice_recipient"
    OTHER = "other"


class StatementKind(StrEnum):
    """Whether a statement repeats the document or reasons from it."""

    DIRECT = "direct"
    INTERPRETATION = "interpretation"


class AnswerType(StrEnum):
    """Outcome of a grounded question."""

    DIRECT = "direct"
    INTERPRETATION = "interpretation"
    NOT_FOUND = "not_found"
    OUT_OF_SCOPE = "out_of_scope"


class Severity(StrEnum):
    """Impact of a risk or a change on the user, given their role."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChecklistStatus(StrEnum):
    """Whether a checklist item was found in the document."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    UNCLEAR = "unclear"


class ObligationOwner(StrEnum):
    """Who has to do the thing."""

    YOU = "you"
    OTHER_PARTY = "other_party"
    BOTH = "both"


class TimingKind(StrEnum):
    """How a deadline is expressed."""

    ABSOLUTE = "absolute"
    RELATIVE = "relative"
    RECURRING = "recurring"
    UNSPECIFIED = "unspecified"


class ChangeKind(StrEnum):
    """How a clause differs between two versions of a document."""

    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


class CompareMode(StrEnum):
    """Whether two documents are versions of one thing or competing offers."""

    VERSIONS = "versions"
    ALTERNATIVES = "alternatives"


class InconsistencyKind(StrEnum):
    """Where an internal contradiction came from."""

    AMOUNT_MISMATCH = "amount_mismatch"
    CONTRADICTION = "contradiction"


class RemovalReason(StrEnum):
    """Why verification dropped a statement or a citation."""

    NO_SUCH_CLAUSE = "no_such_clause"
    QUOTE_NOT_FOUND = "quote_not_found"
    QUOTE_TOO_LONG = "quote_too_long"
    EMPTY_QUOTE = "empty_quote"
    FIGURE_NOT_IN_QUOTE = "figure_not_in_quote"
    NO_VERIFIED_CITATIONS = "no_verified_citations"


class DocumentWarning(StrEnum):
    """Conditions the user is told about after ingestion."""

    OCR_USED = "ocr_used"
    LITTLE_TEXT = "little_text"
    TRUNCATED = "truncated"
    HIDDEN_TEXT = "hidden_text"
    ADDRESSES_AI = "addresses_ai"


class IdentifierKind(StrEnum):
    """Categories of personal identifier masked before any model call."""

    AADHAAR = "aadhaar"
    PAN = "pan"
    PHONE = "phone"
    EMAIL = "email"


class ChangeType(StrEnum):
    """How an old provision relates to the new code."""

    RENUMBERED = "renumbered"
    MODIFIED = "modified"
    MERGED = "merged"
    SPLIT = "split"
    NO_DIRECT_EQUIVALENT = "no_direct_equivalent"
    NEW_PROVISION = "new_provision"


class ReviewStatus(StrEnum):
    """Whether a law row has been checked by a person against the source."""

    EXTRACTED = "extracted"
    VERIFIED = "verified"


class LawAct(StrEnum):
    """The six criminal-law codes NyayaLens maps between."""

    IPC = "ipc"
    BNS = "bns"
    CRPC = "crpc"
    BNSS = "bnss"
    IEA = "iea"
    BSA = "bsa"

    @property
    def is_old(self) -> bool:
        """True for the codes replaced on 1 July 2024."""
        return self in {LawAct.IPC, LawAct.CRPC, LawAct.IEA}


class FieldType(StrEnum):
    """Types a letter template may declare for a fact field."""

    TEXT = "text"
    MULTILINE = "multiline"
    DATE = "date"
    MONEY = "money"
    ADDRESS = "address"
    EMAIL = "email"
    PHONE = "phone"
    CLAUSE_REF = "clause_ref"
    CHOICE = "choice"


class ExportFormat(StrEnum):
    """File formats an export can produce."""

    DOCX = "docx"
    PDF = "pdf"


class ExportKind(StrEnum):
    """What is being exported."""

    DRAFT = "draft"
    BRIEF = "brief"
    COMPARISON = "comparison"
    LAW_COMPARISON = "law_comparison"


class ResourceCategory(StrEnum):
    """Groupings on the Get help page."""

    LEGAL_AID = "legal_aid"
    CYBER_CRIME = "cyber_crime"
    CONSUMER = "consumer"
    LAW_TEXT = "law_text"
