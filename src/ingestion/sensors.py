import os
from dagster import sensor, RunRequest, SensorEvaluationContext, DefaultSensorStatus
from src.storage.minio import MinioClient
from src.ingestion.assets import BUCKET_NAME, process_course_artifact, CourseArtifactConfig

# We need a way to instantiate MinioClient inside the sensor.
# We can reuse the environment variables or a resource approach.
# For sensors, direct instantiation is often simpler if resources are not available directly.

def get_minio_client():
    return MinioClient(
        endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        secure=False # Assuming local dev for now
    )

# Check env var for default sensor status
# Set DAGSTER_SENSOR_DEFAULT_ENABLED=true to auto-start
_sensor_default_enabled = os.getenv("DAGSTER_SENSOR_DEFAULT_ENABLED", "false").lower() == "true"
_sensor_status = DefaultSensorStatus.RUNNING if _sensor_default_enabled else DefaultSensorStatus.STOPPED

@sensor(job_name="process_course_job", default_status=_sensor_status)
def course_upload_sensor(context: SensorEvaluationContext):
    """
    Monitors MinIO 'training-content' bucket for new course artifacts.
    Expected structure: {course_id}/{filename}
    Ignores: 'generated/' directory.
    """
    client = get_minio_client()
    client.ensure_bucket(BUCKET_NAME)
    
    # List objects in the bucket
    # Note: This lists everything. For production with many files, we'd need a cursor/marker.
    # Since MinioClient.list_objects uses default generic list, we'll iterate.
    # To avoid reprocessing, we rely on the cursor (last processed filename) or a more robust state.
    # Here we use the object name as the cursor.
    
    objects = client.list_objects(BUCKET_NAME, recursive=True)
    
    # Sort by modification time or name to have consistent ordering if possible, 
    # but MinIO list might return generator.
    # We'll iterate and check against cursor.
    
    last_processed_object = context.cursor or ""
    new_cursor = last_processed_object
    
    run_requests = []
    
    # Collect all objects first to sort them? 
    # For simplicity, let's process any object strictly greater than cursor (lexicographically).
    # A timestamp-based cursor is safer for uploads. 
    # Let's store (last_modified_timestamp, object_name) as cursor?
    # Simpler: just use object name for now, assuming no backfilling of old names.
    
    # Iterate and filter
    # Minio list_objects returns objects. sorted_objects is better.
    
    sorted_objects = sorted(objects, key=lambda obj: obj.object_name)
    
    from src.ingestion.assets import course_files_partition
    
    new_partition_keys = []
    
    for obj in sorted_objects:
        if obj.is_dir:
            continue
            
        obj_name = obj.object_name
        
        # Skip generated artifacts
        if "/generated/" in obj_name:
            continue
            
        # Skip metadata files to avoid double triggering
        if obj_name.endswith("/metadata.json"):
            continue
            
        # Skip if already processed (based on cursor)
        if obj_name <= last_processed_object:
            continue
            
        # Parse course_id and filename
        # Expecting: {course_id}/{filename}
        parts = obj_name.split('/')
        if len(parts) != 2:
            continue
            
        # Collect valid object names as partition keys
        new_partition_keys.append(obj_name)
        
        # Construct run request for this partition
        # Note: With dynamic partitions, we first need to ADD the partition, then trigger the run.
        # However, the sensor context allows returning RunRequests.
        # We also need to tell Dagster that these partitions exist.
        # The standard pattern for dynamic partitions in sensors is:
        # 1. context.instance.add_dynamic_partitions(partition_def_name, [keys])
        # 2. yield RunRequest(partition_key=key)
        
        # We limit batch size here to avoid timeouts
        if len(new_partition_keys) >= 5:
            break
            
    if new_partition_keys:
        # Register partitions
        context.instance.add_dynamic_partitions(course_files_partition.name, new_partition_keys)
        
        for key in new_partition_keys:
            yield RunRequest(
                run_key=key,
                partition_key=key
            )
            new_cursor = key # Update cursor to the last processed key
            
    context.update_cursor(new_cursor)
