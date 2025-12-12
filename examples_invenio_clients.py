import time

from invenio_client.invenio_client import InvenioClient, transform_to_invenio_metadata

schema_org_metadata = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    "name": "Application Deployment Metadata",
    "description": "Structured metadata for applications, users, and projects deployed on the SciLifeLab Serve platform (https://serve.scilifelab.se/).",
    "dateCreated": "2025-12-11T10:53:26.264196+00:00",
    "creator": {"@type": "Organization", "name": "SciLifeLab Data Centre", "url": "https://www.scilifelab.se/data"},
    "hasPart": [
        {
            "@type": "SoftwareApplication",
            "name": "test",
            "description": "desc",
            "url": "https://test.studio.127.0.0.1.nip.io",
            "softwareVersion": "ghcr.io/scilifelabdatacentre/serve-charts/custom-app:1.1.4",
            "author": {
                "@type": "Person",
                "name": " ",
                "email": "admin@serve.scilifelab.se",
                "affiliation": {
                    "@type": "Organization",
                    "additionalProperty": {"@type": "PropertyValue", "name": "department"},
                },
            },
            "applicationCategory": "Cloud Application",
            "operatingSystem": "Kubernetes",
            "additionalProperty": [
                {
                    "@type": "PropertyValue",
                    "name": "appImage",
                    "value": "ghcr.io/srijitseal/dili_predictor:20240606-203146",
                },
                {"@type": "PropertyValue", "name": "appCreated", "value": "2025-11-27T12:24:21.003607+00:00"},
                {"@type": "PropertyValue", "name": "appUpdated", "value": "2025-11-27T12:30:30.071306+00:00"},
                {"@type": "PropertyValue", "name": "cpuRequest", "value": "100m"},
                {"@type": "PropertyValue", "name": "cpuLimit", "value": "2000m"},
                {"@type": "PropertyValue", "name": "memoryRequest", "value": "1Gi"},
                {"@type": "PropertyValue", "name": "memoryLimit", "value": "4Gi"},
                {"@type": "PropertyValue", "name": "storageRequest", "value": "100Mi"},
                {"@type": "PropertyValue", "name": "storageLimit", "value": "5000Mi"},
            ],
            "hasPart": {"@type": "SoftwareSourceCode", "codeRepository": "https://source.org"},
        }
    ],
    "about": {
        "@type": "Project",
        "name": "test",
        "description": "",
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "dateCreated", "value": "2025-11-18T12:29:51.674636+00:00"},
            {"@type": "PropertyValue", "name": "minio", "value": "1"},
            {"@type": "PropertyValue", "name": "mlflow", "value": "1"},
            {"@type": "PropertyValue", "name": "vscode", "value": "3"},
            {"@type": "PropertyValue", "name": "dashapp", "value": "10"},
            {"@type": "PropertyValue", "name": "mongodb", "value": "0"},
            {"@type": "PropertyValue", "name": "reducer", "value": "0"},
            {"@type": "PropertyValue", "name": "rstudio", "value": "3"},
            {"@type": "PropertyValue", "name": "combiner", "value": "0"},
            {"@type": "PropertyValue", "name": "depictio", "value": "1"},
            {"@type": "PropertyValue", "name": "shinyapp", "value": "10"},
            {"@type": "PropertyValue", "name": "customapp", "value": "10"},
            {"@type": "PropertyValue", "name": "netpolicy", "value": "0"},
            {"@type": "PropertyValue", "name": "volumeK8s", "value": "0"},
            {"@type": "PropertyValue", "name": "tissuumaps", "value": "1"},
            {"@type": "PropertyValue", "name": "filemanager", "value": "1"},
            {"@type": "PropertyValue", "name": "jupyter-lab", "value": "3"},
            {"@type": "PropertyValue", "name": "mlflow-serve", "value": "10"},
            {"@type": "PropertyValue", "name": "python-serve", "value": "10"},
            {"@type": "PropertyValue", "name": "mongo-express", "value": "0"},
            {"@type": "PropertyValue", "name": "pytorch-serve", "value": "10"},
            {"@type": "PropertyValue", "name": "shinyproxyapp", "value": "10"},
            {"@type": "PropertyValue", "name": "tensorflow-serve", "value": "10"},
        ],
        "funder": {"@type": "Person", "name": " ", "email": "admin@serve.scilifelab.se"},
        "parentOrganization": {
            "@type": "Organization",
            "additionalProperty": {"@type": "PropertyValue", "name": "department"},
        },
    },
}

