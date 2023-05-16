import abc
import os
import pathlib
import asyncssh
import asyncio
import getpass
import stat
import time
import logging
from io import BytesIO
from datetime import datetime
from aiofile import async_open
from queue import Queue, Empty
from threading import Thread
from fnmatch import fnmatchcase
log = logging.getLogger('iris')


TMP_PREFIX = '.iris-tmp.'
IGNORED_PATTERNS = ('*.swpx', '*.md5', '.swp', '.swx', '.DS_Store', '~')


def enhance_pattern(pattern):
    if pattern.endswith('/'):  # Automatically append an * if a directory is specified
        pattern = pattern + '*'
    pattern = pattern.replace('./', '', 1)  # if ./ at start remove it # TODO
    return pattern


async def gather_with_concurrency(n, *coros):
    semaphore = asyncio.Semaphore(n)

    async def sem_coro(coro):
        async with semaphore:
            return await coro
    return await asyncio.gather(*(sem_coro(c) for c in coros))


def run(tasks):
    if not tasks:
        return None

    if not isinstance(tasks, list):
        tasks = [tasks]

    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(gather_with_concurrency(128, *tasks))[0]  # TODO: Gather concurrency?
    return res


class File:
    def __init__(self, path, time, path_holder, change_type=None):
        self.path = path
        self.holder = path_holder
        self.time = self.set_time(time) if time is not None else None
        self.change_type = change_type

    def set_time(self, time):
        if isinstance(time, datetime):
            return time
        else:
            if isinstance(time, str):
                return datetime.fromtimestamp(int(float(time)))
            else:
                return datetime.fromtimestamp(int(time))

    def fetch_time(self):
        return self.holder.get_time(self.path)

    def get_content(self, cb=None):
        return self.holder.get_content(self.path, cb)

    @property
    def short_path(self):
        return self.path.split(self.holder.path)[-1]

    def __repr__(self):
        try:
            return f'Path: {self.path} - {self.time.ctime()} - {self.time.timestamp()}'
        except AttributeError:
            return f'Path: {self.path}'


