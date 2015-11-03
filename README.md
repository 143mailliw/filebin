[![Build Status](https://travis-ci.org/espebra/filebin.svg)](https://travis-ci.org/espebra/filebin)

# Requirements

To build ``filebin``, a Golang build environment and some Golang packages are needed.

When ``filebin`` has been built, it doesn't have any specific requirements to run. It even comes with its own web server bundled.

It is recommended but not required to run it behind a TLS/SSL proxy such as [Hitch](http://hitch-tls.org/) and web cache such as [Varnish Cache](https://www.varnish-cache.org/).

# Installation

Install ``golang``:

```
$ sudo yum/apt-get/brew install golang
```

Create the Go workspace and set the ``GOPATH`` environment variable:

```
$ mkdir ~/go
$ cd ~/go
$ mkdir src bin pkg
$ export GOPATH="~/go"
```

Download and install filebin. The binary will be created as ``~/go/bin/filebin``.

```
$ go get github.com/espebra/filebin
$ cd src/github.com/espebra/filebin
$ go install
```

Create the directories to use for storing files, logs and temporary files:

```
$ mkdir ~/filebin/files ~/filebin/logs ~/filebin/temp
```

# Usage

The built in help text will show the various command line arguments and their meaning.

```
~/go/bin/filebin --help
```

Some arguments commonly used to start ``filebin`` are:

```
~/go/bin/filebin --filedir ~/filebin/files --logdir ~/filebin/logs --tempdir ~/filebin/temp --verbose --host 0.0.0.0 --port 8080 --expiration 604800
```

By default, filebin will listen on ``127.0.0.1:31337``.


## Expiration

Tags expire after some time of inactivity. By default, tags will expire 3 months after the most recent file was uploaded. It is not possible to download files or upload more files to tags that are expired.

# API

## Upload file

In all examples, I will upload the file ``/path/to/file``.

Using the following command, the ``tag`` will be automatically generated and the ``filename`` will be set to the SHA256 checksum of the content. The checksum of the content will not be verified.

```
$ curl --data-binary @/path/to/file http://localhost:31337/
```

Using the following command, ``tag`` will be set to ``customtag`` and ``filename`` will be set to ``myfile``.

```
$ curl --data-binary @/path/to/file http://localhost:31337/ -H "tag: customtag" -H "filename: myfile"
```

## Show tag

The following command will print a JSON structure showing which files that available in the tag ``customtag``.

```
$ curl http://localhost:31337/customtag
```

## Download file

Downloading a file is as easy as specifying the ``tag`` and the ``filename`` in the request URI:

```
$ curl http://localhost:31337/customtag/myfile
```
