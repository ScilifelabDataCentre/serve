#!/bin/bash
# Dependencies: 1. jq for JSON parsing, 2. curl for HTTP requests

# Default configuration
DEFAULT_BASE_URL="https://serve-dev.scilifelab.se"
DEFAULT_USERS=1
DEFAULT_PROJECTS=1
DEFAULT_APPS=1

show_how_to() {

    echo ""
    echo "Usage: $0 [create] [user|project|app] [OPTIONS]"
    echo "Usage: $0 [delete] [user|project|all-users|all-projects] [OPTIONS]"
    echo "Options:"
    echo "  -s <SUPER-USER>    : If this flag is present, the operation creates a superuser (no value needed)."
    echo "  -b <URL>          : Base URL for the Studio API (default: ${DEFAULT_BASE_URL})"
    echo "  -c <CONFIG FILE>         : Path to a custom JSON config file"
    echo "  -u <USERS NUMBER>          : Number of users to create/delete (default: ${DEFAULT_USERS})"
    echo "  -p <PROJECTS NUMBER>          : Number of projects per user (default: ${DEFAULT_PROJECTS})"
    echo "  -a <APPS NUMBER>          : Number of apps per project (default: ${DEFAULT_APPS})"
    echo "  -S <APP-SLUG>         : Override base app slug"
    echo "  -O <APP-PORT>         : Override base app port"
    echo "  -i <APP-IMAGE>        : Override base app image"
    echo "  -N <TEST-PREFIX>       : Prefix for all generated names (e.g., 'mytest')"
    echo "  -v <VERBOSE-FLAG>     : If this flag is present, detail log will be shown (no value needed)."
    echo ""

}

# --- Hard-coded Default JSON Data ---
read -r -d '' HARDCODED_DEFAULT_JSON_DATA << 'EOF'
{
    "user_data": {
        "username": "django-endpoint-test-user",
        "password": "django-endpoint-test-user-password",
        "email": "django-endpoint-test-user@serve.scilifelab.se",
        "affiliation": "uu",
        "department": "django-endpoint-test-user-department-name",
        "first_name": "django-endpoint-test-user-first-name",
        "last_name": "django-endpoint-test-user-last-name"
    },
    "project_data": {
        "project_name": "django-endpoint-test-project-name",
        "project_description": "django-endpoint-test-project-description"
    },
    "app_data": {
        "app_slug": "dashapp",
        "name": "django-endpoint-test-app-name",
        "description": "django-endpoint-test-app-description",
        "access": "public",
        "port": 8000,
        "image": "ghcr.io/scilifelabdatacentre/example-dash:latest",
        "source_code_url": "https://django-endpoint-test-scilifelab.com"
    }
}
EOF
# --- End Hard-coded Default JSON Data ---

# Command-line parameters
NAME_PREFIX="" # Optional prefix for test-names
LATEST_BASE_URL=""
CONFIG_FILE="" # Optional external config file
USERS=""
PROJECTS=""
APPS=""
APP_SLUG_OVERRIDE=""
APP_PORT_OVERRIDE=""
APP_IMAGE_OVERRIDE=""
IS_SUPERUSER_FLAG=false
IS_VERBOSE_FLAG=false # flag for verbose logs

# This will be used for printing the full command later
FULL_COMMAND_LINE=("$0" "$@") # Capture $0 and all arguments

# extract ACTION and TARGET
ACTION="$1"
TARGET="$2"

# Validate that ACTION and TARGET are provided before shifting
if [ -z "${ACTION}" ] || [ -z "${TARGET}" ]; then
    show_how_to
    exit 1
fi

# Now, shift off the ACTION and TARGET so getopts only sees the options
shift 2

# Parse command-line options
while getopts ":b:c:u:p:a:sO:i:N:S:v" opt; do
  case ${opt} in
    b) LATEST_BASE_URL="${OPTARG}" ;;
    c) CONFIG_FILE="${OPTARG}" ;;
    u) USERS="${OPTARG}" ;;
    p) PROJECTS="${OPTARG}" ;;
    a) APPS="${OPTARG}" ;;
    s) IS_SUPERUSER_FLAG=true ;; # Flag for superuser, no argument
    O) APP_PORT_OVERRIDE="${OPTARG}" ;;
    i) APP_IMAGE_OVERRIDE="${OPTARG}" ;;
    N) NAME_PREFIX="${OPTARG}" ;;
    S) APP_SLUG_OVERRIDE="${OPTARG}" ;;
    v) IS_VERBOSE_FLAG=true ;; # Flag for verbose logs, no argument
    \?) echo "Invalid option: -${OPTARG}" >&2; show_how_to; exit 1 ;;
    :) echo "Option -${OPTARG} requires an argument." >&2; show_how_to; exit 1 ;;
  esac
