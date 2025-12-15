import os
from dagster import sensor, RunRequest, SensorEvaluationContext, DefaultSensorStatus
from src.storage.neo4j import Neo4jClient

# Check env var for default sensor status
_sensor_default_enabled = os.getenv("DAGSTER_SENSOR_DEFAULT_ENABLED", "false").lower() == "true"
_sensor_status = DefaultSensorStatus.RUNNING if _sensor_default_enabled else DefaultSensorStatus.STOPPED

# Configuration
UNHARMONIZED_THRESHOLD = 5  # Trigger when this many unharmonized concepts exist
POLL_INTERVAL_SECONDS = 300  # Check every 5 minutes


def get_neo4j_client():
    """Create a Neo4j client for sensor use."""
    return Neo4jClient()


@sensor(job_name="harmonize_concepts_job", minimum_interval_seconds=POLL_INTERVAL_SECONDS, default_status=_sensor_status)
def unharmonized_concepts_sensor(context: SensorEvaluationContext):
    """
    Monitors Neo4j for Concept nodes without ALIGNS_TO relationships to CanonicalConcept.
    Triggers harmonization job when the count exceeds the threshold.
    
    This batches harmonization to avoid running for every single new concept.
    """
    client = get_neo4j_client()
    
    try:
        # Count concepts that have no alignment to a CanonicalConcept
        query = """
        MATCH (c:Concept)
        WHERE NOT (c)-[:ALIGNS_TO]->(:CanonicalConcept)
        RETURN count(c) as cnt
        """
        results = client.execute_query(query)
        unharmonized_count = results[0]["cnt"] if results else 0
        
        context.log.info(f"Found {unharmonized_count} unharmonized concepts (threshold: {UNHARMONIZED_THRESHOLD})")
        
        if unharmonized_count >= UNHARMONIZED_THRESHOLD:
            # Use an incrementing run key to allow multiple runs over time
            run_number = int(context.cursor or "0") + 1
            
            context.log.info(f"Triggering harmonization job (run #{run_number})")
            
            yield RunRequest(
                run_key=f"harmonize_batch_{run_number}",
            )
            
            # Update cursor so next trigger gets a new run key
            context.update_cursor(str(run_number))
        else:
            context.log.debug(f"Below threshold, skipping harmonization")
            
    except Exception as e:
        context.log.error(f"Error checking unharmonized concepts: {e}")
    finally:
        client.close()
