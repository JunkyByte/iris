# Iris

The idea is to build a simple tool to sync folders / files between local and ssh.
The idea is to use just python and some libraries:
- Watchdog for intercepting system events (file changes)
- Asyncssh for remote communication
- Rich for beautiful visualization
- PyYAML to create configurations

I would like to have a one or two way file sync based on 'newest' changes.
To run on a remote host this means we need to intercept remote system events, we can do this
using watchdog + remote python process spawned from local.
To have a 2 way communication we need to do both checks using the local script (+ remote watchdog), this may create a bit of complexity.
This should support file format exclusion or inclusion / recursive folders / symbolic links (?) / maybe regex but I know nothing about them.
yaml files should be cool to store setting, config files could be created to specify host fast aliases, default configurations or whatever.

----

(THIS SEEMS TO BE TRUE ONLY ON MACOS)

Sync logic:
- R: Remote
- L: Local

We have 3 types of intercepted events:
- C: Created
- M: Modified
- D: Deleted

### What is called and when?
note that these are in order, the delete is called only after the other operations ends.

On file creation:
- C on the full file path
- M on the directory containing the file

On dir creation:
- C on the full dir path
- M on the directory containing the dir

(So creation is pretty coherent)

On file modification:
- D on the file
- C on the file
- M on the dir

On file deletion:
- D on the file
- M on the dir

----
