<p align="center">
   <a href="https://opensource.org/license/apache-2-0/">
      <img alt="Licence: Apache 2.0" src="https://img.shields.io/badge/License-Apache_2.0-yellow.svg">
   </a>
   <a href="[https://opensource.org/licenses/MIT](https://github.com/psf/black)">
      <img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg">
   </a>
   <br />
      <img alt="Pre-commit" src="https://github.com/ScilifelabDataCentre/serve/actions/workflows/pre-commit.yaml/badge.svg?branch=develop">
      <img alt="CI" src="https://github.com/ScilifelabDataCentre/serve/actions/workflows/ci.yaml/badge.svg?branch=develop">
      <img alt="End2end tests" src="https://github.com/ScilifelabDataCentre/serve/actions/workflows/e2e-tests.yaml/badge.svg?branch=develop">

</p>

# SciLifeLab Serve

SciLifeLab Serve ([https://serve.scilifelab.se](https://serve.scilifelab.se)) is a platform offering machine learning model serving, app hosting (Shiny, Streamlit, Dash, etc.), web-based integrated development environments, and other tools to life science researchers affiliated with a Swedish research institute. It is developed and operated by the [SciLifeLab Data Centre](https://github.com/ScilifelabDataCentre), part of [SciLifeLab](https://scilifelab.se/). See [this page for information about funders and mandate](https://serve.scilifelab.se/about/).

This repository contains source code for the main Django application of SciLifeLab Serve.

## Reporting bugs and requesting features

If you are using SciLifeLab Serve and notice a bug or if there is a feature you would like to be added feel free to [create an issue](https://github.com/ScilifelabDataCentre/serve/issues/new/choose) with a bug report or feature request.

## Development and contributions

SciLifeLab Serve is built with [Django](https://github.com/django/django) and uses [Kubernetes](https://kubernetes.io/) [API](https://kubernetes.io/docs/concepts/overview/kubernetes-api/) to control resources on a dedicated Kubernetes cluster (located at and administered by KTH Royal Institute of Technology on behalf of SciLifeLab Data Centre). It is possible to deploy SciLifeLab Serve on your own machine and connect it to a locally running Kubernetes cluster. Below you can find information on how to set up a local development environment.

We welcome contributions to the code. When you want to make a contribution please fork this repository and use the `develop` branch as a starting point for your changes/additions. Once done, please send a pull request against the `develop` branch. The pull requests will be reviewed by our team of developers.

The  `main` branch contains code behind the version that is currently deployed in production - https://serve.scilifelab.se. The branches `develop` and `staging` contain current development versions at different stages.

### Deploy Serve for local development with Docker Compose

It is possible to deploy and work with the user interface of Serve without a running Kubernetes cluster, in that case you can skip the step related to that below. However, in order to be able to deploy and modify resources (apps, notebooks, persistent storage, etc.) a running local cluster is required; it can be created for example with [microk8s](https://microk8s.io/).

1. Clone this repository locally:
```
$ git clone https://github.com/ScilifelabDataCentre/serve
$ cd serve
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

## Contact information

To get in touch with the development team behind SciLifeLab Serve send us an email: serve@scilifelab.se.
