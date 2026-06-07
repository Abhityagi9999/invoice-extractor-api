"""
Broadcaster Invoice PDF Parser Engine
Extracts structured data from TV broadcaster invoices.

Supports 7 formats:
  1. Star India (O-prefix) — Star India Pvt Ltd / Novi Digital (Hotstar)
  2. Matrix/Republic (TK-prefix) — Matrix Publicities (Annexure-style)
  3. ABP Network (numeric) — ABP Network Pvt Ltd
  4. News18/Sony (293-prefix) — Bangla Entertainment / TV18
  5. Asianet News (AN-prefix) — Asianet News Network
  6. Mathrubhumi (321-prefix) — Mathrubhumi Printing & Publishing
  7. Enter10/Dangal (824-prefix) — Enter 10 Television Pvt Ltd
"""

import re
import pdfplumber
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BroadcasterHeader:
    """Stores header metadata from broadcaster invoice."""
    advertiser_name: str = ""
    broadcaster_name: str = ""
    agency_name: str = ""
    channel_name: str = ""
    billing_period: str = ""
    po_number: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    brand: str = ""
    total_spots: int = 0
    net_amount: float = 0.0
    tax_amount: float = 0.0
    total_amount: float = 0.0


@dataclass
class BroadcasterSpot:
    """Stores individual spot/ad record from broadcaster invoice."""
    tp: str = ""            # Telecast Time Band / time slot
    program: str = ""       # Actual show name
    date: str = ""
    day: str = ""
    air_time: str = ""
    duration: int = 0       # seconds
    spot_copy: str = ""     # Caption / Creative name
    brand: str = ""
    rate: float = 0.0
    amount: float = 0.0


@dataclass
class ParsedBroadcasterInvoice:
    """Complete parsed broadcaster invoice."""
    header: BroadcasterHeader = field(default_factory=BroadcasterHeader)
    spots: List[BroadcasterSpot] = field(default_factory=list)
    format_type: str = ""
    source_file: str = ""
    errors: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def _parse_num(value: str) -> float:
    if not value:
        return 0.0
    try:
        cleaned = re.sub(r'[^\d.]', '', value.replace(',', ''))
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def _extract(text: str, pattern: str, group: int = 1, default: str = "") -> str:
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return _clean(m.group(group)) if m else default


def _clean_air_time(t: str) -> str:
    """Normalize air time: '09:35:08:07' -> '09:35:08'."""
    if not t:
        return ""
    t = t.strip()
    parts = t.split(':')
    if len(parts) == 4 and all(p.strip().isdigit() for p in parts):
        return ':'.join(parts[:3])
    return t


def _get_day_from_date(date_str: str) -> str:
    """Get day abbreviation from date string."""
    for fmt in ['%d/%m/%Y', '%d.%m.%Y', '%d-%b-%Y', '%d/%m/%y', '%d.%m.%y']:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime('%a')[:3]
        except ValueError:
            continue
    return ""


# ─────────────────────────────────────────────────────────────────
# Format Detection
# ─────────────────────────────────────────────────────────────────

def detect_format(full_text: str) -> str:
    """Detect which broadcaster format this PDF uses."""
    t = full_text.upper()

    # Matrix / Republic — agency-style Annexure format for broadcaster invoices
    if 'MATRIX PUBLICITIES' in t:
        return 'matrix'

    # TV9 Bharatvarsh
    if 'ASSOCIATED BROADCASTING' in t or 'TV9 BHARATVARSH' in t:
        return 'tv9'

    # Polimer News
    if 'POLIMER' in t:
        return 'polimer'

    # Public TV
    if 'WRITEMEN MEDIA' in t or 'PUBLIC TV' in t:
        return 'publictv'

    # Mazhavil Manorama
    if 'MM TV' in t or 'MAZHAVIL MANORAMA' in t:
        return 'mmtv'

    # NewsFirst Kannada
    if 'NEWSFIRST' in t or 'OLECOM MEDIA' in t:
        return 'newsfirst'

    # News18 Lokmat
    if 'IBN LOKMAT' in t or 'NEWS18 LOKMAT' in t:
        return 'news18_lokmat'

    # Network18 Band (J-Band/L-Band)
    if ('NETWORK18' in t or 'TV18' in t or 'BEPL' in t) and ('L BAND' in t or 'J BAND' in t or 'BUG' in t):
        return 'network18_band'

    if 'STAR INDIA' in t or ('STATION RELATION' in t and 'SCHEDULE BROADCAST' in t):
        return 'star'

    if ('ABP NETWORK' in t or 'ABP NEWS NETWORK' in t) and ('BROADCAST CERTIFICATE' in t or 'ABP' in t):
        return 'abp'

    if 'ASIANET NEWS NETWORK' in t or ('ASIANET' in t and 'TELECAST CERTIFICATE' in t):
        return 'asianet'

    if 'MATHRUBHUMI' in t:
        return 'mathrubhumi'

    if 'ENTER' in t and ('ENTER 10' in t or 'ENTERR10' in t or 'DANGAL' in t):
        return 'enter10'

    # Exact section header check for News18/Sony to avoid legal disclaimer match in Polimer/others
    if re.search(r'^\s*BROADCAST\s*INFORMATION\s*$', t, re.MULTILINE):
        return 'news18'

    if 'TELECAST CERTIFICATE' in t:
        return 'generic_telecast'

    return 'unknown'


