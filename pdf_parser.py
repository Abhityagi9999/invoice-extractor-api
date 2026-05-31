"""
Agency Invoice PDF Parser Engine
Extracts structured data from GroupM/M-Six TV advertising invoices.

Handles 4 sections:
  - Page 1: Invoice header metadata
  - Page 2: Channel-wise summary
  - Page 3: Annexure-1 (consolidated spot summary with date-wise counts)
  - Pages 4+: Annexure-2 (individual spot detail records)
"""

import re
import pdfplumber
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class InvoiceHeader:
    """Stores all metadata extracted from Page 1 of the invoice."""
    agency_name: str = ""
    agency_branch: str = ""
    advertiser_name: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    activity_month: str = ""
    estimate_number: str = ""
    estimate_period: str = ""
    po_number: str = ""
    brand_name: str = ""
    campaign_name: str = ""
    net_cost: str = ""
    service_charge: str = ""
    total_chargeable: str = ""
    cgst: str = ""
    sgst: str = ""
    total_amount_payable: str = ""
    pan_number: str = ""
    gstin: str = ""
    place_of_supply: str = ""
    irn: str = ""
    hsn_sac: str = ""


@dataclass
class ChannelSummary:
    """Stores channel-wise spot summary from Page 2."""
    channel: str = ""
    no_of_spots: int = 0
    net_cost: float = 0.0


@dataclass
class AnnexureRecord:
    """Stores consolidated spot summary from Annexure-1 (Page 3)."""
    channel: str = ""
    program: str = ""
    producer: str = ""
    dates_with_spots: str = ""  # e.g., "21(6),22(6),23(6)..."
    spot_duration: int = 0
    net_spot_rate_per_10sec: float = 0.0
    no_of_spots: int = 0
    net_cost: float = 0.0


@dataclass
class SpotDetail:
    """Stores individual spot record from Annexure-2 (Pages 4+)."""
    supp_bill_no: str = ""
    mon_report_no: str = ""
    producer: str = ""
    channel: str = ""
    program: str = ""
    time_band: str = ""
    day: str = ""
    start_time: str = ""
    spot_date: str = ""
    spot_duration: int = 0
    net_spot_rate_per_10sec: float = 0.0
    net_cost: float = 0.0
    mba_full_bill_no: str = ""
    invoice_number: str = ""  # Added for cross-reference


@dataclass
class ParsedInvoice:
    """Complete parsed invoice data."""
    header: InvoiceHeader = field(default_factory=InvoiceHeader)
    channel_summaries: List[ChannelSummary] = field(default_factory=list)
    annexure_records: List[AnnexureRecord] = field(default_factory=list)
    spot_details: List[SpotDetail] = field(default_factory=list)
    total_spots: int = 0
    total_duration: int = 0
    total_net_cost: float = 0.0
    source_file: str = ""
    errors: List[str] = field(default_factory=list)


def _clean_text(text: str) -> str:
    """Clean extracted text by normalizing whitespace."""
    if not text:
        return ""
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _parse_number(value: str) -> float:
    """Parse Indian number format (e.g., '14,34,348.28') to float."""
    if not value:
        return 0.0
    try:
        # Remove commas and spaces
        cleaned = value.replace(',', '').replace(' ', '').strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _extract_field(text: str, pattern: str, group: int = 1, default: str = "") -> str:
    """Extract a field from text using regex pattern."""
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        return _clean_text(match.group(group))
    return default


