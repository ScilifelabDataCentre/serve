import subprocess
import json
import yaml
import shlex

import os
import uuid

def refresh_charts(branch='master'):

    cwd = os.getcwd()
    try:
        charts_url = os.environ['CHARTS_URL']
    except Exception:
        charts_url = 'https://github.com/scaleoutsystems/charts/archive/{}.zip'.format(branch)

    status = subprocess.run('rm -rf charts-{}'.format(branch).split(' '), cwd=cwd)
    status = subprocess.run('wget -O {}.zip {}'.format(branch.replace('/', '-'), charts_url).split(' '), cwd=cwd)
    status = subprocess.run('unzip {}.zip'.format(branch.replace('/', '-')).split(' '),cwd=cwd)


class Controller:

    def __init__(self, cwd):
        self.cwd = cwd
        self.branch = os.environ['BRANCH']
        self.default_args = ['helm']
        pass

    def deploy(self, options, action='install'):
        # extras = ''
        """
        try:
            minio = ' --set service.minio=' + str(options['minio_port'])
            extras = extras + minio
        except KeyError as e:
            print("could not get minioport!")
        try:
            controller = ' --set service.controller=' + str(options['controller_port'])
            extras = extras + controller
        except KeyError as e:
            print("could not get controllerport")
            pass
        try:
            user = ' --set alliance.user=' + str(options['user'])
            extras = extras + user
        except KeyError as e:
            print("could not get user")
            pass
        try:
            project = ' --set alliance.project=' + str(options['project'])
            extras = extras + project
        except KeyError as e:
            print("could not get project")
            pass
        try:
            apiUrl = ' --set alliance.apiUrl=' + str(options['api_url'])
            extras = extras + apiUrl
        except KeyError as e:
            print("could not get apiUrl")
            pass
        """

        # for key in options:
        #     print(key)
        #     print(options[key])
        #     extras = extras + ' --set {}={}'.format(key, options[key])

        volume_root = "/"
        if "TELEPRESENCE_ROOT" in os.environ:
            volume_root = os.environ["TELEPRESENCE_ROOT"]
        kubeconfig = os.path.join(volume_root, 'root/.kube/config')

        if 'DEBUG' in os.environ and os.environ['DEBUG'] == 'true':
            chart = 'charts/scaleout/'+options['chart']
        else:
            refresh_charts(self.branch)
            fname = self.branch.replace('/', '-')
            chart = 'charts-{}/scaleout/{}'.format(fname, options['chart'])

        args = ['helm', action, '--kubeconfig', kubeconfig, options['release'], chart]
        # tmp_file_name = uuid.uuid1().hex+'.yaml'
        # tmp_file = open(tmp_file_name, 'w')
        # yaml.dump(options, tmp_file, allow_unicode=True)
        # tmp_file.close()
        # args.append('-f')
        # args.append(tmp_file_name)
        for key in options:
            args.append('--set')
            # args.append('{}={}'.format(key, options[key]))
            args.append(key+"="+options[key].replace(',', '\,'))

        print(args)
        status = subprocess.run(args, cwd=self.cwd)
        # os.remove(tmp_file_name)
        return json.dumps({'helm': {'command': args, 'cwd': str(self.cwd), 'status': str(status)}})

    def delete(self, options):
        volume_root = "/"
        if "TELEPRESENCE_ROOT" in os.environ:
            volume_root = os.environ["TELEPRESENCE_ROOT"]
        kubeconfig = os.path.join(volume_root, 'root/.kube/config')
        print(type(options))
        print(options)
        # args = 'helm --kubeconfig '+str(kubeconfig)+' delete {release}'.format(release=options['release']) #.split(' ')
        args = ['helm', '--kubeconfig', str(kubeconfig), 'delete', options['release']]
        status = subprocess.run(args, cwd=self.cwd)

        return json.dumps({'helm': {'command': args, 'cwd': str(self.cwd), 'status': str(status)}})

    def update(self, options, chart):
        pass
