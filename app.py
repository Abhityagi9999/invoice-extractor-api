"""
Flask Web Application for Invoice PDF Data Extraction System.
Supports both Agency Invoices (GroupM/M-Six) and Broadcaster Invoices.
Uses async background processing so the browser never times out.
"""

import os
import glob
import uuid
import logging
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file

from pdf_parser import parse_invoice
from broadcaster_router import parse_broadcaster_invoice, is_broadcaster_invoice
from po_parser import parse_po_invoice, is_po_invoice
from data_processor import (
    process_multiple_invoices,
    export_to_excel,
    get_results_summary,
    invoice_to_summary_dict,
    spots_to_dicts,
    build_broadcaster_data,
    build_po_data,
    broadcaster_to_summary_dict,
    broadcaster_spots_to_dicts,
    build_invoice_summary_sheet,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── In-memory task store ────────────────────────────────────────────────
# task_id → {status, progress, message, files, result, error}
TASKS = {}
TASKS_LOCK = threading.Lock()


def _new_task():
    task_id = str(uuid.uuid4())
    with TASKS_LOCK:
        TASKS[task_id] = {
            'status':   'running',   # running | complete | error
            'progress': 5,
            'message':  'Starting...',
            'files':    [],          # [{name, status}]
            'result':   None,
            'error':    None,
        }
    return task_id


def _update_task(task_id, **kwargs):
    with TASKS_LOCK:
        if task_id in TASKS:
            TASKS[task_id].update(kwargs)


def _build_result(parsed_agency, parsed_broadcaster, excel_path, excel_filename):
    """Build the JSON result dict returned to the frontend."""
    # Agency data
    agency_summary = get_results_summary(parsed_agency) if parsed_agency else {
        'total_invoices': 0, 'total_spots': 0, 'total_net_cost': 0, 'total_amount_payable': 0
    }
    inv_data = [invoice_to_summary_dict(r) for r in parsed_agency]
    spot_data = []
    for r in parsed_agency:
        spot_data.extend(spots_to_dicts(r))

    # Broadcaster data — also generate aggregated spot data for UI preview
    bc_data = [broadcaster_to_summary_dict(r) for r in parsed_broadcaster]
    bc_total_spots = sum(len(r.spots) for r in parsed_broadcaster)
    bc_net_amount = sum(r.header.net_amount for r in parsed_broadcaster)
    bc_total_payable = bc_net_amount * 1.18  # 18% GST added for total payable

    bc_spot_data = []
    for r in parsed_broadcaster:
        bc_spot_data.extend(broadcaster_spots_to_dicts(r))

    # Merge spot data: agency + broadcaster
    all_spot_data = spot_data + bc_spot_data

    combined_summary = {
        'total_invoices':       agency_summary['total_invoices'] + len(parsed_broadcaster),
        'total_spots':          agency_summary['total_spots'] + bc_total_spots,
        'total_net_cost':       round(agency_summary['total_net_cost'] + bc_net_amount, 2),
        'total_amount_payable': round(agency_summary['total_amount_payable'] + bc_total_payable, 2),
        'agency_invoices':      agency_summary['total_invoices'],
        'broadcaster_invoices': len(parsed_broadcaster),
        'broadcaster_spots':    bc_total_spots,
    }

    return {
        'success':              True,
        'summary':              combined_summary,
        'invoices':             inv_data + bc_data,
        'spot_details':         all_spot_data[:500],
        'total_spot_records':   len(all_spot_data),
        'download_url':         f'/download/{excel_filename}',
        'excel_filename':       excel_filename,
    }


# ── Background worker ───────────────────────────────────────────────────

def _process_pdfs_background(task_id, pdf_paths):
    """Parse PDFs one by one, auto-detect type, update progress, export Excel."""
    total = len(pdf_paths)
    parsed_agency       = []
    parsed_broadcaster  = []
    parsed_po           = []
    file_statuses       = []

    try:
        # Initialise file list as pending
        _update_task(task_id,
                     progress=5,
                     message='Scanning %d files...' % total,
                     files=[{'name': os.path.basename(p), 'status': 'pending'}
                            for p in pdf_paths])

        for idx, pdf_path in enumerate(pdf_paths):
            filename = os.path.basename(pdf_path)

            # Mark current file as processing
            file_statuses.append({'name': filename, 'status': 'processing'})
            rest = [{'name': os.path.basename(p), 'status': 'pending'}
                    for p in pdf_paths[idx + 1:]]
            done = [{'name': f['name'], 'status': 'done'}
                    for f in file_statuses[:-1]]

            pct = 5 + int((idx / total) * 85)
            _update_task(task_id,
                         progress=pct,
                         message='Parsing %s  (%d/%d)' % (filename, idx + 1, total),
                         files=done + file_statuses[-1:] + rest)

            try:
                # Auto-detect invoice type
                is_bc = is_broadcaster_invoice(pdf_path)
                is_po = False if is_bc else is_po_invoice(pdf_path)

                if is_po:
                    result = parse_po_invoice(pdf_path)
                    if not result:
                        raise ValueError("Unknown PO format or parsing error")
                    parsed_po.append(result)
                    file_statuses[-1] = {
                        'name':   filename,
                        'status': 'done',
                        'spots':  1,
                        'type':   'Purchase Order',
                    }
                    logger.info('Parsed PO %s → PO Number: %s', filename, result.po_number)
                elif is_bc:
                    result = parse_broadcaster_invoice(pdf_path)
                    if not result:
                        raise ValueError("Unknown broadcaster format or parsing error")
                    parsed_broadcaster.append(result)
                    file_statuses[-1] = {
                        'name':   filename,
                        'status': 'done',
                        'spots':  len(result.spots),
                        'type':   'broadcaster (%s)' % result.format_type,
                    }
                    logger.info('Parsed BROADCASTER %s → %d spots (%s)',
                                filename, len(result.spots), result.format_type)
                else:
                    result = parse_invoice(pdf_path)
                    if not result:
                        raise ValueError("Could not parse agency invoice")
                    parsed_agency.append(result)
                    file_statuses[-1] = {
                        'name':   filename,
                        'status': 'done',
                        'spots':  len(result.spot_details),
                        'type':   'agency',
                    }
                    logger.info('Parsed AGENCY %s → %d spots', filename, len(result.spot_details))

            except Exception as exc:
                file_statuses[-1] = {'name': filename, 'status': 'error', 'error': str(exc)}
                logger.error('Error parsing %s: %s', filename, exc)

        if not parsed_agency and not parsed_broadcaster and not parsed_po:
            _update_task(task_id, status='error',
                         error='Could not parse any PDF files.')
            return

        # Build DataFrames for both types
        _update_task(task_id, progress=92, message='Generating Excel...',
                     files=file_statuses)

        dfs = {}

        # 1. High-level Invoice Summary Sheet (Sheet 1)
        dfs['summary'] = build_invoice_summary_sheet(parsed_agency, parsed_broadcaster)

        # Agency data
        if parsed_agency:
            agency_dfs = process_multiple_invoices(parsed_agency)
            dfs['channel'] = agency_dfs.get('channel', None)

        # Broadcaster data
        if parsed_broadcaster:
            dfs['broadcaster'] = build_broadcaster_data(parsed_broadcaster)
            
        # PO data
        if parsed_po:
            dfs['po'] = build_po_data(parsed_po)

        # Export combined Excel
        timestamp      = datetime.now().strftime('%Y%m%d_%H%M%S')
        has_agency     = bool(parsed_agency)
        has_bc         = bool(parsed_broadcaster)
        if has_agency and has_bc:
            excel_filename = 'Invoices_Combined_%s.xlsx' % timestamp
        elif has_bc:
            excel_filename = 'Broadcaster_Invoices_%s.xlsx' % timestamp
        else:
            excel_filename = 'Agency_Invoices_%s.xlsx' % timestamp

        excel_path = os.path.join(OUTPUT_DIR, excel_filename)
        export_to_excel(dfs, excel_path)

        result_payload = _build_result(parsed_agency, parsed_broadcaster,
                                        excel_path, excel_filename)
        result_payload['file_statuses'] = file_statuses

        total_spots = result_payload['summary']['total_spots']
        total_inv   = result_payload['summary']['total_invoices']

        _update_task(task_id,
                     status='complete',
                     progress=100,
                     message='Done! %d invoices (%d agency + %d broadcaster), %d spots.' % (
                         total_inv,
                         len(parsed_agency),
                         len(parsed_broadcaster),
                         total_spots),
                     files=file_statuses,
                     result=result_payload)

        logger.info('Task %s complete — %d agency + %d broadcaster, Excel: %s',
                    task_id, len(parsed_agency), len(parsed_broadcaster), excel_filename)

    except Exception as exc:
        logger.exception('Background task %s failed', task_id)
        _update_task(task_id, status='error', error=str(exc))


# ── Routes ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_files():
    """Upload PDFs directly from the browser (multipart form)."""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400

        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files selected'}), 400

        session_id  = str(uuid.uuid4())[:8]
        session_dir = os.path.join(UPLOAD_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)

        saved_paths = []
        for f in files:
            if f.filename and f.filename.lower().endswith('.pdf'):
                fname = os.path.basename(f.filename)
                if fname.startswith('~$'):
                    logger.info('Skipping temporary owner file: %s', f.filename)
                    continue
                safe = f.filename.replace('/', '_').replace('\\', '_')
                path = os.path.join(session_dir, safe)
                f.save(path)
                saved_paths.append(path)

        if not saved_paths:
            return jsonify({'error': 'No valid PDF files found'}), 400

        # Start background task
        task_id = _new_task()
        t = threading.Thread(target=_process_pdfs_background,
                             args=(task_id, saved_paths), daemon=True)
        t.start()

        return jsonify({'task_id': task_id, 'total_files': len(saved_paths)})

    except Exception as exc:
        logger.exception('Upload error')
        return jsonify({'error': str(exc)}), 500


@app.route('/process-folder', methods=['POST'])
def process_folder():
    """Process all PDFs inside a local folder path."""
    try:
        data = request.get_json()
        if not data or 'folder_path' not in data:
            return jsonify({'error': 'No folder path provided'}), 400

        folder_path = data['folder_path'].strip()

        if not os.path.isdir(folder_path):
            return jsonify({'error': 'Folder not found: ' + folder_path}), 400

        # Use recursive glob so we can find PDFs in subfolders (e.g. Broadcaster_Invoices_Organized)
        pdf_paths = sorted(glob.glob(os.path.join(folder_path, '**', '*.pdf'), recursive=True))
        pdf_paths = [p for p in pdf_paths if not os.path.basename(p).startswith('~$')]
        if not pdf_paths:
            return jsonify({'error': 'No PDF files found in: ' + folder_path}), 400

        logger.info('Folder "%s"  →  %d PDFs', folder_path, len(pdf_paths))

        # Start background task immediately; return task_id to JS
        task_id = _new_task()
        t = threading.Thread(target=_process_pdfs_background,
                             args=(task_id, pdf_paths), daemon=True)
        t.start()

        return jsonify({'task_id': task_id, 'total_files': len(pdf_paths)})

    except Exception as exc:
        logger.exception('Folder processing error')
        return jsonify({'error': str(exc)}), 500


@app.route('/process-status')
def process_status():
    """Poll endpoint called by the frontend every 2 seconds."""
    task_id = request.args.get('task_id', '')
    with TASKS_LOCK:
        task = TASKS.get(task_id)

    if not task:
        return jsonify({'status': 'error', 'message': 'Unknown task ID'}), 404

    response = {
        'status':   task['status'],
        'progress': task['progress'],
        'message':  task['message'],
        'files':    task['files'],
    }

    if task['status'] == 'complete':
        response['result'] = task['result']
    elif task['status'] == 'error':
        response['message'] = task.get('error', 'Unknown error')

    return jsonify(response)


@app.route('/download/<filename>')
def download_file(filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


# ── Entry point ─────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('\n' + '=' * 60)
    print('  Invoice PDF Data Extraction System')
    print('  (Agency + Broadcaster Auto-Detect)')
    print('  Starting web server...')
    print('=' * 60)
    print('\n  Open in browser: http://localhost:5000')
    print('  Upload dir: ' + UPLOAD_DIR)
    print('  Output dir: ' + OUTPUT_DIR)
    print('=' * 60 + '\n')
    app.run(debug=False, host='0.0.0.0', port=5000)
