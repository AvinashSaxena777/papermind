import uuid
import redis
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Paper, AnalysisJob
from .serializers import ( PaperSerializer, PaperSubmitSerializer, AnalysisJobSerializer, JobStatusSerializer)
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from django.core.cache import cache
from .throttles import AnalyzeRateThrottle
from django.conf import settings
import json
from kafka import KafkaProducer
from django.conf import settings

# redis_client = redis.Redis.from_url(settings.REDIS_URL)
kafka_producer = KafkaProducer(
    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

class PaperViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']
    
    def get_queryset(self):
        return Paper.objects.filter(
            submitted_by=self.request.user
        ).order_by('-created_at')
        
    def get_serializer_class(self):
        if self.action=='create':
            return PaperSubmitSerializer
        return PaperSerializer
    
    def perform_create(self, serializer):
        serializer.save(submitted_by=self.request.user)
        
    def create(self, request, *args, **kwargs):
        input_serializer = PaperSubmitSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        paper = input_serializer.save(submitted_by=request.user)
        
        output_serializer = PaperSerializer(paper)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'], url_path='analyze', throttle_classes=[AnalyzeRateThrottle])
    def analyze(self, request, pk=None):
        """POST /api/papers/<id>/analyze/

        Args:
            request (_type_): _description_
            pk (_type_, optional): _description_. Defaults to None.
        """
        paper = self.get_object()
        
        job = AnalysisJob.objects.create(
            paper=paper,
            status='pending'
        )
        
        cache_key = f"job:{job.id}:status"
        cache.set(cache_key, 'pending', timeout=3600)
        
        
        # from django.core.cache import caches
        # redis_client = caches['default'].client.get_client()
        # redis_client.lpush('job_queue', str(job.id))
        
        # redis_client.lpush('job_queue', str(job.id))
        
        kafka_producer.send(
            settings.KAFKA_ANALYZE_TOPIC,
            value={
                'job_id': str(job.id),
                'paper_id': str(paper.id),
                'paper_url': paper.url,
                'paper_title': paper.title
            }
        )
        
        kafka_producer.flush()
        
        paper.status = 'processing'
        paper.save()
        
        return Response({
            'job_id': str(job.id),
            'status':'pending',
            'message':'Analysis job queued. Poll /api/jobs/<job_id>/status for updates.'
        }, status=status.HTTP_202_ACCEPTED)
        
        
class JobStatusView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=True, methods=['get'], url_path='status')
    def status(self, request, pk=None):
        """
        GET /api/jobs/<job_id>/status/
        Reads from Redis first - falls back to DB on cache miss

        Args:
            request (_type_): _description_
            pk (_type_, optional): _description_. Defaults to None.
        """
        job_id = pk
        cache_key = f"job:{job_id}:status"
        cached_status=cache.get(cache_key)
        
        if cached_status:
            return Response({
                'job_id':job_id,
                'status':cached_status,
                'source':'cache'
            })
            
        try:
            job = AnalysisJob.objects.get(id=job_id, paper__submitted_by=request.user)
            cache.set(cache_key, job.status, timeout=3600)
            return Response({
                'job_id':job_id,
                'status':job.status,
                'source':'database'
            })
        except AnalysisJob.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )