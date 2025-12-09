from typing import List, Any, Dict

def detect_layout(slide_elements: List[Dict[str, Any]]) -> str:
    """
    Detects the layout archetype of a slide based on heuristics.
    
    Args:
        slide_elements: List of dictionaries representing elements on the slide.
                        Expected keys: 'type' (str), 'text' (str), 'metadata' (dict).
                        Metadata may contain 'coordinates' or 'image_path' etc.
                        
    Returns:
        One of: 'hero', 'documentary', 'split', 'content_caption', 'grid', 'table', 'blank'
    """
    
    # Step A: Inventory
    tables = 0
    embedded_artifacts = 0 # images, videos, figures
    text_content = ""
    
    max_embedded_width_ratio = 0.0
    
    # We assume standard slide width if not provided (e.g. 1920px or 1280px or points)
    # If coordinates are normalized (0-1), great. If pixels, we guess.
    # Unstructured often gives 'coordinates' in pixels.
    # For ratio calculation, we'll try to deduce from metadata if available.
    
    for el in slide_elements:
        el_type = el.get("type", "").lower()
        text = el.get("text", "") or ""
        metadata = el.get("metadata", {})
        
        # Accumulate text
        if el_type in ["title", "narrativeText", "listitem", "text"]:
             text_content += text + " "
             
        # Count Tables
        if el_type == "table":
            tables += 1
            
        # Count Embedded (Image, Figure, Picture)
        # Unstructured types: Image, Figure
        if el_type in ["image", "figure", "picture"]:
            embedded_artifacts += 1
            
            # Check width ratio if coordinates exist
            # specific to Unstructured output format which often has points
            # We'll just assume a standard width of ~1700ish for calculation if unknown?
            # Or checks relative size? 
            # Without rigorous coordinate data, we make best effort.
            
            coords = metadata.get("coordinates") # List of points [[x,y], ...]
            if coords:
                # Calculate width
                try:
                    xs = [p[0] for p in coords.points] if hasattr(coords, 'points') else [p[0] for p in coords]
                    width = max(xs) - min(xs)
                    
                    # Estimate slide width based on max element extent seen so far? 
                    # Or just assume 1000? 
                    # Let's assume the user supplied logic: `embedded.width / slide.width > 0.7`
                    # If we don't know slide width, we can't be sure.
                    # As a fallback, if width > 800 (assuming 72dpi 1024 width? or 1920?)
                    # Let's guess standard PPTX width is often 1280 (720p) or 960 (4:3)
                    slide_width_est = 1280 
                    ratio = width / slide_width_est
                    if ratio > max_embedded_width_ratio:
                        max_embedded_width_ratio = ratio
                except:
                    pass

    text_length = len(text_content.strip())
    
    # Step B: Apply Heuristics
    
    # 1. Table
    if tables > 0:
        return "table"
        
    # 2. Hero (No embedded, short text)
    if embedded_artifacts == 0 and text_length < 200: # Bumped 50 to 200 to be safe for titles + subtitles
        return "hero"
        
    # 3. Documentary (No embedded, long text)
    if embedded_artifacts == 0 and text_length >= 200:
        return "documentary"
        
    # 4. Grid (3+ embedded)
    if embedded_artifacts >= 3:
        return "grid"
        
    # 5. Single Embedded Logic
    if embedded_artifacts == 1:
        if max_embedded_width_ratio > 0.6: # 0.7 might be strict if coords are messy
            return "content_caption"
        else:
            return "split"
            
    # 6. Default Fallback
    if embedded_artifacts == 2:
        return "split" # 2 images often split
        
    return "documentary"