done

# After getopts, shift any remaining processed options (should be none if options are last)
shift $((OPTIND-1))

# Check for unpermitted characters after action, target, and option(s)
if [ -n "$1" ]; then

    UNPERMITTED_INPUT="$*" # Join all remaining arguments into a single string

    # Use a regex to check if the string contains any non-whitespace character
    if [[ "${UNPERMITTED_INPUT}" =~ [^[:space:]] ]]; then
        echo "Error: Unpermitted character(s) '${UNPERMITTED_INPUT}' found"
        echo "You typed: '${FULL_COMMAND_LINE[*]}'"
        echo "Only spaces are allowed except the following:"
        show_how_to
        exit 1
    fi
fi

# Set defaults if not provided (these are now applied after options are parsed)
LATEST_BASE_URL=${LATEST_BASE_URL:-${DEFAULT_BASE_URL}}
USERS=${USERS:-${DEFAULT_USERS}}
PROJECTS=${PROJECTS:-${DEFAULT_PROJECTS}}
APPS=${APPS:-${DEFAULT_APPS}}

if [ "${IS_VERBOSE_FLAG}" = true ]; then
    echo "DEBUG: Using BASE_URL: ${LATEST_BASE_URL}"
    echo "DEBUG: Using NAME_PREFIX: '${NAME_PREFIX}'"
    echo "DEBUG: IS_SUPERUSER_FLAG: ${IS_SUPERUSER_FLAG}"
    echo "DEBUG: IS_VERBOSE_FLAG: ${IS_VERBOSE_FLAG}"
fi

# Check for jq dependency
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed. Please install jq first."
    exit 1
fi

# --- Determine JSON Data Source ---
LOCAL_JSON_SOURCE=""
if [ -n "${CONFIG_FILE}" ]; then
    if [ ! -f "${CONFIG_FILE}" ]; then
        echo "Error: Config file ${CONFIG_FILE} not found!"
        exit 1
    fi

    if [ "${IS_VERBOSE_FLAG}" = true ]; then
        echo "DEBUG: Using external config file: ${CONFIG_FILE}"
    fi

    LOCAL_JSON_SOURCE=$(cat "${CONFIG_FILE}")
else
    if [ "${IS_VERBOSE_FLAG}" = true ]; then
        echo "DEBUG: Using hard-coded default config."
    fi

    LOCAL_JSON_SOURCE="${HARDCODED_DEFAULT_JSON_DATA}"
fi

# Validate LOCAL_JSON_SOURCE before parsing
if ! echo "${LOCAL_JSON_SOURCE}" | jq -e . &>/dev/null; then
    echo "Error: The resolved JSON source is not valid JSON." >&2
    echo "Source content:" >&2
    echo "${LOCAL_JSON_SOURCE}" >&2
    exit 1
fi

# Read base JSON data (from chosen source)
BASE_USER_DATA=$(echo "${LOCAL_JSON_SOURCE}" | jq -c '.user_data // {}')
BASE_PROJECT_DATA=$(echo "${LOCAL_JSON_SOURCE}" | jq -c '.project_data // {}')
BASE_APP_DATA=$(echo "${LOCAL_JSON_SOURCE}" | jq -c '.app_data // {}')

# Extract email base and domain, providing robust defaults
HARDCODED_USER_EMAIL_BASE=$(echo "${BASE_USER_DATA}" | jq -r '.email | split("@")[0] // "default-test-user-base"' | tr -d '\n')
EMAIL_DOMAIN=$(echo "${BASE_USER_DATA}" | jq -r '.email | split("@")[1] // "serve.scilifelab.se"' | tr -d '\n')

