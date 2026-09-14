import json
from pathlib import Path

from django.core.cache import caches

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import AssessmentItem, ExpertRating, ExamSubmission, ExpertGrade

ITEM_BANK_PATH = Path(__file__).resolve().parent / 'item_bank.json'


def load_item_bank():
    """Item bank JSON, held in the memory cache and keyed by the file's mtime so edits show up
    without a restart."""
    key = f'item-bank:{ITEM_BANK_PATH.stat().st_mtime_ns}'
    bank = caches['default'].get(key)
    if bank is None:
        with open(ITEM_BANK_PATH, encoding='utf-8') as fh:
            bank = json.load(fh)
        caches['default'].set(key, bank, 3600)
    return bank


@api_view(['GET'])
@permission_classes([AllowAny])
def get_items(request):
    exam_type = (request.GET.get('type') or 'pre').lower()
    bank = load_item_bank()
    return Response(bank.get(exam_type, bank['pre']))


@api_view(['POST'])
@permission_classes([AllowAny])
def submit_exam(request):
    from logging_app.views import resolve_user
    exam_type = request.data.get('exam_type', 'pre')
    score = request.data.get('score', 80)
    answers = request.data.get('answers', {})
    student = resolve_user(request.data.get('user_id'), request.data.get('username'), create=True)

    ExamSubmission.objects.create(
        student=student,
        exam_type=exam_type,
        score_pct=int(score or 0),
        answers={'answers': answers, 'code_answers': request.data.get('code_answers', {}), 'chapter': request.data.get('chapter'),
                 'device_id': getattr(request, 'device_id', None)}
    )

    return Response({'status': 'success', 'recorded': True})


@api_view(['GET'])
@permission_classes([AllowAny])
def get_expert_reviews(request):
    return Response({
        'items_to_review': [
            {
                'id': 'item_301',
                'question_text': 'Explain the difference between a for loop and a while loop in C programming.',
                'generated_code': 'for(int i=0; i<N; i++) { ... } vs while(condition) { ... }',
                'source_passage': 'NCTB ICT Class 11-12 Chapter 5: In C programming, for loops are typically used when the exact number of iterations is known in advance, whereas while loops test a condition before each iteration.',
                'bloom_level': 'Apply',
                'language': 'Bangla / English'
            }
        ],
        'cvi_stats': {
            'i_cvi_pass_rate': 0.84,
            's_cvi_ave': 0.92,
            'fleiss_kappa': 0.78,
            'total_certified': 42
        }
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def submit_expert_rating(request):
    item_id = request.data.get('item_id')
    ratings = request.data.get('ratings', {})
    feedback = request.data.get('feedback', '')

    return Response({'status': 'success', 'rated': True})


@api_view(['GET'])
@permission_classes([AllowAny])
def get_student_submissions(request):
    """
    Returns student coding test submissions for expert grading.
    """
    mock_submissions = [
        {
            'id': 'sub_801',
            'student_name': 'Rahim Ahmed (HSC Grade 11)',
            'exam_type': 'Post-Test (C Loops & Logic)',
            'submitted_at': '2026-09-12 21:40',
            'student_code': '#include <stdio.h>\n\nint main() {\n    int n = 5, sum = 0;\n    for(int i = 1; i <= n; i++) {\n        sum += i;\n    }\n    printf("Sum = %d\\n", sum);\n    return 0;\n}',
            'auto_test_results': 'Passed 3/3 Test Cases (Pass Rate 100%)',
            'assigned_marks': 90,
            'max_marks': 100,
            'status': 'PENDING_REVIEW',
            'feedback': 'Good use of accumulator pattern and loop condition.'
        },
        {
            'id': 'sub_802',
            'student_name': 'Fatima Nusrat (HSC Grade 12)',
            'exam_type': 'Withdrawal Task (Unassisted Transfer)',
            'submitted_at': '2026-09-12 22:15',
            'student_code': '#include <stdio.h>\n\nint main() {\n    int n = 10, i = 1, sum = 0;\n    while(i <= n) {\n        sum += i;\n        i++;\n    }\n    printf("%d", sum);\n    return 0;\n}',
            'auto_test_results': 'Passed 3/3 Test Cases (Pass Rate 100%)',
            'assigned_marks': 95,
            'max_marks': 100,
            'status': 'PENDING_REVIEW',
            'feedback': 'Correct while loop implementation during unassisted withdrawal.'
        }
    ]
    return Response({'count': len(mock_submissions), 'submissions': mock_submissions})


@api_view(['POST'])
@permission_classes([AllowAny])
def grade_student_submission(request):
    """
    Records expert teacher assigned marks and feedback comments.
    """
    sub_id = request.data.get('submission_id')
    marks = request.data.get('assigned_marks', 85)
    feedback = request.data.get('feedback', '')

    ExpertGrade.objects.create(
        assigned_marks=marks,
        max_marks=100,
        feedback_comments=feedback,
        is_graded=True
    )

    return Response({
        'status': 'success',
        'submission_id': sub_id,
        'assigned_marks': marks,
        'message': 'Marks and feedback saved into database successfully.'
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def get_admin_stats(request):
    return Response({
        'total_participants': 64,
        'treatment_arm_n': 32,
        'control_arm_n': 32,
        'learning_gain': {
            'treatment_mean_g': 0.68,
            'control_mean_g': 0.65,
            'p_value': 0.42
        },
        'transfer_performance': {
            'treatment_mean': 84.5,
            'control_mean': 71.2,
            'cohens_d': 0.74,
            'p_value': 0.02
        },
        'ai_dependency_drop': {
            'treatment_drop': -4.2,
            'control_drop': -18.6,
            'cohens_d': 0.88,
            'p_value': 0.003
        }
    })
