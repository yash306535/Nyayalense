# Data and its provenance

Everything NyayaLens states about the law, or about where to get help, comes
from a file in `app/data/`. Every such file is validated against a Pydantic
schema when the process starts, so a malformed one stops the deployment rather
than reaching a reader.

The rule that governs this directory:

> **Nothing here is written from a model's memory.** A record either names the
> official source it was read from, or it does not ship.

## The files

| File | What it holds | Where it comes from | Validated by |
| --- | --- | --- | --- |
| `checklists/*.json` | 8 curated review checklists, one per document type | Written by the team as review prompts. Not claimed to be law. | [`domain/checklists.py`](../app/domain/checklists.py) |
| `glossary.json` | 20 legal terms with general meanings in en, hi, mr | Written by the team. Always labelled "General meaning" and always loses to the document's own definition. | [`domain/glossary.py`](../app/domain/glossary.py) |
| `resources.json` | 6 official places to get help | Official sites, each with `source_url` and `verified_on`. | [`domain/resources.py`](../app/domain/resources.py) |
| `samples/*.txt` | 4 fictional documents | Written by the team. Every name, address and number is invented. | — |
| `laws/mappings/*.json` | 102 old-to-new criminal law rows | **Seed rows. See below.** | [`domain/laws/models.py`](../app/domain/laws/models.py) |
| `laws/texts/*.json` | Statutory text | **Empty. See below.** | [`domain/laws/models.py`](../app/domain/laws/models.py) |

---

## Law mappings: read this before trusting a row

The Indian Penal Code, the Code of Criminal Procedure and the Indian Evidence
Act were replaced on 1 July 2024 by the Bharatiya Nyaya Sanhita, the Bharatiya
Nagarik Suraksha Sanhita and the Bharatiya Sakshya Adhiniyam. The Bureau of
Police Research & Development publishes correspondence tables mapping the old
provisions to the new ones.

### What ships today

`app/data/laws/mappings/` contains **1,150 rows genuinely extracted** from the
three official BPR&D correspondence-table PDFs (downloaded from bprd.nic.in →
"Nyaya Sanhita" → "Documents by BPR&D" → row 3, "Comparison summary" links),
plus 3 rows added by hand for sections known to have no new-code counterpart
(IPC 124A, 377, 497 — see below for why). **Every row is still marked
`review_status: "extracted"`**, each carrying the real page number it came
from within its source PDF.

Because they are unreviewed, they are **hidden from users by default**:
`GET /laws/lookup` filters them out unless `LAW_DATA_SHOW_UNREVIEWED=true`, and
when that flag is on, every row carries a visible "Not yet reviewed" label and
an explanation.

**A note on table layout.** The three official PDFs are not laid out
consistently with each other: the IPC and CrPC tables list the new section
first (new section, subject, old section, note), while the IEA table lists the
old section first (old, new, subject, note). `scripts/build_law_data.py`
handles both. Roughly 6-8% of rows in each table cite something other than a
plain section number — a proviso, an explanation, an illustration — and those
are skipped and counted rather than forced into a section number they are not.

**A structural gap, not a data gap.** Because these tables are organised by
the *new* code, a section that is genuinely new in BNS/BNSS/BSA with no old
counterpart has no row to extract (there is no old section number to key it
on). The reverse is also true: IPC 124A, 377 and 497 have no BNS row at all,
because a table organised by the new code has nothing to list them under. Those
three are added by hand in `scripts/build_law_data.py`'s
`KNOWN_NOT_CARRIED_FORWARD`, sourced honestly as "publicly reported, not from
the BPR&D table itself" rather than claiming a page citation that does not
exist. They still ship `extracted`, not `verified`.

### Making them real

1. **Download the official PDFs** from <https://bprd.nic.in> and save them into
   `data_sources/` with the names listed in
   [`data_sources/README.md`](../data_sources/README.md). That folder is
   git-ignored: the documents belong to their publisher.

2. **Run the extractor.**

   ```bash
   make laws-data              # or: python scripts/build_law_data.py --dry-run
   ```

   It reads the tables with pdfplumber and writes one JSON file per transition.
   Every row it writes records the document and the **page** it came from, and
   is marked `extracted`. Rows it cannot parse cleanly are skipped and counted:
   a smaller checked set is worth more than a larger guessed one.

3. **Check each row against its source page.** This is the part no script does.
   Open the PDF at the page the row names and confirm the old section, the new
   section or sections, and the note.

4. **Mark what you have checked.**

   ```json
   {
     "old": { "act": "ipc", "section": "420", "title": "Cheating..." },
     "new": [{ "act": "bns", "section": "318", "title": "Cheating" }],
     "change_type": "merged",
     "source": { "document": "BPR&D correspondence table: bprd-ipc-bns.pdf", "page": 7 },
     "review_status": "verified",
     "verified_on": "2026-09-22"
   }
   ```

   A row marked `verified` without a `verified_on` date fails validation at
   startup, so the two cannot drift apart.

