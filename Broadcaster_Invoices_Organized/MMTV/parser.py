import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='mmtv')
    h = result.header

    h.broadcaster_name = "MM TV Ltd."
    h.advertiser_name = _extract(full_text, r'Client\s*:\s*(.+?)(?:\n|\.)', default="Xiaomi Technology India Private Limited")
    h.agency_name = _extract(full_text, r'To\s*,\s*\n?\s*([\w\s]+(?:Pvt|Private|Pvt\.\s*Ltd|Ltd))', default="Group M Media India Pvt Limited")
    h.channel_name = "Mazhavil Manorama"
    h.invoice_number = _extract(full_text, r'Bill\s*No\.\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Bill\s*Date\s*:\s*(\S+)')
    h.billing_period = _extract(full_text, r'Period\s*:\s*(.+?)(?:\n|$)')
    h.po_number = _extract(full_text, r'R\.?O\.\s*#\s*:\s*(\S+)')
    h.brand = _extract(full_text, r'Product\s*:\s*(\w+)', default="Xiaomi")

    # Get rate table from Page 1
    rate_table = {}
    rate_pattern = re.compile(
        r'(\d+)\s+'                                  # Sl
        r'(\d{1,2}-\w{3}-\d{4})\s+'                  # Date
        r'\.\s*(.+?)\s+'                             # Particulars
        r'([\d,]+\.\d{2})\s+'                        # Rate
        r'(\d+)\s+'                                  # Duration
        r'([\d,]+\.\d{2})'                           # Amount
    )

    for page_text in pages_text[:3]:
        for line in page_text.split('\n'):
            rm = rate_pattern.search(line.strip())
            if rm:
                part_key = _clean(rm.group(3))
                caption_part = part_key
                if "Xiaomi - " in part_key:
                    caption_part = part_key.split("Xiaomi - ")[1].strip()
                rate_table[caption_part] = _parse_num(rm.group(4))

    # Parse telecast certificate spots
    in_telecast = False
    spot_pattern = re.compile(
        r'^(\d+)\s+'                                  # Sl
        r'(\d{1,2}-\w{3}-\d{4})\s+'                  # Date
        r'\.\s*-\s*'                                 # . -
        r'(.+?)\s+-\s+'                              # Program Name (before " - Brand")
        r'Xiaomi\s+-\s+'                             # Xiaomi -
        r'(.+?)\s+'                                  # Caption
        r'(\d{1,2}:\d{2}:\d{2})\s+'                  # TC In
        r'(\d{1,2}:\d{2}:\d{2})\s+'                  # TC Out
        r'(\d+)'                                     # Duration
    )

    for page_text in pages_text:
        if 'Telecast Certificate' in page_text:
            in_telecast = True
        if not in_telecast:
            continue

        lines = page_text.split('\n')
        for line in lines:
            m = spot_pattern.search(line.strip())
            if m:
                spot = BroadcasterSpot()
                spot.date = m.group(2)
                spot.day = _get_day_from_date(spot.date)
                spot.program = _clean(m.group(3))
                spot.tp = spot.program
                spot.spot_copy = _clean(m.group(4))
                spot.air_time = m.group(5)
                spot.duration = int(m.group(7))
                spot.brand = h.brand

                # Look up rate
                matched_rate = 0.0
                for cap_key, rate_val in rate_table.items():
                    if cap_key in spot.spot_copy or spot.spot_copy in cap_key:
                        matched_rate = rate_val
                        break
                if not matched_rate:
                    matched_rate = 748.0 # Default fallback rate

                spot.rate = matched_rate
                spot.amount = matched_rate * (spot.duration / 10)
                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
