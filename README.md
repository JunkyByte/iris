# iris

Iris is a simple utility written completely in python which allows to sync folders between local and remote ssh (sftp) server.
Iris runs locally and requires a working python installation on remote server (if you want the connection to be bidirectional).

Iris features are:
- Local and Remote ssh (sftp) directories support
- Changes are sync in realtime using python watchdogs both locally and remotely
- Modified time preserved during copy, merge by newer strategy
- Pattern / Pattern ignore

Linux / Mac / Windows support (UNTESTED Windows)

## Installation
```
git clone https://github.com/JunkyByte/iris.git
cd iris/
pip install .
```

## Examples
Inside your terminal you can start iris by typing
```
iris --config config_file.yaml
```