# Apply app_slug override if provided
if [ -n "${APP_SLUG_OVERRIDE}" ]; then
    BASE_APP_DATA=$(echo "${BASE_APP_DATA}" | jq --arg slug "${APP_SLUG_OVERRIDE}" '.app_slug = $slug')
fi

# Apply app port override if provided
if [ -n "${APP_PORT_OVERRIDE}" ]; then
    if [[ "${APP_PORT_OVERRIDE}" =~ ^[0-9]+$ ]]; then
        BASE_APP_DATA=$(echo "${BASE_APP_DATA}" | jq --argjson port "${APP_PORT_OVERRIDE}" '.port = $port')
    else
        echo "Warning: APP_PORT_OVERRIDE '${APP_PORT_OVERRIDE}' is not a valid number. Using default or existing port." >&2
    fi
fi

# Apply app image override if provided
if [ -n "${APP_IMAGE_OVERRIDE}" ]; then
    BASE_APP_DATA=$(echo "${BASE_APP_DATA}" | jq --arg image "${APP_IMAGE_OVERRIDE}" '.image = $image')
fi

# Get CSRF token function
get_csrf_token() {
    curl -s -X GET "${LATEST_BASE_URL}/accounts/login/" -c - | awk '/csrftoken/ {print $NF}'
}

# Make authenticated request function
make_request() {

    echo ""

    local endpoint=$1
    local payload=$2
    local token=$(get_csrf_token)

    if [ -z "${token}" ]; then
        echo "Error: Failed to retrieve CSRF token. Exiting."
        exit 1
    fi

    if [ "${IS_VERBOSE_FLAG}" = true ]; then
        echo "Sending request to ${endpoint} with payload: ${payload}"
    fi

    curl -s -w "\n" -b "csrftoken=${token}" \
          -H "X-CSRFToken: ${token}" \
          -H "Content-Type: application/json" \
          -X POST \
          -d "${payload}" \
          "${LATEST_BASE_URL}${endpoint}"
}

# Function to prepend prefix if available, then append index and combine (for indexed users/projects/apps)
apply_naming_convention() {
    local base_name_from_json=$1
    local index=$2
    local current_prefix="${NAME_PREFIX}"
    local final_name=""

    if [ -z "${base_name_from_json}" ] || [ "${base_name_from_json}" = "null" ]; then
        base_name_from_json="default-base-name"
    fi

    if [ -n "${current_prefix}" ]; then
        final_name="${current_prefix}-${base_name_from_json}_${index}"
    else
        final_name="${base_name_from_json}_${index}"
    fi

    echo "${final_name}"
}

# Function to modify email for indexed users, including optional prefix
modify_email_with_prefix() {
    local base_email_name_from_json=$1
    local index=$2
    local current_prefix="${NAME_PREFIX}"
    local final_email_base=""

    if [ -z "${base_email_name_from_json}" ] || [ "${base_email_name_from_json}" = "null" ]; then
        base_email_name_from_json="default-email-part"
    fi

    if [ -n "${current_prefix}" ]; then
        final_email_base="${current_prefix}-${base_email_name_from_json}_${index}"
    else
        final_email_base="${base_email_name_from_json}_${index}"
    fi

    echo "${final_email_base}@${EMAIL_DOMAIN}"
}

# Function to modify user payload data and subsequent sending to endpoint
manage_user_data_payload(){

    u_idx=$1
    endpoint=$2
    message_verb=$3

    local base_user_data_json="${BASE_USER_DATA}"
    local hardcoded_email_base=$(echo "${BASE_USER_DATA}" | jq -r '.email | split("@")[0] // "default-test-user-base"' | tr -d '\n')

    local base_username=$(echo "${base_user_data_json}" | jq -r '.username // "default-username"' | tr -d '\n')
    local base_user_password=$(echo "${base_user_data_json}" | jq -r '.password // "default-password"' | tr -d '\n')

    local user_data_payload=$(echo "${base_user_data_json}") # Start with base data

    local username=$(apply_naming_convention "${base_username}" ${u_idx})
    local email=$(modify_email_with_prefix "${hardcoded_email_base}" ${u_idx})

    # Add common fields (username, password, email)
    user_data_payload=$(echo "${user_data_payload}" | jq \
        --arg u "${username}" \
        --arg p "${base_user_password}" \
        --arg e "${email}" \
        '.username = $u | .password = $p | .email = $e')

    # Add optional fields if they exist in BASE_USER_DATA
    for field in "affiliation" "department" "first_name" "last_name"; do
        local field_value=$(echo "${BASE_USER_DATA}" | jq -r ".${field} // null")
        if [ "${field_value}" != "null" ]; then
            user_data_payload=$(echo "${user_data_payload}" | jq --arg fv "${field_value}" --arg fn "${field}" '.[$fn] = $fv')
        fi
    done

    if [ "${IS_VERBOSE_FLAG}" = true ]; then
        echo "${message_verb}: $(echo "${user_data_payload}" | jq -r '.username')"
    fi

    make_request "${endpoint}" "{\"user_data\": ${user_data_payload}}"
}