def is_broadcaster_invoice(pdf_path: str) -> bool:
    """Check if a PDF is a broadcaster invoice (vs agency invoice)."""
    try:
        # Check filename prefix first for safety (common in standard deployments)
        fname = os.path.basename(pdf_path).upper()
        if fname.startswith('GB') or 'AGENCY' in fname:
            return False

        pdf = pdfplumber.open(pdf_path)
        first_page = pdf.pages[0].extract_text() or ""
        pdf.close()

        upper = first_page.upper()

        # Find where "TAX INVOICE" is written on page 1 (the header title area)
        tax_idx = upper.find('TAX INVOICE')
        if tax_idx != -1:
            # Look at the 250 characters following "TAX INVOICE" (the header company name section)
            header_area = upper[tax_idx:tax_idx+250]
            if 'GROUP M' in header_area or 'GROUPM' in header_area or 'M-SIX' in header_area:
                # GroupM/M-Six is the seller -> This is an Agency invoice!
                return False

        # If it doesn't match the agency seller pattern, we fall back to standard checks
        # But wait! If it contains estimate markers but is NOT billed by GroupM, it's a broadcaster invoice!
        # Matrix invoices contain: "Estimate Number : "
        # If we didn't match GroupM/M-Six as the seller, let's look at broadcaster markers:
        broadcaster_names = ['MATRIX PUBLICITIES', 'STAR INDIA', 'ABP NETWORK', 'ASIANET NEWS', 
                             'MATHRUBHUMI', 'ENTER 10', 'ENTERR10', 'BANGLA ENTERTAINMENT', 
                             'ARNAB GOSWAMI', 'POLIMER', 'WRITEMEN MEDIA', 'PUBLIC TV', 
                             'MM TV', 'MAZHAVIL MANORAMA', 'NEWSFIRST', 'OLECOM MEDIA', 
                             'ASSOCIATED BROADCASTING', 'TV9', 'IBN LOKMAT', 'NEWS18 LOKMAT', 
                             'NETWORK18', 'TV18', 'BEPL']
        
        for name in broadcaster_names:
            if name in upper:
                return True

        # Check for broadcaster sections
        if 'TELECAST CERTIFICATE' in upper or 'BROADCAST CERTIFICATE' in upper:
            return True
        if 'BROADCAST INFORMATION' in upper:
            return True
        if 'SCHEDULE BROADCAST' in upper and 'STATION RELATION' in upper:
            return True

        # Fallback to agency check using general markers if "TAX INVOICE" wasn't found
        if 'ESTIMATE NUMBER' in upper or 'ESTIMATE PERIOD' in upper or 'ACTIVITY MONTH' in upper:
            return False

        return True  # Default: assume broadcaster
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────
# Star India Parser
# ─────────────────────────────────────────────────────────────────

