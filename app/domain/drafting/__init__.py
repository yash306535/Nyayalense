"""Locked-fact drafting.

A generated letter contains only facts the user confirmed. A model may suggest
wording, and refers to every fact through a ``[[slot]]`` token that code fills
in, so it never types a number, a date or a name.
"""
