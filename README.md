# telegrafbacnet

Telegraf execd plugin for BACnet.

## Installing and Running

To install telegrafbacnet and its dependencies run in the project root:
```sh
pip install -U .
```

It will also create an entrypoint that can be used to run telegrafbacnet from any
directory like this:
```sh
telegrafbacnet [OPTIONS]
```

## Options

`-h`, `--help`

- show help message and exit

`--debug`

- show debug output on stderr

`--config CONFIG`

- load config from the file `CONFIG` or load config from files in the directory
  `CONFIG` in alphabetical order

## Configuration

By default, config is loaded from files in the directory `/etc/telegrafbacnet/` in
alphabetical order.

See `config.toml` for more information about options that can be configured.

## Use with Telegraf

Telegrafbacnet is an execd plugin that outputs metrics on its own.
Here is an example part of Telegraf configuration:

```toml
[[inputs.execd]]
  ## Program to run as daemon
  command = ["telegrafbacnet", "--config", "/etc/telegrafbacnet.toml"]

  ## Define how the process is signaled on each collection interval.
  ## Valid values are:
  ##   "none"   : Do not signal anything.
  ##              The process must output metrics by itself.
  ##   "STDIN"   : Send a newline on STDIN.
  ##   "SIGHUP"  : Send a HUP signal. Not available on Windows.
  ##   "SIGUSR1" : Send a USR1 signal. Not available on Windows.
  ##   "SIGUSR2" : Send a USR2 signal. Not available on Windows.
  signal = "none"

  ## Delay before the process is restarted after an unexpected termination
  restart_delay = "10s"

  ## Data format to consume.
  ## Each data format has its own unique set of configuration options, read
  ## more about them here:
  ## https://github.com/influxdata/telegraf/blob/master/docs/DATA_FORMATS_INPUT.md
  data_format = "influx"
```
