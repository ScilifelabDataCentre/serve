<p align="center">
   <a href="https://opensource.org/license/apache-2-0/">
      <img alt="Licence: Apache 2.0" src="https://img.shields.io/badge/License-Apache_2.0-yellow.svg">
   </a>
   <a href="[https://opensource.org/licenses/MIT](https://github.com/psf/black)">
      <img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg">
   </a>
   <br />
      <img alt="Pre-commit" src="https://github.com/ScilifelabDataCentre/stackn/actions/workflows/pre-commit.yaml/badge.svg?branch=develop">
      <img alt="CI" src="https://github.com/ScilifelabDataCentre/stackn/actions/workflows/ci.yaml/badge.svg?branch=develop">
      <img alt="End2end tests" src="https://github.com/ScilifelabDataCentre/stackn/actions/workflows/e2e-tests.yaml/badge.svg?branch=develop">

</p>

# SciLifeLab Serve

SciLifeLab Serve ([https://serve.scilifelab.se](https://serve.scilifelab.se)) is a platform offering machine learning model serving, app hosting (Shiny, Streamlit, Dash, etc.), web-based integrated development environments, and other tools to life science researchers affiliated with a Swedish research institute. It is developed and operated by the [SciLifeLab Data Centre](https://github.com/ScilifelabDataCentre), part of [SciLifeLab](https://scilifelab.se/). See [this page for information about funders and mandate](https://serve.scilifelab.se/about/).

This repository contains source code for SciLifeLab Serve. It is  based on the open-source platform [Stackn](https://github.com/scaleoutsystems/stackn).

## Reporting bugs and requesting features

If you are using SciLifeLab Serve and notice a bug or if there is a feature you would like to be added feel free to [create an issue](https://github.com/ScilifelabDataCentre/stackn/issues/new/choose) with a bug report or feature request.

## Development and contributions

SciLifeLab Serve is built with [Django](https://github.com/django/django) and uses [Kubernetes](https://kubernetes.io/) [API](https://kubernetes.io/docs/concepts/overview/kubernetes-api/) to control resources on a dedicated Kubernetes cluster (located at and administered by KTH Royal Institute of Technology on behalf of SciLifeLab Data Centre). It is possible to deploy SciLifeLab Serve on your own machine and connect it to a locally running Kubernetes cluster. Below you can find information on how to set up a local development environment.

We welcome contributions to the code. When you want to make a contribution please fork this repository and use the `develop` branch as a starting point for your changes/additions. Once done, please send a pull request against the `develop` branch. The pull requests will be reviewed by our team of developers.

The  `main` branch contains code behind the version that is currently deployed in production - https://serve.scilifelab.se. The branches `develop` and `staging` contain current development versions at different stages.

### Local development setup

There are multiple ways to set up a local development environment for SciLifeLab Serve. Below you can find instructions on how to set up a local development environment using Docker Compose or Rancher Desktop.

Both have their pros and cons. Docker Compose is easier to set up but does not provide a full Kubernetes environment. Rancher Desktop provides a full Kubernetes environment but is more complex to set up.

### Deploy Serve for local development with Docker Compose

It is possible to deploy and work with the user interface of Serve without a running Kubernetes cluster, in that case you can skip the step related to that below. However, in order to be able to deploy and modify resources (apps, notebooks, persistent storage, etc.) a running local cluster is required; it can be created for example with [microk8s](https://microk8s.io/).

1. Clone this repository locally:
```
$ git clone https://github.com/ScilifelabDataCentre/stackn
$ cd stackn
```

2. Create a copy of the .env template file

```
$ cp .env.template .env
```

3. Add your cluster configurations

Add a file `cluster.conf` with cluster configuration at the root. For example, if you are using microk8s, you can use:

```
$ microk8s config > cluster.conf
```

4. Modify the settings file for the Django project - `studio/settings.py`.

The only setting that is required to change is AUTH_DOMAIN, set this to be your local IP (not localhost). By default the service URL will then be http://studio.127.0.0.1.nip.io:8080

Note that certain features will not work if using localhost since Serve apps depends on an external ingress controller. Therefore, it can be useful to use a wildcard dns such as [nip.io](http://nip.io). For example, if your local IP is 192.168.1.10 then your domain field becomes `192.168.1.10.nip.io`.

5. Build image

Since we are dealing with private repos, we need to mount one or several ssh keys to the docker build. Luckily Docker BuildKit has this feature but unfortunately docker compose does not. Therefore we need to build studio first with docker build:

```
$ DOCKER_BUILDKIT=1 docker build -t studio:develop . --ssh=default
```
This assumes you have the correct ssh key in your ssh-agent. If you like to give a specific key replace default with the path to your key.

6. Finally, fire up Serve with compose:

```
$ docker compose up -d
```

### Deploy Serve for local development with Rancher Desktop

Start with instructions in [Serve Charts > How to Deploy](https://github.com/ScilifelabDataCentre/serve-charts?tab=readme-ov-file#how-to-deploy) and come back here when you get to the point of building the studio image.

Again, this setup assumes you have [Rancher Desktop](https://rancherdesktop.io/) installed and running.

```bash
$ git clone git@github.com:ScilifelabDataCentre/stackn.git
$ cd stackn
$ git checkout develop
$ cp .env.template .env
$ cp ~/.kube/config cluster.conf
$ cp ~/.ssh/id_rsa.pub id_rsa.pub
$ nerdctl build -t studio .
$ nerdctl build -t mystudio -f local.Dockerfile .
```

Now continue setting up serve charts until you get to the PyCharm setup.

##### PyCharm setup

Just commands:

1. Do this weirdness due to [this](https://youtrack.jetbrains.com/issue/PY-55338/Connection-to-python-console-refused-with-docker-interpreter-on-Linux)
    1. go to Help | Find Action | Registry
    2. disable python.use.targets.api
    3. recreate the interpreter from scratch
2. Setup ssh interpreter
```bash
# This will open ssh connection from the pod to our host machine
# Because we made everything super NOT secure for local development you can ssh there without password and as root
$ sudo kubectl port-forward svc/serve-studio 22:22
```
3. Set up the interpreter in PyCharm
    1. Go to File | Settings | Project: stackn | Python Interpreter
    2. Add new interpreter
    3. Choose SSH
    4. Host: localhost
    5. Port: 22
    6. Username: root
    7. Auth type: Password
    8. Password: root
    9. Interpreter path: /usr/local/bin/python
    10. Python interpreter path: /usr/local/bin/python
    11. **Important** Don't accept synchronization option from PyCharm. There is no need for it because we already synchronize the code with the pod using volume mounts provided by Rancher Desktop.
4. Set up the environment variables
    1. Go to Run | Edit Configurations
    2. Add new configuration
    3. Choose `Django server`
    4. Name: `Serve`
    5. Host: `0.0.0.0`
    6. Port: `8080`
    7. Click Modify options and select `No reload` and `Environment variables`
    8. Add environment variables from the studio pod

```bash
$ kubectl get po
# find the studio pod serve-studio-123
$ kubectl exec -it <serve-studio-123> -- /bin/bash
# Run migrations
# For simplicity just run sh scripts/run_web.sh
$ sh scripts/run_web.sh
# And then stop the process when the server is running

# Now you are in the studio container
# Type env
$ env
# Copy the whole output in to the pycharm environment configuration 
```

Copy environment variables to the PyCharm Django configuration.

Now that you are done, you can run Django server using PyCharm and access the studio at [http://studio.127.0.0.1.nip.io/](http://studio.127.0.0.1.nip.io/)

## Contact information

To get in touch with the development team behind SciLifeLab Serve send us an email: serve@scilifelab.se.
