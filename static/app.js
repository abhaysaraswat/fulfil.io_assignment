// Global state
let currentPage = 1;
let selectedFile = null;

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    setupTabs();
    loadProducts();
    setupSearch();
});

// Tab navigation
function setupTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(`${tabName}-tab`).classList.add('active');

    // Load data for the tab
    if (tabName === 'products') loadProducts();
    if (tabName === 'webhooks') loadWebhooks();
}

// Products
async function loadProducts(page = 1) {
    const search = document.getElementById('search').value;
    const activeOnly = document.getElementById('filter-active').checked;

    let url = `/api/products?page=${page}&page_size=50`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (activeOnly) url += `&active=true`;

    try {
        const response = await fetch(url);
        const data = await response.json();

        renderProducts(data.items);
        renderPagination(data.page, data.pages);
        currentPage = page;
    } catch (error) {
        showToast('Failed to load products', 'error');
    }
}

function renderProducts(products) {
    const tbody = document.getElementById('products-tbody');

    if (products.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading">No products found</td></tr>';
        return;
    }

    tbody.innerHTML = products.map(product => `
        <tr>
            <td><strong>${escapeHtml(product.sku)}</strong></td>
            <td>${escapeHtml(product.name)}</td>
            <td>${escapeHtml((product.description || '').substring(0, 50))}${product.description && product.description.length > 50 ? '...' : ''}</td>
            <td><span class="badge ${product.active ? 'badge-success' : 'badge-secondary'}">${product.active ? 'Active' : 'Inactive'}</span></td>
            <td>
                <button class="btn btn-small btn-primary" onclick="editProduct(${product.id})">Edit</button>
                <button class="btn btn-small btn-danger" onclick="deleteProduct(${product.id}, '${escapeHtml(product.sku)}')">Delete</button>
            </td>
        </tr>
    `).join('');
}

function renderPagination(current, total) {
    const container = document.getElementById('pagination');
    const buttons = [];

    // Previous button
    buttons.push(`<button onclick="loadProducts(${current - 1})" ${current === 1 ? 'disabled' : ''}>Previous</button>`);

    // Page numbers (show 5 pages max)
    const start = Math.max(1, current - 2);
    const end = Math.min(total, start + 4);

    for (let i = start; i <= end; i++) {
        buttons.push(`<button onclick="loadProducts(${i})" class="${i === current ? 'active' : ''}">${i}</button>`);
    }

    // Next button
    buttons.push(`<button onclick="loadProducts(${current + 1})" ${current === total ? 'disabled' : ''}>Next</button>`);

    container.innerHTML = buttons.join('');
}

function setupSearch() {
    const searchInput = document.getElementById('search');
    const activeFilter = document.getElementById('filter-active');

    let debounceTimer;
    searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => loadProducts(1), 500);
    });

    activeFilter.addEventListener('change', () => loadProducts(1));
}

// Product Modal
function openProductModal(product = null) {
    const modal = document.getElementById('product-modal');
    const form = document.getElementById('product-form');

    if (product) {
        document.getElementById('modal-title').textContent = 'Edit Product';
        document.getElementById('product-id').value = product.id;
        document.getElementById('sku').value = product.sku;
        document.getElementById('name').value = product.name;
        document.getElementById('description').value = product.description || '';
        document.getElementById('active').checked = product.active;
    } else {
        document.getElementById('modal-title').textContent = 'New Product';
        form.reset();
        document.getElementById('product-id').value = '';
    }

    modal.classList.add('show');
}

function closeProductModal() {
    document.getElementById('product-modal').classList.remove('show');
}

async function editProduct(id) {
    try {
        const response = await fetch(`/api/products/${id}`);
        const product = await response.json();
        openProductModal(product);
    } catch (error) {
        showToast('Failed to load product', 'error');
    }
}

