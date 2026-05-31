import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='newsfirst')
    h = result.header

    h.broadcaster_name = "OLECOM MEDIA PRIVATE LIMITED"
    h.advertiser_name = _extract(full_text, r'Advertiser\s*Name\s*:\s*(.+?)(?:\n|Agency)', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIM")
    h.agency_name = _extract(full_text, r'Agency\s*Name\s*:\s*(.+?)(?:\n|Invoice)', default="GROUP M MEDIA INDIA PRIVATE LIMITED BLR")
    h.channel_name = "NEWSFIRST KANNADA"
    h.invoice_number = _extract(full_text, r'Invoice\s*No\.\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Invoice\s*Date\s*:\s*(\S+)')
    h.billing_period = _extract(full_text, r'Period\s*from\s*:\s*(.+?)(?:\n|$)')
    h.po_number = _extract(full_text, r'Client\s*Ref\s*No\.\s*:\s*(\S+)')
    h.brand = _extract(full_text, r'Brand\s*Name\s*:\s*(\w+)', default="XIAOMI")

    # Get rate table from Page 1
    rate_table = {}
    rate_pattern = re.compile(
        r'(\d+)\s+'                                  # Sl
        r'(.+?)\s+'                                  # Description
        r'(BS|PD)\s+'                                # Type
        r'([\d,]+\.\d{2})\s+'                        # Rate/10Sec
        r'(\d+)\s+'                                  # Duration
        r'(\d+)\s+'                                  # No. of spots
        r'(\d+)\s+'                                  # Total Duration
        r'([\d,]+)'                                  # Amount
    )

    for page_text in pages_text[:2]:
        for line in page_text.split('\n'):
            rm = rate_pattern.search(line.strip())
            if rm:
                caption_key = _clean(rm.group(2))
                rate_table[caption_key] = _parse_num(rm.group(4))

    # Parse telecast certificate spots
    in_telecast = False
    spot_pattern = re.compile(
        r'^(\d+)\s+'                                  # SrNo
        r'(\S+.*?)\s+'                               # Caption (starts with XIAOMI)
        r'(\d{1,2}-\w{3}-\d{4})\s+'                  # Date
        r'(\d{1,2}:\d{2}:\d{2})\s+'                  # Time
        r'(.+?)\s+'                                  # Programme
        r'(\d+)\s*$'                                 # Duration
    )

    for page_text in pages_text:
        if 'TELECAST CERTIFICATE' in page_text:
            in_telecast = True
        if not in_telecast:
            continue

        lines = page_text.split('\n')
        idx = 0
        while idx < len(lines):
            line = lines[idx].strip()
            idx += 1
            if not line:
                continue

            m = spot_pattern.search(line)
            if m:
                spot = BroadcasterSpot()
                spot_copy_part = _clean(m.group(2))
                spot.date = m.group(3)
                spot.day = _get_day_from_date(spot.date)
                spot.air_time = m.group(4)
                spot.program = _clean(m.group(5))
                spot.tp = spot.program
                spot.duration = int(m.group(6))
                spot.brand = h.brand

                # Check line below for wrapped caption
                wrapped_part = ""
                if idx < len(lines) and lines[idx].strip() in ['SEC', 'SEC.']:
                    wrapped_part = " " + lines[idx].strip()
                    idx += 1

                spot.spot_copy = spot_copy_part + wrapped_part

                # Look up rate
                matched_rate = 0.0
                for cap_key, rate_val in rate_table.items():
                    if cap_key in spot.spot_copy or spot.spot_copy in cap_key:
                        matched_rate = rate_val
                        break
                if not matched_rate:
                    matched_rate = 350.0 # Default fallback rate

                spot.rate = matched_rate
                spot.amount = matched_rate * (spot.duration / 10)
                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
