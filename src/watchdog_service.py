import time
import sys
import platform
import os
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


class WatchdogManager:
    def __init__(self, path, queue_out=None, log=False, pattern='*', ignore_pattern='//'):
        self.queue_out = queue_out
        self.stdout = True if queue_out is None else False
        self.log = log
        self.prev_ev = {'path': None, 'time': None}

        patterns = list(pattern.split())
        for i, p in enumerate(patterns):  # Setup directories matching
            if p.endswith('/'):
                patterns[i] = '*' + p + '*'
        ignore_patterns = ['*.md5', '*.swp', '*.swx', '*.swpx'] + list(ignore_pattern.split())
        for i, p in enumerate(ignore_patterns):
            if p.endswith('/'):
                ignore_patterns[i] = '*' + p + '*'
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
        print(path)
        try:
            if change != 'D':
                t = os.stat(path).st_mtime

                # Skip if too close to last event already dispatched (on same file)
                if self.prev_ev['path'] == path and datetime.fromtimestamp(time.time()) - self.prev_ev['time'] < timedelta(seconds=0.5):
                    return
            else:
                t = time.time()  # On file deletion use current time as stamp

                if os.path.isfile(path):
                    return

            msg = path + '%' + str(isdir) + '%' + change + '%' + str(t)
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


def run_wd(path, block=False, queue=None, log=False, pattern='*', ignore_pattern='//'):
    wd = WatchdogManager(path, queue, log, pattern, ignore_pattern)
    if block:
        wd.wait()
    return wd


if __name__ == '__main__':
    inp = [l.replace('\n', '') for l in sys.stdin]
    wd = run_wd(inp[0].split('\n')[0], block=True, pattern=inp[1], ignore_pattern=inp[2])