# Combined function to manage users (mutliple create, single delete)
manage_user_operations() {

    local action=$1 # "create" or "delete"
    local is_superuser_op=$2 # true or false
    local num_users=$3
    local endpoint=""
    local message_verb=""

    if [ "${is_superuser_op}" = true ]; then
        if [ "${action}" = "create" ]; then
            endpoint="/devtools/populate-test-superuser/"
            message_verb="Creating superuser"
        fi
    else # other endpoints are valid and $is_superuser_op is always false
        if [ "${action}" = "create" ]; then
            endpoint="/devtools/populate-test-user/"
            message_verb="Creating user"
        else # delete
            endpoint="/devtools/cleanup-test-user/"
            message_verb="Deleting user"
        fi
    fi

    # Multiple user creation possible
    if [ "${action}" = "create" ]; then
        for u_idx in $(seq 1 "${num_users}"); do
            manage_user_data_payload "${u_idx}" "${endpoint}" "${message_verb}"
        done
    else # delete only specific one
        manage_user_data_payload "${num_users}" "${endpoint}" "${message_verb}"
    fi
}

# Function to delete all the users
delete_all_users() {

    local num_users=$1

    for u_idx in $(seq 1 "${num_users}"); do
        delete_all_projects "${u_idx}"
        manage_user_operations "delete" false "${u_idx}"
    done
}

# Function to create projects
create_projects() {
    local num_users=$1
    local num_projects=$2
    local base_username=$(echo "${BASE_USER_DATA}" | jq -r '.username // "default-username"' | tr -d '\n')
    local base_user_password=$(echo "${BASE_USER_DATA}" | jq -r '.password // "default-password"' | tr -d '\n')
    local base_project_name=$(echo "${BASE_PROJECT_DATA}" | jq -r '.project_name // "default-project-name"' | tr -d '\n')
    local base_project_description=$(echo "${BASE_PROJECT_DATA}" | jq -r '.project_description // "default-project-description"' | tr -d '\n')
    local hardcoded_email_base=$(echo "${BASE_USER_DATA}" | jq -r '.email | split("@")[0] // "default-test-user-base"' | tr -d '\n')


    for u_idx in $(seq 1 ${num_users}); do
        local username=$(apply_naming_convention "${base_username}" ${u_idx})
        local email=$(modify_email_with_prefix "${hardcoded_email_base}" ${u_idx})
        local user_data=$(echo "{}" | jq \
            --arg u "${username}" \
            --arg p "${base_user_password}" \
            --arg e "${email}" \
            '.username = $u | .password = $p | .email = $e')

        # Add optional fields if they exist in BASE_USER_DATA
        for field in "affiliation" "department" "first_name" "last_name"; do
            local field_value=$(echo "${BASE_USER_DATA}" | jq -r ".${field} // null")
            if [ "${field_value}" != "null" ]; then
                user_data=$(echo "${user_data}" | jq --arg fv "${field_value}" --arg fn "${field}" '.[$fn] = $fv')
            fi
        done

        for p_idx in $(seq 1 ${num_projects}); do
            local project_name=$(apply_naming_convention "${base_project_name}" ${p_idx})
            local project_data=$(echo "{}" | jq \
                --arg n "${project_name}" \
                --arg d "${base_project_description}" \
                '.project_name = $n | .project_description = $d')
            local payload="{\"user_data\": ${user_data}, \"project_data\": ${project_data}}"

            if [ "${IS_VERBOSE_FLAG}" = true ]; then
                echo "Creating project: $(echo "${project_data}" | jq -r '.project_name') for user: $(echo "${user_data}" | jq -r '.username')"
            fi

            make_request "/devtools/populate-test-project/" "${payload}"
        done
    done
}

