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
