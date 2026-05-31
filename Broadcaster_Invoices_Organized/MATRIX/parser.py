import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    """Parse Matrix Publicities invoices (Republic TV, Star Sports etc.) - Annexure-2 format.

    Annexure-2 line layout:
    SUPP_BILL_NO  MON_REPORT_NO  PRODUCER  CHANNEL  PROGRAM  DAY  START_TIME  SPOT_DATE  SPOT_DUR  NET_SPOT_RATE  NET_COST  MBA_FULL_BILL_NO

    Example lines:
    O03300268106 M4659916598 STAR INDIA PVT LTD STAR SPORTS 1 HD TELUGU B1 VS D1 FRI 20:00 21-Jun-2024 10 4,009.25 4,009.25 TK2405927
    M4562229953 REPUBLIC TV RODP (07.00 - 12.00) FRI 07:00 24-May-2024 20 925.56 1,851.12 TK2404159
    """
    result = ParsedBroadcasterInvoice(format_type='matrix')
    h = result.header

    h.broadcaster_name = _extract(full_text, r'(MATRIX\s+PUBLICITIES\s+AND\s+MEDIA\s+INDIA\s+(?:PVT|PRIVATE)?\.?\s*(?:LTD|LIMITED)\.?)', default="MATRIX PUBLICITIES AND MEDIA INDIA PVT. LTD.")
    h.advertiser_name = _extract(full_text, r'(?:Client|Advertiser)\s*:?\s*\n?\s*([A-Z][A-Z\s]+(?:PVT|PRIVATE)\s*(?:LTD|LIMITED))', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")
    h.agency_name = _extract(full_text, r'Service\s*provided\s*To\s*:\s*\n?\s*(GROUP\s*M\s*MEDIA\s*INDIA\s*(?:PVT|PRIVATE)?\.?\s*(?:LTD|LIMITED)\.?)', default="GROUP M MEDIA INDIA PVT. LTD.")
    h.invoice_number = _extract(full_text, r'Invoice\s*Number\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Invoice\s*Date\s*:\s*(\S+)')
    h.billing_period = _extract(full_text, r'Activity\s*Month\s*:\s*(\S+)')
    h.po_number = _extract(full_text, r'Client\s*PO\s*Number\s*:\s*(\S+)')
    h.brand = _extract(full_text, r'Brand\s*Name\s*:\s*(\w+)', default="XIAOMI")

    # Channel from summary table on page 1/2
    ch_m = re.search(r'Channel\s+No\s+of\s+Spots\s+Net\s+Cost\s*\n\s*(.+?)\s+(\d+)\s+([\d,]+\.\d{2})', full_text, re.IGNORECASE)
    if ch_m:
        h.channel_name = _clean(ch_m.group(1))
        h.total_spots = int(ch_m.group(2))
        h.net_amount = _parse_num(ch_m.group(3))

    # Collect all Annexure-2 lines
    in_annexure2 = False

    for page_text in pages_text:
        if 'Annexure-2' in page_text:
            in_annexure2 = True
        if not in_annexure2:
            if 'SUPP BILL NO' in page_text or 'MON REPORT' in page_text:
                in_annexure2 = True
        if not in_annexure2:
            continue

        lines = page_text.split('\n')
        for ls_raw in lines:
            ls = ls_raw.strip()
            if not ls:
                continue

            # Skip headers/footers
            if any(skip in ls for skip in ['SUPP BILL NO', 'Invoice Number', 'TAX INVOICE',
                                            'Annexure', 'Page ', 'Registered Office',
                                            'Correspondence', 'FOR MATRIX', 'CHECKED BY',
                                            'E. & O. E.', 'PER 10 SEC']):
                continue

            # Skip producer continuation lines
            if ls in ['LIMITED', 'LTD', 'PVT LTD', 'PRIVATE LIMITED']:
                continue

            # Find monitoring report number (M followed by 7+ digits)
            m_match = re.search(r'(M\d{7,})', ls)
            if not m_match:
                continue

            # Find DAY + TIME + DATE + DUR + RATE + COST + BILL_NO after the M-number
            after_m = ls[m_match.end():]
            dtd_m = re.search(
                r'(MON|TUE|WED|THU|FRI|SAT|SUN)\s+'
                r'(\d{1,2}:\d{2})\s+'
                r'(\d{1,2}-\w{3}-\d{4})\s+'
                r'(\d+)\s+'
                r'([\d,]+\.?\d*)\s+'
                r'([\d,]+\.?\d*)\s+'
                r'(\S+)',
                after_m, re.IGNORECASE
            )

            if not dtd_m:
                continue

            # Text between M-number and DAY = PRODUCER + CHANNEL + PROGRAM
            between = after_m[:dtd_m.start()].strip()

            producer = ""
            program = between

            # Try to extract known producer names
            for pp in [r'(STAR INDIA PVT\.?\s*LTD\.?)',
                       r'(ARG OUTLIER MEDIA (?:PRIVATE\s+)?LIMITED)',
                       r'([\w\s]+PVT\.?\s*LTD\.?)',
                       r'([\w\s]+PRIVATE\s+LIMITED)']:
                pp_m = re.search(pp, between, re.IGNORECASE)
                if pp_m:
                    producer = _clean(pp_m.group(1))
                    after_producer = between[pp_m.end():].strip()
                    if h.channel_name and h.channel_name in after_producer:
                        ch_idx = after_producer.index(h.channel_name)
                        program = after_producer[ch_idx + len(h.channel_name):].strip()
                    else:
                        program = after_producer
                    break

            spot = BroadcasterSpot()
            spot.program = _clean(program)
            spot.day = dtd_m.group(1).capitalize()[:3]
            spot.air_time = dtd_m.group(2)
            spot.date = dtd_m.group(3)
            spot.duration = int(dtd_m.group(4))
            spot.rate = _parse_num(dtd_m.group(5))
            spot.amount = _parse_num(dtd_m.group(6))
            spot.brand = h.brand
            spot.tp = spot.program
            spot.spot_copy = ""
            result.spots.append(spot)

    h.total_spots = max(h.total_spots, len(result.spots))
    if result.spots:
        h.net_amount = h.net_amount or sum(s.amount for s in result.spots)
    return result
