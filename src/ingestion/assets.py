import os
import uuid
import json
import io
from typing import List, Dict, Any
from dagster import asset, Output, AssetExecutionContext
from src.storage.dagster_resources import MinioResource
from src.ingestion.rendering import render_pdf_pages, render_pptx_slides
from src.ingestion.extraction import extract_text_and_metadata

# Default source directory
SOURCE_DIR = os.getenv("INGESTION_SOURCE_DIR", "data/raw")

@asset
def raw_documents(context: AssetExecutionContext, minio: MinioResource) -> List[Dict[str, Any]]:
    """
    Ingests documents from the source directory.
    Renders pages to images, extracts text, and uploads everything to MinIO.
    Returns a list of document manifests.
    """
    client = minio.get_client()
    client.ensure_bucket("images")
    client.ensure_bucket("text")
    client.ensure_bucket("manifests")

    if not os.path.exists(SOURCE_DIR):
        os.makedirs(SOURCE_DIR)
        context.log.info(f"Created source directory: {SOURCE_DIR}")
        return []

    processed_docs = []

    for filename in os.listdir(SOURCE_DIR):
        file_path = os.path.join(SOURCE_DIR, filename)
        if not os.path.isfile(file_path):
            continue
        
        if filename.startswith("."):
            continue

        doc_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, filename))
        context.log.info(f"Processing {filename} (UUID: {doc_uuid})")

        # 1. Render Images
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
            
            object_name = f"{doc_uuid}/page_{page_num}.png"
            url = client.upload_bytes("images", object_name, img_bytes, content_type="image/png")
            image_urls[page_num] = url
            context.log.info(f"Uploaded page {page_num} image")

        # 2. Extract Text
        try:
            elements = extract_text_and_metadata(file_path)
            text_json = json.dumps(elements, indent=2)
            client.upload_bytes("text", f"{doc_uuid}.json", text_json.encode('utf-8'), content_type="application/json")
            context.log.info(f"Uploaded text extraction for {filename}")
        except Exception as e:
            context.log.error(f"Failed to extract text from {filename}: {e}")
            elements = []

        # 3. Create Manifest
        manifest = {
            "doc_uuid": doc_uuid,
            "filename": filename,
            "page_count": len(images) if images else 0, # Approx if PDF
            "image_urls": image_urls,
            # linking text elements could be complex if we want page mapping, 
            # but for now just storing the raw extraction separately is fine.
            "text_location": f"text/{doc_uuid}.json"
        }
        
        manifest_json = json.dumps(manifest, indent=2)
        client.upload_bytes("manifests", f"{doc_uuid}.json", manifest_json.encode('utf-8'), content_type="application/json")
        
        processed_docs.append(manifest)
    
    return processed_docs
