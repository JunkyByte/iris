import os
import asyncio, asyncssh, sys
import time
from asyncio.subprocess import PIPE


async def handle_request(process):
    """Run a command on the client, piping I/O over an SSH session"""

    local_proc = await asyncio.create_subprocess_shell(
        process.command, stdin=PIPE, stdout=PIPE, stderr=PIPE)

    await process.redirect(stdin=local_proc.stdin, stdout=local_proc.stdout,
                           stderr=local_proc.stderr)

    process.exit(await local_proc.wait())
    await process.wait_closed()


import getpass
async def run_reverse_client():
    """Make an outbound connection and then become an SSH server on it"""

    key = await load_agent_keys()
    key2 = import_private_key('/Users/adryw/.ssh/id_rsa')
    conn = await asyncssh.connect('104.196.18.97', client_keys=key2)
    conn = await asyncssh.connect_reverse(
        'localhost', port=8022, tunnel=conn, server_host_keys=key2,
        process_factory=handle_request, encoding=None)
    await conn.wait_closed()

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

async def load_agent_keys(agent_path=None):
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
    return await co_load_agent_keys(agent_path)


try:
    asyncio.get_event_loop().run_until_complete(run_reverse_client())
except (OSError, asyncssh.Error) as exc:
    sys.exit('Reverse SSH connection failed: ' + str(exc))