5. **Run the tests.** `tests/api/test_laws.py` enforces that every row has a
   source, that ids are unique, that the reverse index agrees with the forward
   one, and the specific traps below.

### The traps the tests enforce

Some rows are dangerous to get wrong, so they are asserted rather than trusted:

- **IPC 124A (sedition) is never shown as a renumbering.** The row is
  `no_direct_equivalent` with an explanatory note. BNS 152 is a separately
  worded offence and this dataset does not present it as a renamed 124A.
- **IPC 377 and IPC 497** are `no_direct_equivalent`.
- **BNS 302 is not murder.** A test asserts that nothing mapping to BNS 302
  describes murder. Murder is BNS 103.
- **IPC 498A is a split**, into BNS 85 with the definition of cruelty in BNS 86.

### What the tables are, and are not

They are a police training aid and reference document. They are not a statutory
instrument, and correspondence is not equivalence: a renumbered section may
still have been reworded. The interface says this on every row, and the law
views carry a standing note that NyayaLens will not say which section applies to
anyone's situation.

India Code's side-by-side pages and similarity scores are useful while checking
a row. A similarity score is not a legal equivalence and must not be recorded as
a `change_type`.

---

## Statutory text: why none ships

`app/data/laws/texts/` is empty, and a test asserts that it is.

Statutory text has to be exact. Writing it from memory is precisely the failure
this product exists to prevent, and a plausible-looking wrong section is worse
than no section at all. So the comparison view shows the mapping, the change
type and the source, and says:

> The full text of this section is not stored in NyayaLens. Read it on India Code.

### Adding provision texts

Copy them from <https://www.indiacode.nic.in>, one JSON file per act, as a list:

```json
[
  {
    "act": "ipc",
    "section": "420",
    "title": "Cheating and dishonestly inducing delivery of property",
    "text": "<the exact text, copied from India Code>",
    "source": { "document": "India Code", "url": "https://www.indiacode.nic.in/..." },
    "review_status": "verified",
    "verified_on": "2026-09-22"
  }
]
```

Start with the sections people meet most: cheating, criminal breach of trust,
criminal intimidation, defamation, cruelty and dowry offences, FIR registration,
bail, and the electronic-evidence certificate.

Once both sides of a mapping have stored text, three things switch on by
themselves: the word-level diff, the extracted punishment, and a plain-language
description of the difference. That description is generated **only** from the
two stored texts, treated as a two-clause document, and goes through the same
verifier as everything else. With no stored text, nothing is generated.

---

## The help directory

`app/data/resources.json` holds six entries, checked on **22 September 2026**
against official or official-press sources:

| Entry | Contact | Source |
| --- | --- | --- |
| NALSA free legal aid | 15100 | <https://nalsa.gov.in> |
| National Cyber Crime Reporting Portal | 1930 | <https://cybercrime.gov.in> |
| National Consumer Helpline | 1915 | <https://consumerhelpline.gov.in> |
| e-Daakhil | — | <https://edaakhil.nic.in> |
| India Code | — | <https://www.indiacode.nic.in> |
| BPR&D | — | <https://bprd.nic.in> |

**Re-verify these before release.** Helplines and portals change. Every entry
shows its check date in the interface, so a stale one is visible rather than
silent.

### Adding a resource

Add an object to `entries`. The schema enforces what matters:

- `contact.url` must be `https`. An `http` link fails validation.
- `source_url` and `verified_on` are required.
- `cost` and `hours` are only filled in if the source states them.
- `relevant_for` lists document types or situation keys (`online_fraud`,
  `consumer_complaint`, `law_reference`) that make the entry worth surfacing.

Add no phone number or URL that you have not read off an official page.
**No private lawyers or firms**, and nothing is ranked or endorsed.

---

## Checklists

One file per document type in `app/data/checklists/`. Each holds 10 to 15 items,
suggested questions, preset what-if scenarios, and the "facts to have ready" and
"documents to bring" lists the lawyer brief uses.

These are **review prompts, not legal rules**, and every checklist carries that
sentence as its `note`. A test asserts the sentence is present.

Adding a document type is a data change: add `<doc_type>.json`, add the enum
member in [`domain/enums.py`](../app/domain/enums.py), and the routes, the
review prompt, the brief and the drafting prefill all pick it up.

## Letter templates

Each is a folder under `app/templates/drafts/` holding `template.md.j2` and
`fields.json`. Adding one needs no code change.

- `fields.json` declares every field: its type, whether it is required, its
  length limit, labels in all three languages, and optionally where it can be
  prefilled from.
- `template.md.j2` is Markdown rendered by a sandboxed Jinja environment with
  `StrictUndefined`. Every interpolated value is Markdown-escaped, so a fact
  containing `**` or `#` prints as written.
- `wording_field` names the one free-text field a model may be asked to word
  better. `required_slots` lists the slots that wording must contain.

Titles and wording must never imply the writer has a lawyer behind them: say
"letter" or "request", never "legal notice". A test asserts this.
