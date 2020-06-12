#!/usr/bin/python
import os
import re
import subprocess
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

    def add_pub_key_to_gh(self, title, key):
        self.gh.get_user().create_key(title, key)


class GithubRepo:

    def __init__(self, username, email):
        self.username = username
        self.email = email
        self.__auth__()
        self.__config__()

    def __auth__(self):
        if check_password_free_ssh("git@github.com"):
            print('ssh established')
        else:
            my_title = self.email
            my_key = ssh_keygen_silent(my_title)
            my_gh = GithubAuth.from_token_file(os.environ.get("GITHUB_TOKEN"))
            my_gh.add_pub_key_to_gh(my_title, my_key)

    def __config__(self):
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
            'user.name %s' % self.username,
            'user.email %s' % self.email
        ]

        for config in configs:
            os.system('git config --global ' + config)

if __name__ == '__main__':
    GithubRepo('luc', 'luc@sietium.com')

