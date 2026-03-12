from django.contrib import admin
from .models import Paper, AnalysisJob


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'url', 'status', 'submitted_by', 'created_at']
    list_filter = ['status']
    search_fields = ['title', 'url']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    list_display = ['id', 'paper', 'status', 'created_at']
    list_filter = ['status']
    readonly_fields = ['id', 'created_at', 'updated_at']