# Iris

The idea is to build a simple tool to sync folders / files between local and ssh.
This has been a pain on osx (using rsync + watch).
The idea is to use just python and libraries:
- Watchdog for intercepting system events (like file changes)
- Fabric for remote communication
- Rich for beautiful visualization
- PyYAML to create configurations
- Subprocess to run remote rsync UP: See below
+ rsync UP: This may not be needed

I would like to have a one or two way file sync based on 'newest' changes.
To run on a remote host this means we need to intercept remote system events, we can do this
using watchdog + remote python process spawned from local.
The remote process will automatically die if not accessed for a while.
To have a 2 way communication we need to do both checks using the local script (+ remote watchdog), this may create a bit of complexity.
This should support file format exclusion or inclusion / recursive folders / symbolic links (?) / maybe regex but I know nothing about them.
yaml files should be cool to store setting, config files could be created to specify host fast aliases, default configurations or whatever.

Rsync will be used to sync the actual files. People said that you can just run 2 with different from to to be able to have a double direction newest sync, that may be cool.

UP: Rsync may not be needed as fabric allows get / put.

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
- M on the `ds_store` if present (should be ignored)

On program run we need to sync the two folders.
If target folder does not exist we can create the whole thing.
If both folders exist we need to sync the content:
- For each file in local: create on remote if newer
- For each file in remote: create on local if newer
Given the sync logic we just need to call it on all these files.
How to iterate on files in remote? `find PATH` seems to work.
Use it with remote running and then iterate locally on those files and get them if needed.

Mac:
`find . -type f -print0 | xargs -0 stat -f "%m %N"`

Linux:
`find . -type f -printf "%T@ %p\n"` Note that this one gives fractional value as well


# The transfer is pretty slow :(
