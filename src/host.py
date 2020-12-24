import abc
import os
import pathlib
from hashlib import md5
from io import BytesIO, StringIO
from functools import partial
from datetime import datetime
from shutil import copyfile
from fabric import Connection
from invoke.exceptions import UnexpectedExit


class File:
    def __init__(self, path, time, path_holder):
        self.path = path
        self.holder = path_holder
        if isinstance(time, datetime):
            self.time = time
        else:
            if isinstance(time, str):
                self.time = datetime.fromtimestamp(int(time.split('.')[0]))
            else:
                self.time = datetime.fromtimestamp(time)

    def get_content(self):
        return self.holder.get_content(self.path)

    def __repr__(self):
        return 'Path: %s - %s' % (self.path, self.time.ctime())


class Path:
    def __init__(self, path):
        self.path = path
        self.host = None

    def __repr__(self):
        return 'Host %s:%s' % (self.host, self.path)

    def relative_path(self, path):
        return path.split(self.path)[1]

    @abc.abstractmethod
    def check_connection(self):
        return True

    def write(self, origin, target_holder):
        """ Overwrite target with origin if newer """
        # Find correct path for target file
        target_path = os.path.join(target_holder.path, self.relative_path(origin.path))
        origin_content = None

        try:
            target_md5 = target_holder.get_md5(target_path)
            origin_content = origin.get_content()
            origin_md5 = md5(origin_content).hexdigest()
            origin.holder.update_md5(origin.path, origin_md5)

            if target_md5 == origin_md5:
                return
        except FileNotFoundError:
            pass

        force = False
        target = None
        try:
            target = target_holder.get_file(target_path)
        except FileNotFoundError:
            force = True

        merged = False
        if force or origin.time > target.time:
            if origin_content is None:
                origin_content = origin.get_content()
            target_holder._writefile(origin_content, target_path)
            merged = True

        return merged

    @abc.abstractmethod
    def _writefile(self, origin, target):
        raise NotImplementedError

    @abc.abstractmethod
    def all_files(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_content(self, path):
        raise NotImplementedError

    @abc.abstractmethod
    def get_file(self, path):
        raise NotImplementedError

    @abc.abstractmethod
    def get_md5(self, path):
        raise NotImplementedError

    @abc.abstractmethod
    def update_md5(self, path, md5):
        raise NotImplementedError

class RemotePath(Path):
    def __init__(self, path, host):
        super().__init__(path)
        self.host = host
        self.conn = Connection(host)

    def check_connection(self):
        # Check connection to remote host
        x = self.conn.run('echo "Hello World"', hide=True)
        if x.failed or x.stdout != 'Hello World\n':
            return False
        self.os = self.conn.run('echo $(uname)', hide=True).stdout.split('\n')[0]

        # Check path is valid
        x = self.conn.run('file %s' % self.path, hide=True)
        if x.failed or 'directory' not in x.stdout:
            return False
        return True

    def all_files(self):
        return self._files_path()  # This returns all files in default path

    def _files_path(self, path=None):
        path = self.path if path is None else path

        if self.os == 'Darwin':
            x = self.conn.run(f'find {path} -type f -print0 | xargs -0 stat -f "%m %N"', hide=True).stdout
        elif self.os == 'Linux':
            x = self.conn.run(f'find {path} -type f -printf "%T@ %p\n"', hide=True).stdout
        else:
            raise NotImplementedError

        x = [y.split() for y in x.split('\n')[:-1]]
        files = [File(path, time, self) for time, path in x]
        return files

    def get_content(self, path):
        fd = BytesIO()
        self.conn.get(path, fd)
        return fd.getvalue()

    def get_file(self, path):
        try:
            return self._files_path(path)[0]
        except UnexpectedExit:
            raise FileNotFoundError

    def _writefile(self, origin, target):
        self.conn.run('mkdir -p %s' % os.path.dirname(target))
        self.conn.put(StringIO(origin.decode('utf-8')), remote=target)

        # Write md5 file
        content = md5(origin).hexdigest() + '  ' + os.path.basename(target) + '\n'
        self.conn.put(StringIO(content), remote=target + '.md5')

    def update_md5(self, path, md5):
        content = md5 + '  ' + os.path.basename(path) + '\n'
        self.conn.put(StringIO(content), remote=path + '.md5')

    def get_md5(self, path):
        try:
            return self.conn.run('md5sum %s' % path, hide=True).stdout.split()[0]
        except UnexpectedExit:
            raise FileNotFoundError


class LocalPath(Path):
    def __init__(self, path):
        super().__init__(path)
        self.host = 'local'

    def check_connection(self):
        if os.path.isdir(self.path):
            return True
        return False

    def all_files(self):
        files = []
        for root, _, fs in os.walk(self.path):
            for name in fs:
                path = os.path.join(root, name)
                time = pathlib.Path(path).stat().st_mtime
                files.append(File(path, time, self))
        return files

    def get_content(self, path):
        with open(path, 'rb') as f:
            return f.read()

    def get_file(self, path):
        return File(path, pathlib.Path(path).stat().st_mtime, self)

    def _writefile(self, origin, target):
        with open(target, 'wb') as f:
            f.write(origin)

        with open(target + '.md5', 'w') as f:
            f.write(md5(origin).hexdigest() + '  ' + os.path.basename(target))

    def update_md5(self, path, md5):
        with open(path + '.md5', 'w') as f:
            f.write(md5 + '  ' + os.path.basename(path))

    def get_md5(self, path):
        with open(path + '.md5', 'rb') as f:
            return md5(f.read()).hexdigest()
