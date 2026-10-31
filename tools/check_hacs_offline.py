#!/usr/bin/env python3
"""Exercise unmodified official HACS repository code with local network fixtures.

This is an offline engine/HA-loader check, NOT a real GitHub/HACS download.
Official HACS source is supplied separately and never bundled with Virtavo.
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import logging
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HACS_COMMIT = 'c0dfd8b44297c3673c21973e2539375a53687a9c'


async def check(source: Path, archive: Path):
    revision = subprocess.check_output(
        ['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True,
    ).strip()
    if revision != HACS_COMMIT:
        raise ValueError('Expected official HACS2.0.5 source revision')
    if subprocess.check_output(
        ['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'],
        text=True,
    ).strip():
        raise ValueError('Official HACS tracked sources must be unmodified')
    package = source / 'custom_components/hacs'
    # Load the actual repository modules without starting the HACS integration
    # or requiring its separately generated browser frontend. No method body
    # is extracted, replaced, patched or reimplemented.
    for name, path in [('custom_components', package.parent),
                       ('custom_components.hacs', package)]:
        module = ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    from custom_components.hacs.repositories.integration import HacsIntegrationRepository
    from custom_components.hacs.utils.validate import (
        HACS_MANIFEST_JSON_SCHEMA, INTEGRATION_MANIFEST_JSON_SCHEMA,
    )
    from homeassistant.core import HomeAssistant

    with zipfile.ZipFile(archive) as packed:
        entries = packed.infolist()
        if len(entries) > 2048 or len({p.filename for p in entries}) != len(entries):
            raise ValueError('Excessive or duplicate archive members')
        if sum(p.file_size for p in entries) > 25 * 1024 * 1024:
            raise ValueError('Oversized source archive')
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                    or stat.S_ISLNK(entry.external_attr >> 16)
                    or entry.file_size > 2 * 1024 * 1024):
                raise ValueError('Unsafe or oversized archive member')
        files = {n: packed.read(n) for n in packed.namelist() if not n.endswith('/')}
    inventory = json.loads(files['PACKAGE_SHA256.json'])
    if any(hashlib.sha256(files[n]).hexdigest() != h for n, h in inventory.items()):
        raise ValueError('Source archive integrity failure')
    HACS_MANIFEST_JSON_SCHEMA(json.loads(files['hacs.json']))
    INTEGRATION_MANIFEST_JSON_SCHEMA(
        json.loads(files['custom_components/virtavo/manifest.json']))
    directory_names = {'custom_components', 'custom_components/virtavo'}
    for name in files:
        directory_names.update(str(p) for p in Path(name).parents if str(p) != '.')
    tree = [SimpleNamespace(full_path=n, filename=Path(n).name, is_directory=True)
            for n in sorted(directory_names)]
    tree += [SimpleNamespace(full_path=n, filename=Path(n).name, is_directory=False)
             for n in sorted(files)]
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as packed:
        for name, value in files.items():
            packed.writestr('offline-fixture-main/' + name, value)
    downloads = []
    async def download(url, **kwargs):
        downloads.append(url)
        if '/tags/' in url:
            return None
        if '/heads/' in url:
            return payload.getvalue()
        raise AssertionError('Unexpected network fixture request')
    async def save(path, value):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(value)
        return True
    async def api(**kwargs):
        if (name := kwargs.get('path')) is not None:
            return SimpleNamespace(data=SimpleNamespace(
                content=base64.b64encode(files[str(name)]).decode()))
        return SimpleNamespace(data=[])
    class Remote:
        full_name = 'example/virtavo-offline-fixture'
        attributes = {'full_name': full_name, 'id': 1, 'default_branch': 'main',
                      'archived': False, 'has_issues': True}
        async def get_tree(self, ref):
            return tree
    async def get_repo(*args, **kwargs):
        return Remote()
    with tempfile.TemporaryDirectory(prefix='virtavo-official-hacs-') as directory:
        config = Path(directory) / 'config'
        config.mkdir()
        hass = HomeAssistant(str(config))
        logger = logging.getLogger('virtavo.hacs.offline')
        hacs = SimpleNamespace(
            hass=hass, core=SimpleNamespace(config_path=str(config)),
            log=logger, queue=None,
            status=SimpleNamespace(startup=False),
            system=SimpleNamespace(action=False, generator=False),
            common=SimpleNamespace(renamed_repositories={}, archived_repositories=set()),
            repositories=SimpleNamespace(is_removed=lambda name: False),
            github=SimpleNamespace(get_repo=get_repo,
                client=SimpleNamespace(last_response=SimpleNamespace(etag='offline'))),
            githubapi=SimpleNamespace(repos=SimpleNamespace(
                contents=SimpleNamespace(get=object()), releases=SimpleNamespace(list=object()))),
            async_github_api_method=api, async_download_file=download,
            async_save_file=save,
        )
        try:
            repository = HacsIntegrationRepository(hacs, Remote.full_name)
            assert await repository.validate_repository(), repository.validate.errors
            assert repository.content.path.remote == 'custom_components/virtavo'
            assert repository.data.domain == 'virtavo'
            assert repository.repository_manifest.content_in_root is False
            await repository.download_content()
            assert not repository.validate.errors, repository.validate.errors
            installed = config / 'custom_components/virtavo'
            expected = {n.removeprefix('custom_components/virtavo/'): value
                        for n, value in files.items()
                        if n.startswith('custom_components/virtavo/')}
            actual = {str(p.relative_to(installed)): p.read_bytes()
                      for p in installed.rglob('*') if p.is_file()}
            assert actual == expected, 'HACS selection/extraction differs from runtime'
            assert not (config / 'README.md').exists()
            sys.path.insert(0, str(ROOT / 'tests'))
            from test_full_ha_loader import RUNNER
            runner = Path(directory) / 'loader.py'
            runner.write_text(RUNNER)
            completed = subprocess.run(
                [sys.executable, '-I', str(runner), str(config)], cwd=config,
                capture_output=True, text=True, timeout=45,
            )
            if completed.returncode:
                raise AssertionError(completed.stderr[-4000:])
            loader = json.loads(completed.stdout.strip().splitlines()[-1])
            return {
                'HACS_version': '2.0.5', 'HACS_commit': revision,
                'official_repository_engine_unmodified': True,
                'official_HACS_metadata_validation': True,
                'official_HACS_manifest_schemas': True,
                'official_HACS_archive_selection_extraction': True,
                'selected_runtime_files': len(actual), 'all_runtime_bytes_match': True,
                'branch_fallback_fixture_requests': len(downloads),
                'actual_HA_loader_after_HACS_extraction': loader,
                'GitHub_metadata_and_network': 'local fixtures only',
                'HACS_UI_or_startup_tested': False,
                'actual_remote_HACS_download': False,
                'private_repositories_supported': False,
                'camera_or_cloud_contacted': False,
                'runtime_dependencies_added': False,
            }
        finally:
            await hass.async_stop(force=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hacs-source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(check(args.hacs_source.resolve(), args.archive.resolve()))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
