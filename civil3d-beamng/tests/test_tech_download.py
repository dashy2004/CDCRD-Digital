"""Installer safety checks using tiny synthetic ZIPs, never the licensed game."""
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('tech_download', Path(__file__).parents[1]/'tools/tech/descargar_build.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(tmp_path, monkeypatch, unsafe=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        z.writestr('build/Bin64/BeamNG.tech.x64.exe', b'synthetic test only')
        if unsafe:
            z.writestr('../escaped.txt', b'no')
    data = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        expanded = sum(i.file_size for i in z.infolist())
    job = tmp_path/'job'; job.mkdir()
    (job/'build-download.private.json').write_text(json.dumps({'url':'https://api.beamng.com/synthetic-test.zip'}))
    (job/'archive-size.json').write_text(json.dumps({'zip_bytes':len(data),'uncompressed_bytes':expanded}))
    license_file = tmp_path/'fake.key'; license_file.write_bytes(b'fixture, not a license')
    class Response(io.BytesIO):
        status = 206
    def urlopen(request, timeout):
        start,end = map(int, request.get_header('Range').split('=')[1].split('-'))
        response=Response(data[start:end+1])
        response.headers={'Content-Range':f'bytes {start}-{end}/{len(data)}'}
        return response
    monkeypatch.setattr(module.urllib.request,'urlopen',urlopen)
    return job, tmp_path/'installed', license_file


def test_installs_synthetic_archive_and_keeps_activation_unverified(tmp_path, monkeypatch):
    job,destination,key=fixture(tmp_path,monkeypatch)
    module.install(job,destination,key,2)
    status=json.loads((job/'install-status.json').read_text())
    assert status['state']=='installed'
    assert status['license_activation_verified'] is False
    assert (destination/'build/tech.key').read_bytes()==key.read_bytes()
    assert not list(job.glob('build.part*'))


def test_rejects_traversal_before_creating_installation(tmp_path, monkeypatch):
    job,destination,key=fixture(tmp_path,monkeypatch,unsafe=True)
    with pytest.raises(RuntimeError):
        module.install(job,destination,key,2)
    assert not destination.exists()
    assert not (tmp_path/'escaped.txt').exists()
    assert json.loads((job/'install-status.json').read_text())['state']=='failed'


def test_preserves_existing_destination(tmp_path, monkeypatch):
    job,destination,key=fixture(tmp_path,monkeypatch)
    destination.mkdir(); marker=destination/'keep.txt';marker.write_text('preserve')
    with pytest.raises(ValueError,match='already exists'):
        module.install(job,destination,key,2)
    assert marker.read_text()=='preserve'


def test_resume_keeps_partition_when_lowering_concurrency(tmp_path, monkeypatch):
    job,destination,key=fixture(tmp_path,monkeypatch)
    size=json.loads((job/'archive-size.json').read_text())['zip_bytes']
    request=module.urllib.request.Request('https://api.beamng.com/synthetic-test.zip',headers={'Range':f'bytes=0-{(size+1)//2-1}'})
    with module.urllib.request.urlopen(request,timeout=1) as response:
        (job/'build.part0').write_bytes(response.read())
    module.install(job,destination,key,2,workers=1)
    assert json.loads((job/'install-status.json').read_text())['state']=='installed'
    assert json.loads((job/'download-partition.json').read_text())['parts']==2


def test_partition_change_preserves_partial_files(tmp_path, monkeypatch):
    job,destination,key=fixture(tmp_path,monkeypatch)
    (job/'download-partition.json').write_text(json.dumps({'zip_bytes':1,'parts':8}))
    (job/'build.part0').write_bytes(b'keep')
    with pytest.raises(ValueError,match='Partition changed'):
        module.install(job,destination,key,2,workers=1)
    assert (job/'build.part0').read_bytes()==b'keep'


def test_single_connection_uses_one_worker_by_default(tmp_path, monkeypatch):
    job,destination,key=fixture(tmp_path,monkeypatch)
    module.install(job,destination,key,1)
    assert json.loads((job/'install-status.json').read_text())['state']=='installed'


def local_fixture(tmp_path, monkeypatch, unsafe=False):
    job,destination,key=fixture(tmp_path,monkeypatch,unsafe)
    size=json.loads((job/'archive-size.json').read_text())['zip_bytes']
    request=module.urllib.request.Request('https://api.beamng.com/synthetic-test.zip',headers={'Range':f'bytes=0-{size-1}'})
    with module.urllib.request.urlopen(request,timeout=1) as response:
        data=response.read()
    archive=tmp_path/'recovered.zip'; archive.write_bytes(data)
    def forbid_network(*args,**kwargs):
        pytest.fail('Local recovery must not access the network.')
    monkeypatch.setattr(module.urllib.request,'urlopen',forbid_network)
    (job/'build-download.private.json').unlink()
    return job,destination,key,archive,hashlib.sha256(data).hexdigest()


def test_local_install_without_network_preserves_archive_and_parts(tmp_path, monkeypatch):
    job,destination,key,archive,digest=local_fixture(tmp_path,monkeypatch)
    (job/'build.part0').write_bytes(b'prior interrupted download')
    module.install_from_archive(job,destination,key,archive,digest)
    report=json.loads((job/'install-status.json').read_text())
    assert report['state']=='installed' and report['source']=='local_archive'
    assert report['license_activation_verified'] is False
    assert (destination/'build/tech.key').read_bytes()==key.read_bytes()
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest
    assert (job/'build.part0').read_bytes()==b'prior interrupted download'


def test_local_hash_mismatch_never_creates_destination(tmp_path, monkeypatch):
    job,destination,key,archive,digest=local_fixture(tmp_path,monkeypatch)
    with pytest.raises(RuntimeError):
        module.install_from_archive(job,destination,key,archive,'0'*64)
    assert not destination.exists() and archive.exists()
    assert json.loads((job/'install-status.json').read_text())['state']=='failed'


def test_local_unsafe_paths_fail_before_extraction(tmp_path, monkeypatch):
    job,destination,key,archive,digest=local_fixture(tmp_path,monkeypatch,unsafe=True)
    with pytest.raises(RuntimeError):
        module.install_from_archive(job,destination,key,archive,digest)
    assert not destination.exists() and not (tmp_path/'escaped.txt').exists()


def test_local_crc_failure_preserves_partial_but_does_not_install_license(tmp_path, monkeypatch):
    job,destination,key,archive,digest=local_fixture(tmp_path,monkeypatch)
    corrupted=archive.read_bytes().replace(b'synthetic test only',b'Synthetic test only',1)
    archive.write_bytes(corrupted)
    with pytest.raises(RuntimeError):
        module.install_from_archive(job,destination,key,archive,hashlib.sha256(corrupted).hexdigest())
    assert archive.exists() and destination.exists()
    assert not (destination/'build/tech.key').exists()
    assert json.loads((job/'install-status.json').read_text())['state']=='failed'


def test_local_existing_installation_is_preserved(tmp_path, monkeypatch):
    job,destination,key,archive,digest=local_fixture(tmp_path,monkeypatch)
    destination.mkdir(); (destination/'keep').write_text('existing')
    with pytest.raises(ValueError,match='already exists'):
        module.install_from_archive(job,destination,key,archive,digest)
    assert (destination/'keep').read_text()=='existing'
