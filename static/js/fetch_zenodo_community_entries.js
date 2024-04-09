document.addEventListener('DOMContentLoaded', function() {
    const communityId = document.getElementById('zenodo-entries').getAttribute('data-community-id');
    const apiUrl = `https://zenodo.org/api/records?communities=${communityId}&sort=mostrecent&size=30`;
    const entriesLoading = document.getElementById('zenodo-entries-loading');

    fetch(apiUrl)
        .then(response => {
            if (!response.ok) {
                entriesLoading.style.display = "none";
                throw new Error(`Fetching Zenodo entries failed. HTTP error, status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const totalEntries = data.hits.total;
            if (totalEntries === 0) {
                // Check if no entries are found
                throw new Error('No entries found for the specified community ID.');
            } else if (totalEntries > 1000) {
                // When the community is not found, Zenodo returns all entries by default. To figure out that this happened, I check if the number of entries is unreasonably high.
                throw new Error('Seems like there is no community with the specified ID on Zenodo.');
            }
            else {
                // Otherwise display the number of entries found
                document.getElementById('zenodo-entries-total').innerHTML = `${totalEntries}`;
            }

            const entries = data.hits.hits;
            const container = document.getElementById('zenodo-entries');
            entries.forEach(entry => {
                const card = document.createElement('div');
                card.className = 'card shadow mb-3';
                card.innerHTML = `
                    <div class="card-header">
                        <span class="badge text-bg-secondary">${entry.metadata.publication_date}</span>
                        <span class="badge text-bg-warning">${entry.metadata.resource_type.title}</span>
                    </div>
                    <div class="card-body">
                      <h5 class="card-title"><a href="https://zenodo.org/record/${entry.id}" target="_blank">${entry.metadata.title}</a></h5>
                      <p class="text-muted">${entry.metadata.creators.map(creator => creator.name).join('; ')}</p>
                      <p class="card-text">${entry.metadata.description}</p>
                    </div>
                `;
                container.appendChild(card);
            });
            entriesLoading.style.display = "none";
        })
        .catch(error => {
            entriesLoading.style.display = "none";
            document.getElementById('zenodo-entries').innerHTML = `<div class="alert alert-danger" role="alert">Fetching Zenodo entries failed. ${error.message}</div>`;
        });
});
