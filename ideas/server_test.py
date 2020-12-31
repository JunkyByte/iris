import asyncio, asyncssh, sys

async def run_commands(conn):
    """Run a series of commands on the client which connected to us"""

    commands = ('ls', 'sleep 30 && date', 'sleep 5 && cat /proc/cpuinfo')

    async with conn:
        tasks = [conn.run(cmd) for cmd in commands]

        for task in asyncio.as_completed(tasks):
            result = await task
            print('Command:', result.command)
            print('Return code:', result.returncode)
            print('Stdout:')
            print(result.stdout, end='')
            print('Stderr:')
            print(result.stderr, end='')
            print(75*'-')

async def start_reverse_server():
    """Accept inbound connections and then become an SSH client on them"""

    await asyncssh.listen_reverse(host='localhost', port=8022, client_keys=None, 
                                  known_hosts=None,
                                  acceptor=run_commands)

loop = asyncio.get_event_loop()

try:
    loop.run_until_complete(start_reverse_server())
except (OSError, asyncssh.Error) as exc:
    sys.exit('Error starting server: ' + str(exc))

loop.run_forever()
