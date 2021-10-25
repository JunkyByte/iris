import argparse
import time
import sys
import yaml
import os
import signal
import logging
from functools import partial
from rich.console import Console
from src.host import RemotePath, LocalPath, run
logging.basicConfig()

parser = argparse.ArgumentParser(description='iris is a command line tool to sync folders between local and remote')
KEYS = ['from', 'to', 'mirror', 'from_path', 'to_path', 'pattern', 'ignore_pattern', 'from_jump', 'to_jump']
DEFAULTS = {'mirror': True, 'pattern': '*', 'ignore_pattern': '//', 'from_jump': None, 'to_jump': None}


class PrettyConsole(Console):
    def __init__(self):
        super().__init__()
        self.counter = 0

    def callback_write(self, from_host, path, to_host, rev=False):
        return partial(self.log_write, from_host=from_host, path=path, to_host=to_host, rev=rev)

    def log_write(self, merged, from_host, path, to_host, change, rev):
        # Choose change symbol
        if merged:
            if change == 'M':
                change = '--->'
            elif change == 'D':
                change = '-D->'
            else:
                change = '--->'
        else:
            change = '|'

        # Change direction if reversed
        change = change.replace('>', '<')[::-1] if rev else change

        msg = '[green]%s:%s[/green] [bold blue]%5s [red]%s'
        if rev:
            msg = '[green]%s[/green] [bold blue]%5s [red]%s:%s'

        subs = (from_host, change, to_host, path) if rev else (from_host, path, change, to_host)
        self.print(f'[white]{self.counter} [/white]' + msg % subs)
        self.counter += 1


def init_config():
    # Setup rich
    console = PrettyConsole()
    parser.add_argument('--config', type=str, help='yaml config file path', default='iris_conf.yaml')
    args = parser.parse_args()

    if os.path.isfile(args.config):
        console.print('[bold red] The configuration file [bold green]%s[/bold green] already exists, exiting.' % args.config)
        sys.exit(0)

    config = {k: '' for k in KEYS}
    config = {**config, **DEFAULTS}
    with open(args.config, 'w') as f:
        yaml.dump(config, f)
    console.print('[bold green]The configuration file %s has been created' % args.config)
    sys.exit(0)


def main():
    # Setup rich
    console = PrettyConsole()
    log = logging.getLogger('iris')
    log.setLevel(logging.INFO)

    # Setup signal cleanup
    def cleanup(sig, frame):
        console.print('[bold red]Cleaning up and exiting')
        from_path.cleanup()
        to_path.cleanup()
        sys.exit(0)

    def file_path(string):
        if os.path.isfile(string):
            return string
        else:
            console.print('[green]%s[/green] [red] - Config file not found[/red]' % string)
            sys.exit()

    parser.add_argument('--config', type=file_path, help='yaml config file path')
    parser.add_argument('--debug', action='store_true', help='Debug infos')
    parser.add_argument('--dry', action='store_true', help='Fake run with no file writing')

    # Arg parsing and setup
    args = parser.parse_args()
    if args.config is None:
        console.print('[red]Error on parameter validation[/red]')
        console.print('Run as `python iris.py --config yaml_file`')
        sys.exit()

    if args.debug:
        log.setLevel(logging.DEBUG)

    log.debug('DRY RUN: %s' % args.dry)

    config = None
    if os.path.isfile(args.config):
        with open(args.config, 'r') as f:
            config = yaml.load(f, Loader=yaml.FullLoader)

    if all([k in config.keys() or k in DEFAULTS.keys() for k in KEYS]):
        config = {**DEFAULTS, **config}
    else:
        console.print('[red]Parameters missing on yaml config file')
        missing = [k for k in KEYS if k not in config.keys() and k not in DEFAULTS.keys()]
        console.print('Missing parameters: \n[green]%s' % '\n'.join(missing))

    mirror = config['mirror']
    from_local = config['from'] == 'local'
    to_local = config['to'] == 'local'
    from_path = config['from_path']
    to_path = config['to_path']
    pat = config['pattern']
    npat = config['ignore_pattern']
    mirror = config['mirror']
    from_jump = config['from_jump']
    to_jump = config['to_jump']

    from_host = 'local' if from_local else config['from']
    to_host = 'local' if to_local else config['to']

    # Create Path connections
    if from_local:
        from_path = LocalPath(from_path, args.dry, pat, npat)
    else:
        from_path = RemotePath(from_path, from_host, args.dry, pat, npat, jump_host=from_jump)

    if to_local:
        to_path = LocalPath(to_path, args.dry, pat, npat)
    else:
        to_path = RemotePath(to_path, to_host, args.dry, pat, npat, jump_host=to_jump)

    # Create signal after creating from_path and to_path for cleanup
    signal.signal(signal.SIGINT, cleanup)

    with console.status('[bold blue] Testing connection to paths') as status:
        # Test connection to Paths is working.
        if not from_path.check_connection():
            console.print('[red]Connection to [green]%s:%s[/green] failed[/red] path may not exist' % (from_host, from_path.path))
            sys.exit()
        console.print('Connection to [green]%s:%s[/green] established' % (from_host, from_path.path))
        if not to_path.check_connection():
            console.print('[red]Connection to [green]%s:%s[/green] failed[/red] path may not exist' % (to_host, to_path.path))
            sys.exit()
        console.print('Connection to [green]%s:%s[/green] established' % (to_host, to_path.path))

        # Get all files from both sources
        status.update(status='[bold green]Getting all files from both paths')
        from_files = from_path.all_files()
        console.print('[green]%s[/green] Files received from [green]%s' % (len(from_files), from_host))

        if mirror:
            to_files = to_path.all_files()
            console.print('[green]%s[/green] Files received from [green]%s' % (len(to_files), to_host))

            # For each file do a merge on both sides.
            status.update(status='[bold blue] Merging files from %s:%s -> %s:%s' % (from_host, from_path.path, to_host, to_path.path))

        t0 = time.time()

        # Process tasks
        tasks = [from_path.write(f, to_path, console.callback_write(from_host, f.short_path, to_host)) for f in from_files]

        if tasks:
            run(tasks)

        status.update(status='[bold blue] Merging files from %s:%s -> %s:%s' % (to_host, to_path.path, from_host, from_path.path))

        if mirror:
            tasks = [to_path.write(f, from_path, console.callback_write(from_host, f.short_path, to_host, True)) for f in to_files]

            if tasks:
                run(tasks)

        console.print('[bold blue]Initial sync completed in %.2f seconds' % (time.time() - t0))

    with console.status('[bold blue] Launching watchdog programs') as status:
        from_path.start_watchdog()

        if mirror:
            to_path.start_watchdog()

        status.update(status='[bold blue]Listening for changes on local and remote path')

        req = []
        while True:  # Process requests for watchdogs
            from_req = from_path.next_task()
            to_req = to_path.next_task()

            if from_req:
                for r in from_req:
                    req.append(from_path.write(r, to_path, console.callback_write(from_host, r.short_path, to_host)))
            if to_req:
                for r in to_req:
                    req.append(to_path.write(r, from_path, console.callback_write(from_host, r.short_path, to_host, True)))

            if req:
                run(req)
                req = []

            time.sleep(1e-2)


# TODO: Inspect remove multifile missing some? rm dir example
if __name__ == '__main__':
    main()
