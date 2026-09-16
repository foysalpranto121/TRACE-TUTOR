"""Withdrawal from the study: erase what we hold about a participant.

Consent forms promise that a participant can leave at any time and have their data
removed. This is the code that keeps that promise. It is deliberately a hard erasure
rather than a flag:

  * every interaction event and every exam submission (with its expert grades) is deleted;
  * the profile's personal and demographic fields are blanked and the avatar file removed;
  * the account is retired - username replaced, email cleared, password made unusable,
    login disabled, API tokens revoked.

What survives is the profile row itself, carrying only the pseudonymous participant
code, the arm it was allocated to, and when and by whom it was withdrawn. That keeps
the enrolment denominator honest ("N enrolled, k withdrew") without keeping anything
that could identify the person or that they generated.

Idempotent: withdrawing twice changes nothing the second time.
"""
import logging

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from assessment.models import ExamSubmission, PaperSitting
from logging_app.models import InteractionLog

from .models import EDITABLE_PROFILE_FIELDS, ParticipantProfile

logger = logging.getLogger(__name__)

PARTICIPANT, RESEARCHER = 'participant', 'researcher'

# Cleared at withdrawal. preferred_language is not personal data and is left alone so
# the closing screen can still be shown in the participant's language.
_KEEP = {'preferred_language'}


class NotAParticipant(ValueError):
    """Only enrolled students withdraw; staff accounts are not study participants."""


def erase_profile_fields(profile):
    for field, kind in EDITABLE_PROFILE_FIELDS.items():
        if field in _KEEP:
            continue
        if kind == 'list':
            setattr(profile, field, [])
        elif kind in ('int', 'bool'):
            setattr(profile, field, None)
        else:
            setattr(profile, field, '')
    profile.grade = ''
    profile.prior_experience = ''
    profile.consent_given = False


def withdraw(user, by=PARTICIPANT):
    """Erase a participant's data and retire the account. Returns the profile."""
    with transaction.atomic():
        queryset = ParticipantProfile.objects.filter(user=user)
        if connection.features.has_select_for_update:
            queryset = queryset.select_for_update()
        profile = queryset.first()
        if profile is None or profile.role != 'STUDENT':
            raise NotAParticipant('Only enrolled participants can withdraw from the study.')
        if profile.withdrawn_at:
            return profile

        events = InteractionLog.objects.filter(user=user).delete()[0]
        submissions = ExamSubmission.objects.filter(student=user).delete()[0]
        PaperSitting.objects.filter(student=user).delete()   # when they sat each paper, and for how long

        if profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = None
        erase_profile_fields(profile)
        profile.withdrawn_at = timezone.now()
        profile.withdrawn_by = by
        profile.save()

        user.username = f'withdrawn-{user.pk}'
        user.email = ''
        user.first_name = ''
        user.last_name = ''
        user.set_unusable_password()
        user.is_active = False
        user.save()
        Token.objects.filter(user=user).delete()

    logger.info('Participant %s withdrawn by %s: %s events and %s submissions erased',
                profile.participant_code, by, events, submissions)
    return profile


def personal_data(user):
    """Everything held about the caller, for the right of access. Plain JSON."""
    profile = ParticipantProfile.objects.filter(user=user).first()
    profile_fields = {}
    if profile:
        for field in EDITABLE_PROFILE_FIELDS:
            profile_fields[field] = getattr(profile, field)
        profile_fields.update({
            'participant_code': profile.participant_code,
            'role': profile.role,
            'assigned_arm': profile.assigned_arm,
            'consent_given': profile.consent_given,
            'consent_at': profile.consent_at.isoformat() if profile.consent_at else None,
            'consent_version': profile.consent_version,
            'enrolled_at': profile.created_at.isoformat() if profile.created_at else None,
            'withdrawn_at': profile.withdrawn_at.isoformat() if profile.withdrawn_at else None,
        })
    return {
        'account': {
            'username': user.username,
            'email': user.email,
            'joined': user.date_joined.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None,
        },
        'profile': profile_fields,
        'submissions': [
            {
                'exam_type': s.exam_type,
                'submitted_at': s.submitted_at.isoformat(),
                'grading_status': s.grading_status,
                'score_pct': s.score_pct,
                'answers': s.answers,
            }
            for s in ExamSubmission.objects.filter(student=user).order_by('submitted_at')
        ],
        'events': [
            {
                'event_type': e.event_type,
                'arm': e.arm,
                'problem_id': e.problem_id,
                'timestamp': e.timestamp.isoformat(),
                'payload': e.payload,
            }
            for e in InteractionLog.objects.filter(user=user).order_by('timestamp')
        ],
    }
