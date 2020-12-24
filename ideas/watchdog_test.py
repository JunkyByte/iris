import time
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


patterns = "*"
ignore_patterns = ""
ignore_directories = False
case_sensitive = True
my_event_handler = PatternMatchingEventHandler(patterns, ignore_patterns,
                    ignore_directories, case_sensitive)


def on_created(event):
    print("%s has been created" % event.src_path)


def on_deleted(event):
    print("Delete %s!" % event.src_path)


def on_modified(event):
    print("%s has been modified" % event.src_path)


my_event_handler.on_created = on_created
my_event_handler.on_deleted = on_deleted
my_event_handler.on_modified = on_modified

path = "./test"
go_recursively = True
my_observer = Observer()
my_observer.schedule(my_event_handler, path, recursive=go_recursively)
my_observer.start()
try:
    while True:
        time.sleep(5)
except Exception:
    my_observer.stop()

my_observer.join()
