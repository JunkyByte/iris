import time
import sys
import platform
import pathlib
import os
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


class WatchdogManager:
    def __init__(self, path, queue_out=None, log=False):
        self.queue_out = queue_out
        self.stdout = True if queue_out is None else False
        self.log = log
        self.prev_ev = {'path': None, 'time': None}

        #if self.log:
        #    print('Starting watchdog on %s' % path)

        patterns = "*"
        ignore_patterns = ['*.md5', '*.swp', '*.swx', '*.swpx']
        ignore_directories = True
        case_sensitive = True
        handler = PatternMatchingEventHandler(patterns, ignore_patterns, ignore_directories, case_sensitive)

        handler.on_created = self.on_created
        handler.on_deleted = self.on_deleted
        handler.on_modified = self.on_modified

        go_recursively = True
        self.observer = Observer()
        self.observer.schedule(handler, path, recursive=go_recursively)
        self.observer.start()

    def log_change(self, path, isdir=False, change='M'):
        try:
            if change != 'D':
                t = pathlib.Path(path).stat().st_mtime

                # Skip if too close to last event already dispatched (on same file)
                #if self.prev_ev['path'] == path:
                    #if self.log:
                    #    print('TIME FROM LAST EV:', datetime.fromtimestamp(t) - self.prev_ev['time'])

                if self.prev_ev['path'] == path and datetime.fromtimestamp(time.time()) - self.prev_ev['time'] < timedelta(seconds=0.5):
                    #if self.log:
                    #    print("SKIPPED EVENT")
                    return
            else:
                t = time.time()  # On file deletion use current time as stamp

                if os.path.isfile(path):
                    #if self.log:
                    #    print('Skipping delete as file exists')
                    return

            msg = path + ' ' + str(isdir) + ' ' + change + ' ' + str(t)
            if self.stdout:
                print(msg)
            else:
                self.queue_out.put(msg)
        except FileNotFoundError:
            return

        self.prev_ev['path'] = path
        self.prev_ev['time'] = datetime.fromtimestamp(time.time())

    def on_created(self, event):
        #if self.log:
        #    print('Created a file')
        self.log_change(event.src_path, event.is_directory, 'C')

    def on_deleted(self, event):
        #if self.log:
        #    print('Deleted a file')
        self.log_change(event.src_path, event.is_directory, 'D')

    def on_modified(self, event):
        #if self.log:
        #    print('Modified a file')
        self.log_change(event.src_path, event.is_directory, 'M')

    def wait(self):
        self.observer.join()


def run_wd(path, block=False, queue=None, log=False):
    wd = WatchdogManager(path, queue, log)
    if block:
        wd.wait()
    return wd


if __name__ == '__main__':
    line = None
    while line is None:
        for line in sys.stdin:
            if line is not None:
                break
    wd = run_wd(line.split('\n')[0], block=True)
