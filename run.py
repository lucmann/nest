#!/usr/bin/python3
import argparse
import importlib
import os
import re
import sys
import subprocess
import getpass
import socket
from multiprocessing.pool import ThreadPool

APT_SOURCE_CANDIDATES = ['aliyun', 'tsinghua', 'ustc', '163', 'sohu']

def ubuntu_codename():
    proc = subprocess.Popen('. /etc/os-release && echo $UBUNTU_CODENAME',
                            stdout=subprocess.PIPE, shell=True, universal_newlines=True)
    return proc.communicate()[0].strip()


class AptInstaller:

    def __init__(self, domain='aliyun'):
        self.domain = domain
        self.install_apt_source()
        self.update_apt_source()

    def gen_apt_source(self):
        if self.domain in ['tsinghua', 'ustc']:
            protocol = 'https://'
        else:
            protocol = 'http://'

        if self.domain in ['ustc']:
            domain_name = '.'.join([self.domain, 'edu', 'cn'])
        elif self.domain in ['tsinghua']:
            domain_name = '.'.join(['tuna', self.domain, 'edu', 'cn'])
        else:
            domain_name = '.'.join([self.domain, 'com'])

        suffixes = ['', '-updates', '-backports', '-security', '-proposed']

        codename = ubuntu_codename()

        sources = []
        for suffix in suffixes:
            sources.append('deb {}mirrors.{}/ubuntu/ {}{} main restricted universe multiverse'.format(
                protocol, domain_name, codename, suffix))
            sources.append('deb-src {}mirrors.{}/ubuntu/ {}{} main restricted universe multiverse'.format(
                protocol, domain_name, codename, suffix))

        return '\n'.join(sources)

    @staticmethod
    def apt_source_file_abspath(name):
        if name == 'sources':
            return os.path.join('/etc/apt', '{}.list'.format(name))
        else:
            return os.path.join('/etc/apt/sources.list.d', '{}.list'.format(name))

    def install_apt_source(self):
        """
        > to check root privilege
        > to accelerate apt update/upgrade
        :return:
        """
        try:
            apt_file = self.apt_source_file_abspath('sources')
            if os.path.exists(apt_file):
                os.rename(apt_file, apt_file + '.bak')

            # clean the old before installing the new
            subprocess.check_call('rm -f *.list', cwd='/etc/apt/sources.list.d', shell=True)

            source_filename = self.apt_source_file_abspath(self.domain)
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
    from github import Github

try:
    from gitlab import Gitlab
except ModuleNotFoundError:
    pip_install('python-gitlab')
    from gitlab import Gitlab


def ssh_keygen_silent(comment):
    key_file = os.path.join('/home', getpass.getuser(), '.ssh', 'id_rsa.pub')

    if not os.path.exists(key_file):
        cmd = 'cat /dev/zero | ssh-keygen -t rsa -C %s -q -N "" >/dev/null' % comment
        os.system(cmd)

    with open(key_file) as f:
        key = f.readline()
        return key.strip('\n')


class Cloner:
    def __init__(self, repo, dest_dir):
        self.pool = ThreadPool(processes=1)
        self.repo = repo
        self.dir = dest_dir

    @staticmethod
    def __clone__(src, dest):
        cmd = 'git clone --depth 1 %s' % src.url
        print("""Cloning {}\n\n{}\n\n""".format(src.url, subprocess.check_output(
            cmd, cwd=dest, shell=True, text=True
        )))

        return True

    def start(self):
        return self.pool.apply_async(self.__clone__, (self.repo, self.dir))


class CHSAccount(type):
    """
    Code Hosting Sites account metaclass. use github.com by default.
    """
    def __init__(cls, *args, **kwargs):
        cls._username = 'lucmann'
        cls._email = 'lucmann@qq.com'
        cls._ssh = 'git@github.com'
        cls._token = None

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
    def ssh(cls):
        return cls._ssh

    @ssh.setter
    def ssh(cls, ssh):
        cls._ssh = ssh

    @property
    def token(cls):
        return cls._token

    @token.setter
    def token(cls, file):
        cls._token = file

    @property
    def ssh_is_password_free(cls):
        """
        :param cls:
        :return: if ssh is connected

        The strings returned by ssh servers may vary. For example,

        Welcome to GitLab, @$username!
        Hi $username! You've successfully authenticated, but GitHub does not provide shell access.

        But anyway on success, $username will be echoed.
        """

        private_key_path = os.path.join('/home', getpass.getuser(), '.ssh', 'id_rsa')
        if not os.path.exists(private_key_path):
            return False

        cmd = 'ssh -o "StrictHostKeyChecking=no" -T {} -i {}'.format(cls._ssh, private_key_path)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
        for s in proc.communicate():
            if re.search(r'{}'.format(cls._username), s):
                return True

        return False