# This function deletes a single project based on user_data and project_data
# It expects a user index and a project index, starting from 1
delete_single_project() {
    local user_idx=$1
    local project_idx=$2
    local base_username=$(echo "${BASE_USER_DATA}" | jq -r '.username // "default-username"' | tr -d '\n')
    local base_user_password=$(echo "${BASE_USER_DATA}" | jq -r '.password // "default-password"' | tr -d '\n')
    local base_project_name=$(echo "${BASE_PROJECT_DATA}" | jq -r '.project_name // "default-project-name"' | tr -d '\n')
    local base_project_description=$(echo "${BASE_PROJECT_DATA}" | jq -r '.project_description // "default-project-description"' | tr -d '\n')
    local hardcoded_email_base=$(echo "${BASE_USER_DATA}" | jq -r '.email | split("@")[0] // "default-test-user-base"' | tr -d '\n')


    local user_data_payload=$(echo "${BASE_USER_DATA}") # Start with base data for user data

    local username=$(apply_naming_convention "${base_username}" ${user_idx})
    local email=$(modify_email_with_prefix "${hardcoded_email_base}" ${user_idx})

    # Add common fields (username, password, email)
    user_data_payload=$(echo "${user_data_payload}" | jq \
        --arg u "${username}" \
        --arg p "${base_user_password}" \
        --arg e "${email}" \
        '.username = $u | .password = $p | .email = $e')

    # Add optional fields if they exist in BASE_USER_DATA
    for field in "affiliation" "department" "first_name" "last_name"; do
        local field_value=$(echo "${BASE_USER_DATA}" | jq -r ".${field} // null")
        if [ "${field_value}" != "null" ]; then
            user_data_payload=$(echo "${user_data_payload}" | jq --arg fv "${field_value}" --arg fn "${field}" '.[$fn] = $fv')
        fi
    done

    local project_name=$(apply_naming_convention "${base_project_name}" ${project_idx})
    local project_data=$(echo "{}" | jq \
        --arg n "${project_name}" \
        --arg d "${base_project_description}" \
        '.project_name = $n | .project_description = $d')

    local payload="{\"user_data\": ${user_data_payload}, \"project_data\": ${project_data}}"

    if [ "${IS_VERBOSE_FLAG}" = true ]; then
        echo "Deleting project: $(echo "${project_data}" | jq -r '.project_name') for user: $(echo "${user_data_payload}" | jq -r '.username')"
    fi

    make_request "/devtools/cleanup-test-project/" "${payload}"
}

# Function to delete all projects for a particular user
delete_all_projects() {
    local user_idx=$1

    local base_username=$(echo "${BASE_USER_DATA}" | jq -r '.username // "default-username"' | tr -d '\n')
    local base_user_password=$(echo "${BASE_USER_DATA}" | jq -r '.password // "default-password"' | tr -d '\n')
    local hardcoded_email_base=$(echo "${BASE_USER_DATA}" | jq -r '.email | split("@")[0] // "default-test-user-base"' | tr -d '\n')


    local username=$(apply_naming_convention "${base_username}" ${user_idx})
    local email=$(modify_email_with_prefix "${hardcoded_email_base}" ${user_idx})
    local user_data_payload=$(echo "${BASE_USER_DATA}")

    user_data_payload=$(echo "${user_data_payload}" | jq \
        --arg u "${username}" \
        --arg p "${base_user_password}" \
        --arg e "${email}" \
        '.username = $u | .password = $p | .email = $e')

    # Add optional fields if they exist in BASE_USER_DATA
    for field in "affiliation" "department" "first_name" "last_name"; do
        local field_value=$(echo "${BASE_USER_DATA}" | jq -r ".${field} // null")
        if [ "${field_value}" != "null" ]; then
            user_data_payload=$(echo "${user_data_payload}" | jq --arg fv "${field_value}" --arg fn "${field}" '.[$fn] = $fv')
        fi
    done

    if [ "${IS_VERBOSE_FLAG}" = true ]; then
        echo "Deleting all projects for user: $(echo "${user_data_payload}" | jq -r '.username')"
    fi

    make_request "/devtools/cleanup-all-test-projects/" "{\"user_data\": ${user_data_payload}}"
}

