"""Shared platform code.

``common`` holds code that several business modules genuinely need and that has no business
rules of its own: abstract model bases, the pagination class, the error envelope, permission
primitives and small utilities.

It is deliberately **not** a Django app (see INSTALLED_APPS): it has no concrete models, so it
needs no migrations. The rule of thumb is that if code in ``common`` starts importing a business
module, it belongs in that module instead.
"""
