window.onload = (event) => {
    const email = document.getElementById('id_email');
    const request_account_field = document.getElementById('id_request_account_info');
    const request_account_label = document.querySelector('label[for="id_why_account_needed"]');

    const domainRegex = /^(?:(?!\b(?:student|stud)\b\.)[A-Z0-9](?:[\.A-Z0-9-]{0,61}[A-Z0-9])?\.)*?(uu|lu|gu|su|umu|liu|ki|kth|chalmers|ltu|hhs|slu|kau|lth|lnu|oru|miun|mau|mdu|bth|fhs|gih|hb|du|hig|hh|hkr|his|hv|ju|sh|nrm)\.se$/i;

    function changeVisibility() {
        let shouldHide = false;
        let match;

        if (email.value == '') {
            match = false;
            shouldHide = true;
        } else {
            const lst = email.value.split('@');
            const domainName = lst[lst.length - 1].toLowerCase();
            match = domainRegex.exec(domainName);
        }

        if (match) {
            shouldHide = true;
        }

        if (request_account_field) {
            if (shouldHide) {
                request_account_field.classList.add('hidden');
            } else {
                request_account_field.classList.remove('hidden');
                if (request_account_label) request_account_label.classList.add('required');
            }
        }
    }

    if (request_account_field) {
        request_account_field.style.transition = 'none';
        changeVisibility();
        setTimeout(() => { request_account_field.style.transition = ''; }, 50);
    }

    if (email) email.addEventListener('input', changeVisibility);
};


