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
import json
import django
import redis
import logging
import grpc
from kafka import KafkaConsumer, KafkaProducer

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

# #Redis Connection
# redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

# QUEUE_NAME = 'job_queue'

GRPC_SERVER = settings.GRPC_SERVER
KAFKA_SERVERS = settings.KAFKA_BOOTSTRAP_SERVERS
ANALYZE_TOPIC = settings.KAFKA_ANALYZE_TOPIC
RESULTS_TOPIC = settings.KAFKA_RESULTS_TOPIC


def create_consumer():
    """
    KafkaConsumer : reads message from paper.analyze topic
    """
    return KafkaConsumer(
        ANALYZE_TOPIC,
        bootstrap_servers = KAFKA_SERVERS,
        group_id = 'paper-workers',
        value_deserializer = lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        enable_auto_commit=True
    )

def create_producer():
    """
    KafkaProducer : sends results to paper.results topic
    """
    return KafkaProducer(
        bootstrap_servers=KAFKA_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )


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
    

def process_job(event, producer):
    """
    Processes one job event from kafka
    event = dict with job_id, paper_id, paper_url, paper_title
    """
    
    job_id = event['job_id']
    paper_url = event['paper_url']
    paper_title = event['paper_title']
    
    if not job_id:
        logger.warning(f"Skipping message with no job_id: {event}")
        return
    
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
        
        result_event = {
            'job_id': job_id,
            'status': 'completed',
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
        
        # job.status = 'completed'
        # job.result = result
        # job.save()
        
        producer.send(RESULTS_TOPIC, value=result_event)
        producer.flush()
        logger.info(f"Result event produced to {RESULTS_TOPIC}")
        
        cache.set(f"job:{job_id}:status", 'completed', timeout=3600)
        logger.info(f"Job {job_id} -> completed")
        
    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()} - {e.details()}")
        # Produce failure event
        producer.send(RESULTS_TOPIC, value={
            'job_id': job_id,
            'status': 'failed',
            'error_message': e.details()
        })
        producer.flush()
        cache.set(f"job:{job_id}:status", 'failed', timeout=3600)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        cache.set(f"job:{job_id}:status", 'failed', timeout=3600)


def main():
    """This will check redis job queue, pulls any new jobs, calls process job which calls analyze
    main -> processJob -> analyze
    """
    logger.info("PaperMind Worker started.....")
    # logger.info(f"Watching queue: {QUEUE_NAME}")
    logger.info(f"Consuming from: {ANALYZE_TOPIC}")
    logger.info(f"Producing to: {RESULTS_TOPIC}")
    logger.info(f"gRPC server: {GRPC_SERVER}")
    logger.info("Waiting for jobs....(Ctrl+c to stop)")
    
    consumer = create_consumer()
    producer = create_producer()
    
    while True:
        try:
            for message in consumer:
                event = message.value
                logger.info(f"Receieved event: job_id={event.get('job_id')}")
                process_job(event, producer)
        except KeyboardInterrupt:
            logger.info("Worker Stopped by User")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Failed to process message: {e} — skipping")
            continue   # skip bad message, move to next one
        finally:
            consumer.close()
            producer.close()


if __name__ == '__main__':
    main()