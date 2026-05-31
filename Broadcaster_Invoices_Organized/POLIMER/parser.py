import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='polimer')
    h = result.header

    h.broadcaster_name = "POLIMER MEDIA PVT. LTD."
    h.advertiser_name = _extract(full_text, r'Client\s*Name\s*:\s*([\w\s]+(?:Pvt|Private|Pvt\.\s*Ltd|Ltd))', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")
    h.agency_name = _extract(full_text, r'Agency\s*Name\s*:\s*([\w\s]+(?:Pvt|Private|Pvt\.\s*Ltd|Ltd)[\w\s\-]*)', default="GROUP M MEDIA INDIA PVT. LTD.")
    h.channel_name = "Polimer News"
    h.invoice_number = _extract(full_text, r'Invoice\s*No\.\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Invoice\s*Date\s*:\s*(\S+)')
    h.billing_period = _extract(full_text, r'Invoice\s*Period\s*:\s*(.+?)(?:\n|$)')
    h.po_number = _extract(full_text, r'R\.?O\.\s*Number\s*:\s*(\S+)')
    h.brand = _extract(full_text, r'Brand\s*:\s*(\w+)', default="XIAOMI")

    # Get rate table from Page 1
    # Example: 1 XIAOMI-REDMI13-SUSTENANCECREATIVE1- 20 SEC 52 1,400.00 20 2800.00 PD 145,600
    rate_table = {}
    rate_pattern = re.compile(
        r'(\d+)\s+'                          # Sr.No
        r'([\w\-]+\S+)\s+'                   # Caption (part 1)
        r'(\d+\s*SEC)\s+'                    # Duration text
        r'(\d+)\s+'                          # No. of spots
        r'([\d,]+\.\d{2})\s+'                # Rate/10sec
        r'(\d+)\s+'                          # Duration secs
        r'([\d,]+\.\d{2})\s+'                # Spot amount
        r'(PD|BS)\s+'                        # Type
        r'([\d,]+)'                          # Net cost
    )

    for line in (pages_text[0] if pages_text else "").split('\n'):
        rm = rate_pattern.search(line.strip())
        if rm:
            cap_key = _clean(rm.group(2))
            rate_table[cap_key] = {
                'rate': _parse_num(rm.group(5)),
                'duration': int(rm.group(6)),
                'amount': _parse_num(rm.group(7))
            }

    # Parse telecast certificate spots
    # Example: 1 XIAOMI-REDMI13-SUSTENANCECREATIVE1- 8 MANI SEIDIGAL PD 21-May-2024 08:26:33 20
    #          20 SEC
    in_telecast = False
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

            # Match spot line
            m = re.match(
                r'^(\d+)\s+'                                  # SrNo
                r'(\S+)\s+'                                  # Caption (starts with XIAOMI)
                r'(.+?)\s+'                                  # Programme Name
                r'(PD|BS)\s+'                                # Type
                r'(\d{1,2}-\w{3}-\d{4})\s+'                  # Date
                r'(\d{1,2}:\d{2}:\d{2})\s+'                  # Time
                r'(\d+)',                                    # Duration
                line
            )

            if m:
                spot = BroadcasterSpot()
                spot_copy_part = _clean(m.group(2))
                spot.program = _clean(m.group(3))
                spot.tp = spot.program
                spot.date = m.group(5)
                spot.day = _get_day_from_date(spot.date)
                spot.air_time = m.group(6)
                spot.duration = int(m.group(7))

                # Check line below for wrapped caption
                wrapped_part = ""
                if idx < len(lines) and re.match(r'^\d+\s*SEC$', lines[idx].strip(), re.IGNORECASE):
                    wrapped_part = " " + lines[idx].strip()
                    idx += 1 # Consume wrapped line

                spot.spot_copy = spot_copy_part + wrapped_part
                spot.brand = h.brand

                # Look up rate
                matched_rate = 0.0
                for cap_key, r_info in rate_table.items():
                    if cap_key in spot.spot_copy or spot.spot_copy in cap_key:
                        matched_rate = r_info['rate']
                        break
                if not matched_rate:
                    matched_rate = 1400.0 # Default fallback for Polimer

                spot.rate = matched_rate
                spot.amount = matched_rate * (spot.duration / 10)
                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
