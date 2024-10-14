HELP_MESSAGE_MAP = {
    "name": "Display name for the application. This is the name visible on the app catalogue if the app is public",
    "description": "Provide a detailed description of your app. "
    "This will be the description visible in the app catalogue if the app is public.",
    "tags": "Keywords relevant to your app. These will be displayed along with the description "
    "in the app catalogue if the app is public.",
    "subdomain": "Valid subdomain names have minimum length of 3 characters and may contain lower case letters a-z "
    "and numbers 0-9 and a hyphen '-'. The hyphen should not be at the start or end of the subdomain.",
    "access": "Public apps will be displayed on the app catalogue and can be accessed by anyone that has the link to "
    "them. Project apps can only be accessed by project members. Private apps are only accessible by users that "
    "create the apps. Link apps are only accessible to those who have a direct link, they are not "
    "displayed in the public catalogue.",
    "source_code_url": "Provide a URL where the full source code of your app can be accessed (for example, to a GitHub "
    "repository or a Figshare or Zenodo entry).",
    "flavor": "Hardware allocation for your app. Only one option is available by default. If your app requires more "
    "hardware resources, get in touch with us (serve@scilifelab.se) with a request.",
    "image": "Docker Image for the app uploaded to DockerHub or GitHub. Each version of your app should have a unique "
    "tag.",
    "path": "Specify the path inside the container that you want to be persistent (path to database or similar). If "
    "you follow our guide to build the container, then please include the username in the path as well.",
    "port": "Port that the docker container exposes and the application runs on. This should be an integer between "
    "3000-9999.",
    "note_on_linkonly_privacy": "This option can be used only for a limited amount of time, for example while under "
    "development or during peer review.",
    "environment": "Select the environment that you want to use for your app. The environment is a Docker image that "
    "contains the software and dependencies needed to run your app.",
}
