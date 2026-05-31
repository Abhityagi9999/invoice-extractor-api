import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='publictv')
    h = result.header

    h.broadcaster_name = "Writemen Media Private Limited"
    h.advertiser_name = _extract(full_text, r'Client\s*:\s*([\w\s]+(?:Pvt|Private|Pvt\.\s*Ltd|Ltd))', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")
    h.agency_name = _extract(full_text, r'Agency\s*:\s*([\w\s]+(?:Pvt|Private|Pvt\.\s*Ltd|Ltd))', default="GROUP M MEDIA INDIA PRIVATE LIMITED")
    h.channel_name = _extract(full_text, r'Channel\s*:\s*(\w[\w\s]+?)(?:\s*Bill|$)') or "Public TV"
    h.invoice_number = _extract(full_text, r'Invoice\s*No\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Invoice\s*Date\s*:\s*(\S+)')
    h.billing_period = _extract(full_text, r'Invoice\s*Period\s*:\s*([\d.]+ to [\d.]+)', default="")
    h.po_number = _extract(full_text, r'Ro\s*No\s*:\s*(\S+)')
    h.brand = _extract(full_text, r'Brand\s*:\s*(\w+)', default="XIAOMI")

    # Parse telecast certificate spots
    in_telecast = False
    for page_text in pages_text:
        if 'Telecast Certificate' in page_text:
            in_telecast = True
        if not in_telecast:
            continue

        lines = page_text.split('\n')
        for idx in range(1, len(lines)):
            line = lines[idx].strip()
            
            # Match Line from the end: Date ... Duration Time Rate Amount
            m = re.match(r'^(\d{1,2}-\w{3}-\d{4})\s+(.+?)\s+(\d+\.\d{2})\s+(\d{1,2}:\d{2}:\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$', line)

            if m:
                date_str, middle, duration, time, rate, amount = m.groups()
                
                prog, caption = middle, ""
                if h.brand in middle:
                    parts = middle.split(h.brand, 1)
                    prog = parts[0].strip()
                    caption = parts[1].strip()
                
                spot = BroadcasterSpot()
                spot.date = date_str
                spot.day = _get_day_from_date(spot.date)
                spot.program = _clean(prog)
                spot.tp = spot.program
                spot.brand = h.brand
                spot.duration = int(_parse_num(duration))
                spot.air_time = time
                spot.rate = _parse_num(rate)
                spot.amount = _parse_num(amount)
                spot.spot_copy = _clean(caption)
                
                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