class Repo:
    """
    A generic repository encapsulating different repository objects such as gitlab and github
    """
    def __init__(self, name, url):
        self.name = name
        self.url = url
        self.cloned = False


class GitHubRepos(metaclass=CHSAccount):
    def __init__(self):
        self._session = self.open_session()
        self.add_ssh_key()

    def open_session(self):
        try:
            with open(type(self).token) as f:
                token = f.readline().strip('\n')
                return Github(token)
        except TypeError as err:
            assert None, "Please tell me a file that saves a token for {}".format(type(self).ssh)

    def add_ssh_key(self):
        if type(self).ssh_is_password_free:
            print('SSH connection to {} has been available.'.format(type(self).ssh))
        else:
            title = socket.gethostname()
            key = ssh_keygen_silent(type(self).email)
            self._session.get_user().create_key(title, key)

    def get_repos(self):
        return [ Repo(r.name, r.ssh_url) for r in self._session.get_user().get_repos() ]


class GitLabRepos(metaclass=CHSAccount):
    def __init__(self):
        self._session = self.open_session()
        self._session.auth()
        self.add_ssh_key()

    def open_session(self):
        try:
            with open(type(self).token) as f:
                token = f.readline().strip('\n')
                return Gitlab('https://gitlab.freedesktop.org', private_token=token)
        except TypeError as err:
            assert None, "Please tell me a file that saves a token for {}".format(type(self).ssh)

    def add_ssh_key(self):
        if type(self).ssh_is_password_free:
            print('SSH connection to {} has been available.'.format(type(self).ssh))
        else:
            title = socket.gethostname()
            key = ssh_keygen_silent(type(self).email)
            self._session.user.keys.create({'title': title, 'key': key})

    def get_repos(self):
        return [ Repo(r.name, r.ssh_url_to_repo) for r in self._session.projects.list(owned=True) ]


class GitClone:
    def __init__(self, sources, dest=os.path.join('/home', getpass.getuser(), 'github')):
        self.code_hosting_sites = sources
        self.dest_dir = dest
        self.__clone__()

    def __clone__(self):
        target_repos = []
        cloner_threads = []

        for chs in self.code_hosting_sites:
            target_repos += chs.get_repos()

        for repo in target_repos:
            if os.path.exists(os.path.join(self.dest_dir, repo.name)):
                continue

            cloner_threads.append(Cloner(repo, self.dest_dir))

        cloner_results = [ ct.start() for ct in cloner_threads ]

        for r in cloner_results:
            print(r.get())


class GitConfig:
    def __init__(self, username, email):
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
            'pull.rebase true',
            'user.name %s'.format(username),
            'user.email %s'.format(email)
        ]

        for config in configs:
            os.system('git config --global ' + config)

        print("""
            Git configuration done! \n\n%s\n\n
        """ % subprocess.check_output('git config --global -l', shell=True, text=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', '-u', help='specify your username on this machine', default='lucmann')
    parser.add_argument('--email', '-e', help='specify your email for git config', default='lucmann@qq.com')
    parser.add_argument('--apt-source', '-a', dest='apt_src', nargs='?', const='aliyun',
                        help='just update apt source with specified source', choices=
                        APT_SOURCE_CANDIDATES, default=None)
    parser.add_argument('--github-token', dest='gh_token', help='specify file path saving GitHub personal access token',
                        nargs='?', const=os.path.join('/home', getpass.getuser(), 'github-token.txt'), default=None)
    parser.add_argument('--gitlab-token', dest='gl_token', help='specify file path saving GitLab personal access token',
                        nargs='?', const=os.path.join('/home', getpass.getuser(), 'gitlab-token.txt'), default=None)

    args = parser.parse_args()

    if args.apt_src is not None:
        AptInstaller(domain=args.apt_src)
        sys.exit(0)

    code_hosting_sites = []

    if args.gh_token is not None:
        GitHubRepos.username = args.user
        GitHubRepos.email = args.email
        GitHubRepos.token = args.gh_token
        GitHubRepos.ssh = 'git@github.com'

        code_hosting_sites.append(GitHubRepos())

    if args.gl_token is not None:
        GitLabRepos.username = args.user
        GitLabRepos.email = args.email
        GitLabRepos.token = args.gl_token
        GitLabRepos.ssh = 'git@gitlab.freedesktop.org'

        code_hosting_sites.append(GitLabRepos())

    if len(code_hosting_sites):
        GitClone(code_hosting_sites)