def parse_header(page_text: str) -> InvoiceHeader:
    """
    Parse Page 1 of the invoice to extract all header metadata.
    
    The page has a fixed structure:
      - Top: Agency name & address, PAN, CIN, GSTIN
      - Middle: Service provided To (advertiser), Invoice Details, Activity Details
      - Bottom: Financial summary (Net Cost, Taxes, Total)
    """
    header = InvoiceHeader()
    
    if not page_text:
        return header
    
    # === Agency Information ===
    # Agency name is always GROUP M MEDIA INDIA PRIVATE LIMITED
    header.agency_name = _extract_field(
        page_text,
        r'(GROUP\s*M\s*MEDIA\s*INDIA\s*(?:PRIVATE|PVT)?\s*(?:LIMITED|LTD)\.?)',
        default="GROUP M MEDIA INDIA PRIVATE LIMITED"
    )
    
    # Agency branch (M-SIX BANGALORE, M-SIX MUMBAI, etc.)
    header.agency_branch = _extract_field(
        page_text,
        r'(M-SIX\s+\w+)',
        default=""
    )
    
    # === Advertiser Information ===
    # Advertiser name comes after "Service provided To :"
    adv_match = re.search(
        r'Service\s+provided\s+To\s*:\s*(?:Invoice\s+Delivered\s+To\s*:)?\s*(?:Invoice\s+Details)?\s*(?:Activity\s+Details)?\s*\n([A-Z][A-Z\s]+(?:PRIVATE|PVT)\s+(?:LIMITED|LTD)\.?)',
        page_text, re.IGNORECASE
    )
    if adv_match:
        header.advertiser_name = _clean_text(adv_match.group(1))
    else:
        # Fallback: look for pattern between "Service provided To" and address
        adv_match2 = re.search(
            r'Service\s+provided\s+To\s*:.*?\n([A-Z][A-Z\s]+(?:PRIVATE|PVT)\s+(?:LIMITED|LTD)\.?)',
            page_text, re.IGNORECASE | re.DOTALL
        )
        if adv_match2:
            header.advertiser_name = _clean_text(adv_match2.group(1))
    
    # === Invoice Details ===
    header.invoice_number = _extract_field(
        page_text,
        r'Invoice\s+Number\s*:\s*(\S+)'
    )
    
    header.invoice_date = _extract_field(
        page_text,
        r'Invoice\s+Date\s*:\s*(\d{1,2}-\w{3}-\d{4})'
    )
    
    header.activity_month = _extract_field(
        page_text,
        r'Activity\s+Month\s*:\s*(\w+-\d{4})'
    )
    
    # === Activity Details ===
    header.estimate_number = _extract_field(
        page_text,
        r'Estimate\s+Number\s*:\s*(\S+)'
    )
    
    header.estimate_period = _extract_field(
        page_text,
        r'Estimate\s+Period\s*:\s*(\d{1,2}-\w{3}-\d{4}\s+To\s+\d{1,2}-\w{3}-\d{4})'
    )
    
    header.po_number = _extract_field(
        page_text,
        r'(?:Client\s+)?PO\s+Number\s*:\s*(\S+)'
    )
    
    header.brand_name = _extract_field(
        page_text,
        r'Brand\s+Name\s*:\s*(\S+)'
    )
    
    # Campaign Name can span multiple lines
    campaign_match = re.search(
        r'Campaign\s+Name\s*:\s*(.+?)(?:\n\d|\nCountry|\nPAN)',
        page_text, re.DOTALL
    )
    if campaign_match:
        campaign = campaign_match.group(1)
        # Clean up multi-line campaign name
        campaign = re.sub(r'\s+', ' ', campaign).strip()
        header.campaign_name = campaign
    
    # === Financial Summary ===
    # Net Cost from "Billing for XXX Activity" line
    billing_match = re.search(
        r'Billing\s+for\s+\w+-\d{4}\s*Activity\s+([\d,]+\.?\d*)',
        page_text
    )
    if billing_match:
        header.net_cost = billing_match.group(1)
    else:
        # Fallback: look for Total line after Particulars
        total_match = re.search(r'Total\s+([\d,]+\.?\d*)\s*\nAdd', page_text)
        if total_match:
            header.net_cost = total_match.group(1)
    
    header.service_charge = _extract_field(
        page_text,
        r'Add:\s*Service\s+Charge\s+([\d,]+\.?\d*)'
    )
    
    header.total_chargeable = _extract_field(
        page_text,
        r'Total\s+Chargeable\s+([\d,]+\.?\d*)'
    )
    
    # CGST and SGST
    cgst_match = re.search(r'CGST.*?([\d,]+\.?\d*)\s*$', page_text, re.MULTILINE)
    if cgst_match:
        header.cgst = cgst_match.group(1)
    
    sgst_match = re.search(r'SGST.*?([\d,]+\.?\d*)\s*$', page_text, re.MULTILINE)
    if sgst_match:
        header.sgst = sgst_match.group(1)
    
    # Total amount payable
    header.total_amount_payable = _extract_field(
        page_text,
        r'Total\s+amount\s+payable\s*:\s*([\d,]+\.?\d*)'
    )
    
    # === Tax Details ===
    # PAN of advertiser
    pan_match = re.search(r'PAN\s+Number\s*:\s*([A-Z0-9]{10})', page_text)
    if pan_match:
        header.pan_number = pan_match.group(1)
    
    gstin_match = re.search(r'GSTIN\s*/\s*UIN\s*:\s*(\S+)', page_text)
    if gstin_match:
        header.gstin = gstin_match.group(1)
    
    header.place_of_supply = _extract_field(
        page_text,
        r'Place\s+of\s+Supply\s*:\s*(\w+)'
    )
    
    header.irn = _extract_field(
        page_text,
        r'IRN\s*:\s*([a-f0-9]{64})'
    )
    
    header.hsn_sac = _extract_field(
        page_text,
        r'HSN\s*/\s*SAC\s*:\s*(.+?)(?:\n|$)'
    )
    
    return header


def parse_channel_summary(page_text: str) -> List[ChannelSummary]:
    """
    Parse Page 2 to extract channel-wise spot summary.
    
    Format:
      Channel No of Spots Net Cost
      REPUBLIC TV 140 7,61,996.28
    """
    summaries = []
    
    if not page_text:
        return summaries
    
    # Look for channel summary section
    # Pattern: Channel name (uppercase words) followed by number of spots and net cost
    lines = page_text.split('\n')
    in_summary = False
    
    for line in lines:
        if 'Channel No of Spots Net Cost' in line or 'Channel No of Spots' in line:
            in_summary = True
            continue
        
        if in_summary:
            # Stop at Terms & Conditions
            if 'Terms' in line or 'Conditions' in line or line.strip() == '':
                if summaries:  # Only break if we've found some data
                    break
                continue
            
            # Parse channel line: "REPUBLIC TV 140 7,61,996.28" or "REPUBLIC TV BHARAT 96 6,72,352.00"
            match = re.match(
                r'^([A-Z][A-Z\s&]+?)\s+(\d+)\s+([\d,]+\.?\d*)\s*$',
                line.strip()
            )
            if match:
                cs = ChannelSummary()
                cs.channel = match.group(1).strip()
                cs.no_of_spots = int(match.group(2))
                cs.net_cost = _parse_number(match.group(3))
                summaries.append(cs)
    
    return summaries


