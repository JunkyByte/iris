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
    path = event.src_path
    if event.is_directory:
        print('Skipped dir')
        return
    print(f"{event.src_path} has been created")
    c.put(path, remote='/home/adryw/test_wow/')


def on_deleted(event):
    print(f"Delete {event.src_path}!")


def on_modified(event):
    print(f"{event.src_path} has been modified")


from fabric import Connection
c = Connection('35.227.158.60')


my_event_handler.on_created = on_created
my_event_handler.on_deleted = on_deleted
my_event_handler.on_modified = on_modified

path = "./"
go_recursively = False
my_observer = Observer()
my_observer.schedule(my_event_handler, path, recursive=go_recursively)
my_observer.start()
try:
    while True:
        time.sleep(5)
except Exception:
    my_observer.stop()

my_observer.join()
