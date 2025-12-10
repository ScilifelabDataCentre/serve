import requests

def transform_to_invenio_metadata(schema_org_data):
    """Transform Schema.org JSON-LD to InvenioRDM metadata format"""
    
    # Extract data from Schema.org format
    metadata = {
        "access": {
            "record": "public",
            "files": "public"
        },
        "files": {
            "enabled": False
        },
        "metadata": {
            "title": "Serve " + schema_org_data["name"] + " of the App: '" + schema_org_data["hasPart"][0]['name'] + "'",
            "description": schema_org_data["description"],
            "publication_date": schema_org_data["dateCreated"][:10],  # Extract YYYY-MM-DD
            "publisher": schema_org_data["creator"]["name"],
            "resource_type": {"id": "dataset"},
            "creators": [
                {
                    "person_or_org": {
                        "name": schema_org_data["creator"]["name"],
                        "type": "organizational"
                    }
                }
            ],
            "contributors": [],
            "rights": [
                {
                    "id": "cc-by-4.0",
                    "title": {"en": "Creative Commons Attribution 4.0 International"},
                    "description": {"en": "The Creative Commons Attribution license allows re-distribution and re-use of a licensed work on the condition that the creator is appropriately credited."},
                    "link": "https://creativecommons.org/licenses/by/4.0/"
                }
            ],
            "additional_descriptions": [
                {
                    "description": f"Application deployment metadata for SciLifeLab Serve platform. Contains details about software applications and project configuration.",
                    "type": {"id": "technical-info"}
                }
            ],
            "subjects": [
                {"subject": "Scientific Computing"},
                {"subject": "Cloud Deployment"},
                {"subject": "Kubernetes"}
            ]
        }
    }
    
    # Add software application details as custom fields
    if "hasPart" in schema_org_data and len(schema_org_data["hasPart"]) > 0:
        app_data = schema_org_data["hasPart"][0]
        
        metadata["metadata"]["custom_fields"] = {
            "kcr:application_deployment": {
                "software_application": {
                    "name": app_data.get("name", ""),
                    "description": app_data.get("description", ""),
                    "version": app_data.get("softwareVersion", ""),
                    "url": app_data.get("url", ""),
                    "application_category": app_data.get("applicationCategory", ""),
                    "operating_system": app_data.get("operatingSystem", ""),
                    "code_repository": app_data.get("hasPart", {}).get("codeRepository", "")
                },
                "resource_requirements": {},
                "project_metadata": {}
            }
        }
        
        # Extract resource requirements from additionalProperty
        if "additionalProperty" in app_data:
            for prop in app_data["additionalProperty"]:
                prop_name = prop.get("name", "")
                prop_value = prop.get("value", "")
                if "cpu" in prop_name.lower():
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["resource_requirements"][prop_name] = prop_value
                elif "memory" in prop_name.lower():
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["resource_requirements"][prop_name] = prop_value
                elif "storage" in prop_name.lower():
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["resource_requirements"][prop_name] = prop_value
                elif "app" in prop_name.lower():
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["resource_requirements"][prop_name] = prop_value
        
        # Add project metadata
        if "about" in schema_org_data:
            project_data = schema_org_data["about"]
            metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["project_metadata"] = {
                "project_name": project_data.get("name", ""),
                "project_description": project_data.get("description", ""),
                "services": {}
            }
            
            # Extract service counts
            if "additionalProperty" in project_data:
                for prop in project_data["additionalProperty"]:
                    service_name = prop.get("name", "")
                    service_count = prop.get("value", "0")
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["project_metadata"]["services"][service_name] = service_count
    
    return metadata

def create_and_publish_record_on_invenio(record_data):
    
    # Configuration
    BASE_URL = "https://invenio-dev.serve-dev.scilifelab.se/api"
    TOKEN = "G07mW5y9ZvTcCu3Yq8XRLqckxUZpsKGeNFB07Bz1LSaqc1ZekRF3aO8eR5T6"
    HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
    }

    # Disable SSL verification for local testing (-k in cURL)
    session = requests.Session()
    #session.verify = False

    # Step 1: Create the draft record
    create_url = f"{BASE_URL}/records"
    response = session.post(create_url, headers=HEADERS, json=record_data)
    
    if response.status_code != 201:
        print(f"Failed to create draft: {response.text}")
        return None

    # Extract record ID from response
    record_id = response.json().get('id')
    print(f"Created draft record: {record_id}")

    # Step 2: Publish the draft
    publish_url = f"{BASE_URL}/records/{record_id}/draft/actions/publish"
    publish_response = session.post(publish_url, headers=HEADERS)

    if publish_response.status_code == 202:
        print("Record published successfully!")
        return record_id
    else:
        print(f"Failed to publish: {publish_response.text}")
        return None