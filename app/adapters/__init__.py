"""Adapters for everything outside the process.

Each one sits behind a ``typing.Protocol`` so the services never import an SDK,
and so a test or the demo mode can substitute a deterministic implementation.
"""
