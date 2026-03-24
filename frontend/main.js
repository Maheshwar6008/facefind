/**
 * FaceFind — Frontend Application Logic
 * Handles selfie upload, face matching, results display, downloads, and authentication.
 */

const API_BASE = '/api';

// ─── DOM Elements ─────────────────────────────────────────
const appEl = document.getElementById('app');
const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const previewArea = document.getElementById('preview-area');
const previewImg = document.getElementById('preview-img');
const btnMatch = document.getElementById('btn-match');
const btnClear = document.getElementById('btn-clear');
const thresholdSlider = document.getElementById('threshold-slider');
const thresholdValue = document.getElementById('threshold-value');

const loadingEl = document.getElementById('loading');
const errorMsg = document.getElementById('error-msg');
const errorText = document.getElementById('error-text');

const resultsSection = document.getElementById('results-section');
const resultsCount = document.getElementById('results-count');
const resultsGrid = document.getElementById('results-grid');
const btnSelectAll = document.getElementById('btn-select-all');
const btnDownloadSelected = document.getElementById('btn-download-selected');

const btnStatus = document.getElementById('btn-status');
const btnSync = document.getElementById('btn-sync');
const statusPanel = document.getElementById('status-panel');
const syncProgress = document.getElementById('sync-progress');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');

// ─── State ────────────────────────────────────────────────
let selectedFile = null;
let selectedCards = new Set();
let currentMatches = [];
let statusPollInterval = null;
let authToken = localStorage.getItem('facefind_token') || '';


// ─── Auth Helpers ─────────────────────────────────────────

function getAuthHeaders() {
    const headers = {};
    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }
    return headers;
}

async function authFetch(url, options = {}) {
    const headers = { ...getAuthHeaders(), ...(options.headers || {}) };
    const res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
        // Token expired or invalid — show login
        authToken = '';
        localStorage.removeItem('facefind_token');
        showLoginScreen();
        throw new Error('Session expired. Please login again.');
    }
    return res;
}

