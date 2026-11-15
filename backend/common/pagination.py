"""Pagination policy (NFR-2.3).

Every list endpoint is paginated. The client may raise the page size up to
``max_page_size`` — a hard ceiling, because an unlimited page size is a trivial
denial-of-service vector on an endpoint that joins several tables.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class DefaultPagination(PageNumberPagination):
    """``?page=2&page_size=50`` with an explicit maximum."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data) -> Response:
        """Same shape as DRF's default plus ``page``/``page_size``/``total_pages``.

        The extra fields save the client from re-deriving them and keep the frontend's table
        component simple.
        """
        return Response(
            {
                "count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