def parse_annexure1(pages_text: List[str]) -> List[AnnexureRecord]:
    """
    Parse Annexure-1 pages for consolidated spot summary.
    
    The actual layout per record is complex and spans multiple lines:
      Line A: dates_part1 (e.g., "21(6),22(6),23(6),24(6),26")
      Line B: PRODUCER_PART1 (e.g., "MATRIX PUBLICITIES AND MEDIA INDIA PVT")
      Line C: CHANNEL PROGRAM dates_part2 SPOT_DUR RATE NO_SPOTS NET_COST  <-- main line
      Line D: PRODUCER_PART2 (e.g., "LIMITED")
      Line E: dates_part3 (e.g., "(5),31(5)")
    
    Some records may have fewer lines (dates may fit on one line, etc.)
    The KEY identifier of a main data line is: starts with a known channel name AND 
    ends with numeric fields (spot_dur rate spots cost).
    """
    records = []
    
    full_text = '\n'.join(pages_text)
    if not full_text:
        return records
    
    lines = full_text.split('\n')
    
    # Known channels
    known_channels = [
        'REPUBLIC TV BHARAT', 'REPUBLIC TV', 'ABP NEWS', 'ABP MAJHA',
        'AAJ TAK', 'AAJ TAK HD', 'NEWS18 INDIA', 'NEWS 18 INDIA',
        'NEWS18 KANNADA', 'NEWS18 KERALA', 'NEWS18 TAMIL NADU',
        'INDIA TODAY', 'GOOD NEWS TODAY', 'NEWS18 RAJASTHAN',
        'NEWS18 UP UTTARAKHAND', 'NEWS18 BIHAR JHARKHAND',
        'CNBC AWAAZ', 'CNBC TV18', 'CNN NEWS18', 'NEWS18 ASSAM',
        'NEWS18 BANGLA', 'NEWS18 GUJARATI', 'NEWS18 LOKMAT',
        'COLORS KANNADA', 'COLORS MARATHI', 'COLORS TAMIL',
        'TIMES NOW', 'TIMES NOW NAVBHARAT', 'ET NOW', 'MIRROR NOW',
        'ZOOM', 'MOVIES NOW', 'MN+', 'ROMEDY NOW',
        'STAR PLUS', 'STAR GOLD', 'STAR BHARAT',
        'SONY', 'SAB', 'ZEE TV', 'ZEE NEWS', 'WION',
        'INDIA TV', 'TV9 BHARATVARSH', 'R BHARAT',
        'NDTV INDIA', 'NDTV 24X7', 'NDTV PROFIT'
    ]
    known_channels.sort(key=len, reverse=True)
    
    def is_skip_line(line):
        """Check if this line is a header/page marker to skip."""
        if not line:
            return True
        if 'Annexure' in line and '-' in line:
            return True
        if 'Channel' in line and 'Program' in line:
            return True
        if 'Page ' in line and ' of ' in line:
            return True
        if 'Invoice Number' in line:
            return True
        if 'TAX INVOICE' in line:
            return True
        if line.startswith('Duration') or line.startswith('Per 10'):
            return True
        return False
    
    def is_dates_fragment(line):
        """Check if a line contains date(spots) fragments like '21(6),22(6)' or '(5),31(5)'."""
        return bool(re.search(r'\d{1,2}\(\d+\)', line)) or bool(re.match(r'^\(\d+\)', line))
    
    def is_producer_fragment(line):
        """Check if a line looks like a producer name fragment (all uppercase text, no numbers pattern)."""
        if not line:
            return False
        # Producer fragments are like "MATRIX PUBLICITIES AND MEDIA INDIA PVT" or "LIMITED"
        return bool(re.match(r'^[A-Z][A-Z\s&.]+$', line)) and not any(line.startswith(ch) for ch in known_channels)
    
    def find_channel(line):
        """Find a known channel name at the start of a line."""
        for ch in known_channels:
            if line.startswith(ch):
                return ch
        return None
    
    # First pass: identify main data lines (lines with channel name + trailing numbers)
    # Pattern for trailing numbers: spot_dur rate no_spots net_cost
    trailing_nums = re.compile(r'(\d+)\s+([\d,]+\.\d+)\s+(\d+)\s+([\d,]+\.\d+)\s*$')
    
    main_line_indices = []
    for idx, line in enumerate(lines):
        line_s = line.strip()
        if is_skip_line(line_s):
            continue
        ch = find_channel(line_s)
        if ch and trailing_nums.search(line_s):
            main_line_indices.append(idx)
    
    # For each main line, we need to figure out which context lines belong to it.
    # Structure per record:
    #   [dates_above]      - fresh date lines (start with digit) = belong to THIS record
    #   [producer_above]   - producer fragment = belong to THIS record  
    #   MAIN LINE          - channel + program + dates_inline + numbers
    #   [producer_below]   - producer continuation (e.g. "LIMITED") = belong to THIS record
    #   [dates_below]      - date continuation starting with "(" = belong to THIS record
    #
    # Between two main lines, the pattern is:
    #   main_line_A
    #   producer_continuation_A  (e.g., "LIMITED")
    #   dates_continuation_A     (e.g., "(5),31(5)" - starts with parenthesis)
    #   dates_fresh_B            (e.g., "21(3),22(3)..." - starts with digit)
    #   producer_B               (e.g., "MATRIX PUBLICITIES...")
    #   main_line_B
    
    # Classify all non-skip, non-main lines
    line_owners = {}  # idx -> main_line_index it belongs to
    
    for mi, main_idx in enumerate(main_line_indices):
        # Lines BELOW this main line until next main line
        next_main = main_line_indices[mi + 1] if mi + 1 < len(main_line_indices) else len(lines)
        
        between_lines = []
        for k in range(main_idx + 1, next_main):
            ctx = lines[k].strip()
            if is_skip_line(ctx):
                continue
            between_lines.append((k, ctx))
        
        # Split between_lines: first part belongs to current record, rest to next
        # "Below" context for current: producer continuation + date continuation (starts with "(")
        # Once we see a fresh dates line (starts with digit + "(") or a new producer, 
        # the rest belongs to the next record
        
        below_end = 0  # index in between_lines where current record's context ends
        for bi, (k, ctx) in enumerate(between_lines):
            if is_producer_fragment(ctx) and bi == 0:
                # First line after main is producer continuation
                below_end = bi + 1
            elif re.match(r'^\(\d+\)', ctx):
                # Parenthesis-starting date continuation belongs to current
                below_end = bi + 1
            elif is_producer_fragment(ctx) and bi > 0 and below_end == bi:
                # Producer fragment right after date continuation
                below_end = bi + 1
            else:
                break
        
        # Assign ownership
        for bi, (k, ctx) in enumerate(between_lines):
            if bi < below_end:
                line_owners[k] = main_idx
            else:
                # These belong to the next main line
                if mi + 1 < len(main_line_indices):
                    line_owners[k] = main_line_indices[mi + 1]
    
    # Also handle lines ABOVE the first main line
    if main_line_indices:
        first_main = main_line_indices[0]
        for k in range(0, first_main):
            ctx = lines[k].strip()
            if not is_skip_line(ctx):
                line_owners[k] = first_main
    
    # Now build records
    for mi, main_idx in enumerate(main_line_indices):
        line_s = lines[main_idx].strip()
        
        record = AnnexureRecord()
        
        # Parse channel
        ch = find_channel(line_s)
        record.channel = ch
        remainder = line_s[len(ch):].strip()
        
        # Parse program
        prog_match = re.match(
            r'((?:RODP|FIXED|ROS|FPC|SPOT BUY)\s*(?:\([^)]*\))?)\s*(.*)',
            remainder
        )
        if prog_match:
            record.program = prog_match.group(1).strip()
            remainder = prog_match.group(2).strip()
        
        # Parse trailing numbers from the main line
        nums_match = trailing_nums.search(remainder)
        if nums_match:
            record.spot_duration = int(nums_match.group(1))
            record.net_spot_rate_per_10sec = _parse_number(nums_match.group(2))
            record.no_of_spots = int(nums_match.group(3))
            record.net_cost = _parse_number(nums_match.group(4))
            
            # What's between program and trailing numbers could be dates
            middle_part = remainder[:nums_match.start()].strip()
        else:
            middle_part = remainder
        
        # Collect owned context lines
        all_dates_parts = []
        all_producer_parts = []
        
        # Gather all lines owned by this main line
        owned_lines_above = []
        owned_lines_below = []
        for k, owner in sorted(line_owners.items()):
            if owner == main_idx:
                ctx = lines[k].strip()
                if k < main_idx:
                    owned_lines_above.append(ctx)
                else:
                    owned_lines_below.append(ctx)
        
        # Classify owned lines
        for ctx in owned_lines_above + owned_lines_below:
            if is_dates_fragment(ctx):
                all_dates_parts.append(ctx)
            elif is_producer_fragment(ctx):
                all_producer_parts.append(ctx)
        
        # Middle part from main line
        if middle_part:
            if is_dates_fragment(middle_part):
                all_dates_parts.append(middle_part)
            elif is_producer_fragment(middle_part):
                all_producer_parts.append(middle_part)
            else:
                all_dates_parts.append(middle_part)
        
        # Combine dates
        combined_dates = ','.join(all_dates_parts)
        combined_dates = re.sub(r',+', ',', combined_dates).strip(',')
        date_matches = re.findall(r'\d{1,2}\(\d+\)', combined_dates)
        record.dates_with_spots = ','.join(date_matches)
        
        # Combine producer
        record.producer = ' '.join(all_producer_parts)
        record.producer = re.sub(r'\s+', ' ', record.producer).strip()
        
        records.append(record)
    
    return records


