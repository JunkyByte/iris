"""Client to handle connections and actions executed against a remote host."""
from os import system
from paramiko import SSHClient, AutoAddPolicy, RSAKey
from paramiko.auth_handler import AuthenticationException, SSHException
from scp import SCPClient, SCPException


class RemoteClient:
    """Client to interact with a remote host via SSH & SCP."""

    def __init__(self, host, user, ssh_key_filepath, remote_path):
        self.host = host
        self.user = user
        self.ssh_key_filepath = ssh_key_filepath
        self.remote_path = remote_path
        self.client = None
        self.scp = None
        self.conn = None
        #self.__upload_ssh_key()

    def __get_ssh_key(self):
        """ Fetch locally stored SSH key."""
        try:
            self.ssh_key = RSAKey.from_private_key_file(self.ssh_key_filepath)
            print(f'Found SSH key at self {self.ssh_key_filepath}')
        except SSHException as error:
            print(error)
        return self.ssh_key

    #def __upload_ssh_key(self):
    #    try:
    #        system(f'ssh-copy-id -i {self.ssh_key_filepath}.pub {self.user}@{self.host}>/dev/null 2>&1')
    #        print(f'{self.ssh_key_filepath} uploaded to {self.host}')
    #    except FileNotFoundError as error:
    #        print(error)

    def __connect(self):
        """Open connection to remote host. """
        if self.conn is None:
            try:
                self.client = SSHClient()
                self.client.load_system_host_keys()
                self.client.set_missing_host_key_policy(AutoAddPolicy())
                self.client.connect(
                    self.host,
                    username=self.user,
                    key_filename=self.ssh_key_filepath,
                    look_for_keys=True,
                    timeout=5000
                )
                self.scp = SCPClient(self.client.get_transport())
            except AuthenticationException as error:
                print(f'Authentication failed: did you remember to create an SSH key? {error}')
                raise error
        return self.client

    def disconnect(self):
        """Close SSH & SCP connection."""
        if self.client:
            self.client.close()
        if self.scp:
            self.scp.close()

    def put(self, files):
        """
        Upload multiple files to a remote directory.

        :param files: List of local files to be uploaded.
        :type files: List[str]
        """
        if isinstance(files, str):
            files = [files]

        self.conn = self.__connect()
        uploads = [self.__upload_single_file(file) for file in files]
        print(f'Finished uploading {len(uploads)} files to {self.remote_path} on {self.host}')

    def __upload_single_file(self, file):
        """Upload a single file to a remote directory."""
        upload = None
        try:
            self.scp.put(
                file,
                recursive=True,
                remote_path=self.remote_path
            )
            upload = file
        except SCPException as error:
            print(error)
            raise error
        finally:
            print(f'Uploaded {file} to {self.remote_path}')
            return upload

    def download_file(self, file):
        """Download file from remote host."""
        self.conn = self.__connect()
        self.scp.get(file)

    def command(self, command, hide=False):
        """
        Execute a command.

        :param commands: Command
        :type commands: str
        """
        self.conn = self.__connect()
        stdin, stdout, stderr = self.client.exec_command(command)
        stdout.channel.recv_exit_status()
        response = stdout.readlines()
        if not hide:
            print('stdin: %s' % stdin)
            print('stdout: %s' % stdout)
        return response

    def execute_commands(self, commands):
        """
        Execute multiple commands in succession.

        :param commands: List of unix commands as strings.
        :type commands: List[str]
        """
        self.conn = self.__connect()
        for cmd in commands:
            stdin, stdout, stderr = self.client.exec_command(cmd)
            stdout.channel.recv_exit_status()
            response = stdout.readlines()
            for line in response:
                print(f'INPUT: {cmd} | OUTPUT: {line}')


if __name__ == '__main__':
    remote = RemoteClient('104.196.18.97', 'adryw', '/Users/adryw/.ssh/id_rsa', '/home/adryw/testparam/')
    import time
    t = time.time()
    remote.put(['/Users/adryw/Documents/iris/ideas/test/file0.txt'])
    print(time.time() - t)
    remote.execute_commands(['ls'])

    scpcl = remote.scp
    import time
    t = time.time()
    scpcl.put(['/Users/adryw/Documents/iris/ideas/test/file0' for i in range(10)])
    print('Mean on 10: ', (time.time() - t) / 10)

    import io

    fl = io.BytesIO()
    fl.write(b'test')
    fl.seek(0)
    # upload it directly from memory
    t = time.time()
    scpcl.putfo(fl, '/home/adryw/testparam/file0.txt')
    print(time.time() - t)

    # close connection
    scpcl.close()
    # close file handler
    fl.close()
    
    import os, asyncssh
    def import_private_key(filename):
        """
        Attempts to import a private key from file
        Prompts for a password if needed
        """
        sshkey = None
        basename = os.path.basename(filename)
        if not os.path.exists(filename):
            print("No such key file {}".format(filename))
            return
        with open(filename) as file:
            data = file.read()
            try:
                sshkey = asyncssh.import_private_key(data)
            except asyncssh.KeyImportError:
                while True:
                    passphrase = input("Enter passphrase for key {} : ".format(basename))
                    if not passphrase:
                        print("Ignoring key {}".format(filename))
                        break
                    try:
                        sshkey = asyncssh.import_private_key(data, passphrase)
                        break
                    except asyncssh.KeyImportError:
                        print("Wrong passphrase")
            except Exception as e:
                import traceback
                traceback.print_exc()
            return sshkey

    key = import_private_key('/Users/adryw/.ssh/id_rsa')
    import time
    import asyncio, asyncssh  # pip install asyncssh
    t = time.time()
    async def main():
        async with asyncssh.connect('104.196.18.97', username='adryw', client_keys=key) as conn:
            async with conn.start_sftp_client() as sftp:
                print('connected')
                await asyncio.wait([sftp.put('/Users/adryw/Documents/iris/ideas/test/file1') for i in range(100)])

    asyncio.run(main())
    print((time.time() - t) / 100)

    import time
    import asyncio, asyncssh  # pip install asyncssh
    t = time.time()

    async def f(conn, sftp, sem, f):
        async with sem:
            print('connected')
            result = await conn.run('echo Hello!', check=True)  # run command before running sftp
            print(result)
            #await sftp.put(f, remotepath='/home/adryw/testparam/')
            await sftp.put(f, remotepath='/home/adryw/testparam/file0')
    
    async def main():
        conn = await asyncssh.connect('104.196.18.97', username='adryw', client_keys=key)
        sftp = await conn.start_sftp_client()
        tasks = []
        # Here we work on dir and get all promises
        #for j in range(20):
        #    for i in range(5):
        #        tasks.append(f(conn, sftp, '/Users/adryw/Documents/iris/ideas/test/file%s' % str(10 * i + j)))  # Non blocking obviously

        #    res = await asyncio.gather(*tasks)
        #    tasks = []

        sem = asyncio.Semaphore(20)
        for i in range(100):
            tasks.append(f(conn, sftp, sem, '/Users/adryw/Documents/iris/ideas/test/file0'))  # Non blocking obviously
        res = await asyncio.gather(*tasks)
        tasks = []

        # Once satisfied wait for all of them to complete
        return res

    res = asyncio.run(main())
    print((time.time() - t) / 100)

    # Request them all in same .put / .get request using custom promise made of just references to write / get procedures
