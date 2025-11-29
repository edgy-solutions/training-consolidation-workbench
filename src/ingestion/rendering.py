import os
import platform
import subprocess
import tempfile
import shutil
from typing import List
from PIL import Image
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError

def render_pdf_pages(file_path: str) -> List[Image.Image]:
    """
    Render each page of a PDF to a PIL Image.
    Requires poppler to be installed on the system.
    """
    try:
        images = convert_from_path(file_path)
        return images
    except PDFInfoNotInstalledError:
        system = platform.system()
        msg = (
            "Unable to find 'pdftoppm' or 'pdftocairo'. Is poppler installed?\n"
        )
        if system == "Windows":
            msg += (
                "On Windows: Download the latest binary from https://github.com/oschwartz10612/poppler-windows/releases/,\n"
                "extract it, and add the 'bin' folder to your PATH environment variable."
            )
        elif system == "Linux":
            msg += "On Linux: Run `sudo apt-get install poppler-utils` (Debian/Ubuntu) or equivalent."
        elif system == "Darwin":
            msg += "On macOS: Run `brew install poppler`."
        
        raise RuntimeError(msg)
    except Exception as e:
        print(f"Error rendering PDF {file_path}: {e}")
        # Fallback or re-raise depending on strictness
        raise

def _check_libreoffice_installed():
    """Check if 'soffice' or 'libreoffice' (including versioned binaries) is available."""
    # 1. Check standard command names
    for cmd in ["soffice", "libreoffice"]:
        if shutil.which(cmd):
            return cmd
            
    # 2. Check for versioned binaries on Linux (e.g., libreoffice25.8)
    if platform.system() == "Linux":
        import glob
        # Check common bin locations
        for bin_dir in ["/usr/bin", "/usr/local/bin", "/opt/libreoffice/program"]:
            if os.path.isdir(bin_dir):
                # Look for libreoffice* or soffice*
                matches = glob.glob(os.path.join(bin_dir, "libreoffice*")) + glob.glob(os.path.join(bin_dir, "soffice*"))
                # Filter out directories and ensure executable
                matches = [m for m in matches if os.path.isfile(m) and os.access(m, os.X_OK)]
                if matches:
                    # Sort to be deterministic (e.g. picking higher version if naming aligns)
                    matches.sort()
                    return matches[0]

    # 3. Common Windows paths if not in PATH
    if platform.system() == "Windows":
        common_paths = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p
    
    return None

def render_pptx_slides(file_path: str) -> List[Image.Image]:
    """
    Render each slide of a PPTX to a PIL Image by converting to PDF first.
    Requires LibreOffice to be installed.
    """
    soffice_cmd = _check_libreoffice_installed()
    
    if not soffice_cmd:
        print(f"Warning: LibreOffice 'soffice' command not found. Cannot render PPTX slides for {file_path}.")
        print("Please install LibreOffice and add it to your PATH.")
        return []

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Convert PPTX to PDF
            cmd = [
                soffice_cmd,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", temp_dir,
                file_path
            ]
            
            print(f"Running LibreOffice conversion: {' '.join(cmd)}")
            
            # Run LibreOffice conversion and capture output
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Check for errors
            if result.returncode != 0:
                print(f"LibreOffice conversion failed with exit code {result.returncode}")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                return []
            
            # Expect filename.pdf in temp_dir
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            pdf_path = os.path.join(temp_dir, f"{base_name}.pdf")
            
            if not os.path.exists(pdf_path):
                print(f"Error: PDF conversion failed. Expected output at {pdf_path}")
                print(f"Files in temp dir: {os.listdir(temp_dir)}")
                return []
                
            # Now render the PDF
            return render_pdf_pages(pdf_path)
            
    except Exception as e:
        print(f"Error rendering PPTX {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return []