# Function to create apps
create_apps() {
    local num_users=$1
    local num_projects=$2
    local num_apps=$3
    local base_username=$(echo "${BASE_USER_DATA}" | jq -r '.username // "default-username"' | tr -d '\n')
    local base_user_password=$(echo "${BASE_USER_DATA}" | jq -r '.password // "default-password"' | tr -d '\n')
    local base_project_name=$(echo "${BASE_PROJECT_DATA}" | jq -r '.project_name // "default-project-name"' | tr -d '\n')
    local base_project_description=$(echo "${BASE_PROJECT_DATA}" | jq -r '.project_description // "default-project-description"' | tr -d '\n')
    local hardcoded_email_base=$(echo "${BASE_USER_DATA}" | jq -r '.email | split("@")[0] // "default-test-user-base"' | tr -d '\n')

    # Extract ALL app fields from BASE_APP_DATA, providing defaults for each
    local base_app_name=$(echo "${BASE_APP_DATA}" | jq -r '.name // "default-app-name"' | tr -d '\n')
    local base_app_slug=$(echo "${BASE_APP_DATA}" | jq -r '.app_slug // "dashapp"' | tr -d '\n')
    local base_app_description=$(echo "${BASE_APP_DATA}" | jq -r '.description // "default-app-description"' | tr -d '\n')
    local base_app_access=$(echo "${BASE_APP_DATA}" | jq -r '.access // "public"' | tr -d '\n')
    local base_app_port=$(echo "${BASE_APP_DATA}" | jq -r '.port // 8000' | tr -d '\n') # Ensure default is number, remove newline
    local base_app_image=$(echo "${BASE_APP_DATA}" | jq -r '.image // "ghcr.io/scilifelabdatacentre/example-dash:latest"' | tr -d '\n')
    local base_app_source_code_url=$(echo "${BASE_APP_DATA}" | jq -r '.source_code_url // "default-url"' | tr -d '\n')

    for u_idx in $(seq 1 ${num_users}); do
        local username=$(apply_naming_convention "${base_username}" ${u_idx})
        local email=$(modify_email_with_prefix "${hardcoded_email_base}" ${u_idx})
        local user_data=$(echo "{}" | jq \
            --arg u "${username}" \
            --arg p "${base_user_password}" \
            --arg e "${email}" \
            '.username = $u | .password = $p | .email = $e')

        # Add optional fields if they exist in BASE_USER_DATA
        for field in "affiliation" "department" "first_name" "last_name"; do
            local field_value=$(echo "${BASE_USER_DATA}" | jq -r ".${field} // null")
            if [ "${field_value}" != "null" ]; then
                user_data=$(echo "${user_data}" | jq --arg fv "${field_value}" --arg fn "${field}" '.[$fn] = $fv')
            fi
        done

        for p_idx in $(seq 1 ${num_projects}); do
            local project_name=$(apply_naming_convention "${base_project_name}" ${p_idx})
            local project_data=$(echo "{}" | jq \
                --arg n "${project_name}" \
                --arg d "${base_project_description}" \
                '.project_name = $n | .project_description = $d')

            for a_idx in $(seq 1 ${num_apps}); do
                local app_name=$(apply_naming_convention "${base_app_name}" ${a_idx})

                local validated_port="${base_app_port}"
                if ! [[ "${validated_port}" =~ ^[0-9]+$ ]]; then
                    echo "Warning: App port '${validated_port}' is not a valid number. Defaulting to 8000. Make sure it is okay for your app type." >&2
                    validated_port="8000"
                fi

                local app_data=$(echo "{}" | jq \
                    --arg n "${app_name}" \
                    --arg s "${base_app_slug}" \
                    --arg d "${base_app_description}" \
                    --arg c "${base_app_access}" \
                    --argjson p "${validated_port}" \
                    --arg i "${base_app_image}" \
                    --arg u "${base_app_source_code_url}" \
                    '{name: $n, app_slug: $s, description: $d, access: $c, port: $p, image: $i, source_code_url: $u}')


                # echo "DEBUG: Generated app_data JSON: '$app_data'"

                local payload="{\"user_data\": ${user_data}, \"project_data\": ${project_data}, \"app_data\": ${app_data}}"

                if [ "${IS_VERBOSE_FLAG}" = true ]; then
                    echo "Creating app: $(echo "${app_data}" | jq -r '.name') (Slug: $(echo "${app_data}" | jq -r '.app_slug')) in project: $(echo "${project_data}" | jq -r '.project_name') for user: $(echo "${user_data}" | jq -r '.username')"
                fi

                make_request "/devtools/populate-test-app/" "${payload}"
            done
        done
    done
}

