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

## What these tables are, and are not

They are a police training aid and reference document, not a statutory
instrument. The application says so on every row it shows. A row extracted from
them stays marked `review_status: "extracted"` and is hidden from users until a
person has checked it against the source and marked it `verified`.

See `docs/DATA.md` for the full procedure.
