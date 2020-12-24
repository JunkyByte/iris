import time
import os
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


patterns = "*"
ignore_patterns = ""
ignore_directories = False
case_sensitive = True
my_event_handler = PatternMatchingEventHandler(patterns, ignore_patterns,
                    ignore_directories, case_sensitive)


def on_created(event):
    print('Called CREATED on %s is dir? %s' % (event.src_path, event.is_directory))
    path = event.src_path
    if event.is_directory:
        print('Skipped dir')
        return

    print(f"{event.src_path} has been created")
    print('Creation time: %s' % time.ctime())

    #c.run('mkdir -p %s' % os.path.dirname(
    with Connection('104.196.18.97') as c:  # This is important otherwise it may hang
        c.put(path, remote='/home/adryw/test_wow/')


def on_deleted(event):
    print('Called DELETED on %s is dir? %s' % (event.src_path, event.is_directory))
    if event.is_directory:
        return
    print(f"Delete {event.src_path}!")


def on_modified(event):
    print('Called MODIFIED on %s is dir? %s' % (event.src_path, event.is_directory))
    if event.is_directory:
        return
    print(f"{event.src_path} has been modified")


from fabric import Connection
c = Connection('104.196.18.97')

PATH = '/home/adryw/test_wow/'

from io import BytesIO
from invoke import UnexpectedExit
from rich.console import Console
console = Console()
def watchdog_remote(path):
    # Copy remote watch dog function
    c.put('./watchdog_remote.py', remote='/tmp/watchdog_tmp.py')
    print('Copied file')

    try:
        c.run('rm /tmp/out_watchdog.out')
    except UnexpectedExit:
        pass

    # TODO Fix conda default python (FIXED WITH NON INTERACTIVE FROM BASHRC ALLOW TO SPECIFY THIS)
    #c.run('screen -dmS daemon_watchdog /home/adryw/miniconda3/bin/python /tmp/watchdog_tmp.py')
    c.run('screen -dmS daemon_watchdog python3 /tmp/watchdog_tmp.py')
    pid = c.run('screen -ls | grep -oE "[0-9]+\.daemon_watchdog" | sed -e "s/\..*$//g"').stdout.split()  # TODO
    last_idx = 0
    while True:
        fd = BytesIO()

        try:
            c.get('/tmp/out_watchdog.out', fd)  # TODO Here better a get or a cat of file from remote?
        except FileNotFoundError:
            time.sleep(3)
            continue

        content = fd.getvalue().decode('utf-8').split('\n')[:-1]
        size = len(content)
        content = content[last_idx:]
        last_idx = size

        if content:
            console.log('[red]' + ' \n'.join(content) + '[/red]')

        time.sleep(1)



import threading
x = threading.Thread(target=watchdog_remote, args=(PATH,), daemon=True)
x.start()


my_event_handler.on_created = on_created
my_event_handler.on_deleted = on_deleted
my_event_handler.on_modified = on_modified

path = "./test/"
go_recursively = False
my_observer = Observer()
my_observer.schedule(my_event_handler, path, recursive=go_recursively)
my_observer.start()
try:
    while True:
        time.sleep(5)
except Exception as e:
    print(e)
    my_observer.stop()

my_observer.join()
