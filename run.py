#!/usr/bin/python3
import argparse
import importlib
import os
import re
import sys
import subprocess
import threading


class AptInstaller:

    def __init__(self, source_name='aliyun', codename='focal'):
        self.source_name = source_name
        self.codename = codename
        self.install_apt_source()
        self.update_apt_source()

    def gen_apt_source(self):
        url = 'http://mirrors.{}.com/ubuntu/'.format(self.source_name)
        sw_repos = [
            ' main restricted',
            '-updates main restricted',
            ' universe',
            '-updates universe',
            ' multiverse',
            '-updates multiverse',
            '-backports main restricted universe multiverse',
            '-security main restricted',
            '-security universe',
            '-security multiverse'
        ]

        sources = []
        for s in sw_repos:
            sources.append('deb {} {}{}'.format(url, self.codename, s))

        return '\n'.join(sources)

    def install_apt_source(self):
        """
        > to check root privilege
        > to accelerate apt update/upgrade
        :return:
        """
        try:
            apt_file = '/etc/apt/sources.list'
            if os.path.exists(apt_file):
                os.rename(apt_file, apt_file + '.bak')

            source_filename = os.path.join('/etc/apt/sources.list.d', '{}.list'.format(self.source_name))

            with open(source_filename, 'w') as f:
                f.write(self.gen_apt_source())
        except IOError:
            sys.exit("""
            You need root privilege to do this!
            try 'sudo -E ./run.py'
            """)

    @staticmethod
    def update_apt_source():
        subprocess.check_call(['apt', 'update'])
        subprocess.check_call(['apt', 'upgrade'])

    @staticmethod
    def apt_install(package):
        subprocess.check_call(['apt', 'install', package])


def pip_install(module):
    pip_spec = importlib.util.find_spec('pip')
    if pip_spec is None:
        AptInstaller.apt_install('python3-pip')

    subprocess.check_call([sys.executable, '-m', 'pip', 'install', module])


try:
    from github import Github
except ModuleNotFoundError:
    pip_install('PyGithub')
finally:
    from github import Github


def check_password_free_ssh(user, remote):
    private_key_path = os.path.join('/home', user, '.ssh', 'id_rsa')
    cmd = 'ssh -o "StrictHostKeyChecking=no" -T {} -i {}'.format(remote, private_key_path)
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
    output = proc.communicate()[1]

    result = re.search(r"successfully authenticated", output)

    return result is not None


def ssh_keygen_silent(comment):
    cmd = 'cat /dev/zero | ssh-keygen -t rsa -C %s -q -N "" >/dev/null' % comment
    os.system(cmd)

    key_file = os.path.join(os.environ.get('HOME'), '.ssh/id_rsa.pub')
    with open(key_file) as f:
        key = f.readline()
        return key.strip('\n')


class GithubAuth:

    def __init__(self, token=None):
        self.gh = Github(token)

    @classmethod
    def from_username_password(cls, username, password):
        obj = cls()
        obj.gh = Github(username, password)

        return obj

    @classmethod
    def from_token_file(cls, filename):
        obj = cls()
        with open(filename) as f:
            # 40-figures GitHub token
            token = f.readline(40)
            obj.gh = Github(token)

        return obj

    def add_pub_key(self, title, key):
        self.gh.get_user().create_key(title, key)

    def get_git_repos(self):
        return self.gh.get_user().get_repos()


class Cloner(threading.Thread):
    def __init__(self, ssh_url, dest_dir):
        threading.Thread.__init__(self)
        self.url = ssh_url
        self.dir = dest_dir

    def run(self):
        cmd = 'git clone %s' % self.url
        print("""\n\n%s\n\n""" % subprocess.check_output(
            cmd, cwd=self.dir, shell=True, universal_newlines=True
        ))


class GithubMeta(type):
    def __init__(cls, *args, **kwargs):
        cls._username = 'luc'
        cls._email = 'lucmann@qq.com'
        cls._gh = GithubAuth.from_token_file(os.environ.get("GITHUB_TOKEN"))

    @property
    def username(cls):
        return cls._username

    @username.setter
    def username(cls, username):
        cls._username = username

    @property
    def email(cls):
        return cls._email

    @email.setter
    def email(cls, email):
        cls._email = email

    @property
    def gh(cls):
        return cls._gh


class GithubRepo(metaclass=GithubMeta):

    def __init__(self):
        self.__auth__()
        self.__config__()
        self.__clone__()

    @staticmethod
    def __auth__():
        if check_password_free_ssh(GithubRepo.username, "git@github.com"):
            print('ssh established')
        else:
            my_title = GithubRepo.email
            my_key = ssh_keygen_silent(my_title)
            GithubRepo.gh.add_pub_key(my_title, my_key)

    @staticmethod
    def __config__():
        configs = [
            'alias.br branch',
            'alias.ci commit',
            'alias.co checkout',
            'alias.st "status -s"',
            'color.branch true',
            'color.diff true',
            'color.interactive true',
            'color.status true',
            'core.editor vim',
            'core.filemode false',
            'core.autocrlf true',
            'pull.rebase true',
            'user.name %s' % GithubRepo.username,
            'user.email %s' % GithubRepo.email
        ]

        for config in configs:
            os.system('git config --global ' + config)

        print("""
            Git configuration done! \n\n%s
        """ % subprocess.check_output('git config --global -l', shell=True, universal_newlines=True))

    @staticmethod
    def __clone__():
        repos_dir_path = os.path.join('/home', GithubRepo.username, 'github')
        cloner_threads = []

        for repo in GithubRepo.gh.get_git_repos():
            if os.path.exists(os.path.join(repos_dir_path, repo.name)):
                continue

            cloner_threads.append(Cloner(repo.ssh_url, repos_dir_path))

        for t in cloner_threads:
            t.start()
        for t in cloner_threads:
            t.join()

        print("""
            Git repositories cloned! 
        """)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', '-u', help='specify your username on this machine', default='luc')
    parser.add_argument('--email', '-e', help='specify your email for git config', default='lucmann@qq.com')
    parser.add_argument('--apt-source', '-a', dest='apt', help='if you just want to update apt sources', action='store_true')
    args = parser.parse_args()

    if args.apt:
        AptInstaller()

    GithubRepo.username = args.user
    GithubRepo.email = args.email
    GithubRepo()
