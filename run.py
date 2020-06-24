#!/usr/bin/python3
import argparse
import importlib
import os
import re
import sys
import subprocess
import threading

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

    key_file = os.path.join('/home', GithubRepo.username, '.ssh', 'id_rsa.pub')
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
        try:
            with open(filename) as f:
                # 40-figures GitHub token
                token = f.readline(40)
                obj.gh = Github(token)
        except TypeError as err:
            print("Token file not found!")
        finally:
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
    parser.add_argument('--apt-source', '-a', dest='apt_src', nargs='?', const='aliyun',
                        help='just update apt source with specified source', choices=
                        APT_SOURCE_CANDIDATES, default=None)

    args = parser.parse_args()

    if args.apt_src is not None:
        AptInstaller(domain=args.apt_src)
        sys.exit(0)

    GithubRepo.username = args.user
    GithubRepo.email = args.email
    GithubRepo()