def parse_spot_details(pages_text: List[str], invoice_number: str = "") -> Tuple[List[SpotDetail], int, int, float]:
    """
    Parse Annexure-2 pages for individual spot detail records.
    
    Each spot record spans 2 lines:
      Line 1: SUPP_BILL MON_REPORT PRODUCER(part1) CHANNEL PROGRAM DAY TIME DATE DUR RATE COST BILL_NO
      Line 2: PRODUCER(part2) — continuation of producer name (e.g., "MEDIA INDIA PVT LIMITED")
    
    Header columns:
      SUPP BILL NO | MON REPORT NO | PRODUCER | CHANNEL | PROGRAM | DAY | START TIME | SPOT DATE | SPOT DUR | NET SPOT RATE PER 10 SEC | NET COST | MBA FULL BILL NO
    
    Returns: (spot_details, total_spots, total_duration, total_net_cost)
    """
    spots = []
    total_spots = 0
    total_duration = 0
    total_net_cost = 0.0
    
    # Combine all spot detail pages
    full_text = '\n'.join(pages_text)
    
    if not full_text:
        return spots, total_spots, total_duration, total_net_cost
    
    lines = full_text.split('\n')
    
    # Known channels for matching — comprehensive list across all invoices
    known_channels = [
        # Republic TV group
        'REPUBLIC TV BHARAT', 'REPUBLIC TV',
        # ABP group
        'ABP NEWS', 'ABP MAJHA', 'ABP ANANDA', 'ABP LIVE',
        # Aaj Tak / India Today group
        'AAJ TAK HD', 'AAJ TAK', 'INDIA TODAY', 'GOOD NEWS TODAY',
        'INDIA TODAY NE', 'INDIA TODAY BANGLA',
        # News18 group (all regional)
        'NEWS18 UP UTTARAKHAND', 'NEWS18 BIHAR JHARKHAND',
        'NEWS18 TAMIL NADU', 'NEWS18 RAJASTHAN',
        'NEWS18 MADHYA PRADESH', 'NEWS18 CHHATTISGARH',
        'NEWS18 KANNADA', 'NEWS18 KERALA', 'NEWS18 ASSAM',
        'NEWS18 BANGLA', 'NEWS18 GUJARATI', 'NEWS18 LOKMAT',
        'NEWS18 ODIA', 'NEWS18 PUNJAB HARYANA HIMACHAL',
        'NEWS18 INDIA', 'NEWS 18 INDIA',
        'CNN NEWS18', 'CNBC TV18', 'CNBC AWAAZ',
        # Times Group
        'TIMES NOW NAVBHARAT', 'TIMES NOW', 'ET NOW', 'MIRROR NOW',
        # Colors group
        'COLORS KANNADA CINEMA', 'COLORS KANNADA', 'COLORS MARATHI',
        'COLORS TAMIL', 'COLORS BANGLA', 'COLORS ODIA',
        'COLORS GUJARATI', 'COLORS CINEPLEX',
        # Star group
        'STAR PLUS', 'STAR GOLD', 'STAR BHARAT', 'STAR VIJAY',
        'STAR SPORTS', 'STAR MAA',
        # Sony group
        'SONY LIV', 'SONY SAB', 'SONY TEN', 'SONY SET',
        'SONY', 'SAB',
        # Zee group
        'ZEE NEWS', 'ZEE TV', 'ZEE TAMIL', 'ZEE KANNADA',
        'ZEE TELUGU', 'ZEE MARATHI', 'ZEE BANGLA',
        'ZEE CINEMA', 'ZEE ANMOL', 'ZEE BISKOPE',
        # NDTV group
        'NDTV INDIA', 'NDTV 24X7', 'NDTV PROFIT',
        # Other news channels
        'WION', 'INDIA TV', 'TV9 BHARATVARSH', 'TV9 TELUGU',
        'TV9 KANNADA', 'TV9 MARATHI', 'TV9 GUJARATI',
        'R BHARAT', 'R BANGLA',
        # Entertainment / Infotainment
        'ZOOM', 'MOVIES NOW', 'MN+', 'ROMEDY NOW',
        'ZEE CAFE', 'WB', '&TV', '&PICTURES',
        'DD NEWS', 'DD NATIONAL',
        # Regional / Other
        'MAA TV HD', 'STAR MAA HD', 'STAR MAA', 'MAA TV',
        'NTV', 'ETV TELUGU', 'ETV ANDHRA PRADESH',
        'GEMINI TV', 'GEMINI NEWS', 'GEMINI MOVIES',
        'RACHANA TV', 'SUVARNA TV', 'SUVARNA PLUS',
        'SUN TV', 'SUN NEWS', 'SUN LIFE', 'KTV',
        'VIJAY TV', 'VIJAY SUPER', 'VIJAY COMEDY',
        'ASIANET', 'ASIANET NEWS', 'ASIANET MOVIES',
        'MANORAMA NEWS', 'KAIRALI TV', 'FLOWERS TV',
        'MAZHAVIL MANORAMA',
        'ETV BANGLA', 'ETV PLUS', 'ETV2',
        'KRISHNA MUKUNDA MURARI',  # show that became channel label in PDF
    ]
    known_channels.sort(key=len, reverse=True)
    
    # Days of the week
    days = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
    days_pat = '|'.join(days)
    
    # Regex for a spot detail line — handles ALL SUPP BILL NO formats:
    #   TK2404159       (2 uppercase letters + digits)       — most common
    #   2429500188      (pure digits, 10 digits)             — ABP invoices
    #   KA134WB2420050  (mixed alphanumeric)                 — News18/special invoices
    #   N/712/24-25     (with slashes and hyphens)           — Rachana TV invoices
    #   O03300264737    (O + digits)                         — Star India invoices
    # MON REPORT NO formats:
    #   4562229953      (7-10 digit number)
    #   TC              (short code for special spot buys)
    
    spot_line_pattern = re.compile(
        r'^([A-Z0-9][A-Z0-9/\-]+)\s+'   # SUPP BILL NO: alphanumeric with optional /- (e.g. N/712/24-25)
        r'(\d{7,10}|TC|\w{2})\s+'       # MON REPORT NO: 7-10 digits OR short code like TC
        r'(.+?)\s+'                     # PRODUCER (partial) + CHANNEL + PROGRAM  
        r'(' + days_pat + r')\s+'       # DAY
        r'(\d{1,2}:\d{2})\s+'          # START TIME
        r'(\d{1,2}-\w{3}-\d{4})\s+'    # SPOT DATE
        r'(\d+)\s+'                     # SPOT DUR
        r'([\d,]+\.?\d*)\s+'            # NET SPOT RATE
        r'([\d,]+\.?\d*)\s+'            # NET COST
        r'(\S+)\s*$'                    # MBA FULL BILL NO
    )
    
    producer_continuation = ""
    
    for idx, line in enumerate(lines):
        line = line.strip()
        
        # Skip headers and page markers
        if not line:
            continue
        if 'Page ' in line and ' of ' in line:
            continue
        if 'Invoice Number' in line and ':' in line:
            continue
        if 'TAX INVOICE' in line:
            continue
        if 'SUPP BILL NO' in line:
            continue
        if 'Annexure' in line:
            continue
        if line.startswith('NO') and 'PER 10 SEC' in line:
            continue
        
        # Check for total line at the end
        total_match = re.match(r'Total\s*:\s*(\d+)\s+(\d+)\s+([\d.]+)', line)
        if total_match:
            total_spots = int(total_match.group(1))
            total_duration = int(total_match.group(2))
            total_net_cost = _parse_number(total_match.group(3))
            continue
        
        # Try to match a spot detail line
        match = spot_line_pattern.match(line)
        if match:
            spot = SpotDetail()
            spot.supp_bill_no = match.group(1)
            spot.mon_report_no = match.group(2)
            
            # Parse the middle section: PRODUCER(part1) + CHANNEL + PROGRAM
            middle = match.group(3).strip()
            
            # Find channel in the middle section
            # First try exact substring match
            channel_found = None
            channel_pos = -1
            for ch in known_channels:
                pos = middle.find(ch)
                if pos != -1:
                    channel_found = ch
                    channel_pos = pos
                    break
            
            # If not found, try to find channel that appears merged with producer (no space)
            # e.g. "RACHANA TELEVISION PVT LTDNTV" -> "NTV" is merged at end
            if channel_found is None:
                for ch in known_channels:
                    # Look for channel name possibly merged (no space) with preceding text
                    # Search case-insensitively in the middle
                    idx = middle.upper().find(ch)
                    if idx != -1:
                        channel_found = ch
                        channel_pos = idx
                        break
            
            if channel_found:
                producer_part1 = middle[:channel_pos].strip()
                after_channel = middle[channel_pos + len(channel_found):].strip()
                spot.channel = channel_found
                spot.program = after_channel
                
                # Extract time band from program name
                time_band_match = re.search(r'\((\d{2}\.\d{2}\s*-\s*\d{2}\.\d{2})\)', spot.program)
                if time_band_match:
                    spot.time_band = time_band_match.group(1)
                elif spot.program == 'FIXED':
                    spot.time_band = 'FIXED'
            else:
                producer_part1 = middle
                spot.channel = ""
                spot.program = ""
            
            spot.day = match.group(4)
            spot.start_time = match.group(5)
            spot.spot_date = match.group(6)
            spot.spot_duration = int(match.group(7))
            spot.net_spot_rate_per_10sec = _parse_number(match.group(8))
            spot.net_cost = _parse_number(match.group(9))
            spot.mba_full_bill_no = match.group(10)
            spot.invoice_number = invoice_number
            
            # Producer name is split across up to 3 parts:
            #   Part A: Line BEFORE spot line (e.g., "MATRIX PUBLICITIES AND MEDIA INDIA PVT")
            #   Part B: producer_part1 - text before channel on the spot line (often empty)
            #   Part C: Line AFTER spot line (e.g., "LIMITED")
            
            def is_skip(txt):
                if not txt: return True
                if spot_line_pattern.match(txt): return True
                if txt.startswith('Total'): return True
                if 'Page ' in txt and ' of ' in txt: return True
                if 'Invoice Number' in txt: return True
                if 'TAX INVOICE' in txt: return True
                if 'SUPP BILL NO' in txt: return True
                if 'Annexure' in txt: return True
                if txt.startswith('NO') and 'PER 10 SEC' in txt: return True
                return False
            
            # Part A: check previous line for producer prefix
            producer_prefix = ""
            if idx > 0:
                prev_line = lines[idx - 1].strip()
                if not is_skip(prev_line):
                    # Check it's not a known data line by checking it has no day+time pattern
                    has_date = bool(re.search(r'\d{1,2}-\w{3}-\d{4}', prev_line))
                    has_time = bool(re.search(r'\d{1,2}:\d{2}', prev_line))
                    if not has_date and not has_time:
                        producer_prefix = prev_line
            
            # Part C: check next line for producer suffix
            producer_suffix = ""
            if idx + 1 < len(lines):
                next_line = lines[idx + 1].strip()
                if not is_skip(next_line):
                    has_date = bool(re.search(r'\d{1,2}-\w{3}-\d{4}', next_line))
                    has_time = bool(re.search(r'\d{1,2}:\d{2}', next_line))
                    if not has_date and not has_time:
                        producer_suffix = next_line
            
            # Combine all parts
            parts = [p for p in [producer_prefix, producer_part1, producer_suffix] if p]
            spot.producer = ' '.join(parts)
            
            # Clean producer name
            spot.producer = re.sub(r'\s+', ' ', spot.producer).strip()
            
            spots.append(spot)
    
    return spots, total_spots, total_duration, total_net_cost


