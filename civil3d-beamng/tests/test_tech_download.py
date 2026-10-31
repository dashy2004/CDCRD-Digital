"""Installer safety checks using tiny synthetic ZIPs, never the licensed game."""
import importlib.util
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