async function saveProduct(event) {
    event.preventDefault();

    const id = document.getElementById('product-id').value;
    const data = {
        sku: document.getElementById('sku').value,
        name: document.getElementById('name').value,
        description: document.getElementById('description').value || null,
        active: document.getElementById('active').checked
    };

    try {
        const url = id ? `/api/products/${id}` : '/api/products';
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save product');
        }

        showToast(id ? 'Product updated successfully' : 'Product created successfully', 'success');
        closeProductModal();
        loadProducts(currentPage);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function deleteProduct(id, sku) {
    const confirmed = await showConfirm(
        'Delete Product',
        `Are you sure you want to delete product "${sku}"?`
    );
    if (!confirmed) return;

    try {
        const response = await fetch(`/api/products/${id}`, { method: 'DELETE' });

        if (!response.ok) throw new Error('Failed to delete product');

        showToast('Product deleted successfully', 'success');
        loadProducts(currentPage);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function confirmBulkDelete() {
    const confirmed = await showConfirm(
        'Delete All Products',
        'Are you sure you want to delete ALL products? This cannot be undone!'
    );
    if (!confirmed) return;

    const doubleConfirm = await showConfirm(
        'Final Confirmation',
        'This will permanently delete all products. Are you absolutely sure?'
    );
    if (!doubleConfirm) return;

    try {
        const response = await fetch('/api/products/bulk/all', { method: 'DELETE' });
        const result = await response.json();

        showToast(`Successfully deleted ${result.deleted_count} products`, 'success');
        loadProducts(1);
    } catch (error) {
        showToast('Failed to delete products', 'error');
    }
}

// CSV Upload
function handleFileSelect(event) {
    selectedFile = event.target.files[0];
    if (selectedFile) {
        document.getElementById('file-name').textContent = selectedFile.name;
        document.getElementById('upload-btn').disabled = false;
    }
}

async function uploadCSV() {
    if (!selectedFile) return;

    const uploadBtn = document.getElementById('upload-btn');
    const progressContainer = document.getElementById('progress-container');
    const resultDiv = document.getElementById('upload-result');

    uploadBtn.disabled = true;
    progressContainer.style.display = 'block';
    resultDiv.style.display = 'none';

    try {
        // Direct upload with FormData
        updateProgress(10, 'Uploading file...');

        const formData = new FormData();
        formData.append('file', selectedFile);

        const uploadResponse = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!uploadResponse.ok) {
            const errorData = await uploadResponse.json();
            throw new Error(errorData.detail || 'Failed to upload file');
        }

        const uploadResult = await uploadResponse.json();
        const jobId = uploadResult.job_id;

        updateProgress(30, 'File uploaded, starting processing...');

        // Track progress via SSE (starts automatically after upload)
        trackUploadProgress(jobId);

    } catch (error) {
        uploadBtn.disabled = false;
        resultDiv.className = 'result error';
        resultDiv.textContent = error.message;
        resultDiv.style.display = 'block';
        progressContainer.style.display = 'none';
    }
}

function trackUploadProgress(jobId) {
    // Use polling only - no SSE to avoid timeout issues
    pollUploadProgress(jobId);
}

async function pollUploadProgress(jobId) {
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`/api/upload/${jobId}`);
            const data = await response.json();

            if (data.status === 'completed') {
                clearInterval(interval);
                updateProgress(100, 'Import complete!');
                showUploadResult(true, `Successfully imported products`);
                document.getElementById('upload-btn').disabled = false;
                loadProducts(1);
            } else if (data.status === 'failed') {
                clearInterval(interval);

                // Get error message from backend (or default)
                const errorMsg = data.error_message || 'Unknown error occurred';

                // CRITICAL: Hide progress bar explicitly
                document.getElementById('progress-container').style.display = 'none';

                // CRITICAL: Show error result with explicit DOM manipulation
                const resultDiv = document.getElementById('upload-result');
                resultDiv.className = 'result error';
                resultDiv.textContent = `Import failed: ${errorMsg}`;
                resultDiv.style.display = 'block';

                // Re-enable upload button for retry
                document.getElementById('upload-btn').disabled = false;

                // Reset file input to allow retry
                document.getElementById('csv-file').value = '';
                selectedFile = null;
                document.getElementById('file-name').textContent = 'Choose CSV file...';
            } else if (data.total_rows > 0) {
                // Map processing to 30-100% range (upload already used 0-30%)
                const percent = 30 + Math.round((data.processed_rows / data.total_rows) * 70);
                updateProgress(percent, `Processing: ${data.processed_rows.toLocaleString()} / ${data.total_rows.toLocaleString()} rows`);
            }
        } catch (error) {
            clearInterval(interval);
            showUploadResult(false, 'Failed to track progress');
        }
    }, 2000);
}

function updateProgress(percent, text) {
    document.getElementById('progress-fill').style.width = `${percent}%`;
    document.getElementById('progress-text').textContent = text;
}