def find_annexure_pages(pdf) -> Tuple[List[int], List[int]]:
    """
    Identify which pages contain Annexure-1 and Annexure-2 data.
    
    Returns: (annexure1_page_indices, annexure2_page_indices)
    """
    annexure1_pages = []
    annexure2_pages = []
    
    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if not text:
            continue
        
        first_500 = text[:500]
        
        if 'Annexure-1' in first_500 or ('Channel' in first_500 and 'Program' in first_500 and 'Dates' in first_500):
            annexure1_pages.append(i)
        elif 'Annexure-2' in first_500 or 'SUPP BILL NO' in first_500:
            annexure2_pages.append(i)
    
    return annexure1_pages, annexure2_pages


def parse_invoice(pdf_path: str) -> ParsedInvoice:
    """
    Main function to parse a complete agency invoice PDF.
    
    Args:
        pdf_path: Path to the PDF file
    
    Returns:
        ParsedInvoice with all extracted data
    """
    result = ParsedInvoice()
    result.source_file = pdf_path
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            num_pages = len(pdf.pages)
            logger.info(f"Parsing {pdf_path} ({num_pages} pages)")
            
            if num_pages < 1:
                result.errors.append("PDF has no pages")
                return result
            
            # === Page 1: Header ===
            page1_text = pdf.pages[0].extract_text()
            if page1_text:
                result.header = parse_header(page1_text)
                logger.info(f"  Invoice: {result.header.invoice_number}, Date: {result.header.invoice_date}")
            else:
                result.errors.append("Could not extract text from Page 1")
            
            # === Page 2: Channel Summary ===
            if num_pages >= 2:
                page2_text = pdf.pages[1].extract_text()
                if page2_text:
                    result.channel_summaries = parse_channel_summary(page2_text)
                    logger.info(f"  Channels: {len(result.channel_summaries)}")
            
            # === Find Annexure pages ===
            annexure1_pages, annexure2_pages = find_annexure_pages(pdf)
            
            # === Annexure-1: Consolidated Summary ===
            if annexure1_pages:
                annexure1_texts = []
                for pi in annexure1_pages:
                    text = pdf.pages[pi].extract_text()
                    if text:
                        annexure1_texts.append(text)
                result.annexure_records = parse_annexure1(annexure1_texts)
                logger.info(f"  Annexure-1 records: {len(result.annexure_records)}")
            
            # === Annexure-2: Spot Details ===
            if annexure2_pages:
                spot_texts = []
                for pi in annexure2_pages:
                    text = pdf.pages[pi].extract_text()
                    if text:
                        spot_texts.append(text)
                
                spots, total_s, total_d, total_c = parse_spot_details(
                    spot_texts,
                    invoice_number=result.header.invoice_number
                )
                result.spot_details = spots
                result.total_spots = total_s
                result.total_duration = total_d
                result.total_net_cost = total_c
                logger.info(f"  Spots: {len(spots)}, Total from PDF: {total_s}")
            else:
                # If no explicit annexure-2 pages found, try all pages after page 2
                # (some PDFs may not have "Annexure-2" label)
                if num_pages > 3:
                    spot_texts = []
                    for pi in range(3, num_pages):
                        text = pdf.pages[pi].extract_text()
                        if text and 'SUPP BILL NO' in text[:500]:
                            spot_texts.append(text)
                        elif text and any(re.match(r'^[A-Z]{2}\d+', line.strip()) for line in text.split('\n') if line.strip()):
                            spot_texts.append(text)
                    
                    if spot_texts:
                        spots, total_s, total_d, total_c = parse_spot_details(
                            spot_texts,
                            invoice_number=result.header.invoice_number
                        )
                        result.spot_details = spots
                        result.total_spots = total_s
                        result.total_duration = total_d
                        result.total_net_cost = total_c
                        logger.info(f"  Spots (fallback): {len(spots)}")
            
            # === Validation ===
            _validate_parsed_data(result)
    
    except Exception as e:
        error_msg = f"Error parsing {pdf_path}: {str(e)}"
        logger.error(error_msg)
        result.errors.append(error_msg)
    
    return result


