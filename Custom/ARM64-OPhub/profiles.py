#!/usr/bin/env python3
"""Select ARM64 devices and check their recipes against the locked OPhub resources."""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def select(device):
    profiles = json.loads((HERE / 'devices.json').read_text(encoding='utf-8'))
    names = list(profiles) if device == 'all' else [device]
    return [dict(board=name, **profiles[name]) for name in names]


def validate(profiles, database, boot_root):
    rows = {}
    for line in Path(database).read_text(encoding='utf-8').splitlines():
        columns = [value.strip() for value in line.split(':')]
        if len(columns) == 15 and not line.lstrip().startswith('#'):
            rows[columns[13]] = columns
    for profile in profiles:
        row = rows[profile['board']]
        for index, key in ((2, 'soc'), (3, 'dtb'), (4, 'trust'),
                           (5, 'uboot'), (6, 'bootloader')):
            if row[index] != profile[key]:
                raise ValueError(f"{profile['board']}: upstream {key} differs: {row[index]}")
        if row[9] != 'rockchip' or row[11] != 'armbianEnv.txt' or row[14] != 'yes':
            raise ValueError(f"{profile['board']}: unsupported platform/boot configuration")
        lock = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))
        series = '.'.join(lock['kernel']['version'].split('.')[:2])
        if f'stable/{series}.y' not in row[8].split(','):
            raise ValueError(f"{profile['board']}: locked stable kernel is not listed upstream")
        for key in ('bootloader', 'uboot', 'trust'):
            if profile[key] != 'NA':
                path = Path(boot_root) / 'rockchip' / profile['board'] / profile[key]
                if not path.is_file() or path.stat().st_size == 0:
                    raise ValueError(f'Missing boot resource: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='all')
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--boot-root', type=Path)
    args = parser.parse_args()
    profiles = select(args.device)
    if args.database:
        if not args.boot_root:
            parser.error('--database requires --boot-root')
        validate(profiles, args.database, args.boot_root)
    lock = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))
    outputs = {
        'matrix': json.dumps({'include': profiles}, separators=(',', ':')),
        'dtbs': json.dumps([p['dtb'] for p in profiles], separators=(',', ':')),
        'packer_commit': lock['packer_commit'],
        'uboot_commit': lock['repositories']['https://github.com/ophub/u-boot'],
        **{'kernel_' + key: value for key, value in lock['kernel'].items()},
        'kernel_config_file': 'config-' + '.'.join(lock['kernel']['version'].split('.')[:2]),
    }
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as output:
            for key, value in outputs.items():
                print(f'{key}={value}', file=output)
    print(json.dumps(profiles, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
