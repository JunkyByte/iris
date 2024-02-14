import argparse
import time
import sys
import yaml
import os
import signal
import logging
from dataclasses import dataclass, fields, MISSING, asdict
from typing import Optional
from functools import partial
from rich.console import Console, Group
from rich.live import Live
from rich.progress import Progress
from .host import RemotePath, LocalPath, run
logging.basicConfig()

parser = argparse.ArgumentParser(description='iris is a command line tool to sync folders between local and remote')


@dataclass
class IrisConfig:
    origin: str
    origin_path: str
    dest: str
    dest_path: str
    mirror: bool = True
    pattern: str = '*'
    ignore_pattern: str = '//'
    origin_jump: Optional[str] = None
    dest_jump: Optional[str] = None
    origin_key: Optional[str] = '~/.ssh/id_rsa'
    dest_key: Optional[str] = '~/.ssh/id_rsa'
    
    def sided_configs(self, origin=True):
        pat = 'origin' if origin else 'dest'
        npat = 'origin' if not origin else 'dest'
        config = {k: v for k, v in asdict(self).items() if npat not in k}
        config['path'] = config[pat + '_path']
        config.pop(pat + '_path')
        config['key'] = config[pat + '_key']
        config.pop(pat + '_key')
        config['host'] = config.pop(pat)
        config['jump_host'] = config.pop(pat + '_jump')
        return config

    @staticmethod
    def static_dict():
        return {k.name: k.default if k.default is not MISSING else '' for k in fields(IrisConfig)}


class PrettyConsole(Console):
    def __init__(self):
        super().__init__()
        self.counter = 0
        self.progress = Progress(console=self)

    def callback_write(self, from_host, path, to_host, rev=False):
        return partial(self.log_write, from_host=from_host, path=path, to_host=to_host, rev=rev)

    def callback_progress(self, name):
        task_id = self.progress.add_task(f'[bold blue]Reading: {name}', total=1, visible=False)
        return partial(self._callback_progress, id=task_id, name=name)

    def _callback_progress(self, adv, id, name):
        if adv is True:  # Use this to trigger completion
            self.progress.remove_task(id)
            return
        if adv is False:
            self.progress.reset(id, description=f'[bold blue]Writing: {name}', visible=False)
            return
        self.progress._tasks[id].visible = True
        self.progress.update(id, advance=adv)

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
        console.print(f'[bold red] The configuration file [bold green]{args.config}[/bold green] already exists, exiting.')
        sys.exit(0)

    with open(args.config, 'w') as f:
        yaml.dump(IrisConfig.static_dict(), f, sort_keys=False)
    console.print(f'[bold green]The configuration file {args.config} has been created')
    sys.exit(0)


def main():
    # Setup rich
    console = PrettyConsole()
    status = console.status('[bold blue] Iris launching')
    progress_group = Group(
        console.progress,
        status,
    )

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
            console.print(f'[green]{string}[/green] [red] - Config file not found[/red]')
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

    log.debug(f'DRY RUN: {args.dry}')

    with open(args.config, 'r') as f:
        config_yaml = yaml.load(f, Loader=yaml.FullLoader)
        config = IrisConfig(**config_yaml)

    from_class = LocalPath if config.origin == 'local' else RemotePath
    to_class = LocalPath if config.dest == 'local' else RemotePath

    from_path = from_class(**config.sided_configs(origin=True), dry=args.dry)
    to_path = to_class(**config.sided_configs(origin=False), dry=args.dry)

    # Create signal after creating from_path and to_path for cleanup
    signal.signal(signal.SIGINT, cleanup)

    status.update('[bold blue] Testing connection to paths')
    with Live(progress_group, console=console):
        # Test connection to Paths is working.
        if not from_path.check_connection():
            console.print(f'[red]Connection to '
                          f'[green]{from_path.host}:{from_path.path}[/green] '
                          f'failed[/red] path may not exist')
            sys.exit()
        console.print(f'Connection to [green]{from_path.host}:{from_path.path}[/green] established')
        if not to_path.check_connection():
            console.print(f'[red]Connection to '
                          f'[green]{to_path.host}:{to_path.path}[/green] '
                          f'failed[/red] path may not exist')
            sys.exit()
        console.print(f'Connection to [green]{to_path.host}:{to_path.path}[/green] established')

        # Get all files from both sources
        status.update(status='[bold green]Getting all files from both paths')
        from_files = from_path.all_files()
        console.print(f'[green]{len(from_files)}[/green] Files received from [green]{from_path.host}')

        if config.mirror:
            to_files = to_path.all_files()
            console.print(f'[green]{len(to_files)}[/green] Files received from [green]{to_path.host}')

        # For each file do a merge on both sides.
        status.update(status=f'[bold blue] Merging files from '
                      f'{from_path.host}:{from_path.path} -> '
                      f'{to_path.host}:{to_path.path}')

        t0 = time.time()

        # Process tasks
        tasks = [from_path.write(f, to_path,
                                 console.callback_write(from_path.host,
                                                        f.short_path,
                                                        to_path.host),
                                 console.callback_progress(f.short_path))
                 for f in from_files]
        run(tasks)

        if config.mirror:
            status.update(status=f'[bold blue] Merging files from '
                          f'{to_path.host}:{to_path.path} -> '
                          f'{from_path.host}:{from_path.path}')

            tasks = [to_path.write(f, from_path,
                                   console.callback_write(from_path.host,
                                                          f.short_path,
                                                          to_path.host, True),
                                   console.callback_progress(f.short_path))
                     for f in to_files]
            run(tasks)

        console.print(f'[bold blue]Initial sync completed in {(time.time() - t0):.2f} seconds')

        status.update('[bold blue] Launching watchdog programs')
        from_path.start_watchdog()

        if config.mirror:
            to_path.start_watchdog()

        status.update(status='[bold blue]Listening for changes on local and remote path')

        req = []
        while True:  # Process requests for watchdogs
            from_req = from_path.next_task()
            to_req = to_path.next_task()

            if from_req:
                for r in from_req:
                    req.append(from_path.write(r, to_path,
                                               console.callback_write(from_path.host,
                                                                      r.short_path,
                                                                      to_path.host),
                                               console.callback_progress(r.short_path)))
            if to_req:
                for r in to_req:
                    req.append(to_path.write(r, from_path,
                                             console.callback_write(from_path.host,
                                                                    r.short_path,
                                                                    to_path.host,
                                                                    True),
                                             console.callback_progress(r.short_path)))

            if req:
                run(req)
                req = []

            time.sleep(1e-2)


if __name__ == '__main__':
    main()
