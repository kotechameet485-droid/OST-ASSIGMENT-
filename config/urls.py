"""
URL configuration for OpenSourceLens project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])

handler400 = 'dashboard.views.error_400_view'
handler404 = 'dashboard.views.error_404_view'
handler500 = 'dashboard.views.error_500_view'
