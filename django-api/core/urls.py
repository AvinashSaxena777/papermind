from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from papers.views import PaperViewSet, JobStatusView

router=DefaultRouter()
router.register(r'papers', PaperViewSet, basename='paper')
router.register(r'jobs', JobStatusView, basename='job')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/', include(router.urls)),
]
