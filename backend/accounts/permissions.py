"""Role gates for the research-facing endpoints.

Both fail closed: an anonymous caller, or one whose profile is missing or carries a
student role, is refused. That matters for more than privacy - the expert review
queue serves the questions of all four exam forms, so leaving it open would let a
participant read the transfer and withdrawal papers before sitting them.
"""
from rest_framework.permissions import BasePermission

from .models import ParticipantProfile, STAFF_ROLES


def _role(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None
    profile = ParticipantProfile.objects.filter(user=user).only('role').first()
    return profile.role if profile else None


class IsStaffRole(BasePermission):
    """Expert teachers and researchers: item certification and submission grading."""
    message = 'This area is for expert teachers and researchers only.'

    def has_permission(self, request, view):
        return _role(request) in STAFF_ROLES


class IsResearcher(BasePermission):
    """Researchers only: study-wide statistics and participant data."""
    message = 'This area is for researcher accounts only.'

    def has_permission(self, request, view):
        return _role(request) == 'RESEARCHER_ADMIN'