class Path:
    def __init__(self, path, dry=False, pattern='*', ignore_pattern='//', *args, **kwargs):
        self.path = path + ('/' if not path.endswith('/') else '')
        self.host = None
        self.dry = dry
        self.pattern = pattern
        self.ignore_pattern = ignore_pattern
        self.wd = None
        self.tasks = None
        self.CHUNK_SIZE = int(1e+7)  # Default 10 megabytes for each write/read progress

    def has_pattern(self, p, path):
        return any([fnmatchcase(p.split(path)[1], enhance_pattern(pat))
                    for pat in self.pattern.split()])

    def has_ignore(self, p, path):
        return any([fnmatchcase(p.split(path)[1], enhance_pattern(pat))
                    for pat in self.ignore_pattern.split()])

    def __repr__(self):
        return f'Host {self.host}:{self.path}'

    def relative_path(self, path):
        path = os.path.abspath(path)
        return path.split(self.path)[1]

    @abc.abstractmethod
    def check_connection(self):
        return True

    async def _empty(self):
        return None

    def write(self, origin, target_holder, write_cb=None, write_p_cb=None):
        # Find correct path for target file
        target_path = os.path.join(target_holder.path,
                                   origin.holder.relative_path(origin.path))

        # If tried to write a tmp file just delete original and return
        # This does not seem the best place but it works fine
        if os.path.basename(target_path).startswith(TMP_PREFIX):
            return self._delete(origin, origin.holder)

        # Ignore some files (this is a good place as is implementation independent)
        if (target_path.endswith(IGNORED_PATTERNS)
                or self.has_ignore(target_path, target_holder.path)):
            log.debug(f'Ignored file {origin}')
            return self._empty()

        if not self.has_pattern(target_path, target_holder.path):
            return self._empty()

        if origin.change_type in [None, 'C', 'M']:
            return self._write(origin, target_holder, write_cb, write_p_cb)
        else:
            return self._delete(origin, target_holder, write_cb)

    async def _delete(self, origin, target_holder, callback=None):
        """ Delete file """
        # Find correct path for target file
        target_path = os.path.join(target_holder.path,
                                   origin.holder.relative_path(origin.path))

        target = None
        try:
            target = await target_holder.get_file(target_path)
        except FileNotFoundError:
            return True

        merged = False
        if origin.time > target.time:
            log.debug(f'Calling delete on {target_path}')
            if not self.dry:
                await target_holder._deletefile(target_path)
            merged = True

        if callback is not None:
            callback(merged=merged, change='D')

        return merged

    async def _write(self, origin, target_holder, callback=None, p_callback=None):
        """ Overwrite target with origin if newer """
        # Find correct path for target file
        target_path = os.path.join(target_holder.path,
                                   origin.holder.relative_path(origin.path))
        force = False
        target = None
        try:
            target = await target_holder.get_file(target_path)
        except FileNotFoundError:
            force = True

        # Watchdog return File instances with no time, we fetch it now
        try:
            if origin.time is None:
                origin.time = await origin.fetch_time()
        except FileNotFoundError:
            return False

        merged = False
        if force or origin.time > target.time:
            origin_content = await origin.get_content(p_callback)
            if origin_content is None:
                return False

            log.debug(f'Calling write on {target_path}')
            if not self.dry:
                basename = os.path.basename(target_path)
                tmp_target_path = target_path.replace(basename, f'{TMP_PREFIX}{basename}')
                await target_holder._writefile(origin_content, tmp_target_path,
                                               mtime=origin.time, cb=p_callback)
                await target_holder._renamefile(tmp_target_path, target_path)
            merged = True

        if callback is not None:
            callback(merged=merged, change='M')

        return merged

    def next_task(self, n=100):
        if self.tasks is None:
            return None

        res = []
        try:
            for i in range(n):
                res.append(self.tasks.get_nowait())
        except Empty:
            pass
        return res

    @abc.abstractmethod
    async def _writefile(self, origin, target, mtime, cb):
        raise NotImplementedError

    @abc.abstractmethod
    async def _deletefile(self, target):
        raise NotImplementedError

    @abc.abstractmethod
    async def _renamefile(self, old_path, new_path):
        raise NotImplementedError

    @abc.abstractmethod
    def all_files(self):
        raise NotImplementedError

    @abc.abstractmethod
    async def get_content(self, path, cb):
        raise NotImplementedError

    @abc.abstractmethod
    async def get_file(self, path):
        raise NotImplementedError

    @abc.abstractmethod
    async def get_time(self, path):
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
    def __init__(self, path, host, dry=False, pattern='*', ignore_pattern='//', key='~/.ssh/id_rsa', jump_host=None, *args, **kwargs):
        super().__init__(path, dry, pattern, ignore_pattern, *args, **kwargs)
        # Setup configs for connection
        user = os.getlogin()
        self.port = 22  # Default port
        if '@' in host:
            user, _, host = host.partition('@')
        if ':' in host:
            host, _, port = host.partition(':')
            self.port = int(port)
        self.host = host
        self.user = user

        # Jumping connection
        self.jump = jump_host is not None
        jump_user = os.getlogin()
        self.jump_port = 22
        if jump_host is not None:
            if '@' in jump_host:
                jump_user, _, jump_host = jump_host.partition('@')
            if ':' in jump_host:
                jump_host, _, jump_port = jump_host.partition(':')
                self.jump_port = int(port)
        self.jump_host = jump_host
        self.jump_user = jump_user

        self.password = None
        try:
            self.key = RemotePath.load_agent_keys()
        except ValueError:
            try:
                self.key = RemotePath.import_private_key(key)
            except FileNotFoundError:
                self.key = None
                self.password = getpass.getpass('No valid key found, '
                                                'specify a password for auth: ')

        self._conn = None
        self._sftp = None
        self._last_check = 0
        self.open_sem = asyncio.Semaphore(128)  # Max open files?
        self.req = set()

    @property
    def conn(self):
        if self._conn is None:
            return self.ssh_connect()
        return self._conn

    @property
    def sftp(self):
        if self._sftp is None:
            return self.sftp_connect()
        return self._sftp

    async def sftp_connect(self):  # This is awaited on check connection
        self._sftp = await self.conn.start_sftp_client()
        return self._sftp

    async def ssh_connect(self):
        options = asyncssh.SSHClientConnectionOptions(
            client_keys=self.key if self.key is not None else None,
            password=self.password if self.key is None else None)
        if self.jump:
            self._tunnel = await asyncssh.connect(self.jump_host,
                                                  port=self.jump_port,
                                                  username=self.jump_user,
                                                  options=options)
            self._conn = await self._tunnel.connect_ssh(self.host,
                                                        port=self.port,
                                                        username=self.user,
                                                        options=options)
        else:
            self._conn = await asyncssh.connect(self.host, port=self.port,
                                                username=self.user,
                                                options=options)
        return self._conn

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
            except ValueError as exc:
                # not quite sure which exceptions to expect here
                log.error(f"When fetching agent keys: "
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
            log.error("No such key file {}".format(filename))
            raise FileNotFoundError
        with open(filename) as file:
            data = file.read()
            try:
                sshkey = asyncssh.import_private_key(data)
            except asyncssh.KeyImportError:
                while True:
                    passphrase = getpass.getpass(f"Enter passphrase for key {basename} : ")
                    if not passphrase:
                        log.info(f"Ignoring key {filename}")
                        break
                    try:
                        sshkey = asyncssh.import_private_key(data, passphrase)
                        break
                    except asyncssh.KeyImportError:
                        log.error("Wrong passphrase")
            return sshkey

    def check_connection(self):
        return run(self._check_connection())

    async def _check_connection(self):
        if time.time() - self._last_check < 30:
            return True
        self._last_check = time.time()

        if self._conn is None:
            try:
                await self.conn  # This will initialize the connections
            except asyncssh.misc.PermissionDenied:
                self.key = None
                # TODO: This is temporary
                print('No valid key found, specify a password for auth:')
                self.password = getpass.getpass()
                await self.conn
            await self.sftp

        try:  # Check connection to remote host
            if await self.sftp.isdir(self.path):
                return True
            return False
        except TimeoutError:
            return False

    def all_files(self):
        res = run(self._files_path())  # This returns all files in default path
        if not isinstance(res, list):
            return [res]
        return res

    async def _recursive_scan(self, path, files):
        if await self.sftp.isfile(path):
            return [[(await self.sftp.stat(path)).mtime, path]]

        tasks = set()
        async for f in self.sftp.scandir(path):
            if f.filename in ('.', '..'):  # Ignore reference to self and parent
                continue

            if stat.S_ISLNK(f.attrs.permissions):  # Ignore symbolic links
                continue

            remotepath = os.path.join(path, f.filename)
            if (not self.has_pattern(remotepath, self.path)
                    or self.has_ignore(remotepath, self.path)):
                continue

            if stat.S_ISDIR(f.attrs.permissions):
                tasks.add(asyncio.create_task(self._recursive_scan(remotepath, files)))
            else:
                files.append([f.attrs.mtime, remotepath])

        if tasks:
            await asyncio.gather(*tasks)
        return files

    async def _files_path(self, path=None):
        path = self.path if path is None else path
        files = await self._recursive_scan(path, [])
        files = [File(path, time, self) for time, path in files]
        return files[0] if len(files) == 1 else files

    async def get_content(self, path, cb):
        fd = BytesIO()
        try:
            size = (await self.sftp.lstat(path)).size
            async with self.open_sem:
                async with self.sftp.open(path, 'rb', block_size=65536 * 100) as src:
                    data = True
                    while data:
                        data = await src.read(size=self.CHUNK_SIZE)
                        if data:
                            fd.write(data)
                            if cb is not None and size > self.CHUNK_SIZE:
                                cb(self.CHUNK_SIZE / size)
            if cb is not None:
                cb(False)
        except asyncssh.SFTPNoSuchFile:
            return None

        return fd.getvalue()

    async def get_time(self, path):
        return (await self.get_file(path)).time

    async def get_file(self, path):
        try:
            return await self._files_path(path)
        except (asyncssh.ProcessError, asyncssh.SFTPNoSuchFile):
            raise FileNotFoundError

    async def _writefile(self, origin, target, mtime, cb):
        path = self.sftp.encode(os.path.dirname(target))

        await self.sftp.makedirs(path, exist_ok=True)
        if not await self.sftp.isdir(path):
            raise asyncssh.SFTPFailure(f'{path} is not a directory') from None

        data = BytesIO(origin).read()
        async with self.open_sem:
            async with self.sftp.open(target, 'wb', block_size=65536 * 100) as dst:
                ith = 0
                while ith * self.CHUNK_SIZE < len(origin):
                    await dst.write(data[ith * self.CHUNK_SIZE: (ith + 1) * self.CHUNK_SIZE])
                    ith += 1
                    if cb is not None and len(origin) > self.CHUNK_SIZE:
                        cb(self.CHUNK_SIZE / len(origin))
                await dst.utime(times=(mtime.timestamp(), mtime.timestamp()))
            if cb is not None:
                cb(True)

    async def _deletefile(self, target):
        try:
            await self.sftp.remove(target)
        except (asyncssh.ProcessError, asyncssh.SFTPNoSuchFile):
            pass

    async def _renamefile(self, old_path, new_path):
        try:
            await self.sftp.rename(old_path, new_path, flags=0x00000001)
        except (asyncssh.ProcessError, asyncssh.SFTPNoSuchFile):
            pass

    def start_watchdog(self):
        assert self.tasks is None, 'Already initialized the watchdog'
        self.tasks = Queue(maxsize=-1)

        import iris.watchdog_service
        src_path = os.path.abspath(iris.watchdog_service.__file__)

        async def upload_watchdog():
            await self.sftp.put(src_path, '/tmp/iris_wd.py')

        log.debug('Running remote wd')
        run(upload_watchdog())
        self.wd = RemoteWDThread(self)
        self.wd.start()

        while self.wd.process is None:
            time.sleep(1e-2)

    def cleanup(self):
        if self.wd is None:
            return

        try:
            self.wd.process.terminate()
        except AttributeError:
            pass

    def next_task(self):
        # Be sure the connection does not drop here
        self.check_connection()
        return super().next_task()


class RemoteWDThread(Thread):
    def __init__(self, holder):
        Thread.__init__(self)
        # Setup remote connection
        self.path = holder.path
        self.user = holder.user
        self.host = holder.host
        self.port = holder.port
        # Setup jump connection
        self.jump = holder.jump
        self.jump_user = holder.jump_user
        self.jump_host = holder.jump_host
        self.jump_port = holder.jump_port
        # Authentication
        self.key = holder.key
        self.password = holder.password
        # WD setup
        self.tasks = holder.tasks
        self.holder = holder
        self.pattern = holder.pattern
        self.ignore_pattern = holder.ignore_pattern
        self.process = None

    def run(self):
        loop = asyncio.new_event_loop()

        async def async_wd():
            options = asyncssh.SSHClientConnectionOptions(
                client_keys=self.key,
                password=self.password if self.key is None else None)
            provider = asyncssh.connect
            if self.jump:
                self._tunnel = await asyncssh.connect(self.jump_host,
                                                      port=self.jump_port,
                                                      username=self.jump_user,
                                                      options=options)
                provider = self._tunnel.connect_ssh

            async with provider(self.host, port=self.port,
                                keepalive_interval=60, keepalive_count_max=9,
                                options=options) as conn:
                async with conn.create_process('python3 -u /tmp/iris_wd.py',
                                               input='\n'.join([self.path, self.pattern, self.ignore_pattern]),
                                               stderr=asyncssh.STDOUT) as process:
                    self.process = process
                    line = False
                    while True:
                        try:
                            line = (await process.stdout.readline()).split('%')
                            path, isdir, change, mtime = line
                            log.debug(f'Remote WD event: {path} {isdir} {change} {mtime}')
                            if change != 'D':
                                mtime = None
                            self.tasks.put(File(path, mtime, self.holder, change))
                        except Exception as e:
                            log.debug(e)
                            while line:
                                if line != ['']:
                                    log.info(line)  # Output info about exception
                                line = await process.stdout.readline()
                            break
        loop.run_until_complete(async_wd())
        loop.close()


class LocalPath(Path):
    def __init__(self, path, dry=False, pattern='*', ignore_pattern='//', *args, **kwargs):
        super().__init__(os.path.expanduser(path), dry, pattern, ignore_pattern, *args, **kwargs)
        self.host = 'local'
        self.open_sem = asyncio.Semaphore(128)  # Max open files?
        self.CHUNK_SIZE = int(1e+8)  # 100 mb for local writing and reading

    def check_connection(self):
        if os.path.isdir(self.path):
            return True
        return False

    def all_files(self):
        files = []
        for root, _, fs in os.walk(self.path):
            for name in fs:
                path = os.path.join(root, name)

                if os.path.islink(path):  # Ignore sys links
                    continue

                if not self.has_pattern(path, self.path) or self.has_ignore(path, self.path):
                    continue

                time = pathlib.Path(path).stat().st_mtime
                files.append(File(path, time, self))
        return files

    async def get_content(self, path, cb):
        if not os.path.isfile(path):
            return None
        fd = BytesIO()
        async with self.open_sem:
            size = os.path.getsize(path)
            async with async_open(path, 'rb') as src:
                data = True
                while data:
                    data = await src.read(length=self.CHUNK_SIZE)
                    if data:
                        fd.write(data)
                        if cb is not None and size > self.CHUNK_SIZE:
                            cb(self.CHUNK_SIZE / size)
        if cb is not None:
            cb(False)
        return fd.getvalue()

    async def get_file(self, path):
        return File(path, pathlib.Path(path).stat().st_mtime, self)

    async def get_time(self, path):
        return (await self.get_file(path)).time

    async def _writefile(self, origin, target, mtime, cb):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        async with self.open_sem:
            async with async_open(target, 'wb') as dst:
                ith = 0
                while ith * self.CHUNK_SIZE < len(origin):
                    await dst.write(origin[ith * self.CHUNK_SIZE: (ith + 1) * self.CHUNK_SIZE])
                    ith += 1
                    if cb is not None and len(origin) > self.CHUNK_SIZE:
                        cb(self.CHUNK_SIZE / len(origin))
            if cb is not None:
                cb(True)
            os.utime(target, (mtime.timestamp(), mtime.timestamp()))

    async def _deletefile(self, target):
        try:
            os.remove(target)
        except FileNotFoundError:
            pass

    async def _renamefile(self, old_path, new_path):
        try:
            os.replace(old_path, new_path)
        except FileNotFoundError:
            pass

    def _wd(path, self, q):
        from iris.watchdog_service import run_wd
        run_wd(path, queue=q, log=True, pattern=self.pattern,
               ignore_pattern=self.ignore_pattern)
        while True:
            path, isdir, change, mtime = q.get().split('%')
            log.debug(f'Local WD event: {path} {isdir} {change} {mtime}')
            if change != 'D':
                mtime = None
            self.tasks.put(File(os.path.relpath(path), mtime, self, change))  # TODO: This works but is not abs, why?

    def start_watchdog(self):
        assert self.tasks is None, 'Already initialized the watchdog'
        self.tasks = Queue(maxsize=-1)

        self.wd = Thread(target=LocalPath._wd,
                         args=(os.path.abspath(self.path), self,
                               Queue(maxsize=-1)))
        self.wd.daemon = True
        self.wd.start()
