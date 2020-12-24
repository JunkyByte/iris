import time
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

import logging
import sys

root = logging.getLogger()
root.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
#formatter = logging.Formatter('* remote * %(asctime)s - %(name)s - %(levelname)s - %(message)s')
#handler.setFormatter(formatter)
root.addHandler(logging.FileHandler('/tmp/out_watchdog.out'))
root.addHandler(handler)  # TODO


patterns = "*"
ignore_patterns = ""
ignore_directories = False
case_sensitive = True
my_event_handler = PatternMatchingEventHandler(patterns, ignore_patterns,
                    ignore_directories, case_sensitive)


def on_created(event):
    logging.info("%s has been created" % event.src_path)


def on_deleted(event):
    logging.info("Delete %s!" % event.src_path)


def on_modified(event):
    logging.info("%s has been modified" % event.src_path)


my_event_handler.on_created = on_created
my_event_handler.on_deleted = on_deleted
my_event_handler.on_modified = on_modified

path = "/home/adryw/test_wow/"
go_recursively = False
my_observer = Observer()
my_observer.schedule(my_event_handler, path, recursive=go_recursively)
my_observer.start()
try:
    while True:
        time.sleep(5)
        logging.info('Remote is connected %s' % time.ctime())
except Exception:
    my_observer.stop()

my_observer.join()
