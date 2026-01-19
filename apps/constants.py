from enum import IntEnum, StrEnum


class HandleUpdateStatusResponseCode(IntEnum):
    NO_ACTION = 0
    UPDATED_STATUS = 1
    UPDATED_TIME_OF_STATUS = 2
    CREATED_FIRST_STATUS = 3
    OBJECT_NOT_FOUND = 4


class AppActionOrigin(StrEnum):
    UNSET = "UNSET"
    USER = "USER"
    SYSTEM = "SYSTEM"


HELP_MESSAGE_MAP = {
    "name": "The app title is visible in the app catalogue if the app is public",
    "description": "The app description is visible in the app catalogue if the app is public.",
    "tags": "These keywords are displayed along with the description in the app catalogue if the app is public.",
    "subdomain": "Valid subdomain names have minimum length of 3 characters and may contain lower case letters a-z "
    "and numbers 0-9 and a hyphen '-'. The hyphen should not be at the start or end of the subdomain.",
    "access": "Public apps will be displayed on the app catalogue and can be accessed by anyone that has the link to "
    "them. Project apps can only be accessed by project members. Private apps are only accessible by users that "
    "create the apps. Link apps are only accessible to those who have a direct link, they are not "
    "displayed in the public catalogue.",
    "source_code_url": "This URL is listed in the app catalogue if your app is public.",
    "flavor": "Hardware allocation for your app. Only one option is available by default. If your app requires more "
    "hardware resources, get in touch with us (serve@scilifelab.se) with a request.",
    "image": "This information is used to host the application on our servers. Docker Image for the app uploaded "
    "to DockerHub or GitHub. Each version of your app should have a unique "
    "tag.",
    "path": "Specify the path inside the container that you want to be persistent (path to database or similar). If "
    "you follow our guide to build the container, then please include the username in the path as well.",
    "port": "This information is used to host the application on our servers.",
    "note_on_linkonly_privacy": "This will not be published anywhere. We use this information internally to keep "
    "track of apps available through SciLifeLab Serve.",
    "environment": "Select the environment that you want to use for your app. The environment is a Docker image that "
    "contains the software and dependencies needed to run your app.",
    "mount_path": "Specify the path inside your Docker container that you want to persist; for example, the directory "
    "where you plan to store or load data. If you followed our guide to build the Docker container, "
    "please include the username you specified in the Dockerfile as part of the path.",
    "volume": "This is where this application will be able to read, edit, and save files.",
}
