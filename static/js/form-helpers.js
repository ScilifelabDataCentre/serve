window.onload = (event) => {
    const email = document.getElementById('id_email');
    const request_account_field = document.getElementById('id_request_account_info');
    const request_account_label = document.querySelector('label[for="id_why_account_needed"]');
    const department_label = document.querySelector('label[for="id_department"]');

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
            const domain = match[1];
            shouldHide = true;
            department_label.classList.add('required');
        } else {
            department_label.classList.remove('required');
        }

        if (request_account_field){ // to prevent Uncaught TypeError for null value
            if (shouldHide) {
                request_account_field.classList.add('hidden');
            } else {
                request_account_field.classList.remove('hidden');
                request_account_label.classList.add('required');
            }
        }
    }

    if (request_account_field){ // to prevent Uncaught TypeError for null value
        // Temporarily disable transitions
        request_account_field.style.transition = 'none';

        changeVisibility();

        // Restore transitions after a short delay
        setTimeout(() => {
            request_account_field.style.transition = '';
        }, 50);
    }

    email.addEventListener('input', changeVisibility);
};

// Organization auto-complete with strict ROR validation
document.addEventListener('DOMContentLoaded', function() {
    const orgInput = document.getElementById('organization-autocomplete');
    const orgDataInput = document.getElementById('organization-data');
    const suggestionsDiv = document.getElementById('organization-suggestions');

    // Exit early if organization elements don't exist or input is disabled
    if (!orgInput || !orgDataInput || !suggestionsDiv || orgInput.disabled) {
        return;
    }

    const form = orgInput.closest('form');
    let selectedOrgData = null;
    let debounceTimer;

    // On page load: if there's organization data from server, parse it
    if (orgDataInput.value) {
        try {
            selectedOrgData = JSON.parse(orgDataInput.value);
        } catch (e) {
            console.error('Failed to parse organization data:', e);
        }
    }

    let isValidSelection = !!selectedOrgData;

    // Create error message element
    const errorDiv = document.createElement('div');
    errorDiv.id = 'validation_organization_custom';
    errorDiv.className = 'pt-1 text-warning';
    errorDiv.style.display = 'none';
    orgInput.parentNode.insertBefore(errorDiv, orgInput.nextSibling);

    function showError(message) {
        errorDiv.innerHTML = `<p class="m-0">${message}</p>`;
        errorDiv.style.display = 'block';
        //orgInput.classList.add('is-invalid');
        isValidSelection = false;
    }

    function clearError() {
        errorDiv.style.display = 'none';
        orgInput.classList.remove('is-invalid');
        isValidSelection = true;
    }

    function verifyOrganization(orgName) {
        if (!orgName.trim()) {
            clearError();
            return Promise.resolve(false);
        }

        return fetch(`/api/ror-autocomplete/?query=${encodeURIComponent(orgName)}`)
            .then(response => response.json())
            .then(data => {
                if (data.results && data.results.length > 0) {
                    const exactMatch = data.results.find(org =>
                        org.title.toLowerCase() === orgName.toLowerCase()
                    );

                    if (exactMatch) {
                        selectedOrgData = {
                            title: exactMatch.title,
                            ror_id: exactMatch.ror_id
                        };
                        orgDataInput.value = JSON.stringify(selectedOrgData);
                        orgInput.value = exactMatch.title;
                        isValidSelection = true;
                        clearError();
                        return true;
                    } else {
                        showError(
                            'Your organization name does not match the ROR list. Please select from the suggestions. ' +
                            '<a href="https://ror.org/search" target="_blank" rel="noopener">Search ROR registry</a>'
                        );
                        return false;
                    }
                } else {
                    showError(
                        'Organization not found in ROR registry. Please verify the name and select from suggestions. ' +
                        '<a href="https://ror.org/search" target="_blank" rel="noopener">Search ROR registry</a>'
                    );
                    return false;
                }
            })
            .catch(error => {
                console.error('ROR verification error:', error);
                showError('Unable to verify organization.');
                return false;
            });
    }

    setTimeout(() => {
        if (orgInput.value.trim() && !isValidSelection) {
            verifyOrganization(orgInput.value.trim());
        }
    }, 100);

    orgInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        const query = this.value.trim();

        if (!selectedOrgData || query !== selectedOrgData.title) {
            isValidSelection = false;
            selectedOrgData = null;
            orgDataInput.value = '';
        }

        if (query.length < 2) {
            suggestionsDiv.style.display = 'none';
            return;
        }

        debounceTimer = setTimeout(() => {
            fetch(`/api/ror-autocomplete/?query=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    suggestionsDiv.innerHTML = '';

                    if (data.results && data.results.length > 0) {
                        data.results.forEach(org => {
                            const item = document.createElement('a');
                            item.href = '#';
                            item.className = 'list-group-item list-group-item-action';
                            item.textContent = org.title;
                            item.addEventListener('click', (e) => {
                                e.preventDefault();
                                orgInput.value = org.title;
                                selectedOrgData = {
                                    title: org.title,
                                    ror_id: org.ror_id
                                };
                                orgDataInput.value = JSON.stringify(selectedOrgData);
                                isValidSelection = true;
                                clearError();
                                suggestionsDiv.style.display = 'none';
                            });
                            suggestionsDiv.appendChild(item);
                        });
                        suggestionsDiv.style.display = 'block';
                    } else {
                        suggestionsDiv.style.display = 'none';
                    }
                })
                .catch(error => {
                    console.error('ROR autocomplete error:', error);
                    suggestionsDiv.style.display = 'none';
                });
        }, 300);
    });

    orgInput.addEventListener('blur', function() {
        setTimeout(() => {
            const inputValue = orgInput.value.trim();

            if (inputValue && !isValidSelection) {
                verifyOrganization(inputValue);
            }

            suggestionsDiv.style.display = 'none';
        }, 200);
    });

    orgInput.addEventListener('focus', function() {
        if (!isValidSelection) {
            selectedOrgData = null;
        }
    });

    form.addEventListener('submit', function(e) {
        const inputValue = orgInput.value.trim();

        if (inputValue && !isValidSelection) {
            // Submit even when ROR is invalid
            showError(
                'No match found in ROR registry. You can still register, but please double-check your organization name. ' +
                '<a href="https://ror.org/search" target="_blank" rel="noopener">Search ROR registry</a>'
            );
        } else {
            clearError();
        }
    });
});
