import os
import uuid
import json
import io
import shutil
import tempfile
from typing import List, Dict, Any
from dagster import asset, Output, AssetExecutionContext, Config, DynamicPartitionsDefinition
from src.storage.dagster_resources import MinioResource
from src.ingestion.rendering import render_pdf_pages, render_pptx_slides, _check_libreoffice_installed
from src.ingestion.extraction import extract_text_and_metadata

BUCKET_NAME = "training-content"

course_files_partition = DynamicPartitionsDefinition(name="course_files")

class CourseArtifactConfig(Config):
    course_id: str
    filename: str
    object_name: str

from src.ingestion.models import CourseMetadata

@asset(partitions_def=course_files_partition)
def process_course_artifact(context: AssetExecutionContext, minio: MinioResource) -> Dict[str, Any]:
    """
    Processes a single course artifact downloaded from MinIO.
    Triggered by the sensor when a new file is found in 'training-content/{course_id}/{filename}'.
    Uses the partition key as the MinIO object name.
    """
    client = minio.get_client()
    
    # Get partition key (object name)
    source_object_name = context.partition_key
    
    # Parse object name to get details
    parts = source_object_name.split('/')
    course_id = parts[0]
    filename = parts[1]
    
    context.log.info(f"Processing artifact: {source_object_name} (Course ID: {course_id})")

    # Download source file to temp
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, filename)
        client.download_file(BUCKET_NAME, source_object_name, file_path)
        
        # Try to download metadata.json if it exists
        course_metadata = {}
        try:
            metadata_path = os.path.join(temp_dir, "metadata.json")
            client.download_file(BUCKET_NAME, f"{course_id}/metadata.json", metadata_path)
            with open(metadata_path, 'r', encoding='utf-8') as f:
                course_metadata = json.load(f)
            context.log.info("Downloaded course metadata.")
        except Exception:
            context.log.warning("No metadata.json found for this course.")

        # 1. Prepare File for Processing (Convert to PDF if needed)
        # We convert DOCX to PDF first because Unstructured extracts page numbers reliably from PDF.
        # For PPTX, we try original file first (as it usually has page numbers), but fallback to PDF if needed.
        processing_file_path = file_path
        is_converted_pdf = False
        
        # Determine if conversion is needed (Force for DOCX, and PPT -> PPTX)
        if filename.lower().endswith((".docx", ".doc")):
            try:
                # We use the temp_dir for the converted PDF
                from src.ingestion.rendering import convert_to_pdf
                context.log.info(f"Converting {filename} to PDF for reliable page extraction...")
                processing_file_path = convert_to_pdf(file_path, temp_dir)
                is_converted_pdf = True
                context.log.info(f"Conversion successful: {processing_file_path}")
            except Exception as e:
                context.log.error(f"PDF conversion failed: {e}. Falling back to original file.")
                processing_file_path = file_path
        
        elif filename.lower().endswith(".ppt"):
            try:
                # Convert PPT to PPTX for python-pptx compatibility
                from src.ingestion.rendering import convert_to_pptx
                context.log.info(f"Converting legacy {filename} to PPTX for extraction...")
                processing_file_path = convert_to_pptx(file_path, temp_dir)
                context.log.info(f"Conversion successful: {processing_file_path}")
            except Exception as e:
                context.log.error(f"PPTX conversion failed: {e}. Falling back to original file (likely to fail extraction).")
                processing_file_path = file_path

        # 2. Render Images (Slides/Pages)
        images = []
        try:
            if processing_file_path.lower().endswith(".pdf"):
                images = render_pdf_pages(processing_file_path)
            elif filename.lower().endswith((".pptx", ".ppt", ".docx", ".doc")):
                # Fallback if conversion failed or if it's a PPTX (we render PPTX via PDF conversion internally anyway)
                images = render_pptx_slides(file_path)
        except Exception as e:
            context.log.error(f"Image rendering failed: {e}")

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

        # 3. Extract Text & Embedded Images
        elements = []
        embedded_images_map = {}
        extraction_metadata = {}
        try:
            with tempfile.TemporaryDirectory() as temp_extract_dir:
                try:
                    # Use the (potentially converted) PDF for extraction
                    elements = extract_text_and_metadata(
                        processing_file_path, 
                        extract_images=True, 
                        image_output_dir=temp_extract_dir
                    )

                    # PPTX Special Handling: Direct Extraction + PDF Fallback
                    if filename.lower().endswith((".pptx", ".ppt")) and not is_converted_pdf:
                        # 1. Try Direct Extraction using python-pptx (Preserves quality and slide context)
                        from src.ingestion.pptx_media_extractor import extract_images_from_pptx
                        
                        direct_images = extract_images_from_pptx(processing_file_path, temp_extract_dir)
                        context.log.info(f"Direct PPTX extraction found {len(direct_images)} images.")
                        
                        # Check total images found so far (unstructured + direct)
                        all_images = [f for f in os.listdir(temp_extract_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                        
                        # 2. If still no images, trigger PDF Fallback (Visual extraction)
                        if not all_images:
                            context.log.warning("No images found via direct extraction. Triggering PDF fallback...")
                            from src.ingestion.rendering import convert_to_pdf
                            
                            # Convert to PDF
                            pdf_path = convert_to_pdf(file_path, temp_dir) # Use main temp_dir for PDF file
                            
                            # Extract from PDF (using unstructured's CV)
                            # Note: This will extract images *from* the rendered PDF pages
                            elements_pdf = extract_text_and_metadata(
                                pdf_path,
                                extract_images=True,
                                image_output_dir=temp_extract_dir
                            )
                            
                            # Merge elements? Or just rely on the images being in temp_extract_dir?
                            # The images are now in temp_extract_dir, which is what we iterate over below.
                            # We might want to update 'elements' with the PDF elements if the original PPTX text extraction was also poor,
                            # but for now we are focusing on images.
                            context.log.info("PDF fallback extraction completed.")
                            
                except Exception as extract_err:
                    context.log.error(f"Extraction error: {extract_err}")
                    # If it was a critical error, we might want to re-raise, but for now we log and continue
                    # to ensure at least text/other assets are processed if possible.
                    # But if this was the main extraction, 'elements' might be empty.
                    if not elements:
                         raise extract_err
                
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
            
            # Capture extraction metadata (e.g. from first element)
            if elements:
                # Use the first element's metadata as representative for file-level info (filetype, languages, etc.)
                # Exclude element-specific fields like coordinates or page_number
                first_meta = elements[0].get("metadata", {})
                extraction_metadata = {k: v for k, v in first_meta.items() if k not in ["coordinates", "page_number", "image_path"]}
            
            # Upload text.json only if extraction succeeded
            text_object_name = f"{course_id}/generated/text.json"
            text_json = json.dumps(elements, indent=2)
            client.upload_bytes(BUCKET_NAME, text_object_name, text_json.encode('utf-8'), content_type="application/json")
            context.log.info(f"Uploaded text extraction for {filename} ({len(elements)} elements)")

        except Exception as e:
            context.log.error(f"Failed to extract text from {filename}: {e}")
            # Re-raise to fail the asset - don't silently continue with no data
            raise

        # 3. Create Manifest
        manifest = {
            "course_id": course_id,
            "filename": filename,
            "metadata": course_metadata,
            "extraction_metadata": extraction_metadata,
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