function showLoginScreen() {
    // Create login overlay
    let overlay = document.getElementById('login-overlay');
    if (overlay) return; // Already showing

    overlay = document.createElement('div');
    overlay.id = 'login-overlay';
    overlay.style.cssText = `
        position: fixed; inset: 0; z-index: 1000;
        background: rgba(10, 10, 26, 0.95);
        display: flex; align-items: center; justify-content: center;
        backdrop-filter: blur(20px);
    `;
    overlay.innerHTML = `
        <div style="
            background: rgba(30, 30, 60, 0.8);
            border: 1px solid rgba(120, 100, 255, 0.2);
            border-radius: 20px;
            padding: 40px;
            max-width: 380px;
            width: 90%;
            text-align: center;
            backdrop-filter: blur(30px);
        ">
            <div style="
                width: 60px; height: 60px; margin: 0 auto 20px;
                background: linear-gradient(135deg, #7c3aed, #3b82f6, #06b6d4);
                border-radius: 14px;
                display: flex; align-items: center; justify-content: center;
            ">
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                </svg>
            </div>
            <h2 style="font-size: 1.4rem; margin-bottom: 8px; color: #f0f0ff;">Welcome to FaceFind</h2>
            <p style="color: #9898c8; font-size: 0.85rem; margin-bottom: 24px;">Enter the access password to continue</p>
            <input id="login-password" type="password" placeholder="Password"
                style="
                    width: 100%; padding: 12px 16px;
                    background: rgba(20, 20, 45, 0.8);
                    border: 1px solid rgba(120, 100, 255, 0.2);
                    border-radius: 10px;
                    color: #f0f0ff; font-size: 1rem;
                    outline: none; font-family: inherit;
                    margin-bottom: 16px;
                ">
            <button id="login-btn"
                style="
                    width: 100%; padding: 12px;
                    background: linear-gradient(135deg, #7c3aed, #3b82f6, #06b6d4);
                    border: none; border-radius: 10px;
                    color: white; font-size: 1rem; font-weight: 600;
                    cursor: pointer; font-family: inherit;
                ">Login</button>
            <p id="login-error" style="color: #fca5a5; font-size: 0.85rem; margin-top: 12px; display: none;"></p>
        </div>
    `;
    document.body.appendChild(overlay);

    const passwordInput = document.getElementById('login-password');
    const loginBtn = document.getElementById('login-btn');
    const loginError = document.getElementById('login-error');

    async function doLogin() {
        const password = passwordInput.value.trim();
        if (!password) return;

        loginBtn.textContent = 'Logging in...';
        loginBtn.disabled = true;

        try {
            const res = await fetch(`${API_BASE}/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });

            const data = await res.json();

            if (res.ok && data.success) {
                authToken = data.token;
                localStorage.setItem('facefind_token', authToken);
                overlay.remove();
            } else {
                loginError.textContent = data.detail || 'Incorrect password';
                loginError.style.display = 'block';
                loginBtn.textContent = 'Login';
                loginBtn.disabled = false;
            }
        } catch (err) {
            loginError.textContent = 'Connection failed. Is the server running?';
            loginError.style.display = 'block';
            loginBtn.textContent = 'Login';
            loginBtn.disabled = false;
        }
    }

    loginBtn.addEventListener('click', doLogin);
    passwordInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') doLogin();
    });
    passwordInput.focus();
}


// ─── Upload Handling ──────────────────────────────────────

uploadArea.addEventListener('click', () => fileInput.click());

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type.startsWith('image/')) {
        handleFileSelect(files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
    }
});

function handleFileSelect(file) {
    selectedFile = file;
    hideError();

    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
        uploadArea.classList.add('hidden');
        previewArea.classList.remove('hidden');
    };
    reader.readAsDataURL(file);
}

btnClear.addEventListener('click', () => {
    selectedFile = null;
    fileInput.value = '';
    previewArea.classList.add('hidden');
    uploadArea.classList.remove('hidden');
    resultsSection.classList.add('hidden');
    hideError();
});


// ─── Threshold Slider ─────────────────────────────────────

thresholdSlider.addEventListener('input', () => {
    thresholdValue.textContent = parseFloat(thresholdSlider.value).toFixed(2);
});


// ─── Match Request ────────────────────────────────────────

btnMatch.addEventListener('click', async () => {
    if (!selectedFile) return;

    showLoading();
    hideError();
    resultsSection.classList.add('hidden');

    const formData = new FormData();
    formData.append('file', selectedFile);

    const threshold = parseFloat(thresholdSlider.value);

    try {
        const res = await authFetch(
            `${API_BASE}/match?threshold=${threshold}`,
            { method: 'POST', body: formData }
        );

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || `Server error (${res.status})`);
        }

        const data = await res.json();
        hideLoading();

        if (data.matches && data.matches.length > 0) {
            displayResults(data.matches);
        } else {
            showError('No matching photos found. Try lowering the match sensitivity slider.');
        }

    } catch (err) {
        hideLoading();
        showError(err.message || 'Failed to process selfie. Is the backend running?');
    }
});


// ─── Results Display ──────────────────────────────────────

function displayResults(matches) {
    currentMatches = matches;
    selectedCards.clear();

    resultsCount.textContent = matches.length;
    resultsGrid.innerHTML = '';

    matches.forEach((match, idx) => {
        const card = createResultCard(match, idx);
        resultsGrid.appendChild(card);
    });

    resultsSection.classList.remove('hidden');
    updateDownloadBtn();

    // Smooth scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function createResultCard(match, idx) {
    const card = document.createElement('div');
    card.className = 'result-card';
    card.style.animationDelay = `${idx * 0.05}s`;
    card.dataset.index = idx;

    const scorePercent = Math.round(match.score * 100);
    const barWidth = Math.min(scorePercent, 100);

    card.innerHTML = `
        <img class="card-img" 
             src="" 
             alt="${match.filename || 'Matched photo'}"
             loading="lazy"
             data-drive-id="${match.drive_id}"
             onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22><rect width=%22200%22 height=%22200%22 fill=%22%231a1a3e%22/><text x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22 fill=%22%235050a0%22 font-size=%2214%22>No Preview</text></svg>'">
        <div class="card-checkbox" data-index="${idx}"></div>
        <button class="card-download" data-drive-id="${match.drive_id}" title="Download">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
        </button>
        <div class="card-info">
            <div class="card-name" title="${match.filename}">${match.filename || 'Unknown'}</div>
            <div class="card-score">
                ${scorePercent}% match
                <span class="score-bar" style="width: ${barWidth}px"></span>
            </div>
        </div>
    `;

    // Load thumbnail with auth header
    const img = card.querySelector('.card-img');
    if (match.thumbnail_url) {
        fetch(match.thumbnail_url, { headers: getAuthHeaders() })
            .then(res => res.ok ? res.blob() : Promise.reject())
            .then(blob => { img.src = URL.createObjectURL(blob); })
            .catch(() => { img.dispatchEvent(new Event('error')); });
    }

    // Checkbox click
    const checkbox = card.querySelector('.card-checkbox');
    checkbox.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleSelect(idx, checkbox, card);
    });

    // Download button click
    const dlBtn = card.querySelector('.card-download');
    dlBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        downloadSingle(match.drive_id, match.filename);
    });

    // Card click → toggle select
    card.addEventListener('click', () => {
        toggleSelect(idx, checkbox, card);
    });

    return card;
}

function toggleSelect(idx, checkbox, card) {
    if (selectedCards.has(idx)) {
        selectedCards.delete(idx);
        checkbox.classList.remove('checked');
        card.classList.remove('selected');
    } else {
        selectedCards.add(idx);
        checkbox.classList.add('checked');
        card.classList.add('selected');
    }
    updateDownloadBtn();
}


// ─── Selection & Download ─────────────────────────────────

btnSelectAll.addEventListener('click', () => {
    const allSelected = selectedCards.size === currentMatches.length;
    const cards = resultsGrid.querySelectorAll('.result-card');

    cards.forEach((card, idx) => {
        const checkbox = card.querySelector('.card-checkbox');
        if (allSelected) {
            selectedCards.delete(idx);
            checkbox.classList.remove('checked');
            card.classList.remove('selected');
        } else {
            selectedCards.add(idx);
            checkbox.classList.add('checked');
            card.classList.add('selected');
        }
    });

    btnSelectAll.textContent = allSelected ? 'Select All' : 'Deselect All';
    updateDownloadBtn();
});

function updateDownloadBtn() {
    const count = selectedCards.size;
    btnDownloadSelected.disabled = count === 0;

    const label = count > 0 ? `Download (${count})` : 'Download Selected';
    const svg = btnDownloadSelected.querySelector('svg');
    btnDownloadSelected.textContent = '';
    if (svg) btnDownloadSelected.appendChild(svg);
    btnDownloadSelected.appendChild(document.createTextNode(' ' + label));
}

btnDownloadSelected.addEventListener('click', () => {
    selectedCards.forEach(idx => {
        const match = currentMatches[idx];
        if (match) {
            downloadSingle(match.drive_id, match.filename);
        }
    });
});

async function downloadSingle(driveId, filename) {
    try {
        const res = await authFetch(`${API_BASE}/download/${driveId}`);
        if (!res.ok) throw new Error('Download failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || 'photo.jpg';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (err) {
        showError('Download failed: ' + err.message);
    }
}


// ─── Status Panel ─────────────────────────────────────────

btnStatus.addEventListener('click', () => {
    statusPanel.classList.toggle('hidden');
    if (!statusPanel.classList.contains('hidden')) {
        fetchStatus();
    }
});

async function fetchStatus() {
    try {
        const res = await authFetch(`${API_BASE}/status`);
        const data = await res.json();

        document.getElementById('stat-total').textContent = data.total_images || 0;
        document.getElementById('stat-processed').textContent = data.processed_images || 0;
        document.getElementById('stat-faces').textContent = data.total_faces || 0;

        const lastSync = data.last_sync
            ? new Date(data.last_sync).toLocaleString()
            : 'Never';
        document.getElementById('stat-sync').textContent = lastSync;

        if (data.is_syncing) {
            syncProgress.classList.remove('hidden');
            const pct = Math.round((data.sync_progress || 0) * 100);
            progressFill.style.width = pct + '%';
            progressText.textContent = `Syncing... ${pct}%`;
        } else {
            syncProgress.classList.add('hidden');
        }

    } catch (err) {
        console.error('Failed to fetch status:', err);
    }
}


// ─── Sync Trigger ─────────────────────────────────────────

btnSync.addEventListener('click', async () => {
    btnSync.disabled = true;
    btnSync.style.opacity = '0.5';

    try {
        const res = await authFetch(`${API_BASE}/sync?incremental=true`, { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            statusPanel.classList.remove('hidden');
            syncProgress.classList.remove('hidden');
            startStatusPolling();
        } else {
            showError(data.message || 'Sync failed to start');
        }

    } catch (err) {
        showError('Failed to start sync. Is the backend running?');
    }

    setTimeout(() => {
        btnSync.disabled = false;
        btnSync.style.opacity = '1';
    }, 3000);
});

function startStatusPolling() {
    if (statusPollInterval) clearInterval(statusPollInterval);

    statusPollInterval = setInterval(async () => {
        try {
            const res = await authFetch(`${API_BASE}/status`);
            const data = await res.json();

            document.getElementById('stat-total').textContent = data.total_images || 0;
            document.getElementById('stat-processed').textContent = data.processed_images || 0;
            document.getElementById('stat-faces').textContent = data.total_faces || 0;

            if (data.is_syncing) {
                const pct = Math.round((data.sync_progress || 0) * 100);
                progressFill.style.width = pct + '%';
                progressText.textContent = `Syncing... ${pct}%`;
            } else {
                syncProgress.classList.add('hidden');
                clearInterval(statusPollInterval);
                statusPollInterval = null;
                fetchStatus();
            }

        } catch (err) {
            console.error('Poll error:', err);
        }
    }, 2000);
}


// ─── Helpers ──────────────────────────────────────────────

function showLoading() { loadingEl.classList.remove('hidden'); }
function hideLoading() { loadingEl.classList.add('hidden'); }
function showError(msg) {
    errorText.textContent = msg;
    errorMsg.classList.remove('hidden');
}
function hideError() { errorMsg.classList.add('hidden'); }


// ─── Init ─────────────────────────────────────────────────

(async function init() {
    try {
        // Check if auth is required
        const res = await fetch(`${API_BASE}/auth/check`, {
            headers: getAuthHeaders()
        });
        const data = await res.json();

        if (data.auth_required && !data.authenticated) {
            showLoginScreen();
        }

        console.log('✅ FaceFind connected');
    } catch {
        console.warn('⚠️ Backend not reachable. Start it with: cd backend && python main.py');
    }
})();
