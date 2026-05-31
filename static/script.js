/* ============================================
   Agency Invoice Extractor — Frontend Script
   ============================================ */

(function () {
    'use strict';

    // ── DOM References ──────────────────────────────────────────
    const uploadArea       = document.getElementById('upload-area');
    const fileInput        = document.getElementById('file-input');
    const folderInput      = document.getElementById('folder-input');
    const selectedFiles    = document.getElementById('selected-files');
    const selectedList     = document.getElementById('selected-files-list');
    const uploadBtn        = document.getElementById('upload-btn');
    const processFolderBtn = document.getElementById('process-folder-btn');

    const processingSection = document.getElementById('processing-section');
    const progressBar       = document.getElementById('progress-bar');
    const progressText      = document.getElementById('progress-text');
    const progressLabel     = document.getElementById('progress-label');
    const fileList          = document.getElementById('file-list');

    const resultsSection    = document.getElementById('results-section');
    const summaryCards      = document.getElementById('summary-cards');
    const downloadBtn       = document.getElementById('download-btn');

    // State
    let collectedFiles = [];
    let currentDownloadUrl = '';
    let spotDetailsData = { headers: [], rows: [] };
    let spotDetailsShown = 0;
    const SPOT_PAGE_SIZE = 100;

    // ── Tab Switching ───────────────────────────────────────────
    window.switchTab = function (tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(tabName + '-tab').classList.add('active');
    };

    // ── Data Tab Switching ──────────────────────────────────────
    window.switchDataTab = function (tabName) {
        document.querySelectorAll('.data-tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.dtab === tabName);
        });

        document.querySelectorAll('.data-tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(tabName + '-tab').classList.add('active');
    };

    // ── Drag & Drop ────────────────────────────────────────────
    if (uploadArea) {
        uploadArea.addEventListener('click', () => fileInput.click());

        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadArea.classList.add('drag-over');
        });

        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadArea.classList.remove('drag-over');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadArea.classList.remove('drag-over');

            const files = Array.from(e.dataTransfer.files).filter(
                f => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
            );

            if (files.length === 0) {
                showToast('Please drop PDF files only.', 'error');
                return;
            }

            addFiles(files);
        });

        fileInput.addEventListener('change', () => {
            const files = Array.from(fileInput.files);
            if (files.length) addFiles(files);
            fileInput.value = '';
        });
    }

    // ── File Management ─────────────────────────────────────────
    function addFiles(files) {
        files.forEach(f => {
            // Avoid duplicates
            if (!collectedFiles.find(cf => cf.name === f.name && cf.size === f.size)) {
                collectedFiles.push(f);
            }
        });
        renderSelectedFiles();
    }

    window.clearFiles = function () {
        collectedFiles = [];
        renderSelectedFiles();
    };

    function renderSelectedFiles() {
        if (collectedFiles.length === 0) {
            selectedFiles.style.display = 'none';
            return;
        }

        selectedFiles.style.display = 'block';
        selectedList.innerHTML = '';

        collectedFiles.forEach((file, idx) => {
            const li = document.createElement('li');
            li.className = 'selected-file-item';
            li.style.animationDelay = `${idx * 0.05}s`;
            li.innerHTML = `
                <i class="fas fa-file-pdf"></i>
                <span>${escapeHtml(file.name)}</span>
                <span class="file-size">${formatFileSize(file.size)}</span>
            `;
            selectedList.appendChild(li);
        });
    }

    // ── Upload Files ────────────────────────────────────────────
    window.uploadFiles = function () {
        if (collectedFiles.length === 0) {
            showToast('No files selected.', 'error');
            return;
        }

        const formData = new FormData();
        collectedFiles.forEach(file => formData.append('files', file));

        // Show processing UI with file names
        showProcessing(collectedFiles.map(f => f.name));
        updateProgress(5, 'Uploading files...');

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload', true);

        // Track upload progress (0-40%)
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 40);
                updateProgress(pct, 'Uploading files...');
            }
        });

        xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    const data = JSON.parse(xhr.responseText);

                    if (data.task_id) {
                        // ✅ New async flow — poll for status updates
                        updateProgress(45, 'Processing PDFs...');
                        pollProcessStatus(data.task_id);
                    } else if (data.summary) {
                        // Legacy immediate response
                        updateProgress(100, 'Complete!');
                        markAllFilesDone();
                        setTimeout(() => displayResults(data), 500);
                        showToast('Extraction complete!', 'success');
                    } else if (data.error) {
                        handleError(data.error);
                    } else {
                        handleError('Unexpected response from server.');
                    }
                } catch (err) {
                    handleError('Failed to parse server response.');
                }
            } else {
                try {
                    const err = JSON.parse(xhr.responseText);
                    handleError(err.error || `Server error (${xhr.status}).`);
                } catch (_) {
                    handleError(`Server error (${xhr.status}).`);
                }
            }
        });

        xhr.addEventListener('error', () => handleError('Network error occurred.'));
        xhr.addEventListener('abort', () => handleError('Upload aborted.'));

        xhr.send(formData);
    };

    // ── Process Folder ──────────────────────────────────────────

    window.processFolder = function () {
        const folderPath = folderInput.value.trim();
        if (!folderPath) {
            showToast('Please enter a folder path.', 'error');
            return;
        }

        showProcessing(['Scanning folder...']);
        updateProgress(5, 'Initializing...');

        fetch('/process-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPath })
        })
        .then(res => {
            if (!res.ok) throw new Error(`Server error: ${res.status}`);
            return res.json();
        })
        .then(data => {
            if (data.task_id) {
                // Async processing — poll for status
                pollProcessStatus(data.task_id);
            } else if (data.summary) {
                // Immediate result
                updateProgress(100, 'Complete!');
                markAllFilesDone();
                displayResults(data);
                showToast('Extraction complete!', 'success');
            } else {
                handleError('Unexpected response format.');
            }
        })
        .catch(err => handleError(err.message));
    };

    function pollProcessStatus(taskId) {
        const pollInterval = setInterval(() => {
            fetch(`/process-status?task_id=${encodeURIComponent(taskId)}`)
                .then(res => res.json())
                .then(data => {
                    // Update progress
                    if (data.progress != null) {
                        updateProgress(data.progress, data.message || 'Processing...');
                    }

                    // Update file list
                    if (data.files && data.files.length) {
                        updateFileList(data.files);
                    }

                    // Check completion
                    if (data.status === 'complete') {
                        clearInterval(pollInterval);
                        updateProgress(100, 'Complete!');
                        markAllFilesDone();
                        displayResults(data.result);
                        showToast('Extraction complete!', 'success');
                    } else if (data.status === 'error') {
                        clearInterval(pollInterval);
                        handleError(data.message || 'Processing failed.');
                    }
                })
                .catch(() => {
                    clearInterval(pollInterval);
                    handleError('Lost connection to server.');
                });
        }, 2000);
    }

    // ── Display Results ─────────────────────────────────────────
    function displayResults(data) {
        if (!data) return;

        resultsSection.style.display = 'block';
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

        // Summary cards with animated counters
        const summary = data.summary || {};
        animateCounter(
            document.getElementById('total-invoices'),
            summary.total_invoices || 0,
            1200,
            false
        );
        animateCounter(
            document.getElementById('total-spots'),
            summary.total_spots || 0,
            1400,
            false
        );
        animateCounter(
            document.getElementById('total-net-cost'),
            summary.total_net_cost || 0,
            1600,
            true
        );
        animateCounter(
            document.getElementById('total-amount-payable'),
            summary.total_amount_payable || 0,
            1800,
            true
        );

        // Invoice summary table
        if (data.invoices && data.invoices.length > 0) {
            const invHeaders = Object.keys(data.invoices[0]);
            const invRows = data.invoices.map(inv => invHeaders.map(h => inv[h]));
            displayTable('invoice-summary-table', invHeaders, invRows);
        }

        // Spot details table (with load-more)
        if (data.spot_details && data.spot_details.length > 0) {
            const spotHeaders = Object.keys(data.spot_details[0]);
            const spotRows = data.spot_details.map(sd => spotHeaders.map(h => sd[h]));
            spotDetailsData = { headers: spotHeaders, rows: spotRows };
            spotDetailsShown = 0;
            displaySpotDetailsTable();
        }

        // Download URL
        if (data.download_url) {
            currentDownloadUrl = data.download_url;
            downloadBtn.style.display = 'inline-flex';
        }
    }

    // ── Table Rendering ─────────────────────────────────────────
    function displayTable(containerId, headers, rows) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const numericCols = detectNumericColumns(headers, rows);

        let html = '<table class="data-table"><thead><tr>';
        headers.forEach((h, i) => {
            html += `<th${numericCols.has(i) ? ' style="text-align:right"' : ''}>${escapeHtml(formatHeader(h))}</th>`;
        });
        html += '</tr></thead><tbody>';

        rows.forEach((row, ri) => {
            html += `<tr style="animation-delay:${ri * 0.02}s">`;
            row.forEach((cell, ci) => {
                const isNum = numericCols.has(ci);
                const formatted = isNum ? formatNumber(cell) : escapeHtml(String(cell ?? ''));
                html += `<td${isNum ? ' class="number"' : ''}>${formatted}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    }

    function displaySpotDetailsTable() {
        const container = document.getElementById('spot-details-table');
        if (!container) return;

        const { headers, rows } = spotDetailsData;
        const numericCols = detectNumericColumns(headers, rows);
        const nextBatch = rows.slice(0, spotDetailsShown + SPOT_PAGE_SIZE);
        spotDetailsShown = nextBatch.length;

        let html = '<table class="data-table"><thead><tr>';
        headers.forEach((h, i) => {
            html += `<th${numericCols.has(i) ? ' style="text-align:right"' : ''}>${escapeHtml(formatHeader(h))}</th>`;
        });
        html += '</tr></thead><tbody>';

        nextBatch.forEach((row, ri) => {
            html += '<tr>';
            row.forEach((cell, ci) => {
                const isNum = numericCols.has(ci);
                const formatted = isNum ? formatNumber(cell) : escapeHtml(String(cell ?? ''));
                html += `<td${isNum ? ' class="number"' : ''}>${formatted}</td>`;
            });
            html += '</tr>';
        });

        // Load more button
        if (spotDetailsShown < rows.length) {
            const remaining = rows.length - spotDetailsShown;
            html += `<tr class="load-more-row"><td colspan="${headers.length}">
                <button class="btn-load-more" onclick="loadMoreSpots()">
                    <i class="fas fa-chevron-down"></i> Load ${Math.min(remaining, SPOT_PAGE_SIZE)} more of ${remaining} remaining
                </button>
            </td></tr>`;
        }

        html += '</tbody></table>';
        container.innerHTML = html;
    }

    window.loadMoreSpots = function () {
        displaySpotDetailsTable();
    };

    // ── Animated Counter ────────────────────────────────────────
    function animateCounter(element, target, duration, isCurrency) {
        if (!element) return;

        const startTime = performance.now();
        const startVal = 0;

        element.style.animation = 'countUp 0.4s ease-out';

        function tick(now) {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // Ease-out cubic
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = startVal + (target - startVal) * eased;

            if (isCurrency) {
                element.textContent = formatCurrency(current);
            } else {
                element.textContent = Math.round(current).toLocaleString('en-IN');
            }

            if (progress < 1) {
                requestAnimationFrame(tick);
            } else {
                element.textContent = isCurrency
                    ? formatCurrency(target)
                    : Math.round(target).toLocaleString('en-IN');
            }
        }

        requestAnimationFrame(tick);
    }

    // ── Currency Formatter (Indian ₹) ──────────────────────────
    function formatCurrency(num) {
        if (num == null || isNaN(num)) return '₹0';
        num = Number(num);
        const isNeg = num < 0;
        num = Math.abs(num);

        const parts = num.toFixed(2).split('.');
        let intPart = parts[0];
        const decPart = parts[1];

        // Indian grouping: last 3 digits, then groups of 2
        if (intPart.length > 3) {
            const last3 = intPart.slice(-3);
            let remaining = intPart.slice(0, -3);
            const groups = [];
            while (remaining.length > 2) {
                groups.unshift(remaining.slice(-2));
                remaining = remaining.slice(0, -2);
            }
            if (remaining.length > 0) groups.unshift(remaining);
            intPart = groups.join(',') + ',' + last3;
        }

        return (isNeg ? '-' : '') + '₹' + intPart + '.' + decPart;
    }

    // ── Processing UI Helpers ───────────────────────────────────
    function showProcessing(fileNames) {
        processingSection.style.display = 'block';
        resultsSection.style.display = 'none';
        processingSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        // Render file items
        fileList.innerHTML = '';
        fileNames.forEach((name, i) => {
            const item = document.createElement('div');
            item.className = 'file-item';
            item.style.animationDelay = `${i * 0.08}s`;
            item.dataset.filename = name;
            item.innerHTML = `
                <span class="file-item-name"><i class="fas fa-file-pdf" style="color:var(--error);opacity:0.6;margin-right:8px;"></i>${escapeHtml(name)}</span>
                <span class="file-status file-status-pending">Pending</span>
            `;
            fileList.appendChild(item);
        });
    }

    function updateProgress(pct, label) {
        pct = Math.min(Math.max(0, pct), 100);
        progressBar.style.width = pct + '%';
        progressText.textContent = Math.round(pct) + '%';
        if (label) progressLabel.textContent = label;
    }

    function updateFileList(files) {
        // files: [{name, status}]
        fileList.innerHTML = '';
        files.forEach((f, i) => {
            const item = document.createElement('div');
            item.className = 'file-item';
            item.style.animationDelay = `${i * 0.05}s`;
            item.dataset.filename = f.name;

            const statusClass = `file-status-${f.status || 'pending'}`;
            const statusLabel = (f.status || 'pending').charAt(0).toUpperCase() + (f.status || 'pending').slice(1);

            item.innerHTML = `
                <span class="file-item-name"><i class="fas fa-file-pdf" style="color:var(--error);opacity:0.6;margin-right:8px;"></i>${escapeHtml(f.name)}</span>
                <span class="file-status ${statusClass}">${statusLabel}</span>
            `;
            fileList.appendChild(item);
        });
    }

    function simulateFileProcessing(fileNames, startPct) {
        const perFile = (100 - startPct) / fileNames.length;
        let idx = 0;

        function processNext() {
            if (idx >= fileNames.length) return;

            const items = fileList.querySelectorAll('.file-item');
            // Mark current as processing
            if (items[idx]) {
                const badge = items[idx].querySelector('.file-status');
                badge.className = 'file-status file-status-processing';
                badge.textContent = 'Processing';
            }

            updateProgress(startPct + idx * perFile, `Processing ${fileNames[idx]}...`);

            setTimeout(() => {
                // Mark as done
                if (items[idx]) {
                    const badge = items[idx].querySelector('.file-status');
                    badge.className = 'file-status file-status-done';
                    badge.textContent = 'Done';
                }
                idx++;
                processNext();
            }, 600 + Math.random() * 400);
        }

        setTimeout(processNext, 500);
    }

    function markAllFilesDone() {
        fileList.querySelectorAll('.file-status').forEach(badge => {
            if (!badge.classList.contains('file-status-error')) {
                badge.className = 'file-status file-status-done';
                badge.textContent = 'Done';
            }
        });
    }

    function handleError(message) {
        updateProgress(0, 'Error');
        fileList.querySelectorAll('.file-status-processing').forEach(badge => {
            badge.className = 'file-status file-status-error';
            badge.textContent = 'Error';
        });
        showToast(message, 'error');
    }

    // ── Download ────────────────────────────────────────────────
    window.downloadExcel = function () {
        if (currentDownloadUrl) {
            const a = document.createElement('a');
            a.href = currentDownloadUrl;
            a.download = '';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            showToast('Download started!', 'success');
        } else {
            showToast('No download available.', 'error');
        }
    };

    // ── Toast Notifications ─────────────────────────────────────
    function showToast(message, type) {
        const existing = document.querySelectorAll('.toast');
        existing.forEach(t => t.remove());

        const toast = document.createElement('div');
        toast.className = `toast toast-${type || 'info'}`;

        const icons = { success: 'fa-check-circle', error: 'fa-exclamation-circle', info: 'fa-info-circle' };
        toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i> ${escapeHtml(message)}`;

        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 4200);
    }

    // ── Utility Functions ───────────────────────────────────────
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function formatHeader(str) {
        return String(str)
            .replace(/_/g, ' ')
            .replace(/\b\w/g, c => c.toUpperCase());
    }

    function formatNumber(val) {
        if (val == null || val === '') return '';
        const num = Number(val);
        if (isNaN(num)) return escapeHtml(String(val));
        if (Number.isInteger(num)) return num.toLocaleString('en-IN');
        return num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function detectNumericColumns(headers, rows) {
        const numericCols = new Set();
        if (rows.length === 0) return numericCols;

        headers.forEach((_, ci) => {
            // Check first 10 rows to determine if column is numeric
            let numCount = 0;
            const sample = rows.slice(0, 10);
            sample.forEach(row => {
                const val = row[ci];
                if (val != null && val !== '' && !isNaN(Number(val))) {
                    numCount++;
                }
            });
            if (numCount > sample.length * 0.6) {
                numericCols.add(ci);
            }
        });

        return numericCols;
    }

})();
