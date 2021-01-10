# iris

Iris is a simple utility written completely in python which allows to sync folders between local and remote ssh (sftp) server.
Iris runs locally but requires a working python installation on each machine where you want files to be watched.

Iris features are:
- Local and Remote ssh (sftp) directories support
- Changes are sync in realtime using python watchdogs both locally and remotely
- Modification time is preserved during copy, merge by newer strategy is used
- Pattern / Pattern ignore settings

Linux / Mac / Windows support (UNTESTED Windows)

## Installation
```
git clone https://github.com/JunkyByte/iris.git
cd iris/
pip install .
```

### Remote installation
On remote host you do not need all dependencies, if you have a working python3 install the watchdog package and you should be set
```
pip install watchdog
```


## Examples
Inside your terminal you can start iris by typing
```
iris --config config_file.yaml
```

### Config files
Config files are in `yaml` format, the following parameters can be specified, the default value of optional is specified below.
```yaml
from:  # local or the host for sftp (e.g. 104.30.12.61)
to:  # local or the host for sftp
mirror:  # Whether to mirror sync (from <- to) (optional, default: True)

# optional, default: '*', e.g. '*.yaml *.txt'
pattern:  # Patterns for file name matching separated by a space

# optional, default: '//', e.g. '*.md5'
ignore_pattern:  # Patterns for ignore by file name separated by a space

from_path:  # The `from` absolute path
to_path:  # The `to` absolute path

# optional, default: False
dry: False # Iris won't do any file writing but only log them
# ^^^ Please, use this to check your configs are working correctly without consequences on your files.
```

Right now iris requires a config file to be passed.
For remote connections iris will try to load from your `ssh-agent` first, if it fails right now it uses `~/.ssh/id_rsa` as a key.
(This will be a config option at some point)

## Contribute / Issues
Please create an issue if you have any request / problem or want to contribute.

Hope you find iris useful.

## Warning:
During a bidirectional sync if you delete a file from the `to_path` it will be deleted on your `local_path` and vice versa.
We do not take any responsability for files lost. Iris is a work in progress, be sure to backup your computer before using it,
do not run iris as sudo.

Also syslinks have not been tested.
