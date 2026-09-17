from django.contrib import admin
from django.urls import path, re_path
from trace_backend import views as site_views
from accounts import views as accounts_views
from tutor import views as tutor_views
from logging_app import views as logging_views
from assessment import views as assessment_views
from curriculum import views as curriculum_views

urlpatterns = [
    # Not at admin/: the React app owns /admin (researcher dashboard) and /admin/rag.
    path('django-admin/', admin.site.urls),

    # Liveness probe for a supervisor or uptime monitor; the one unauthenticated GET.
    path('api/health/', site_views.health, name='health'),

    # Accounts, authentication & research profile
    path('api/accounts/register/', accounts_views.register_view, name='register'),
    path('api/accounts/login/', accounts_views.login_view, name='login'),
    path('api/accounts/logout/', accounts_views.logout_view, name='logout'),
    path('api/accounts/me/', accounts_views.me_view, name='me'),
    path('api/accounts/profile/', accounts_views.profile_view, name='profile'),
    path('api/accounts/password/', accounts_views.change_password_view, name='change_password'),
    path('api/accounts/avatar/', accounts_views.avatar_view, name='avatar'),
    path('api/accounts/my-data/', accounts_views.my_data_view, name='my_data'),
    path('api/accounts/withdraw/', accounts_views.withdraw_view, name='withdraw'),
    path('api/admin/participants/<str:participant_code>/withdraw/',
         accounts_views.withdraw_participant_view, name='withdraw_participant'),
    path('api/telemetry/log/', logging_views.log_telemetry, name='log_telemetry'),
    path('api/dashboard/', logging_views.dashboard_summary, name='dashboard_summary'),
    
    # Dual-Mode AI Tutor
    path('api/tutor/query/', tutor_views.query_tutor, name='query_tutor'),

    # Real compile / run service for the code editor
    path('api/code/run/', tutor_views.run_code, name='run_code'),
    path('api/code/status/', tutor_views.code_status, name='code_status'),

    # Curriculum RAG Engine
    path('api/curriculum/search/', curriculum_views.search_curriculum, name='search_curriculum'),
    path('api/curriculum/ingest/', curriculum_views.ingest_curriculum, name='ingest_curriculum'),
    path('api/curriculum/status/', curriculum_views.rag_status, name='rag_status'),
    path('api/curriculum/passages/', curriculum_views.get_passages, name='get_passages'),
    path('api/curriculum/runs/', curriculum_views.ingest_runs, name='ingest_runs'),
    path('api/curriculum/pages/', curriculum_views.ocr_pages, name='ocr_pages'),

    # Assessment Suite & Expert CVI Ratings
    path('api/assessment/items/', assessment_views.get_items, name='get_items'),
    path('api/assessment/submit/', assessment_views.submit_exam, name='submit_exam'),
    path('api/assessment/submissions/<int:pk>/', assessment_views.get_submission, name='get_submission'),
    path('api/expert/reviews/', assessment_views.get_expert_reviews, name='get_expert_reviews'),
    path('api/expert/rating/', assessment_views.submit_expert_rating, name='submit_expert_rating'),
    
    # Expert Student Code Submission Marking & Grading
    path('api/expert/submissions/', assessment_views.get_student_submissions, name='get_student_submissions'),
    path('api/expert/grade/', assessment_views.grade_student_submission, name='grade_student_submission'),

    path('api/admin/stats/', assessment_views.get_admin_stats, name='get_admin_stats'),
    path('api/admin/export/', assessment_views.export_dataset, name='export_dataset'),
    path('api/admin/manifest/', assessment_views.study_manifest, name='study_manifest'),
    path('api/expert/certification/', assessment_views.certification_report, name='certification_report'),
]

# Avatars. Django serves them itself in development, and in a single-site lab deployment
# that sets SERVE_MEDIA=1; put a real file server in front otherwise. The view checks the
# flag per request (django.conf.urls.static.static() is a no-op whenever DEBUG is off).
urlpatterns += [re_path(r'^media/(?P<path>.*)$', site_views.media_file, name='media')]

# Everything that is not the API, the admin, a static file or an upload is a client-side
# route of the React app: return its shell and let the router take it from there. A path
# with a file extension is a missing file, not a route, and stays a 404 so a stale bundle
# name fails loudly instead of being answered with HTML. The extension test tolerates a
# trailing slash, or APPEND_SLASH would redirect /favicon.svg to /favicon.svg/ and serve it.
urlpatterns += [
    re_path(r'^(?!api/|django-admin/|media/|static/|assets/)(?!.*\.[A-Za-z0-9]+/?$).*$',
            site_views.spa_index, name='spa'),
]
