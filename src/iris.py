import time
import os
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from fabric import Connection
from rich.console import Console
import argparse
import sys
import yaml
import rich
from host import RemotePath, LocalPath

# Setup rich
console = Console()


def file_path(string):
    if os.path.isfile(string):
        return string
    else:
        console.log('[green]%s[/green] [red] - Config file not found[/red]' % string)
        sys.exit()


parser = argparse.ArgumentParser(description='TODO: Description')
parser.add_argument('--config', type=file_path, help='TODO: yaml config file')

# Arg parsing and setup
args = parser.parse_args()
if args.config is None:
    console.log('[red]Error on parameter validation[/red]')
    console.log('Run as `python iris.py --config yaml_file`')
    sys.exit()

config = None
if os.path.isfile(args.config):
    with open(args.config, 'r') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

KEYS = ['from', 'to', 'mirror', 'from_path', 'to_path']
DEFAULTS = {'mirror': False}

if all([k in config.keys() or k in DEFAULTS.keys() for k in KEYS]):
    config = {**DEFAULTS, **config}
else:
    console.log('[red]Parameters missing on yaml config file')
    missing = [k for k in KEYS if k not in config.keys() and k not in DEFAULTS.keys()]
    console.log('Missing parameters: \n[green]%s' % '\n'.join(missing))

mirror = config['mirror']
from_local = config['from'] == 'local'
to_local = config['to'] == 'local'
from_path = config['from_path']
to_path = config['to_path']

from_host = 'local' if from_local else config['from']
to_host = 'local' if to_local else config['to']

# Setup Watchdog rules
patterns = '*'
ignore_patterns = ''
ignore_directories = False
case_sensitive = True
my_event_handler = PatternMatchingEventHandler(patterns, ignore_patterns, ignore_directories, case_sensitive)

# Create Path connections
from_path = LocalPath(from_path) if from_local else RemotePath(from_path, from_host)
to_path = LocalPath(to_path) if to_local else RemotePath(to_path, to_host)

with console.status('[bold blue] Testing connection to paths') as status:
    # Test connection to Paths is working.
    if not from_path.check_connection():
        console.log('[red]Connection to [green]%s:%s[/green] failed[/red] path may not exist' % (from_host, from_path.path))
        sys.quit()
    console.log('Connection to [green]%s:%s[/green] established' % (from_host, from_path.path))
    if not to_path.check_connection():
        console.log('[red]Connection to [green]%s:%s[/green] failed[/red] path may not exist' % (to_host, to_path.path))
        sys.quit()
    console.log('Connection to [green]%s:%s[/green] established' % (to_host, to_path.path))

    # Get all files from both sources
    status.update(status='[bold green]Getting all files from both paths...')
    from_files = from_path.all_files()
    console.log('[green]%s[/green] Files received from [green]%s' % (len(from_files), from_host))
    to_files = to_path.all_files()
    console.log('[green]%s[/green] Files received from [green]%s' % (len(to_files), to_host))

    # For each file do a merge on both sides.
    status.update(status='[bold blue] Merging files from %s:%s -> %s:%s' % (from_host, from_path.path, to_host, to_path.path))
    for f in from_files:
        if f.path.endswith('.md5'):
            continue
        merged = from_path.write(f, to_path)
        if merged:
            msg = '[green]%s:%s [bold blue]----> [red]%s'  # TODO Make a function for this, is standard with diff arrows
        else:
            msg = '[red]%s:%s[/red] | [green]%s'
        console.log(msg % (from_host, f.path, to_host))

    status.update(status='[bold blue] Merging files from %s:%s -> %s:%s' % (to_host, to_path.path, from_host, from_path.path))
    for f in to_files:
        if f.path.endswith('.md5'):
            continue
        merged = to_path.write(f, from_path)
        if merged:
            msg = '[green]%s [bold blue]<---- [red]%s:%s'
        else:
            msg = '[green]%s[/green] | [red]%s:%s'
        console.log(msg % (from_host, to_host, f.path))
