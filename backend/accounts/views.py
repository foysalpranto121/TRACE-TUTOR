import re

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import parser_classes
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import ParticipantProfile, EDITABLE_PROFILE_FIELDS, STAFF_ROLES

USERNAME_RE = re.compile(r'^[A-Za-z0-9._-]{3,30}$')
VALID_ROLES = {r for r, _ in ParticipantProfile.ROLE_CHOICES}
VALID_ARMS = {a for a, _ in ParticipantProfile.ARM_CHOICES}


class AuthBurstThrottle(AnonRateThrottle):
    rate = '20/min'


def serialize_user(user, profile):
    data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': profile.full_name or user.first_name or user.username,
        'role': profile.role,
        'arm': profile.assigned_arm,
        'language': profile.preferred_language,
        'participant_code': profile.participant_code,
        'consent_given': profile.consent_given,
        'consent_at': profile.consent_at.isoformat() if profile.consent_at else None,
        'joined': user.date_joined.isoformat(),
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'is_staff_role': profile.role in STAFF_ROLES,
        'avatar_url': _avatar_url(profile),
    }
    for field in EDITABLE_PROFILE_FIELDS:
        data[field] = getattr(profile, field)
    return data


def _avatar_url(profile):
    if not profile.avatar:
        return None
    # Cache-bust with the file's mtime so a replaced picture shows immediately.
    try:
        stamp = int(profile.avatar.storage.get_modified_time(profile.avatar.name).timestamp())
    except Exception:
        stamp = 0
    return f"{profile.avatar.url}?v={stamp}"


def _coerce(kind, value):
    if value in (None, ''):
        return None if kind in ('int', 'bool') else ([] if kind == 'list' else '')
    if kind == 'int':
        try:
            return max(0, min(int(value), 32000))
        except (TypeError, ValueError):
            return None
    if kind == 'bool':
        if isinstance(value, str):
            return value.lower() in ('1', 'true', 'yes')
        return bool(value)
    if kind == 'list':
        if isinstance(value, str):
            value = [v.strip() for v in value.split(',') if v.strip()]
        return [str(v)[:60] for v in (value or [])][:20]
    return str(value).strip()[:200]


def _apply_profile_fields(profile, data):
    for field, kind in EDITABLE_PROFILE_FIELDS.items():
        if field in data:
            setattr(profile, field, _coerce(kind, data.get(field)))
    if profile.preferred_language not in ('bn', 'en'):
        profile.preferred_language = 'bn'
    if profile.grade not in ('11', '12', ''):
        profile.grade = '11'


def _profile_for(user):
    profile, _ = ParticipantProfile.objects.get_or_create(user=user)
    return profile


def _with_lang_cookie(response, profile):
    """Readable (not HttpOnly) cookie so the SPA keeps the participant's language after logout and
    the tutor can default to it when a request does not say."""
    response.set_cookie(
        settings.LANG_COOKIE_NAME, profile.preferred_language or 'bn',
        max_age=settings.LANG_COOKIE_AGE, samesite='Lax', secure=settings.SESSION_COOKIE_SECURE,
    )
    return response


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AuthBurstThrottle])
def register_view(request):
    data = request.data
    username = (data.get('username') or '').strip()
    full_name = (data.get('full_name') or data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    role = (data.get('role') or 'STUDENT').upper()
    consent = _coerce('bool', data.get('consent_given'))

    errors = {}
    if not USERNAME_RE.match(username):
        errors['username'] = 'Use 3-30 letters, digits, dots, underscores or hyphens (no spaces).'
    elif User.objects.filter(username__iexact=username).exists():
        errors['username'] = 'This username is already taken.'
    if email and User.objects.filter(email__iexact=email).exists():
        errors['email'] = 'An account with this email already exists.'
    if not full_name:
        errors['full_name'] = 'Full name is required.'
    if role not in VALID_ROLES:
        errors['role'] = 'Unknown role.'
    elif role in STAFF_ROLES and (data.get('access_code') or '').strip() != settings.STAFF_ACCESS_CODE:
        errors['access_code'] = 'Invalid staff access code. Ask the research coordinator for the code.'
    if role == 'STUDENT' and not consent:
        errors['consent_given'] = 'Research participation consent is required for student accounts.'
    try:
        validate_password(password, User(username=username, email=email, first_name=full_name))
    except ValidationError as e:
        errors['password'] = ' '.join(e.messages)
    if errors:
        return Response({'error': 'Please fix the highlighted fields.', 'fields': errors}, status=400)

    user = User.objects.create_user(username=username, email=email, password=password, first_name=full_name[:150])
    profile = ParticipantProfile(
        user=user,
        role=role,
        full_name=full_name[:150],
        assigned_arm=ParticipantProfile.balanced_arm() if role == 'STUDENT' else 'REASONING_VISIBLE',
    )
    _apply_profile_fields(profile, data)
    profile.full_name = full_name[:150]
    if consent:
        profile.consent_given = True
        profile.consent_at = timezone.now()
        profile.consent_version = str(data.get('consent_version') or 'v1')[:10]
    profile.save()

    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])
    token, _ = Token.objects.get_or_create(user=user)
    return _with_lang_cookie(Response({'status': 'success', 'token': token.key, 'user': serialize_user(user, profile)}, status=201), profile)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AuthBurstThrottle])
