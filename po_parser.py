import re
import pdfplumber
import PyPDF2
from typing import Optional
from po_types import ParsedPOInvoice

def is_po_invoice(pdf_path: str) -> bool:
    """Quickly check if the PDF is a Purchase Order."""
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            if not reader.pages:
                return False
            page1_text = reader.pages[0].extract_text() or ""
            return "PURCHASE ORDER" in page1_text.upper()
    except Exception:
        return False
from typing import Optional
from po_types import ParsedPOInvoice

def parse_po_invoice(pdf_path: str) -> Optional[ParsedPOInvoice]:
    """Parse a Purchase Order (PO) PDF file and extract relevant details."""
    try:
        full_text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
        
        # Check if it's actually a PO
        if "PURCHASE ORDER" not in full_text.upper():
            return None
            
        result = ParsedPOInvoice()
        
        po_number = re.search(r'Purchase Order No\s*:\s*(\d+)', full_text, re.IGNORECASE)
        result.po_number = po_number.group(1).strip() if po_number else ""
        
        po_date = re.search(r'Date:\s*.*?\n(\d{2}\.\d{2}\.\d{4})', full_text, re.IGNORECASE)
        result.po_date = po_date.group(1).strip() if po_date else ""
        
        vendor = re.search(r'Vendor Code.*?Name\s*:\s*(.+?)(?:\n|$)', full_text, re.DOTALL | re.IGNORECASE)
        result.agency_name = vendor.group(1).strip() if vendor else ""
        
        buyer = re.search(r'Buyer \(Bill To\):\s*\n.*?(Cipla Health Limited|CIPLA HEALTH[\w\s\/]+)', full_text, re.IGNORECASE)
        result.advertiser_name = buyer.group(1).strip() if buyer else "Cipla Health Limited"
        
        # In case the format differs slightly, have a fallback for description
        desc = re.search(r'Net Item Value\s*\n\d+\s+(.+?)\s+\d+\.\d{3}\s+AU', full_text, re.IGNORECASE)
        if desc:
            result.description = desc.group(1).strip()
        else:
            # Fallback for description if "AU" format isn't matched
            desc_fallback = re.search(r'Material Description[\s\S]*?\n\d+\s+(.*?)\s+\d+\.\d{3}', full_text, re.IGNORECASE)
            result.description = desc_fallback.group(1).strip() if desc_fallback else ""
            
        amount = re.search(r'Gross Total Value\s*:\s*([\d,]+\.\d{2})', full_text, re.IGNORECASE)
        if amount:
            amt_str = amount.group(1).replace(',', '')
            try:
                result.po_amount = float(amt_str)
            except ValueError:
                result.po_amount = 0.0
                
        # Brand placeholder
        result.brand = ""
        
        return result
        
    except Exception as e:
        print(f"Error parsing PO {pdf_path}: {e}")
        return None
