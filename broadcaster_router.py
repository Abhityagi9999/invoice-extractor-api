import os
import importlib.util
import pdfplumber
from typing import List, Optional
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot

def detect_format(page1_text: str, full_text: str = "", filename: str = "") -> str:
    """Detect the format of the broadcaster invoice."""
    import re
    # Convert to uppercase for easier matching
    p1_upper = page1_text.upper()
    full_upper = full_text.upper()
    filename_upper = filename.upper()

    # Check for Matrix
    if 'MATRIX PUBLICITIES' in p1_upper or 'MATRIX PUBLICITIES AND MEDIA INDIA' in p1_upper:
        return 'matrix'

    # Check for Star India
    if 'STAR INDIA' in p1_upper or re.search(r'\bO\d{10,}\b', page1_text):
        return 'star'
    if 'DIGITAL SIGNATURE' in p1_upper and ('STAR INDIA' in full_upper or re.search(r'\bO\d{10,}\b', full_text)):
        return 'star'
    if re.search(r'^O\d{10,}', filename_upper):
        return 'star'

    # Check for News18 / Bangla Entertainment / Sony
    if 'BANGLA ENTERTAINMENT' in p1_upper or 'CULVER MAX' in p1_upper or ('NETWORK18' in p1_upper and not 'LOKMAT' in p1_upper and not 'BAND' in p1_upper):
        return 'news18'

    # Check for Rachana TV
    if 'RACHANA TELEVISION' in p1_upper:
        return 'rachana'

    # Check for ABP
    if 'ABP NETWORK' in p1_upper or 'ABP NEWS' in p1_upper:
        return 'abp'

    # Check for Asianet News
    if 'ASIANET NEWS NETWORK' in p1_upper:
        return 'asianet'

    # Check for Mathrubhumi
    if 'MATHRUBHUMI' in p1_upper:
        return 'mathrubhumi'

    # Check for Enter10
    if 'ENTER10 TELEVISION' in p1_upper or 'ENTER 10 TELEVISION' in p1_upper:
        return 'enter10'

    # Check for Polimer
    if 'POLIMER MEDIA' in full_upper or 'PN/' in p1_upper:
        return 'polimer'

    # Check for Public TV
    if 'WRITEMEN MEDIA' in p1_upper or 'WRITMEN MEDIA' in p1_upper or 'PUBLIC TV' in p1_upper:
        return 'publictv'

    # Check for MMTV
    if 'MMTV' in p1_upper:
        return 'mmtv'

    # Check for NewsFirst Kannada
    if 'NEWS FIRST KANNADA' in p1_upper or 'SANKSHIPT MEDIA' in p1_upper or 'OLECOM MEDIA' in p1_upper or 'NEWSFIRSTLIVE.COM' in p1_upper:
        return 'newsfirst'
        
    # Check for TV9
    if 'ASSOCIATED BROADCASTING' in p1_upper or 'TV9' in p1_upper:
        return 'tv9'

    # Check for News18 Lokmat
    if ('PANORAMA TELEVISION' in p1_upper or 'IBN LOKMAT' in p1_upper) and 'LOKMAT' in p1_upper:
        return 'news18_lokmat'

    # Check for Network18 Band (generic regional)
    if ('NETWORK18' in p1_upper or 'TV18' in p1_upper) and 'BAND' in p1_upper:
        return 'network18_band'

    return 'unknown'

def parse_broadcaster_invoice(pdf_path: str) -> Optional[ParsedBroadcasterInvoice]:
    """
    Main entry point for parsing any broadcaster invoice.
    It reads the PDF, detects the format, and dynamically routes
    to the specific parser script located in the organized folders.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Read text from PDF
    pages_text = []
    full_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
                    full_text += text + "\n"
    except Exception as e:
        logger.error(f"Error reading PDF {pdf_path}: {e}")
        return None

    if not pages_text:
        logger.warning(f"No text extracted from {pdf_path}")
        return None

    # Detect format
    page1_text = pages_text[0]
    format_type = detect_format(page1_text, full_text, os.path.basename(pdf_path))
    
    logger.info(f"Parsing broadcaster: {os.path.basename(pdf_path)}")
    logger.info(f"  Detected format: {format_type} ({len(pages_text)} pages)")
    
    if format_type == 'unknown' or format_type == 'error':
        logger.warning(f"  Unknown format for {pdf_path}")
        return None

    # Find the parser script in the organized folder
    # Path: Broadcaster_Invoices_Organized/<FORMAT>/parser.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    organized_dir = os.path.join(base_dir, "Broadcaster_Invoices_Organized")
        
    script_path = os.path.join(organized_dir, format_type.upper(), "parser.py")
    
    if not os.path.exists(script_path):
        logger.error(f"Parser script not found for format '{format_type}': {script_path}")
        # In transition, we might still fall back to old parser. 
        # For now, we strictly require the new modular scripts.
        return None
        
    # Dynamically import the parser module
    try:
        spec = importlib.util.spec_from_file_location(f"parser_{format_type}", script_path)
        parser_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser_module)
        
        # Call the parse() function exposed by the script
        result = parser_module.parse(pages_text, full_text)
        
        if result:
            logger.info(f"  Invoice: {result.header.invoice_number} | Channel: {result.header.channel_name} | Spots: {result.header.total_spots}")
        return result
        
    except Exception as e:
        logger.error(f"Error executing parser for {format_type}: {e}", exc_info=True)
        return None

def is_broadcaster_invoice(pdf_path: str) -> bool:
    """Check if a PDF is a broadcaster invoice (vs agency invoice)."""
    try:
        # Check filename prefix first for safety (common in standard deployments)
        fname = os.path.basename(pdf_path).upper()
        if fname.startswith('GB') or 'AGENCY' in fname:
            return False
            
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return False
                
            text_p1 = pdf.pages[0].extract_text() or ""
            text_p2 = pdf.pages[1].extract_text() if len(pdf.pages) > 1 else ""
            full_test_text = text_p1 + "\n" + (text_p2 or "")
            
            if not text_p1:
                return False
                
            text_upper = text_p1.upper()
            
            # Common agency indicators
            if 'GROUP M MEDIA' in text_upper and 'AGENCY INVOICE' in text_upper:
                return False
                
            # If it has a known format, it's definitely a broadcaster invoice
            format_type = detect_format(text_p1, full_test_text, os.path.basename(pdf_path))
            if format_type != 'unknown':
                return True
                
            # Generic checks for broadcaster keywords
            broadcaster_keywords = [
                'TELECAST CERTIFICATE', 'BROADCAST CERTIFICATE', 
                'MATRIX PUBLICITIES', 'STAR INDIA', 'NETWORK18',
                'ABP NETWORK', 'WRITEMEN'
            ]
            
            return any(k in text_upper for k in broadcaster_keywords)
            
    except Exception:
        return False