def _validate_parsed_data(result: ParsedInvoice):
    """Validate parsed data for consistency."""
    # Check if spot count matches
    if result.total_spots > 0 and len(result.spot_details) != result.total_spots:
        result.errors.append(
            f"Spot count mismatch: PDF total={result.total_spots}, parsed={len(result.spot_details)}"
        )
    
    # Check if net cost matches (with tolerance for rounding)
    if result.total_net_cost > 0 and result.spot_details:
        parsed_cost = sum(s.net_cost for s in result.spot_details)
        diff = abs(parsed_cost - result.total_net_cost)
        if diff > 1.0:  # Allow ₹1 tolerance for rounding
            result.errors.append(
                f"Net cost mismatch: PDF total={result.total_net_cost:.2f}, sum of spots={parsed_cost:.2f}, diff={diff:.2f}"
            )
    
    # Check required header fields
    required_fields = ['invoice_number', 'invoice_date', 'brand_name']
    for field_name in required_fields:
        value = getattr(result.header, field_name, '')
        if not value:
            result.errors.append(f"Missing required field: {field_name}")


if __name__ == "__main__":
    import sys
    import os
    
    # Test with a sample invoice
    test_dir = r"C:\Users\asus\Downloads\Sustenance_Redmi_Note_13_May24\Sustenance_Redmi_Note_13_May24\Agency Invoices"
    
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
    else:
        # Use a smaller invoice for quick testing
        test_file = os.path.join(test_dir, "GB2405109_TV_10008571.pdf")
    
    print(f"\n{'='*80}")
    print(f"Testing parser on: {os.path.basename(test_file)}")
    print(f"{'='*80}")
    
    result = parse_invoice(test_file)
    
    print(f"\n--- HEADER ---")
    print(f"  Agency: {result.header.agency_name} ({result.header.agency_branch})")
    print(f"  Advertiser: {result.header.advertiser_name}")
    print(f"  Invoice #: {result.header.invoice_number}")
    print(f"  Invoice Date: {result.header.invoice_date}")
    print(f"  Activity Month: {result.header.activity_month}")
    print(f"  Estimate #: {result.header.estimate_number}")
    print(f"  Estimate Period: {result.header.estimate_period}")
    print(f"  PO Number: {result.header.po_number}")
    print(f"  Brand: {result.header.brand_name}")
    print(f"  Campaign: {result.header.campaign_name}")
    print(f"  Net Cost: {result.header.net_cost}")
    print(f"  Total Payable: {result.header.total_amount_payable}")
    
    print(f"\n--- CHANNEL SUMMARY ({len(result.channel_summaries)} channels) ---")
    for cs in result.channel_summaries:
        print(f"  {cs.channel}: {cs.no_of_spots} spots, ₹{cs.net_cost:,.2f}")
    
    print(f"\n--- ANNEXURE-1 ({len(result.annexure_records)} records) ---")
    for ar in result.annexure_records[:5]:
        print(f"  {ar.channel} | {ar.program} | {ar.no_of_spots} spots | ₹{ar.net_cost:,.2f}")
    if len(result.annexure_records) > 5:
        print(f"  ... and {len(result.annexure_records)-5} more")
    
    print(f"\n--- SPOT DETAILS ({len(result.spot_details)} spots) ---")
    for sd in result.spot_details[:5]:
        print(f"  {sd.spot_date} | {sd.channel} | {sd.program} | {sd.day} | {sd.start_time} | Dur:{sd.spot_duration} | Rate:{sd.net_spot_rate_per_10sec} | Cost:{sd.net_cost}")
    if len(result.spot_details) > 5:
        print(f"  ... and {len(result.spot_details)-5} more")
    
    print(f"\n--- TOTALS ---")
    print(f"  Total Spots (PDF): {result.total_spots}")
    print(f"  Total Duration: {result.total_duration}")
    print(f"  Total Net Cost (PDF): ₹{result.total_net_cost:,.2f}")
    print(f"  Parsed Spots: {len(result.spot_details)}")
    if result.spot_details:
        print(f"  Parsed Net Cost Sum: ₹{sum(s.net_cost for s in result.spot_details):,.2f}")
    
    if result.errors:
        print(f"\n--- ERRORS ({len(result.errors)}) ---")
        for err in result.errors:
            print(f"  ⚠️ {err}")
    else:
        print(f"\n✅ No errors — all data validated successfully!")
