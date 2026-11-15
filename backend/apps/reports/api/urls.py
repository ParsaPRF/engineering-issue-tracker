"""Report routes. The module owns the ``reports/`` prefix."""

from django.urls import path

from apps.reports.api.views import (
    DashboardView,
    MyWorkloadView,
    ProjectOptionsView,
    RecentActivityView,
    WorkloadView,
)

urlpatterns = [
    path("reports/dashboard/", DashboardView.as_view(), name="reports-dashboard"),
    path("reports/workload/", WorkloadView.as_view(), name="reports-workload"),
    path("reports/my-workload/", MyWorkloadView.as_view(), name="reports-my-workload"),
    path("reports/recent-activity/", RecentActivityView.as_view(), name="reports-recent-activity"),
    path("reports/projects/", ProjectOptionsView.as_view(), name="reports-projects"),
]