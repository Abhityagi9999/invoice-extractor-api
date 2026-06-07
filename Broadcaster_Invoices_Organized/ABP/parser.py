import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='abp')
    h = result.header

    h.broadcaster_name = "ABP NETWORK PRIVATE LIMITED"
    h.advertiser_name = _extract(full_text, r'Advertiser\s*:?\s*\n?\s*(XIAOMI[A-Z\s]+(?:PVT|PRIVATE)\s*(?:LTD|LIMITED))', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")
    h.agency_name = _extract(full_text, r'(GROUP\s*M\s*MEDIA\s*INDIA\s*(?:PVT|PRIVATE)?\.?\s*(?:LTD|LIMITED))', default="GROUP M MEDIA INDIA PVT LTD")

    # Station / Channel
    h.channel_name = _extract(full_text, r'Station\s+(\w[\w\s]*?\w)(?:\n|$)')
    if not h.channel_name:
        h.channel_name = _extract(full_text, r'Property\s+.*?(ABP\s+\w+)')

    h.invoice_number = _extract(full_text, r'Invoice\s*No\s*[.:]\s*(\d+)')
    h.invoice_date = _extract(full_text, r'Invoice\s*Date\s*[.:]\s*(\S+)')
    h.billing_period = _extract(full_text, r'Activity\s*Period\s*[.:]\s*(.+?)(?:\n|$)')
    if not h.billing_period:
        h.billing_period = _extract(full_text, r'BC\s*Period\s*(.+?)(?:\n|INR|$)')
    h.po_number = _extract(full_text, r'RO\s*Number\s*#?\s*(\S+)')
    h.brand = _extract(full_text, r'Ad\s*Product\s*[.:]\s*(\w+)', default="XIAOMI")

    days_short = {'M': 'Mon', 'Tu': 'Tue', 'W': 'Wed', 'Th': 'Thu', 'F': 'Fri', 'Sa': 'Sat', 'Su': 'Sun'}

    # ABP Broadcast Certificate spot pattern
    # # Ch Day Air_Date Air_Time[space]Time_Range ... :Duration Ad-ID INRRate Type
    spot_pattern = re.compile(
        r'(\d+)\s+'                               # Spot #
        r'(\w+)\s+'                               # Channel short
        r'(M|Tu|W|Th|F|Sa|Su)\s+'                 # Day
        r'(\d{1,2}/\d{1,2}/\d{2,4})\s+'           # Air Date
        r'(\d{1,2}:\d{2}\s*(?:AM|PM)?)'           # Air Time
    )

    for page_text in pages_text:
        lines = page_text.split('\n')
        for line in lines:
            ls = line.strip()

            if not ls or ls.startswith('Spots:') or ls.startswith('Weeks:'):
                continue
            if 'Line Start Date' in ls or 'Page ' in ls:
                continue

            m = spot_pattern.match(ls)
            if m:
                spot = BroadcasterSpot()
                spot.date = m.group(4)
                spot.day = days_short.get(m.group(3), m.group(3))
                spot.air_time = m.group(5).strip()
                spot.program = ""  # ABP doesn't provide program names

                # Extract duration (:20 format)
                dur_m = re.search(r':(\d{2})\s', ls)
                spot.duration = int(dur_m.group(1)) if dur_m else 20

                # Extract caption/Ad-ID
                caption_m = re.search(r'(XIAOMI\s+REDMI\S*\s+\S+)', ls, re.IGNORECASE)
                spot.spot_copy = _clean(caption_m.group(1)) if caption_m else ""

                # Extract rate (INR7,540.00 format)
                rate_m = re.search(r'INR([\d,]+\.?\d*)', ls)
                spot.rate = _parse_num(rate_m.group(1)) if rate_m else 0.0

                # ABP rates are per 10 sec
                spot.amount = spot.rate * (spot.duration / 10) if spot.rate else 0.0
                spot.brand = h.brand

                # TP from time range (handle AM/PM/XM)
                tp_m = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|XM)\s*-\s*\d{1,2}:\d{2}\s*(?:AM|PM|XM))', ls, re.IGNORECASE)
                spot.tp = tp_m.group(1) if tp_m else ""

                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
