#!/usr/bin/env python
"""
PaperMind Worker - processes analysis jobs from Redis queue.
Runs as a separate process from Django.
Communicates with Django's DB and Redis.

Start with: python worker.py
"""

import os
import sys
import time
import django
import redis
import logging
import grpc

#Django Setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.cache import cache
from papers.models import Paper, AnalysisJob
from django.conf import settings


sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'proto_generated'))
import paper_analysis_pb2 as pb
import paper_analysis_pb2_grpc as pb_grpc


#Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WORKER] %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

#Redis Connection
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

QUEUE_NAME = 'job_queue'
GRPC_SERVER = settings.GRPC_SERVER

def get_grpc_stub():
    """
        Creates a grpc channel and stub.
        Channel = connection to the Go server
        Stub = the client object that has AnalyzePaper() method.
    """
    channel = grpc.insecure_channel(GRPC_SERVER)
    stub = pb_grpc.PaperAnalysisServiceStub(channel)
    return  stub


# def analyze_paper(paper):
#     """
#     Currently stub logic, actual implementation will be done later 

#     Args:
#         paper (_type_): _description_
#     """
#     logger.info(f"Analyzing paper: {paper.title}")
#     time.sleep(2)
    
#     return {
#         'summary': f'Analysis of "{paper.title}": '
#                    f'This paper presents novel contributions to the field. '
#                    f'Key findings include advanced methodology and strong results.',
#         'key_findings': [
#             'Novel approach to the problem',
#             'Strong experimental results',
#             'Clear contribution to the field'
#         ],
#         'confidence_score': 0.85
#     }
    

def process_job(job_id):
    """
    Processes a single analysis job
    1. Fetch job + paper from db
    2. Pass paper to analyze and analysis starts
    3. Update Job Status in DB
    4. Update Job Status in Redis Cache

    Args:
        job_id (_type_): _description_
    """
    logger.info(f"Processing job: {job_id}")
    try:
        job = AnalysisJob.objects.select_related('paper').get(id=job_id)
    except AnalysisJob.DoesNotExist:
        logger.error(f"Job {job_id} not found in DB - skipping")
        return
    
    job.status = 'processing'
    job.save()
    cache.set(f"job:{job_id}:status", 'processing', timeout=3600)
    logger.info(f"Job {job_id} -> processing")
    
    try:
        # result = analyze_paper(job.paper)
        request = pb.AnalyzeRequest(
            job_id=str(job_id),
            paper_url=job.paper.url,
            paper_title=job.paper.title
        )
        logger.info(f"Calling Go gRPC server at {GRPC_SERVER}")
        
        stub = get_grpc_stub()
        response = stub.AnalyzePaper(request, timeout=300)
        
        logger.info(f"gRPC response received: status={response.status}")
        logger.info(f"Summary: {response.summary[:80]}...")
        logger.info(f"Key findings: {len(response.key_findings)}")
        logger.info(f"Confidence: {response.confidence_score}")
        
        result = {
            'summary':response.summary,
            'confidence_score': response.confidence_score,
            'key_findings':[
                {
                    'finding': kf.finding,
                    'relevance_score': kf.relevance_score
                }
                for kf in response.key_findings
            ]
        }
        
        job.status = 'completed'
        job.result = result
        job.save()
        
        cache.set(f"job:{job_id}:status", 'completed', timeout=3600)
        logger.info(f"Job {job_id} -> completed")
        
    except grpc.RpcError as e:
        logger.error(f"gRPC error for job {job_id}: {e.code()} - {e.details()}")
        job.status = 'failed'
        job.error_message = f"gRPC error: {e.details()}"
        job.save()
        cache.set(f"job:{job_id}:status", 'failed', timeout=3600)
        
    except Exception as e:
        logger.error(f"Unexpected error for job {job_id}: {e}")
        job.status = 'failed'
        job.error_message = str(e)
        job.save()
        
        cache.set(f"job:{job_id}:status", 'failed', timeout=3600)
        logger.error(f"Job: {job_id} -> failed: {e}")


def main():
    """This will check redis job queue, pulls any new jobs, calls process job which calls analyze
    main -> processJob -> analyze
    """
    logger.info("PaperMind Worker started.....")
    logger.info(f"Watching queue: {QUEUE_NAME}")
    logger.info(f"gRPC server: {GRPC_SERVER}")
    logger.info("Waiting for jobs....(Ctrl+c to stop)")
    
    while True:
        try:
            result = redis_client.brpop(QUEUE_NAME, timeout=0)
            
            if result:
                queue_name, job_id = result
                logger.info(f"Recieved Job from queue: {job_id}")
                process_job(job_id)
        except redis.ConnectionError:
            logger.error("Redis connection lost - retrying in 5 seconds")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Worker Stopped by User")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected Error: {e}")
            time.sleep(1)


if __name__ == '__main__':
    main()