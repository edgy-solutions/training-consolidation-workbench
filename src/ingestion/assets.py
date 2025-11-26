import os
import uuid
import json
import io
import shutil
import tempfile
from typing import List, Dict, Any
from dagster import asset, Output, AssetExecutionContext, Config
from src.storage.dagster_resources import MinioResource
from src.ingestion.rendering import render_pdf_pages, render_pptx_slides, _check_libreoffice_installed
from src.ingestion.extraction import extract_text_and_metadata

BUCKET_NAME = "training-content"

class CourseArtifactConfig(Config):
    course_id: str
    filename: str
    object_name: str

from src.ingestion.models import CourseMetadata

@asset
def process_course_artifact(context: AssetExecutionContext, config: CourseArtifactConfig, minio: MinioResource) -> Dict[str, Any]:
    """
    Processes a single course artifact downloaded from MinIO.
    Triggered by the sensor when a new file is found in 'training-content/{course_id}/{filename}'.
    """
    client = minio.get_client()
    
    course_id = config.course_id
    filename = config.filename
    source_object_name = config.object_name
    
    # Set LibreOffice path for Unstructured if found
    soffice_path = _check_libreoffice_installed()
    if soffice_path:
        context.log.info(f"Found LibreOffice at: {soffice_path}")
        # Add directory to PATH just in case
        bin_dir = os.path.dirname(soffice_path)
        if bin_dir not in os.environ["PATH"]:
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
            
        # Set environment variables used by Unstructured or dependencies
        # UNSTRUCTURED_SO_SLICE_PATH is the requested var (assuming typo for 'soffice')
        os.environ["UNSTRUCTURED_SO_SLICE_PATH"] = soffice_path 
        # Standard LibreOffice binary path for various tools
        os.environ["LIBREOFFICE_BINARY"] = soffice_path
    else:
        context.log.warning("LibreOffice not found. PPTX extraction might fail.")
    
    context.log.info(f"Processing artifact: {source_object_name} (Course ID: {course_id})")

    # Download source file to temp
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, filename)
        client.download_file(BUCKET_NAME, source_object_name, file_path)
        
        # Try to download metadata.json if it exists
        metadata = {}
        try:
            metadata_path = os.path.join(temp_dir, "metadata.json")
            client.download_file(BUCKET_NAME, f"{course_id}/metadata.json", metadata_path)
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            context.log.info("Downloaded course metadata.")
        except Exception:
            context.log.warning("No metadata.json found for this course.")

        # 1. Render Images (Slides/Pages)
        images = []
        if filename.lower().endswith(".pdf"):
            images = render_pdf_pages(file_path)
        elif filename.lower().endswith(".pptx"):
            images = render_pptx_slides(file_path)
        
        image_urls = {}
        for i, img in enumerate(images):
            page_num = i + 1
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()
            
            object_name = f"{course_id}/generated/pages/page_{page_num}.png"
            url = client.upload_bytes(BUCKET_NAME, object_name, img_bytes, content_type="image/png")
            image_urls[page_num] = url
            context.log.info(f"Uploaded page {page_num} image")

        # 2. Extract Text & Embedded Images
        elements = []
        embedded_images_map = {}
        try:
            with tempfile.TemporaryDirectory() as temp_extract_dir:
                elements = extract_text_and_metadata(
                    file_path, 
                    extract_images=True, 
                    image_output_dir=temp_extract_dir
                )
                
                # Upload extracted embedded images
                for img_filename in os.listdir(temp_extract_dir):
                    img_local_path = os.path.join(temp_extract_dir, img_filename)
                    if os.path.isfile(img_local_path):
                        object_name = f"{course_id}/generated/images/{img_filename}"
                        
                        # Detect content type (basic)
                        ext = os.path.splitext(img_filename)[1].lower()
                        ctype = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                        
                        url = client.upload_file(BUCKET_NAME, object_name, img_local_path, content_type=ctype)
                        embedded_images_map[img_filename] = url
                        context.log.info(f"Uploaded embedded image: {img_filename}")

                # Update elements metadata with new image URLs
                for el in elements:
                    metadata = el.get("metadata", {})
                    image_path = metadata.get("image_path")
                    if image_path:
                        img_filename = os.path.basename(image_path)
                        if img_filename in embedded_images_map:
                            metadata["image_url"] = embedded_images_map[img_filename]

            text_object_name = f"{course_id}/generated/text.json"
            text_json = json.dumps(elements, indent=2)
            client.upload_bytes(BUCKET_NAME, text_object_name, text_json.encode('utf-8'), content_type="application/json")
            context.log.info(f"Uploaded text extraction for {filename}")
        except Exception as e:
            context.log.error(f"Failed to extract text from {filename}: {e}")

        # 3. Create Manifest
        manifest = {
            "course_id": course_id,
            "filename": filename,
            "metadata": metadata,
            "source_url": f"http://{minio.endpoint}/{BUCKET_NAME}/{source_object_name}",
            "page_count": len(images) if images else 0,
            "image_urls": image_urls,
            "embedded_images": embedded_images_map,
            "text_location": f"{course_id}/generated/text.json"
        }
        
        manifest_object_name = f"{course_id}/generated/manifest.json"
        manifest_json = json.dumps(manifest, indent=2)
        client.upload_bytes(BUCKET_NAME, manifest_object_name, manifest_json.encode('utf-8'), content_type="application/json")
        
        return manifest