def _parse_star(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='star')
    h = result.header

    h.broadcaster_name = "Star India Pvt. Ltd."

    # ── Parse header from full_text (Star PDFs have multi-column table layout,
    #    where labels and values are on different lines) ──

    # Advertiser: appears after "Advertiser" label, spans to next label
    adv_m = re.search(
        r'Advertiser\s+Agency.*?\n'
        r'((?:XIAOMI|[A-Z][A-Z ]+)(?:\s+(?:TECHNOLOGY|INDIA|PRIVATE|LIMITED|PVT|LTD))*)',
        full_text, re.IGNORECASE
    )
    if adv_m:
        # Get the full advertiser name which may span 2 lines
        adv_name = _clean(adv_m.group(1))
        # Check next line for continuation (e.g., "PRIVATE LIMITED")
        after_adv = full_text[adv_m.end():]
        cont_m = re.match(r'\s*((?:PRIVATE|LIMITED|PVT|LTD|TECHNOLOGY|INDIA)\s*(?:PRIVATE|LIMITED|PVT|LTD|TECHNOLOGY|INDIA)*)', after_adv, re.IGNORECASE)
        if cont_m:
            adv_name += ' ' + _clean(cont_m.group(1))
        h.advertiser_name = adv_name

    # Invoice Number (O-prefix, 10+ digits)
    inv_m = re.search(r'\bO\d{10,}\b', full_text)
    if inv_m:
        h.invoice_number = inv_m.group(0)

    # Station Relation / Channel — on the same line as invoice number
    # Format: "O03300262172 MAA HD South-SIPL"
    stn_m = re.search(
        r'O\d{10,}\s+([A-Z][A-Za-z0-9 ]+?)\s+(?:South|North|East|West|National)',
        full_text
    )
    if stn_m:
        h.channel_name = _clean(stn_m.group(1))
    else:
        # Try from STN column in spot data
        stn_m2 = re.search(r'STN\b.*?\n.*?Spot Buys\s+(\w+)', full_text, re.DOTALL)
        if stn_m2:
            h.channel_name = stn_m2.group(1)

    # Invoice Date — format: dd/mm/yyyy after "Invoice Date"
    dt_m = re.search(r'Invoice\s+Date\s+.*?\n\s*.*?(\d{1,2}/\d{1,2}/\d{4})', full_text, re.DOTALL)
    if dt_m:
        h.invoice_date = dt_m.group(1)

    # Billing Period — the date pattern dd/mm/yyyy- dd/mm/yyyy appears on the line after "Billing Period"
    # but may be preceded by address text on the same line
    bp_m = re.search(r'Billing\s+Period.*?\n.*?(\d{1,2}/\d{1,2}/\d{4}\s*-\s*\d{1,2}/\d{1,2}/\d{4})', full_text, re.DOTALL)
    if bp_m:
        h.billing_period = re.sub(r'\s+', '', bp_m.group(1))

    # PO Number — appears after the billing period dates on the same line
    po_m = re.search(r'PO\s+Number.*?\n.*?([A-Z]+\d{4}/\w+/\d+/\s*\d*)', full_text, re.DOTALL)
    if not po_m:
        po_m = re.search(r'PO\s+Number.*?\n.*?(\S+/\S+/\S+)', full_text, re.DOTALL)
    if po_m:
        h.po_number = _clean(po_m.group(1))

    # Agency
    h.agency_name = _extract(full_text, r'(GROUP\s*M\s*MEDIA\s*INDIA\s*(?:PVT|PRIVATE)?\.?\s*(?:LTD|LIMITED)\.?[\s(]*(?:BA)?[\s)]*)', default="GROUP M MEDIA INDIA PVT. LTD.")
    if not h.advertiser_name or 'Agency' in h.advertiser_name or h.advertiser_name.strip().upper() == 'XIAOMI TECHNOLOGY INDIA':
        h.advertiser_name = _extract(full_text, r'(XIAOMI\s+TECHNOLOGY\s+INDIA\s+(?:PRIVATE\s+)?(?:LIMITED|LTD))', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")

    # Brand
    h.brand = "Xiaomi"

    # Parse spot table — Star India format
    # Lines look like: 9390385 9 Spot Buys HMAI (...) PROGRAM_NAME [...] DD/MM/YYYY Day HH:MM:SS:FF DUR CAPTION Brand Rate
    current_tp = ""
    current_program_name = ""

    for page_text in pages_text:
        lines = page_text.split('\n')
        for line in lines:
            ls = line.strip()
            if not ls:
                continue

            # Skip headers/footers
            if any(skip in ls for skip in ['ORDER_ID', 'Page ', 'Star India', 'Tax Invoice',
                                            'Original For', 'GSTIN', 'PAN No', 'HSN Code',
                                            'We warrant', 'Help?', 'Printed:', 'signed',
                                            'payments.', 'KARNATAKA', 'Place of Supply']):
                continue

            # Extract TP from time range in parentheses
            tp_m = re.search(r'\((\d{2}:\d{2}-\d{2}:\d{2})\)', ls)
            if tp_m:
                current_tp = tp_m.group(1)

            # Extract program name (text before [CHANNEL_NAME])
            prog_m = re.search(r'([A-Z][A-Z\s\-0-9]+?)\s+\[([^\]]+)\]', ls)
            if prog_m:
                current_program_name = _clean(prog_m.group(1))

            # Find spot data: DATE DAY TIME DUR ... RATE
            spot_m = re.search(
                r'(\d{1,2}/\d{1,2}/\d{4})\s+'           # Date
                r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*'       # Day
                r'\w?\s*'                                  # Optional extra char
                r'(\d{1,2}:\d{2}:\d{2}(?::\d{2})?)\s+'    # Air Time
                r'(\d{1,2})\s+'                            # Duration
                r'(.*?)'                                   # Spot Copy
                r'\s+(\w+)\s+'                             # Brand
                r'([\d,]+\.\d{2})\s*$',                    # Rate
                ls, re.IGNORECASE
            )

            if spot_m:
                spot = BroadcasterSpot()
                spot.date = spot_m.group(1)
                spot.day = spot_m.group(2).capitalize()
                spot.air_time = _clean_air_time(spot_m.group(3))
                spot.duration = int(spot_m.group(4))
                spot.spot_copy = _clean(spot_m.group(5))
                spot.brand = spot_m.group(6)
                spot.rate = _parse_num(spot_m.group(7))
                spot.amount = spot.rate  # Star rates are per spot
                spot.tp = current_tp
                spot.program = current_program_name
                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result


# ─────────────────────────────────────────────────────────────────
# Matrix/Republic TV Parser (Annexure-style)
# ─────────────────────────────────────────────────────────────────

