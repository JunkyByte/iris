import sys
import pathlib
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


class WatchdogManager:
    def __init__(self, path, queue_out=None):
        self.queue_out = queue_out
        self.stdout = True if queue_out is None else False

        patterns = "*"
        ignore_patterns = ""
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
        msg = path + ' ' + str(isdir) + ' ' + change + ' ' + str(pathlib.Path(path).stat().st_mtime)
        if self.stdout:
            print(msg)
            sys.stdout.flush()
        else:
            self.queue_out.put(msg)

    def on_created(self, event):
        self.log_change(event.src_path, event.is_directory, 'C')

    def on_deleted(self, event):
        self.log_change(event.src_path, event.is_directory, 'D')

    def on_modified(self, event):
        self.log_change(event.src_path, event.is_directory, 'M')

    def wait(self):
        self.observer.join()


def run_wd(path, block=False, queue=None):
    wd = WatchdogManager(path, queue)
    if block:
        wd.wait()
    return wd


if __name__ == '__main__':
    line = None
    while line is None:
        for line in sys.stdin:
            if line is not None:
                break
    wd = run_wd('/home/adryw/test_wow/', block=True)
