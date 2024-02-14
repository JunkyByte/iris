# iris
![](https://user-images.githubusercontent.com/24314647/235253687-8195f920-7fd3-477b-b583-e909948a5593.gif)

Iris is a simple utility written completely in python which allows to sync folders between local and remote ssh (sftp) server.
Iris runs locally but requires a working python installation on each machine where you want files to be watched.

Iris features are:
- Local and Remote ssh (sftp) directories support
- JumpProxy support for ssh
- Changes are sync in realtime using python watchdogs both locally and remotely
- Modification time is preserved during copy, merge by newer strategy is used
- Pattern / Pattern ignore settings
- Progress bars during large transfers

Linux / Mac / Windows support (UNTESTED Windows)

## Installation
```
git clone https://github.com/JunkyByte/iris.git
cd iris/
pip install .
```

### Remote installation
On remote host you do not need all dependencies, if you have a working python3 env just install the watchdog package and you should be set
```
pip install watchdog
```


## Examples
Inside your terminal you can start iris by typing
```
iris --config config_file.yaml
```
Other options are `--debug` that does not require any explanation and `--dry` which allows you to run iris in test mode,
no file writing will be actually done (please use this to test your settings without altering your files).

To create a configuration file with ease you can use
```
iris-init  # The default name will be iris_conf.yaml
iris-init --config my_new_config.yaml  # You can specify the file path
```

### Config files
Config files are in `yaml` format, the following parameters can be specified, the default value of optional is specified below.
```yaml
origin:  # local or the host for sftp (if not port specified 22 will be used) (e.g. root@104.30.12.61:42)
origin_jump: # host to use for jumping the ssh connection (optional) (e.g. user@104.32.5.42:42)
dest:  # local or the host for sftp
dest_jump: # host to use for jumping the ssh connection (optional)
mirror:  # Whether to mirror sync (origin <- dest) (optional, default: True)

# optional, default: '*', e.g. '*.yaml *.txt' to select a directory just use the relative path e.g. './git/'
pattern:  # Patterns for file name matching separated by a space

# optional, default: '//', e.g. '*.md5' to select a directory just use the relative path e.g. './git/'
ignore_pattern:  # Patterns for ignore by file name separated by a space

origin_path:  # The `origin` absolute path
dest_path:  # The `dest` absolute path
origin_key: # The key to use for origin ssh (if is remote)
dest_key: # The key to use for dest ssh (if is remote)
```
Note that if no user is specified on ssh host the local username will be used.

Right now iris requires a config file to be passed.
For remote connections iris will try to load from your `ssh-agent` first. If it fails it will use the key specified in the config file. More work is required in this regard.

## Under the hood
Iris uses `asyncssh` (which I recommend) for sftp file monitoring / writing, `aiofile` for async local file writing,
`watchdog` for monitoring file changes, `rich` for pretty printing, `pyYAML` for configuration files.

## Contribute / Issues
Please create an issue if you have any request / problem or want to contribute.

Password authentication sftp has not been tested and may not work.

Hope you find iris useful.

## Warning:
During a bidirectional sync if you delete a file from the `dest_path` it will be deleted on your `origin_path` and vice versa.
Also files will be merged based on most recent modification, be careful and run in `dry` mode first.
We do not take any responsability for files lost. Iris is a work in progress, be sure to backup your computer before using it,
do not run iris as sudo.
