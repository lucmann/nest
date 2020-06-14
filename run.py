#!/usr/bin/python3
import os
import re
import subprocess
import threading

from github import Github

def check_password_free_ssh(remote):
    cmd = 'ssh -o "StrictHostKeyChecking=no" -T %s' % remote
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
        if check_password_free_ssh("git@github.com"):
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
        repos_dir_path = os.path.join(os.environ.get('HOME'), 'github')
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
    GithubRepo()