# Initialize the InvenioRDM client
client = InvenioClient(
    base_url="https://invenio-dev.serve-dev.scilifelab.se",  # Base URL without /api
    token="G07mW5y9ZvTcCu3Yq8XRLqckxUZpsKGeNFB07Bz1LSaqc1ZekRF3aO8eR5T6",
    auth_scheme="Bearer",  # or "Token" depending on your server
    verify=True,  # Set to False if using self-signed certificates
)

try:
    invenio_data = transform_to_invenio_metadata(schema_org_metadata)

    # Extract the components
    metadata = invenio_data["metadata"]
    access = invenio_data.get("access")
    files = invenio_data.get("files")
    custom_fields = metadata.pop("custom_fields", None)

    # Add your own custom PID (if needed)
    pids = {"doi": {"identifier": "10.1234/custom.doi", "provider": "external"}}
    #'''
    print("\n=== PHASE 1: Create and publish initial record ===")
    # 1. Create a draft with custom PID
    print("\n1. Creating draft...")
    first_draft = client.create_draft(
        metadata=metadata,
        access=access,
        files=files,
        custom_fields=custom_fields,
        # pids=pids  # Optional: include your custom PID, need to activate it in invenio.cfg
    )

    print(f"Created draft with ID: {first_draft['id']}")

    # 2. Publish the draft
    print("\n2. Publishing draft...")
    published_record = client.publish_draft(first_draft["id"])
    print(f"Successfully published record with ID: {published_record['id']}")
    print(f"Title: {published_record['metadata']['title']}")

    published_record_id = published_record["id"]

    print("\n=== PHASE 2: Search and list operations ===")
    # 3. Search for records
    print("\n3. Searching for records...")
    search_results = client.search_records(query="SciLifeLab Serve", sort="newest", size=5)  # Search query
    print(f"Found {search_results.get('hits', {}).get('total', 0)} records")

    # 4. List user's records
    print("\n4. Listing user's records...")
    user_records = client.list_user_records(sort="newest", size=5)
    print(f"You have {user_records.get('hits', {}).get('total', 0)} records")

    print("\n=== PHASE 3: Edit current version (Version 1) ===")
    # 5. Edit the published record (creates a draft)
    print("\n5. Creating a draft from published record for editing...")
    second_draft = client.edit_published_record(published_record_id)
    print(f"Created draft for editing: {second_draft['id']}")

    # Get current draft to see what pids it has
    current_draft = client.get_draft(second_draft["id"])
    print(f"Current draft has pids: {current_draft.get('pids', {})}")

    # 6. Update the draft
    print("\n6. Updating the draft...")
    updated_draft = client.update_draft(
        record_id=second_draft["id"],
        metadata={**second_draft["metadata"], "title": f"{second_draft['metadata']['title']} - Updated"},
        # Include all required fields from current draft
        access=current_draft.get("access"),
        files={"enabled": False},  # Explicitly set for metadata-only
        custom_fields=current_draft.get("custom_fields"),
        pids=current_draft.get("pids", {}),
    )
    print(f"Updated draft title: {updated_draft['metadata']['title']}")

    # 7. Publish the updated draft
    print("\n7. Publishing the updated draft...")
    published_update = client.publish_draft(updated_draft["id"])
    print(f"Published update: {published_update['id']}")

    # Get the updated record
    final_record_id = published_update["id"]
    print(f"\nRetrieving final record {final_record_id}...")
    final_record = client.get_record(final_record_id)
    print(f"Final record title: {final_record['metadata']['title']}")

    print("\n=== PHASE 4: Create a new version (Version 2) ===")
    # 8. Create a new version of the record
    print("\n8. Creating a new version of the record...")
    new_version = client.create_new_version(final_record_id)
    print(f"Created new version draft with ID: {new_version['id']}")

    # Get the current new version draft to see all fields
    current_new_version_draft = client.get_draft(new_version["id"])
    print(f"New version draft metadata keys: {list(current_new_version_draft.get('metadata', {}).keys())}")

    # 9. Update the new version draft - need to add publication_date
    print("\n9. Updating the new version draft...")
    updated_new_version = client.update_draft(
        record_id=current_new_version_draft["id"],
        metadata={
            **current_new_version_draft["metadata"],
            "title": f"{current_new_version_draft['metadata']['title']} - Version 2",
            # when a new version is created, it has the publication_date and version removed
            # (as those are typically replaced in a new version)
            "publication_date": "2025-12-11",  # Add the publication date from the original schema_org_metadata
        },
        access=current_new_version_draft.get("access"),
        files={"enabled": False},  # Explicitly set for metadata-only
        custom_fields=current_new_version_draft.get("custom_fields"),
        pids=current_new_version_draft.get("pids", {}),
    )
    print(f"Updated new version draft: {updated_new_version['id']}")

    # 10. Publish the new version
    print("\n10. Publishing the new version...")
    published_new_version = client.publish_draft(updated_new_version["id"])
    print(f"Published new version: {published_new_version['id']}")
    print(f"New version title: {published_new_version['metadata']['title']}")

    #'''

    print("\n=== PHASE 5: Version management ===")

    new_version_id = published_new_version["id"]
    old_version_id = final_record_id

    """
    Invenio uses Elasticsearch.
    There is a common issue with Elasticsearch, called 'eventual consistency.'
    Read more: https://medium.com/@zvardhan26/the-sneaky-elasticsearch-surprise-that-broke-my-workflows-and-how-i-fixed-it-a704486b482e
    Because of this 'eventual consistency', there might be a delay in indexing this new published version.
    This means, the get_all_versions() method can provide incorrect result
    if we try to get all versions just right after creating it.
    We need to keep this in mind in case we expect something like this.

    Currently I am waiting 2 seconds to execute it and it gives the correct answer.
    If I don't use it, it will give wrong answer, 1 version instead of two.
    Feel free to try :)
    """
    time.sleep(2)

    # 11. Get all versions
    print("\n11. Getting all versions...")
    print("\nFirst, from the 2nd version id...")
    print(f"New version ID ({new_version_id}):")
    all_versions = client.get_all_versions(new_version_id)  # Use original record ID
    versions_total = all_versions.get("hits", {}).get("total", 0)
    print(f"Total versions: {versions_total}")

    # Print details of each version
    if "hits" in all_versions and "hits" in all_versions["hits"]:
        for i, hit in enumerate(all_versions["hits"]["hits"]):
            print(
                f"  Version {i+1}: ID={hit.get('id')}, Title={hit.get('metadata', {}).get('title')}, "
                f"Index={hit.get('versions', {}).get('index')}"
            )

    print("\nNow, from the first version id...")
    print(f"First version ID ({old_version_id}):")
    all_versions = client.get_all_versions(old_version_id)  # Use original record ID
    versions_total = all_versions.get("hits", {}).get("total", 0)
    print(f"Total versions: {versions_total}")

    # Print details of each version
    if "hits" in all_versions and "hits" in all_versions["hits"]:
        for i, hit in enumerate(all_versions["hits"]["hits"]):
            print(
                f"  Version {i+1}: ID={hit.get('id')}, Title={hit.get('metadata', {}).get('title')}, "
                f"Index={hit.get('versions', {}).get('index')}"
            )

    # 12. Get latest version
    print("\n12. Getting latest version...")
    print(f"Original record ({old_version_id}):")
    latest_version = client.get_latest_version(old_version_id)  # Use original record ID
    print(f"Latest version ID: {latest_version['id']}")
    print(f"Latest version title: {latest_version['metadata']['title']}")
    print(f"Version index: {latest_version.get('versions', {}).get('index')}")

    # 13. Also check the parent relationship
    print("\n13. Checking parent relationships...")
    original_record = client.get_record(old_version_id)
    new_version_record = client.get_record(new_version_id)

    print(f"Original record ({old_version_id}):")
    print(f"  Parent ID: {original_record.get('parent', {}).get('id', 'None')}")
    print(f"  Version index: {original_record.get('versions', {}).get('index')}")

    print(f"New version ({new_version_id}):")
    print(f"  Parent ID: {new_version_record.get('parent', {}).get('id', 'None')}")
    print(f"  Version index: {new_version_record.get('versions', {}).get('index')}")

    # Check if they share the same parent
    original_parent = original_record.get("parent", {}).get("id")
    new_version_parent = new_version_record.get("parent", {}).get("id")
    if original_parent and new_version_parent and original_parent == new_version_parent:
        print(f"\nBoth records share the same parent: {original_parent}")
        print("This means they are part of the same version history.")


except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
