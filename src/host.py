import abc
import os
import pathlib
import asyncssh
import asyncio
import getpass
import stat
import time
from io import BytesIO
from datetime import datetime
from aiofile import async_open
from contextlib import asynccontextmanager
from queue import Queue, Empty
from threading import Thread, Semaphore


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


class RemoteWDThread(Thread):
    def __init__(self, path, host, key, tasks, holder):
        Thread.__init__(self)
        self.path = path
        self.host = host
        self.key = key
        self.holder = holder
        self.process = None
        self.tasks = tasks

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def async_wd():
            async with asyncssh.connect(self.host, client_keys=self.key) as conn:
                async with conn.create_process('python /tmp/iris_wd.py',
                                               input=self.path, stderr=asyncssh.STDOUT) as process:
                    self.process = process
                    while True:
                        try:
                            path, isdir, change, mtime = (await process.stdout.readline()).split()
                            self.tasks.put(File(path, mtime, self.holder))
                        except ValueError:
                            return
        loop.run_until_complete(async_wd())
        loop.close()


def run(tasks):  # This runs tasks
    if not isinstance(tasks, list):
        tasks = [tasks]

    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(asyncio.gather(*tasks))[0]
    return res


class Path:
    def __init__(self, path):
        self.path = path
        self.host = None
        self.wd = None
        self.tasks = None

    def __repr__(self):
        return 'Host %s:%s' % (self.host, self.path)

    def relative_path(self, path):
        return path.split(self.path)[1]

    @abc.abstractmethod
    def check_connection(self):
        return True

    async def write(self, origin, target_holder, callback=None):
        """ Overwrite target with origin if newer """
        # Find correct path for target file
        target_path = os.path.join(target_holder.path, self.relative_path(origin.path))
        origin_content = None

        # Ignore some files (this is a good place as is implementation independent)
        if target_path.endswith('.md5') or target_path.endswith('.swp') or target_path.endswith('.swx'):
            return False

        force = False
        target = None
        try:
            target = await target_holder.get_file(target_path)
        except FileNotFoundError:
            force = True

        merged = False
        if force or origin.time > target.time:
            origin_content = await origin.get_content()
            if origin_content is None:
                return False

            await target_holder._writefile(origin_content, target_path, mtime=origin.time)
            merged = True

        if callback is not None:
            callback(merged)

        return merged

    def next_task(self):
        assert self.tasks is not None, 'The watchdog process is not running'
        try:
            return self.tasks.get(timeout=1e-2)
        except Empty:
            return None

    @abc.abstractmethod
    async def _writefile(self, origin, target, mtime):
        raise NotImplementedError

    @abc.abstractmethod
    def all_files(self):
        raise NotImplementedError

    @abc.abstractmethod
    async def get_content(self, path):
        raise NotImplementedError

    @abc.abstractmethod
    async def get_file(self, path):
        raise NotImplementedError

    @abc.abstractmethod
    def start_watchdog(self):
        """
        This should start the watchdog process on the host
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    def cleanup(self):
        pass


class RemotePath(Path):
    def __init__(self, path, host, max_parallel=10, key='~/.ssh/id_rsa'):
        super().__init__(path)
        self.host = host
        try:
            self.key = RemotePath.load_agent_keys()
        except ValueError:
            self.key = RemotePath.import_private_key(key)
        self.conn = None
        self.sftp = None

    @asynccontextmanager
    async def sftp_context(self):
        if self.sftp is None:
            async with self.ssh_context() as conn:
                self.sftp = await conn.start_sftp_client(env={'block_size': 32768})

        async with self.ssh_context() as conn:
            yield conn, self.sftp

    @asynccontextmanager
    async def ssh_context(self):
        if self.conn is None:
            self.conn = await asyncssh.connect(self.host, client_keys=self.key)

        yield self.conn

    def load_agent_keys(agent_path=None):
        """
        The ssh-agent is a convenience tool that aims at easying the use of
        private keys protected with a password. In a nutshell, the agent runs on
        your local computer, and you trust it enough to load one or several keys
        into the agent once and for good - and you provide the password
        at that time.
        Later on, each time an ssh connection needs to access a key,
        the agent can act as a proxy for you and pass the key along
        to the ssh client without the need for you to enter the password.
        The ``load_agent_keys`` function allows your python code to access
        the keys currently knwns to the agent. It is automatically called by the
        :class:`~apssh.nodes.SshNode` class if you do not explicit the set of
        keys that you plan to use.
        Parameters:
          agent_path: how to locate the agent;
            defaults to env. variable $SSH_AUTH_SOCK
        Returns:
          a list of SSHKey_ keys from the agent
        .. note::
          Use the command ``ssh-add -l`` to inspect the set of keys
          currently present in your agent.
        """
        # pylint: disable=c0111
        async def co_load_agent_keys(agent_path):
            # make sure to return an empty list when something goes wrong
            try:
                agent_client = asyncssh.SSHAgentClient(agent_path)
                keys = await agent_client.get_keys()
                agent_client.close()
                return keys
            except ValueError as exc:                        # pylint: disable=w0703
                # not quite sure which exceptions to expect here
                print(f"When fetching agent keys: "
                      f"ignored exception {type(exc)} - {exc}")
                return []

        agent_path = agent_path or os.environ.get('SSH_AUTH_SOCK', None)
        if agent_path is None:
            return []
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(co_load_agent_keys(agent_path))

    def import_private_key(filename):
        """
        Attempts to import a private key from file
        Prompts for a password if needed
        """
        sshkey = None
        basename = os.path.basename(filename)

        filename = os.path.expanduser(filename)
        if not os.path.exists(filename):
            print("No such key file {}".format(filename))
            return
        with open(filename) as file:
            data = file.read()
            try:
                sshkey = asyncssh.import_private_key(data)
            except asyncssh.KeyImportError:
                while True:
                    passphrase = getpass.getpass("Enter passphrase for key {} : ".format(basename))
                    if not passphrase:
                        print("Ignoring key {}".format(filename))
                        break
                    try:
                        sshkey = asyncssh.import_private_key(data, passphrase)
                        break
                    except asyncssh.KeyImportError:
                        print("Wrong passphrase")
            return sshkey

    def check_connection(self):
        return run(self._check_connection())

    async def _check_connection(self):
        # Check connection to remote host
        async with self.sftp_context() as context:
            conn, sftp = context
            try:
                # Check path is valid
                if await sftp.isdir(self.path):
                    return True
                return False
            except TimeoutError:
                return False

    def all_files(self):
        return run(self._files_path())  # This returns all files in default path

    async def _recursive_scan(self, path, files=[]):
        async with self.sftp_context() as context:
            conn, sftp = context
            if await sftp.isfile(path):
                return [[(await sftp.stat(path)).mtime, path]]

            tasks = set()
            async for f in sftp.scandir(path):
                if f.filename in ('.', '..'):  # Ignore reference to self and parent
                    continue

                remotepath = os.path.join(path, f.filename)
                if stat.S_ISDIR(f.attrs.permissions):
                    tasks.add(asyncio.create_task(self._recursive_scan(remotepath, files)))
                else:
                    files.append([f.attrs.mtime, remotepath])

            if tasks:
                await asyncio.gather(*tasks)
        return files

    async def _files_path(self, path=None):
        path = self.path if path is None else path
        files = await self._recursive_scan(path)
        files = [File(path, time, self) for time, path in files]
        return files[0] if len(files) == 1 else files

    async def get_content(self, path):
        fd = BytesIO()
        try:
            async with self.sftp_context() as context:
                conn, sftp = context

                async with sftp.open(path, 'rb') as src:
                    while True:
                        data = await src.read(32768)
                        if not data:
                            break
                        fd.write(data)
        except asyncssh.sftp.SFTPNoSuchFile:
            return None

        return fd.getvalue()

    async def get_file(self, path):
        try:
            return await self._files_path(path)
        except (asyncssh.process.ProcessError, asyncssh.sftp.SFTPNoSuchFile):
            raise FileNotFoundError

    async def _writefile(self, origin, target, mtime):
        origin = BytesIO(origin)
        async with self.sftp_context() as context:
            conn, sftp = context
            await sftp.makedirs(os.path.dirname(target), exist_ok=True)
            async with sftp.open(target, 'wb', asyncssh.SFTPAttrs(mtime=mtime.timestamp())) as dst:
                while True:
                    data = origin.read(32768)
                    if not data:
                        break
                    await dst.write(data)

    def start_watchdog(self):
        assert self.tasks is None, 'Already initialized the watchdog'
        self.tasks = Queue()

        import watchdog_service
        src_path = os.path.abspath(watchdog_service.__file__)

        async def upload_watchdog():
            async with self.sftp_context() as context:
                conn, sftp = context
                await sftp.put(src_path, '/tmp/iris_wd.py')

        run(upload_watchdog())
        self.wd = RemoteWDThread(self.path, self.host, self.key, self.tasks, self)
        self.wd.start()

        while self.wd.process is None:
            time.sleep(1e-2)

    def cleanup(self):
        if self.wd is None:
            return
        self.wd.process.terminate()


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

    async def get_content(self, path):
        try:
            async with async_open(path, 'rb') as f:
                return await f.read()
        except FileNotFoundError:
            return None

    async def get_file(self, path):
        return File(path, pathlib.Path(path).stat().st_mtime, self)

    async def _writefile(self, origin, target, mtime):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        async with async_open(target, 'wb') as f:
            await f.write(origin)
        os.utime(target, (mtime.timestamp(), mtime.timestamp()))

    def _wd(path, self, q):
        from watchdog_service import run_wd
        run_wd(path, queue=q)
        while True:
            path, isdir, change, mtime = q.get().split()
            self.tasks.put(File(path, mtime, self))

    def start_watchdog(self):
        assert self.tasks is None, 'Already initialized the watchdog'
        self.tasks = Queue()

        self.wd = Thread(target=LocalPath._wd, args=(self.path, self, Queue()))
        self.wd.daemon = True
        self.wd.start()
