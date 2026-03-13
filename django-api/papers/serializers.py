from rest_framework import serializers
from .models import Paper, AnalysisJob

class PaperSerializer(serializers.ModelSerializer):
    """Output Serializer - used when returning paper data (model/pythonObject) to client. (i.e. Serializers are used to convert Python Object to JSON)

    Args:
        serializers (_type_): _description_
    """
    submitted_by = serializers.StringRelatedField(read_only=True)
    class Meta:
        model = Paper
        fields = [
            'id','title', 'url', 'status', 'submitted_by', 'created_at', 'updated_at'
        ]
        
        read_only_fields=['id', 'status', 'submitted_by', 'created_at', 'updated_at']
        
class PaperSubmitSerializer(serializers.ModelSerializer):
    """Input Serializer - used when client/front-end/api sends data, it performs another layer of validation before reaching db. (Here, serializers acts to convert json data to Python Object)

    Args:
        serializers (_type_): _description_
    """
    class Meta:
        model=Paper
        fields=['url','title']
        extra_kwargs = {
            'url' : {'required':True},
            'title' : {'required': False},
        }
        
class AnalysisJobSerializer(serializers.ModelSerializer):
    """Output Serializer for Analysis Job

    Args:
        serializers (_type_): _description_
    """
    paper = PaperSerializer(read_only=True)
    
    class Meta:
        model = AnalysisJob
        fields = ['id', 'paper', 'status', 'result', 'error_message', 'created_at', 'updated_at']
        read_only_fields = ['id', 'paper', 'status', 'result', 'error_message', 'created_at', 'updated_at']
        
class JobStatusSerializer(serializers.Serializer):
    """Simple serializer for job status response. Not tied to a model - just structures the response shape.

    Args:
        serializers (_type_): _description_
    """
    
    job_id = serializers.UUIDField()
    status = serializers.CharField()
    result = serializers.JSONField(required=False, allow_null=True) 