def login_view(request):
    identifier = (request.data.get('identifier') or request.data.get('username') or '').strip()
    password = request.data.get('password') or ''
    if not identifier or not password:
        return Response({'error': 'Username/email and password are required.'}, status=400)

    lookup = User.objects.filter(email__iexact=identifier).first() if '@' in identifier else User.objects.filter(username__iexact=identifier).first()
    user = authenticate(request, username=lookup.username if lookup else identifier, password=password)
    if user is None:
        return Response({'error': 'Invalid username or password.'}, status=401)
    if not user.is_active:
        return Response({'error': 'This account has been deactivated. Contact the research coordinator.'}, status=403)

    profile = _profile_for(user)
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])
    token, _ = Token.objects.get_or_create(user=user)
    return _with_lang_cookie(Response({'status': 'success', 'token': token.key, 'user': serialize_user(user, profile)}), profile)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    Token.objects.filter(user=request.user).delete()
    return Response({'status': 'success'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    return Response(serialize_user(request.user, _profile_for(request.user)))


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def profile_view(request):
    user = request.user
    profile = _profile_for(user)
    if request.method == 'PATCH':
        data = request.data
        errors = {}
        if 'email' in data:
            email = (data.get('email') or '').strip().lower()
            if email and User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                errors['email'] = 'An account with this email already exists.'
            else:
                user.email = email
        if 'full_name' in data and not (data.get('full_name') or '').strip():
            errors['full_name'] = 'Full name cannot be empty.'

        # Tutor mode is self-selectable, but every switch is recorded so the research data stays interpretable.
        arm_switch = None
        if 'assigned_arm' in data:
            arm = str(data.get('assigned_arm') or '').upper()
            if arm not in VALID_ARMS:
                errors['assigned_arm'] = 'Unknown tutor mode.'
            elif arm != profile.assigned_arm:
                arm_switch = (profile.assigned_arm, arm)

        if errors:
            return Response({'error': 'Please fix the highlighted fields.', 'fields': errors}, status=400)

        if arm_switch:
            from logging_app.models import InteractionLog
            profile.assigned_arm = arm_switch[1]
            InteractionLog.objects.create(
                user=user, event_type='ARM_SWITCH', arm=arm_switch[1],
                payload={'from': arm_switch[0], 'to': arm_switch[1], 'source': 'profile', 'self_selected': True,
                         'device_id': getattr(request, 'device_id', None)},
            )
        _apply_profile_fields(profile, data)
        if 'full_name' in data:
            user.first_name = profile.full_name[:150]
        if 'consent_given' in data and _coerce('bool', data.get('consent_given')) and not profile.consent_given:
            profile.consent_given = True
            profile.consent_at = timezone.now()
        user.save(update_fields=['email', 'first_name'])
        profile.save()
        return _with_lang_cookie(Response(serialize_user(user, profile)), profile)
    return Response(serialize_user(user, profile))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    user = request.user
    current = request.data.get('current_password') or ''
    new = request.data.get('new_password') or ''
    if not user.check_password(current):
        return Response({'error': 'Current password is incorrect.', 'fields': {'current_password': 'Incorrect password.'}}, status=400)
    try:
        validate_password(new, user)
    except ValidationError as e:
        return Response({'error': ' '.join(e.messages), 'fields': {'new_password': ' '.join(e.messages)}}, status=400)
    user.set_password(new)
    user.save(update_fields=['password'])
    Token.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)
    return Response({'status': 'success', 'token': token.key})


AVATAR_TYPES = {'image/jpeg', 'image/png', 'image/webp'}


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def avatar_view(request):
    """Upload (multipart field `avatar`) or remove the profile picture. Images are
    square-cropped and shrunk to 512px so a phone photo doesn't become a 6 MB avatar."""
    from io import BytesIO
    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps, UnidentifiedImageError

    profile = _profile_for(request.user)

    if request.method == 'DELETE':
        if profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = None
            profile.save(update_fields=['avatar'])
        return Response(serialize_user(request.user, profile))

    upload = request.FILES.get('avatar')
    if not upload:
        return Response({'error': 'No image was sent.', 'fields': {'avatar': 'Choose a JPG, PNG or WebP image.'}}, status=400)
    if upload.size > settings.AVATAR_MAX_BYTES:
        return Response({'error': 'Image is too large.', 'fields': {'avatar': 'Maximum size is 5 MB.'}}, status=400)
    if upload.content_type not in AVATAR_TYPES:
        return Response({'error': 'Unsupported image type.', 'fields': {'avatar': 'Use a JPG, PNG or WebP image.'}}, status=400)

    try:
        image = Image.open(upload)
        image.load()
    except (UnidentifiedImageError, OSError):
        return Response({'error': 'That file is not a valid image.', 'fields': {'avatar': 'The file could not be read as an image.'}}, status=400)

    image = ImageOps.exif_transpose(image).convert('RGB')
    image = ImageOps.fit(image, (512, 512), Image.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format='WEBP', quality=88, method=6)

    if profile.avatar:
        profile.avatar.delete(save=False)
    profile.avatar.save(f'u{request.user.id}.webp', ContentFile(buffer.getvalue()), save=False)
    profile.save(update_fields=['avatar'])
    return Response(serialize_user(request.user, profile))
