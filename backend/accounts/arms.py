"""When may a participant change tutor mode?

The arm is the experiment's independent variable. Letting a participant move between
arms while their outcomes are being measured turns a randomised comparison into a
comparison of "the kind of student who switches", which no analysis can repair. The
`after_protocol` policy resolves the tension between rigour and autonomy: switching is
allowed, but only after the last paper is in - so every primary outcome is measured in
the allocated condition and the switching itself becomes a secondary, revealed-
preference finding.

Staff accounts are not participants and may always switch to preview both modes.
"""
from django.conf import settings

from .models import STAFF_ROLES

POLICIES = ('after_protocol', 'never', 'always')
PROTOCOL_FORMS = ('pre', 'post', 'transfer', 'withdrawal')

# Reasons reported to the client so it can explain the lock in the right words.
STAFF, ALWAYS, COMPLETED, AFTER_PROTOCOL, NEVER = 'staff', 'always', 'completed', 'after_protocol', 'never'


def policy():
    value = str(getattr(settings, 'ARM_SWITCH_POLICY', 'after_protocol')).lower()
    return value if value in POLICIES else 'after_protocol'


def protocol_complete(user):
    """Has this participant submitted every form? (Pending grading still counts: the
    paper was sat, which is what matters here.)"""
    from assessment.models import ExamSubmission  # local import: assessment imports accounts
    done = set(ExamSubmission.objects.filter(student=user, exam_type__in=PROTOCOL_FORMS)
               .values_list('exam_type', flat=True))
    return all(form in done for form in PROTOCOL_FORMS)


def switch_allowed(profile):
    """(allowed, reason). `reason` is one of the constants above."""
    if profile.role in STAFF_ROLES:
        return True, STAFF
    current = policy()
    if current == 'always':
        return True, ALWAYS
    if current == 'never':
        return False, NEVER
    if protocol_complete(profile.user):
        return True, COMPLETED
    return False, AFTER_PROTOCOL


LOCK_MESSAGES = {
    NEVER: ('Your tutor mode is assigned at enrolment and is fixed for this study. '
            'Contact the research coordinator if you believe it is wrong.'),
    AFTER_PROTOCOL: ('Your tutor mode stays as allocated until you have completed all four papers. '
                     'After the withdrawal task you can switch and try the other mode.'),
}
