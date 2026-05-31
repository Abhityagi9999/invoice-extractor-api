import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='enter10')
    h = result.header

    h.broadcaster_name = "Enter 10 Television Pvt. Ltd."
    h.advertiser_name = _extract(full_text, r'Client\s*:\s*([\w\s]+(?:Pvt|Private)\s*Ltd)', default="Xiaomi Technology India Pvt Ltd")
    h.agency_name = _extract(full_text, r'Agency\s*:\s*([\w\s]+(?:Pvt|Private)?\s*Ltd\.?)', default="Group M Media India Pvt. Ltd.")
    h.channel_name = _extract(full_text, r'Channel\s*:\s*(\w+)', default="Dangal")
    h.invoice_number = _extract(full_text, r'Invoice\s*No\.?\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Invoice\s*Date\s*:\s*(\S+)')
    h.billing_period = _extract(full_text, r'Period\s*From\s*:?\s*(.+?)\s*$', default="")
    if not h.billing_period:
        h.billing_period = _extract(full_text, r'Period\s*From\s*([\d.]+)\s*To\s*([\d.]+)')
    h.po_number = _extract(full_text, r'(?:RO\s*NO|Client\s*Ref\.?\s*No)\s*(?:&\s*Date)?\s*:\s*(\S+)')
    h.brand = _extract(full_text, r'Brand\s*:\s*(\w+)', default="XIAOMI")

    # Get rate summary from Page 1
    # Format: Sr.No Description SpotType Rate/10secs Dur SpotAmount No.ofSpots Amount
    rate_table = {}
    rate_pattern = re.compile(
        r'(\d+)\s+'                          # Sr.No
        r'([\w\-]+\S+)\s+'                   # Description (caption)
        r'(\w+)\s+'                          # Spot Type
        r'([\d,]+)\s+'                       # Rate/10secs
        r'(\d+)\s+'                          # Duration
        r'([\d,]+)\s+'                       # Spot Amount
        r'(\d+)\s+'                          # No. of Spots
        r'([\d,]+\.?\d*)'                    # Amount
    )

    for line in (pages_text[0] if pages_text else "").split('\n'):
        rm = rate_pattern.match(line.strip())
        if rm:
            caption_key = _clean(rm.group(2))
            rate_table[caption_key] = {
                'rate': _parse_num(rm.group(4)),
                'duration': int(rm.group(5)),
                'spot_amount': _parse_num(rm.group(6)),
            }

    # Parse TELECAST CERTIFICATE spots (Page 3+)
    # Format: Sr.No Caption Tx_Date Telecast_Time Program Dur
    in_telecast = False
    skip_words = ['TELECAST CERTIFICATE', 'Enter 10', 'Address:', 'Madhya Pradesh',
                  'Tel No', 'CIN:', 'GSTIN:', 'Website:', 'Client :', 'Client Add',
                  'Embassy', 'Agency :', 'Brand :', 'Sr.No', 'Caption', 'Time',
                  'Total Spots', 'Page ']

    for page_text in pages_text:
        if 'TELECAST CERTIFICATE' in page_text:
            in_telecast = True
        if not in_telecast:
            continue

        lines = page_text.split('\n')
        i = 0
        while i < len(lines):
            ls = lines[i].strip()
            i += 1

            if not ls:
                continue
            if any(skip in ls for skip in skip_words):
                continue

            # Match: SrNo CAPTION DATE TIME PROGRAM DUR
            # Example: 1 XIAOMI-REDMI13-SUSTENANCECREATIVE1-TL-20 22.05.2024 10:23:40 NATH JEWAR YA JANJEER 20
            spot_m = re.match(
                r'(\d+)\s+'                              # Sr.No
                r'(\S+)\s+'                              # Caption (hyphenated, no spaces)
                r'(\d{1,2}\.\d{1,2}\.\d{4})\s+'          # Date (DD.MM.YYYY)
                r'(\d{1,2}:\d{2}:\d{2})\s+'              # Time
                r'(.+?)\s+'                              # Program
                r'(\d+)\s*$',                            # Duration
                ls
            )

            if spot_m:
                spot = BroadcasterSpot()
                spot.spot_copy = _clean(spot_m.group(2))
                spot.date = spot_m.group(3)
                spot.air_time = spot_m.group(4)
                spot.program = _clean(spot_m.group(5))
                spot.duration = int(spot_m.group(6))
                spot.day = _get_day_from_date(spot.date)
                spot.brand = h.brand

                # Look up rate from summary table
                for cap_key, rate_info in rate_table.items():
                    if cap_key in spot.spot_copy or spot.spot_copy in cap_key:
                        spot.rate = rate_info['rate']
                        spot.amount = rate_info['spot_amount']
                        break

                result.spots.append(spot)
                continue

            # Handle multi-line program names (program wraps to next line)
            # Example line 1: 7 XIAOMI-REDMI13-SUSTENANCECREATIVE2-TL-20 22.05.2024 14:57:30 ISHQ KI DASTAAN 20
            #         line 2: NAAGMANI_CLEAN TX
            if result.spots and re.match(r'^[A-Z][\w\s_]+$', ls) and not re.match(r'\d', ls):
                # This is a continuation of the previous program name
                result.spots[-1].program += " " + _clean(ls)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
