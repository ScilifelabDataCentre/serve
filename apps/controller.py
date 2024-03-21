import json
import os
import subprocess
import tarfile
import uuid

import yaml
from django.conf import settings

from studio.utils import get_logger

from .models import Apps

KUBEPATH = settings.KUBECONFIG
logger = get_logger(__name__)


def delete(options):
    logger.info("DELETE FROM CONTROLLER")
    # building args for the equivalent of helm uninstall command
    args = ["helm", "-n", options["namespace"], "delete", options["release"]]
    result = subprocess.run(args, capture_output=True)
    return result


def deploy(options):
    logger.info("STARTING DEPLOY FROM CONTROLLER")

    app = Apps.objects.get(slug=options["app_slug"], revision=options["app_revision"])
    if app.chart_archive and app.chart_archive != "":
        try:
            chart_file = settings.MEDIA_ROOT + app.chart_archive.name
            tar = tarfile.open(chart_file, "r:gz")
            extract_path = "/app/extracted_charts/" + app.slug + "/" + str(app.revision)
            tar.extractall(extract_path)
            tar.close()
            chart = extract_path
        except Exception as err:
            logger.error(err, exc_info=True)
            chart = "charts/" + options["chart"]
    else:
        chart = "charts/" + options["chart"]

    if "release" not in options:
        logger.info("Release option not specified.")
        return json.dumps({"status": "failed", "reason": "Option release not set."})
    if "appconfig" in options:
        # check if path is root path
        if "path" in options["appconfig"]:
            if "/" == options["appconfig"]["path"]:
                logger.info("Root path cannot be copied.")
                return json.dumps({"status": "failed", "reason": "Cannot copy / root path."})
        # check if valid userid
        if "userid" in options["appconfig"]:
            try:
                userid = int(options["appconfig"]["userid"])
            except Exception:
                logger.error("Userid not a number.", exc_info=True)
                return json.dumps({"status": "failed", "reason": "Userid not an integer."})
            if userid > 1010 or userid < 999:
                logger.info("Userid outside of allowed range.")
                return json.dumps({"status": "failed", "reason": "Userid outside of allowed range."})
        else:
            # if no userid, then add default id of 1000
            options["appconfig"]["userid"] = "1000"
        # check if valid port
        if "port" in options["appconfig"]:
            try:
                port = int(options["appconfig"]["port"])
            except Exception:
                logger.error("Userid not a number.", exc_info=True)
                return json.dumps({"status": "failed", "reason": "Port not an integer."})
            if port > 9999 or port < 3000:
                logger.info("Port outside of allowed range.")
                return json.dumps({"status": "failed", "reason": "Port outside of allowed range."})

    # Save helm values file for internal reference
    unique_filename = "charts/values/{}-{}.yaml".format(str(uuid.uuid4()), str(options["app_name"]))
    f = open(unique_filename, "w")
    f.write(yaml.dump(options))
    f.close()

    # building args for the equivalent of helm install command
    args = [
        "helm",
        "upgrade",
        "--install",
        "-n",
        options["namespace"],
        options["release"],
        chart,
        "-f",
        unique_filename,
    ]
    logger.info("CONTROLLER: RUNNING HELM COMMAND... ")
    result = subprocess.run(args, capture_output=True)

    # remove file
    rm_args = ["rm", unique_filename]
    subprocess.run(rm_args)

    return result
