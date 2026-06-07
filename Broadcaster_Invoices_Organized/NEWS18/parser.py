import re
from typing import List
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='news18')
    h = result.header

    # Broadcaster name from first line
    bc_m = re.search(r'^([A-Z][\w\s]+(?:Private|Pvt)\s*(?:Limited|Ltd)\.?)', full_text, re.MULTILINE | re.IGNORECASE)
    h.broadcaster_name = _clean(bc_m.group(1)) if bc_m else ""

    h.advertiser_name = _extract(full_text, r'Client\s*:?\s*\n?\s*([\w\s]+(?:PVT|PRIVATE)\s*(?:LTD|LIMITED))', default="XIAOMI TECHNOLOGY INDIA PVT LTD")
    h.agency_name = _extract(full_text, r'(GROUP\s*M?\s*MEDIA\s*INDIA\s*(?:PVT|PRIVATE)?\.?\s*(?:LTD|LIMITED)\.?)', default="GROUPM MEDIA INDIA PVT. LTD.")

    # Channel
    ch_m = re.search(r'Channel\s*Ref\.?\s*([\w\s]+?)(?:\d{5,}|\n)', full_text)
    if ch_m:
        h.channel_name = _clean(ch_m.group(1))
    if not h.channel_name:
        h.channel_name = _extract(full_text, r'Channel\s*:?\s*([\w\s]+?)(?:\n|$)')

    h.invoice_number = _extract(full_text, r'(?:GST\s*)?Inv\.?\s*No\.?\s*[.:]\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Date\s*[.:]\s*(\d{1,2}[\-/]\w{3}[\-/]\d{4})')
    h.po_number = _extract(full_text, r'(?:R\.?O\.?\s*No|R\.?O\.?\s*No\.?)\s*[.:]\s*(?:\d+\s*[.:]\s*)?(\S+/\S+)')
    if not h.po_number:
        h.po_number = _extract(full_text, r'R\.?O\.?\s*(?:No|Number)\s*[.:]\s*(\S+)')
    h.brand = _extract(full_text, r'Product\s*[.:]\s*(\w+)', default="XIAOMI")

    # Billing Period — try explicit label first
    h.billing_period = _extract(full_text, r'(?:Billing\s*)?Period\s*[.:]\s*(.+?)(?:\n|$)')
    if not h.billing_period:
        # Derive from PO number (e.g., MAY2024/TVBRO/00446/00 → May-2024)
        po_month_m = re.search(r'([A-Z]{3})(\d{4})/\w+/', h.po_number)
        if po_month_m:
            h.billing_period = po_month_m.group(1).capitalize() + '-' + po_month_m.group(2)
    if not h.billing_period and h.invoice_date:
        # Derive from invoice date (e.g., 31-MAY-2024 → May-2024)
        dt_m = re.search(r'(\w{3})[\-/](\d{4})', h.invoice_date)
        if dt_m:
            h.billing_period = dt_m.group(1).capitalize() + '-' + dt_m.group(2)

    # Parse the BROADCAST INFORMATION table
    # Format: Program S.No. Date Day Time [Product_description] Rate Duration Amount
    spot_pattern = re.compile(
        r'^(.+?)\s+'                               # Program
        r'(\d{4,})\s+'                            # S.No.
        r'(\d{1,2}/\d{1,2})\s+'                  # Date
        r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+'       # Day
        r'(\d{1,2}:\d{2}:\d{2})\s+'              # Time
        r'(?:(.+?)\s+)?'                          # Optional Product description
        r'([\d,]+\.\d{2})\s+'                     # Rate
        r'(\d+)\s+'                               # Duration
        r'([\d,]+\.\d{2})$',                      # Amount
        re.IGNORECASE
    )

    for page_text in pages_text:
        lines = page_text.split('\n')
        for idx, line in enumerate(lines):
            ls = line.strip()
            m = spot_pattern.match(ls)
            if m:
                spot = BroadcasterSpot()
                spot.program = _clean(m.group(1))
                spot.date = m.group(3)
                spot.day = m.group(4)
                spot.air_time = m.group(5)
                
                # Reconstruct wrapped caption
                caption_parts = []
                # Check line above
                if idx > 0 and 'XIAOMI' in lines[idx-1].upper() and not re.search(r'\d{2}:\d{2}', lines[idx-1]):
                    caption_parts.append(lines[idx-1].strip())
                
                if m.group(6):
                    caption_parts.append(m.group(6))
                
                # Check line below
                if idx + 1 < len(lines) and not re.search(r'\d{2}:\d{2}', lines[idx+1]) and not any(k in lines[idx+1].upper() for k in ['AMOUNT', 'HSN/SAC', 'TOTAL']):
                    caption_parts.append(lines[idx+1].strip())
                    
                spot.spot_copy = _clean(" ".join(caption_parts))
                spot.rate = _parse_num(m.group(7))
                spot.duration = int(m.group(8))
                spot.amount = _parse_num(m.group(9))
                spot.brand = h.brand
                result.spots.append(spot)

    # If still no spots, try to extract the single line summary format
    if not result.spots:
        # Try: Program S.No Date Day Time Caption Rate Duration Amount (all on one wide line)
        for page_text in pages_text:
            # Single spot in BROADCAST INFORMATION section
            bcast_m = re.search(
                r'BROADCAST\s*INFORMATION\s*\n.*?\n'     # Section header
                r'(.+?)\s+(\d{4,})\s+'                   # Program, S.No.
                r'(\d{1,2}/\d{1,2})\s+'                  # Date
                r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+'       # Day
                r'(\d{1,2}:\d{2}:\d{2})\s+'              # Time
                r'(.+?)\s+'                               # Caption
                r'([\d,]+\.?\d*)\s+'                      # Rate
                r'(\d+)\s+'                               # Duration
                r'([\d,]+\.?\d*)',                        # Amount
                page_text, re.IGNORECASE | re.DOTALL
            )
            if bcast_m:
                spot = BroadcasterSpot()
                spot.program = _clean(bcast_m.group(1))
                spot.date = bcast_m.group(3)
                spot.day = bcast_m.group(4)
                spot.air_time = bcast_m.group(5)
                spot.spot_copy = _clean(bcast_m.group(6))
                spot.rate = _parse_num(bcast_m.group(7))
                spot.duration = int(bcast_m.group(8))
                spot.amount = _parse_num(bcast_m.group(9))
                spot.brand = h.brand
                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
