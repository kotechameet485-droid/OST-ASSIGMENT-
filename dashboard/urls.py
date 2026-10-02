"""
URL patterns for OpenSourceLens Dashboard application.
"""

from django.urls import path
from dashboard import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('analyze/', views.analyze_view, name='analyze'),
    path('history/', views.history_view, name='history'),
    path('history/<str:owner>/<str:repo>/', views.history_detail_view, name='history_detail'),
    path('compare/', views.compare_view, name='compare'),
    path('about/', views.about_view, name='about'),
]

