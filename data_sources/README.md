# Official source documents

This folder holds the **official PDFs** that `scripts/build_law_data.py` reads to
produce `app/data/laws/mappings/*.json`. Its contents are git-ignored: the files
belong to their publishers and are not redistributed here.

## What to place here

Download the correspondence tables published by the Bureau of Police Research &
Development (<https://bprd.nic.in>), dated 21 June 2024, and save them as:

| File | Covers |
| --- | --- |
| `bprd-ipc-bns.pdf` | Indian Penal Code 1860 → Bharatiya Nyaya Sanhita 2023 |
| `bprd-crpc-bnss.pdf` | Code of Criminal Procedure 1973 → Bharatiya Nagarik Suraksha Sanhita 2023 |
| `bprd-iea-bsa.pdf` | Indian Evidence Act 1872 → Bharatiya Sakshya Adhiniyam 2023 |

Then run `make laws-data`.

### For the provision texts

`scripts/build_provision_texts.py` reads the three new codes over India Code's
own REST API, so they need nothing here. The two repealed codes it can still
quote are only published as a PDF, attached to their entry in India Code's
repeal register. Download each one's **consolidated Act PDF** and save it as:

| File | Covers | India Code entry |
| --- | --- | --- |
| `indiacode-ipc.pdf` | Indian Penal Code 1860 (`A1860-45.pdf`) | <https://indiacode.gov.in/handle/123456789/488475> |
| `indiacode-iea.pdf` | Indian Evidence Act 1872 (`A1872-1.pdf`) | <https://indiacode.gov.in/handle/123456789/488783> |

Then run `make provision-texts`.

There is deliberately no file here for the Code of Criminal Procedure. The only
copy India Code still publishes is a scan of the 1974 gazette whose text layer
has decayed past the point of being quotable, so no CrPC text is packaged at
all. See `docs/DATA.md`.

## What these tables are, and are not

They are a police training aid and reference document, not a statutory
instrument. The application says so on every row it shows. A row extracted from
them stays marked `review_status: "extracted"` and is hidden from users until a
person has checked it against the source and marked it `verified`.

See `docs/DATA.md` for the full procedure.
