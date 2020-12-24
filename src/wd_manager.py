import time
from fabric import Connection


class WatchdogManager:
    def __init__(self):
        pass

    def on_created(self, event):
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

    def on_deleted(self, event):
        print('Called DELETED on %s is dir? %s' % (event.src_path, event.is_directory))
        if event.is_directory:
            return
        print(f"Delete {event.src_path}!")

    def on_modified(self, event):
        print('Called MODIFIED on %s is dir? %s' % (event.src_path, event.is_directory))
        if event.is_directory:
            return
        print(f"{event.src_path} has been modified")