// ============================================================
// Multi-affiliation management
// Replaces the single-org autocomplete block
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    const container = document.getElementById('affiliations-container');
    const hiddenInput = document.getElementById('affiliations-data');
    const addBtn = document.getElementById('add-affiliation-btn');

    // Exit if elements not found (e.g. admin pages)
    if (!container || !hiddenInput) return;

    // Parse initial affiliations from hidden input (set by server on GET or re-render)
    let affiliations = [];
    if (hiddenInput.value) {
        try {
            affiliations = JSON.parse(hiddenInput.value);
        } catch (e) {
            console.error('Failed to parse affiliations-data:', e);
        }
    }

    // Ensure at least one blank row
    if (!Array.isArray(affiliations) || affiliations.length === 0) {
        affiliations = [{ title: '', ror_id: '', department: '' }];
    }

    // --- Serialize all rows back to hidden input ---
    function serializeAffiliations() {
        const rows = container.querySelectorAll('.affiliation-row');
        const data = [];
        rows.forEach(row => {
            data.push({
                title: row.querySelector('.aff-org-input').value.trim(),
                ror_id: row.dataset.rorId || 'no ror',
                department: row.querySelector('.aff-dept-input').value.trim(),
            });
        });
        hiddenInput.value = JSON.stringify(data);
    }

    // Gives each row a unique id so its labels stay tied to their inputs.
    // Only increments, so removed rows never clash with new ones.
    let affiliationRowCount = 0;

    // --- Create one affiliation row ---
    function createRow(data) {
        const row = document.createElement('div');
        affiliationRowCount += 1;
        const rowId = `affiliation-${affiliationRowCount}`;
        const orgInputId = `${rowId}-organization`;
        const deptInputId = `${rowId}-department`;
        row.className = 'affiliation-row border rounded p-3 mb-2 bg-light position-relative';
        row.dataset.rorId = data.ror_id || '';

        row.innerHTML = `
            <div class="d-flex justify-content-end mb-1">
                <button type="button" class="btn btn-sm btn-outline-danger aff-remove-btn"
                        title="Remove affiliation">✕ Remove</button>
            </div>
            <div class="row">
                <div class="col-12 col-md-6 mb-2 mb-md-0">
                    <label class="form-label" for="${orgInputId}">Organization:</label>
                    <input type="text" class="form-control aff-org-input" id="${orgInputId}"
                           placeholder="Start typing organization name..."
                           autocomplete="off"
                           value="${escapeHtml(data.title || '')}">
                    <div class="aff-org-suggestions list-group position-absolute"
                         style="z-index: 1000; max-height: 300px; overflow-y: auto; display: none;"></div>
                    <div class="aff-ror-status mt-1" style="font-size: 0.75rem;"></div>
                </div>
                <div class="col-12 col-md-6">
                    <label class="form-label" for="${deptInputId}">Department:</label>
                    <input type="text" class="form-control aff-dept-input" id="${deptInputId}"
                           list="department-datalist"
                           placeholder="Select or enter department"
                           value="${escapeHtml(data.department || '')}">
                </div>
            </div>
        `;

        // --- ROR status indicator ---
        const statusEl = row.querySelector('.aff-ror-status');
        function updateRorStatus() {
            const ror = row.dataset.rorId;
            if (ror && ror !== 'no ror') {
                statusEl.innerHTML = `<a href="${escapeHtml(ror)}" target="_blank" rel="noopener" class="text-success text-decoration-none">✓ ROR: ${escapeHtml(ror)}</a>`;
            } else if (row.querySelector('.aff-org-input').value.trim()) {
                statusEl.innerHTML =
                    '<span style="color: #c28b00; font-size: 0.9rem;">Organization not found in ROR registry. Please verify the name and select from suggestions.</span><br>' +
                    '<a href="https://ror.org/search" target="_blank" rel="noopener" style="color: #00857c; font-size: 0.9rem;">Search ROR registry</a><br>' +
                    '<span style="color: #6c757d; font-size: 0.85rem;">Start typing to select your organization via ROR (Research Organization Registry).</span>';
            } else {
                statusEl.innerHTML = '';
            }
        }
        updateRorStatus();

        // --- ROR autocomplete on org input ---
        const orgInput = row.querySelector('.aff-org-input');
        const suggestions = row.querySelector('.aff-org-suggestions');
        let debounceTimer;

        orgInput.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            const query = this.value.trim();

            // Clear ROR selection when user edits
            row.dataset.rorId = '';
            updateRorStatus();
            serializeAffiliations();

            if (query.length < 2) {
                suggestions.style.display = 'none';
                return;
            }

            debounceTimer = setTimeout(() => {
                fetch(`/api/ror-autocomplete/?query=${encodeURIComponent(query)}`)
                    .then(r => r.json())
                    .then(data => {
                        suggestions.innerHTML = '';
                        if (data.results && data.results.length > 0) {
                            data.results.forEach(org => {
                                const item = document.createElement('a');
                                item.href = '#';
                                item.className = 'list-group-item list-group-item-action';
                                item.textContent = org.title;
                                item.addEventListener('click', (e) => {
                                    e.preventDefault();
                                    orgInput.value = org.title;
                                    row.dataset.rorId = org.ror_id;
                                    updateRorStatus();
                                    suggestions.style.display = 'none';
                                    serializeAffiliations();
                                });
                                suggestions.appendChild(item);
                            });
                            suggestions.style.display = 'block';
                        } else {
                            suggestions.style.display = 'none';
                        }
                    })
                    .catch(err => {
                        console.error('ROR autocomplete error:', err);
                        suggestions.style.display = 'none';
                    });
            }, 300);
        });

        // Verify on blur (soft — shows warning only)
        orgInput.addEventListener('blur', function() {
            setTimeout(() => {
                suggestions.style.display = 'none';
                if (orgInput.value.trim() && !row.dataset.rorId) {
                    // Attempt to find exact match
                    fetch(`/api/ror-autocomplete/?query=${encodeURIComponent(orgInput.value.trim())}`)
                        .then(r => r.json())
                        .then(data => {
                            if (data.results) {
                                const exact = data.results.find(
                                    o => o.title.toLowerCase() === orgInput.value.trim().toLowerCase()
                                );
                                if (exact) {
                                    row.dataset.rorId = exact.ror_id;
                                    orgInput.value = exact.title;
                                }
                            }
                            updateRorStatus();
                            serializeAffiliations();
                        })
                        .catch(() => { updateRorStatus(); serializeAffiliations(); });
                }
            }, 200);
        });

        // Department input change triggers serialization
        row.querySelector('.aff-dept-input').addEventListener('input', serializeAffiliations);

        // --- Remove button ---
        row.querySelector('.aff-remove-btn').addEventListener('click', function() {
            const allRows = container.querySelectorAll('.affiliation-row');
            if (allRows.length <= 1) {
                // Cannot remove last row — show error
                let errEl = container.querySelector('.aff-min-error');
                if (!errEl) {
                    errEl = document.createElement('div');
                    errEl.className = 'aff-min-error text-danger mb-2';
                    errEl.style.fontSize = '0.85rem';
                    errEl.textContent = 'At least one affiliation is required.';
                    container.prepend(errEl);
                }
                // Auto-hide after 3 seconds
                setTimeout(() => { if (errEl) errEl.remove(); }, 3000);
                return;
            }
            row.remove();
            serializeAffiliations();
        });

        return row;
    }

    // --- HTML escaping utility ---
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // --- Render initial rows ---
    affiliations.forEach(aff => {
        container.appendChild(createRow(aff));
    });
    serializeAffiliations();

    // --- Add affiliation button ---
    if (addBtn) {
        addBtn.addEventListener('click', function() {
            // Clear any "minimum 1" error
            const errEl = container.querySelector('.aff-min-error');
            if (errEl) errEl.remove();

            container.appendChild(createRow({ title: '', ror_id: '', department: '' }));
            serializeAffiliations();
        });
    }
});
