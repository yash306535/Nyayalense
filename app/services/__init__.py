"""Use cases.

A service orchestrates: it calls adapters for I/O, the domain for logic, and the
verifier before it returns anything. No route contains business logic and no
domain module performs I/O.
"""