function showUploadResult(success, message) {
    const resultDiv = document.getElementById('upload-result');
    resultDiv.className = `result ${success ? 'success' : 'error'}`;
    resultDiv.textContent = message;
    resultDiv.style.display = 'block';

    if (success) {
        setTimeout(() => {
            document.getElementById('progress-container').style.display = 'none';
        }, 3000);
    }
}

// Webhooks
async function loadWebhooks() {
    try {
        const response = await fetch('/api/webhooks');
        const webhooks = await response.json();
        renderWebhooks(webhooks);
    } catch (error) {
        showToast('Failed to load webhooks', 'error');
    }
}

function renderWebhooks(webhooks) {
    const tbody = document.getElementById('webhooks-tbody');

    if (webhooks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="loading">No webhooks configured</td></tr>';
        return;
    }

    tbody.innerHTML = webhooks.map(webhook => `
        <tr>
            <td>${escapeHtml(webhook.url)}</td>
            <td><code>${webhook.event_type}</code></td>
            <td><span class="badge ${webhook.enabled ? 'badge-success' : 'badge-secondary'}">${webhook.enabled ? 'Enabled' : 'Disabled'}</span></td>
            <td>
                <button class="btn btn-small btn-primary" onclick="testWebhook(${webhook.id})">Test</button>
                <button class="btn btn-small btn-primary" onclick="editWebhook(${webhook.id})">Edit</button>
                <button class="btn btn-small btn-danger" onclick="deleteWebhook(${webhook.id})">Delete</button>
            </td>
        </tr>
    `).join('');
}

function openWebhookModal(webhook = null) {
    const modal = document.getElementById('webhook-modal');
    const form = document.getElementById('webhook-form');

    if (webhook) {
        document.getElementById('webhook-modal-title').textContent = 'Edit Webhook';
        document.getElementById('webhook-id').value = webhook.id;
        document.getElementById('webhook-url').value = webhook.url;
        document.getElementById('event-type').value = webhook.event_type;
        document.getElementById('webhook-enabled').checked = webhook.enabled;
    } else {
        document.getElementById('webhook-modal-title').textContent = 'New Webhook';
        form.reset();
        document.getElementById('webhook-id').value = '';
    }

    modal.classList.add('show');
}

function closeWebhookModal() {
    document.getElementById('webhook-modal').classList.remove('show');
}

async function editWebhook(id) {
    try {
        const response = await fetch(`/api/webhooks/${id}`);
        const webhook = await response.json();
        openWebhookModal(webhook);
    } catch (error) {
        showToast('Failed to load webhook', 'error');
    }
}

async function saveWebhook(event) {
    event.preventDefault();

    const id = document.getElementById('webhook-id').value;
    const data = {
        url: document.getElementById('webhook-url').value,
        event_type: document.getElementById('event-type').value,
        enabled: document.getElementById('webhook-enabled').checked
    };

    try {
        const url = id ? `/api/webhooks/${id}` : '/api/webhooks';
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) throw new Error('Failed to save webhook');

        showToast(id ? 'Webhook updated' : 'Webhook created', 'success');
        closeWebhookModal();
        loadWebhooks();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function testWebhook(id) {
    try {
        const response = await fetch(`/api/webhooks/${id}/test`, { method: 'POST' });
        const result = await response.json();

        if (response.ok) {
            showToast(`Webhook test successful (Status: ${result.status_code})`, 'success');
        } else {
            showToast(`Webhook test failed: ${result.error}`, 'error');
        }
    } catch (error) {
        showToast('Failed to test webhook', 'error');
    }
}

async function deleteWebhook(id) {
    if (!confirm('Are you sure you want to delete this webhook?')) return;

    try {
        const response = await fetch(`/api/webhooks/${id}`, { method: 'DELETE' });

        if (!response.ok) throw new Error('Failed to delete webhook');

        showToast('Webhook deleted', 'success');
        loadWebhooks();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// Utility functions
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function showConfirm(title, message) {
    return new Promise((resolve) => {
        document.getElementById('confirm-title').textContent = title;
        document.getElementById('confirm-message').textContent = message;
        document.getElementById('confirm-modal').classList.add('show');

        window.confirmResolve = resolve;
    });
}

function closeConfirmModal(confirmed) {
    document.getElementById('confirm-modal').classList.remove('show');
    if (window.confirmResolve) {
        window.confirmResolve(confirmed);
        window.confirmResolve = null;
    }
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}
