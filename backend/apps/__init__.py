"""Business modules of the modular monolith.

Each subpackage is a bounded context that owns its tables and exposes behaviour through
``services`` (writes), ``selectors`` (reads) and ``api`` (HTTP). See
docs/architecture/module-responsibilities.md for the ownership map and the dependency rules.
"""