# Handle actions
case ${ACTION} in
    create)
        case ${TARGET} in
            user)
                if [ "${IS_VERBOSE_FLAG}" = true ]; then
                    echo "--- Processing 'create user' ---"
                    echo ""
                fi
                # First, ensure no such user(s) exist including project(s) with app(s), if any.
                delete_all_users "${USERS}"
                # Finally, create the user(s)
                manage_user_operations "create" "${IS_SUPERUSER_FLAG}" "${USERS}"
                ;;

            project)
                if [ "${IS_VERBOSE_FLAG}" = true ]; then
                    echo "--- Processing 'create project' ---"
                    echo ""
                fi
                # First, ensure no such user(s) exist including project(s) with app(s), if any.
                delete_all_users "${USERS}"
                # Next, create the user(s)
                manage_user_operations "create" "${IS_SUPERUSER_FLAG}" "${USERS}"
                # Finally, create the project(s)
                create_projects "${USERS}" "${PROJECTS}"
                ;;

            app)
                if [ "${IS_VERBOSE_FLAG}" = true ]; then
                    echo "--- Processing 'create app' ---"
                    echo ""
                fi
                # First, ensure no such user(s) exist including project(s) with app(s), if any.
                delete_all_users "${USERS}"
                # Next, create the user(s)
                manage_user_operations "create" "${IS_SUPERUSER_FLAG}" "${USERS}"
                # Next, create the project(s)
                create_projects "${USERS}" "${PROJECTS}"
                # Finally, create the app(s)
                create_apps "${USERS}" "${PROJECTS}" "${APPS}"
                ;;

            *)
                echo "Invalid create target: ${TARGET}"
                show_how_to
                exit 1
                ;;
        esac
        ;;

    delete)
        case ${TARGET} in
            user)
                if [ "${IS_VERBOSE_FLAG}" = true ]; then
                    echo "--- Processing 'delete user' ---"
                    echo ""
                fi
                # First, delete projects (including apps) associated with this user first, if any
                delete_all_projects "${USERS}"
                # Finally, delete the particular user with id ${USERS}, if any
                manage_user_operations "delete" false "${USERS}"
                ;;

            all-users)
                if [ "${IS_VERBOSE_FLAG}" = true ]; then
                    echo "--- Processing 'delete all-users' ---"
                    echo ""
                fi
                # Deleting all existing users including project(s) with app(s), if any.
                delete_all_users "${USERS}"

                ;;

            project)
                if [ "${IS_VERBOSE_FLAG}" = true ]; then
                    echo "--- Processing 'delete project' (specific project for a specific user) ---"
                    echo ""
                fi
                # Deleting a single project (including apps) for the specified user, if any
                if [ "${USERS}" -gt 0 ] && [ "${PROJECTS}" -gt 0 ]; then
                    delete_single_project "${USERS}" "${PROJECTS}"
                else
                    echo "Error: To delete a single project, please specify -u (user index, from 1) and -p (project index, from 1)."
                    exit 1
                fi
                ;;

            all-projects)
                if [ "${IS_VERBOSE_FLAG}" = true ]; then
                    echo "--- Processing 'delete all-projects' ---"
                    echo ""
                fi
                # Deleting all projects (including apps) for a specific user, if any.
                delete_all_projects "${USERS}"
                ;;
            app)
                echo "Error: Direct deletion of specific apps is not supported by the provided API."
                echo "To delete apps, delete their parent project(s). See more:"
                show_how_to
                exit 1
                ;;

            *)
                echo "Invalid delete target: ${TARGET}"
                show_how_to
                exit 1
                ;;
        esac
        ;;

    *)
        echo "Invalid action: ${ACTION}"
        show_how_to
        exit 1
        ;;
esac

echo ""
echo "Operation completed.."
echo ""
