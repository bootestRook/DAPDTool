import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import httpx
from PIL import Image

from dapd_tool.content_packs import export_pack, install_pack, load_shared, all_assets
from dapd_tool.media import Assets
from dapd_tool.storage import Store
from dapd_tool.updates import ReleaseClient, REPO_URL, choose_releases, ProgramUpdater, version_tuple


def release(version, content=False, data=b'package'):
    tag = ('content-v' if content else 'v') + version
    name = f'dapd-content-{version}.zip' if content else 'releases.win.json'
    return {'tag_name': tag, 'draft': False, 'prerelease': False, 'body': '更新说明',
            'assets': [{'name': name, 'browser_download_url': f'{REPO_URL}/releases/download/{tag}/{name}',
                        'size': len(data), 'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}]}


class ReleaseTests(unittest.TestCase):
    def test_program_and_content_versions_are_independent(self):
        rows = [release('1.10.0'), release('1.9.0'), release('2.0.0', True),
                {**release('99.0.0'), 'draft': True}, {**release('100.0.0'), 'prerelease': True}]
        result = choose_releases(rows)
        self.assertEqual(result['program']['version'], '1.10.0')
        self.assertEqual(result['content']['version'], '2.0.0')

    def test_asset_must_stay_in_configured_public_repository(self):
        row = release('1.2.0')
        row['assets'][0]['browser_download_url'] = 'https://example.com/payload'
        with self.assertRaises(ValueError): choose_releases([row])

    def test_network_api_is_anonymous_and_paginates(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertNotIn('authorization', request.headers)
            return httpx.Response(200, json=[{}] * 100 if request.url.params['page'] == '1' else [release('1.2.0')])
        with ReleaseClient(httpx.MockTransport(handler)) as client:
            self.assertEqual(client.releases()['program']['version'], '1.2.0')
        self.assertEqual(len(requests), 2)

    def test_content_download_redirect_and_hash(self):
        data = b'valid-package'
        item = choose_releases([release('1.0.0', True, data)])['content']
        def handler(request):
            if request.url.host == 'github.com':
                return httpx.Response(302, headers={'location': 'https://release-assets.githubusercontent.com/asset'})
            return httpx.Response(200, content=data)
        with tempfile.TemporaryDirectory() as directory, ReleaseClient(httpx.MockTransport(handler)) as client:
            path = Path(directory) / 'file.zip'
            client.download_content(item, path)
            self.assertEqual(path.read_bytes(), data)
            item['asset']['digest'] = 'sha256:' + '0' * 64
            with self.assertRaises(ValueError): client.download_content(item, path)
            self.assertFalse(path.exists())

    def test_invalid_version_and_unknown_digest_are_rejected(self):
        for version in ['1.0', '../1.0.0', '01.0.0', '1.0.0-rc1']:
            with self.assertRaises(ValueError): version_tuple(version)
        item = choose_releases([release('1.0.0', True)])['content']
        item['asset']['digest'] = None
        with ReleaseClient(httpx.MockTransport(lambda _: self.fail('must not download'))) as client:
            with self.assertRaises(ValueError): client.download_content(item, Path('unused'))

    def test_program_download_then_graceful_apply(self):
        updater = ProgramUpdater()
        updater.installed = True
        info = Mock()
        info.TargetFullRelease.Version = '1.2.0'
        manager = Mock()
        manager.check_for_updates.return_value = info
        with patch.object(updater, '_manager', return_value=manager):
            updater.download(choose_releases([release('1.2.0')])['program'], Mock())
            self.assertIs(updater.ready, info)
            updater.launch_update()
        manager.wait_exit_then_apply_updates.assert_called_once_with(info, silent=False, restart=True)


class PackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.publisher = Store(self.root / 'publisher')
        self.reader = Store(self.root / 'reader')
        asset_store = Assets(self.publisher.directory)
        image = self.root / 'image.png'
        Image.new('RGB', (8, 8), 'blue').save(image)
        image = asset_store.import_file(image, image_only=True)
        attachment = self.root / '附件.txt'
        attachment.write_text('fixed attachment', encoding='utf-8')
        attachment = asset_store.import_file(attachment)
        content = {'parts': [{'text': '固定描述'}, {'image': image}], 'attachments': [attachment]}
        self.publisher.save_template('共享测试', [{'title': '子任务', 'parent': None, 'content': content}], root=content)
        self.personal_id = self.reader.save_template('个人模板', [])

    def package(self, version='1.0.0'):
        path = self.root / f'dapd-content-{version}.zip'
        export_pack(self.publisher.directory, self.publisher.templates(), version, '内容说明', path)
        return path

    def test_nested_content_and_media_roundtrip_preserves_personal_data(self):
        install_pack(self.reader.directory, self.package(), '1.0.0')
        shared = load_shared(self.reader.directory)
        self.assertEqual(shared['version'], '1.0.0')
        self.assertEqual(shared['templates'][0]['nodes'][0]['content']['parts'][0]['text'], '固定描述')
        assets = Assets(self.reader.directory)
        for asset in all_assets(shared['templates'][0]):
            assets.path(asset, verify_hash=True)
        self.assertEqual(self.reader.templates()[0]['id'], self.personal_id)
        self.assertEqual(len(self.reader.templates()), 1)

    def test_bad_file_never_activates_new_catalog(self):
        install_pack(self.reader.directory, self.package(), '1.0.0')
        before = (self.reader.directory / 'shared-content.json').read_bytes()
        newer = self.package('1.0.1')
        bad = self.root / 'bad.zip'
        with zipfile.ZipFile(newer) as original, zipfile.ZipFile(bad, 'w') as changed:
            for name in original.namelist():
                changed.writestr(name, original.read(name) if name == 'content.json' else b'damaged')
        with self.assertRaises(ValueError): install_pack(self.reader.directory, bad, '1.0.1')
        self.assertEqual(before, (self.reader.directory / 'shared-content.json').read_bytes())

    def test_verified_download_repairs_corrupted_shared_catalog(self):
        pack = self.package()
        install_pack(self.reader.directory, pack, '1.0.0')
        (self.reader.directory / 'shared-content.json').write_text('{damaged', encoding='utf-8')
        install_pack(self.reader.directory, pack, '1.0.0')
        self.assertEqual(load_shared(self.reader.directory)['version'], '1.0.0')
        self.assertEqual(self.reader.templates()[0]['id'], self.personal_id)

    def test_duplicate_or_traversal_zip_entries_are_rejected(self):
        good = self.package()
        bad = self.root / 'bad.zip'
        with zipfile.ZipFile(good) as original, zipfile.ZipFile(bad, 'w') as changed:
            for name in original.namelist(): changed.writestr(name, original.read(name))
            changed.writestr('../escaped.txt', 'escape')
        with self.assertRaises(ValueError): install_pack(self.reader.directory, bad, '1.0.0')
        self.assertFalse((self.reader.directory / 'shared-content.json').exists())
        self.assertFalse((self.root / 'escaped.txt').exists())

    def test_export_only_contains_selected_templates_and_referenced_files(self):
        self.publisher.save_key('dapd_' + '1' * 64)
        self.publisher.save_template('不发布的模板', [])
        selected = [t for t in self.publisher.templates() if t['name'] == '共享测试']
        path = self.root / 'selected.zip'
        export_pack(self.publisher.directory, selected, '1.0.0', '', path)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(len(archive.namelist()), 3)
            raw = archive.read('content.json')
            self.assertNotIn(b'dapd_', raw)
            self.assertEqual(len(json.loads(raw)['templates']), 1)

    def test_older_or_incompatible_content_is_rejected(self):
        pack = self.package()
        with self.assertRaises(ValueError): install_pack(self.reader.directory, pack, '1.0.0', '1.0.0')
        with self.assertRaises(ValueError): install_pack(self.reader.directory, pack, '1.2.0')
        install_pack(self.reader.directory, pack, '1.0.0')
        with self.assertRaises(ValueError): install_pack(self.reader.directory, pack, '1.0.0')

    def test_new_shared_version_does_not_change_copied_personal_template(self):
        install_pack(self.reader.directory, self.package(), '1.0.0')
        original = load_shared(self.reader.directory)['templates'][0]
        self.reader.save_template('我的副本', original['nodes'], root=original['root'])
        old = copy.deepcopy(self.reader.templates())
        source = self.publisher.templates()[0]
        self.publisher.save_template('共享测试', [], source['id'], root={'parts': [{'text': '新内容'}], 'attachments': []})
        install_pack(self.reader.directory, self.package('1.0.1'), '1.0.1')
        self.assertEqual(self.reader.templates(), old)
        self.assertEqual(load_shared(self.reader.directory)['templates'][0]['nodes'], [])


if __name__ == '__main__': unittest.main()
