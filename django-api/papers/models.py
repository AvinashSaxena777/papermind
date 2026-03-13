import uuid
from django.db import models
from django.contrib.auth.models import User

class Paper(models.Model):
    STATUS_CHOICES = {
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title=models.TextField(max_length=500, blank=True)
    url=models.URLField(max_length=1000)
    submitted_by=models.ForeignKey(User, on_delete=models.CASCADE, related_name="papers")
    status= models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.title or self.url}({self.status})"
    
class AnalysisJob(models.Model):
    STATUS_CHOICES = {
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper=models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='jobs')
    status=models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    result=models.JSONField(null=True, blank=True)
    error_message=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering=['-created_at']
        
    def __str(self):
        return f"Job {self.id} for {self.paper}-{self.status}"