Describe this document for the reader.

- summary: 2 to 3 statements saying what kind of document this is, who the parties are as
  the document names them, and what it does.
- parties: every party, named exactly as the document names them. Set is_user on the party
  whose role the reader has chosen.
- key_terms: money (rent, salary, loan amount, deposit, fees), duration, start and end dates,
  notice period, renewal, termination, lock-in and penalties. Give each a stable id in
  snake_case. Leave value empty when the document does not specify the term, and give no
  statements for it. Never invent a value.
- obligations: what each side must do, when, and what the document says happens if they do not.
- key_dates: set date only when the document states a calendar date, formatted yyyy-mm-dd.
  Use timing_kind "relative" for periods such as "within 30 days of signing" and explain them
  in words instead.
