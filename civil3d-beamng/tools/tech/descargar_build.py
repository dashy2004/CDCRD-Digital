"""Install a licensed Tech ZIP from a private job directory; no embedded credentials."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import time
from urllib.parse import urlsplit
import urllib.request
import urllib.error
import zipfile


def extract_installation(archive, destination, license_file, expanded, save_status):
    """Extract into a new directory; preserve an incomplete install on failure."""
    with zipfile.ZipFile(archive) as z:
        members = z.infolist()
        if sum(m.file_size for m in members) != expanded:
            raise ValueError('Expanded size differs from the inspected central directory.')
        for member in members:
            path = PurePosixPath(member.filename.replace('\\', '/'))
            if path.is_absolute() or '..' in path.parts or ':' in member.filename:
                raise ValueError('Unsafe ZIP member path.')
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('ZIP links are not supported.')
            (destination/Path(*path.parts)).resolve().relative_to(destination)
        destination.mkdir(parents=True)
        save_status('extracting', entries=len(members), entries_extracted=0)
        checkpoint = time.monotonic()
        for index, member in enumerate(members):
            # ZipFile checks CRC as each member is extracted.
            z.extract(member, destination)
            if time.monotonic() - checkpoint > 2:
                save_status('extracting', entries=len(members), entries_extracted=index+1)
                checkpoint = time.monotonic()
    executables = list(destination.rglob('BeamNG.tech.x64.exe'))
    if len(executables) != 1 or executables[0].parent.name != 'Bin64':
        raise ValueError('Could not identify one Tech installation.')
    home = executables[0].parent.parent
    shutil.copy2(license_file, home/'tech.key')
    save_status('installed', home=str(home), engine_launched=False, license_activation_verified=False)


def install_from_archive(job, destination, license_file, archive, sha256):
    """Use an already recovered ZIP without a network request or deleting it."""
    job, destination, archive = job.resolve(), destination.resolve(), archive.resolve()
    if destination.exists():
        raise ValueError('Installation destination already exists; preserve it.')
    if not re.fullmatch(r'[0-9a-fA-F]{64}', sha256 or ''):
        raise ValueError('A verified SHA256 is required for a local archive.')
    if not archive.is_file() or not license_file.is_file():
        raise ValueError('Require a local archive and license file.')
    sizes = json.loads((job/'archive-size.json').read_text())
    if sizes['zip_bytes'] <= 0 or sizes['uncompressed_bytes'] <= 0 or archive.stat().st_size != sizes['zip_bytes']:
        raise ValueError('Archive length does not match inspected metadata.')
    # Find an existing ancestor on the installation volume for the space check.
    ancestor = destination.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < sizes['uncompressed_bytes'] + 5_000_000_000:
        raise ValueError('Insufficient free space for extraction.')

    def save_status(state, **extra):
        report = {'state': state, 'source': 'local_archive', 'archive_sha256': sha256.lower(), **extra}
        temporary = job/'install-status.tmp'
        temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
        temporary.replace(job/'install-status.json')

    try:
        save_status('checking_archive_hash')
        with archive.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != sha256.lower():
                raise ValueError('Archive SHA256 mismatch.')
        extract_installation(archive, destination, license_file, sizes['uncompressed_bytes'], save_status)
    except Exception as exc:
        save_status('failed', error_type=type(exc).__name__)
        raise RuntimeError('Local installation failed; archive and partial installation preserved.') from None


def install(job, destination, license_file, connections, workers=None):
    if workers is None:
        workers = min(2, connections)
    if not 1 <= connections <= 8 or not 1 <= workers <= connections:
        raise ValueError('Require 1 <= workers <= connections <= 8.')
    job = job.resolve()
    destination = destination.resolve()
    if job.anchor.casefold() != destination.anchor.casefold():
        raise ValueError('Download and installation must use the same volume.')
    if destination.exists():
        raise ValueError('Installation destination already exists; preserve it.')
    url = json.loads((job / 'build-download.private.json').read_text())['url']
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'api.beamng.com':
        raise ValueError('Expected an official HTTPS BeamNG API download.')
    sizes = json.loads((job / 'archive-size.json').read_text())
    size = sizes['zip_bytes']
    expanded = sizes['uncompressed_bytes']
    if size <= 0 or expanded <= 0 or not license_file.is_file():
        raise ValueError('Archive sizes and a local license file are required.')
    # Parts + assembled ZIP + expanded installation, with a 5 GB margin.
    if shutil.disk_usage(job).free < 2*size + expanded + 5_000_000_000:
        raise ValueError('Insufficient free space for a conservative installation.')
    piece = (size+connections-1)//connections
    parts = [job / f'build.part{i}' for i in range(connections)]
    partition = {'zip_bytes': size, 'parts': connections}
    partition_file = job / 'download-partition.json'
    if partition_file.exists():
        if json.loads(partition_file.read_text()) != partition:
            raise ValueError('Partition changed; preserve existing partial files.')
    else:
        partition_file.write_text(json.dumps(partition, indent=2), encoding='utf-8')
    counts = [part.stat().st_size if part.exists() else 0 for part in parts]

    def save_status(state, **extra):
        report = {'state': state, 'downloaded_bytes': sum(counts), 'total_bytes': size, **extra}
        temporary = job/'install-status.tmp'
        temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
        temporary.replace(job/'install-status.json')

    def fetch(i):
        begin, end = i*piece, min(size, (i+1)*piece)-1
        expected = end-begin+1
        existing = parts[i].stat().st_size if parts[i].exists() else 0
        if existing > expected:
            raise ValueError('A partial file exceeds its assigned range.')
        counts[i] = existing
        for attempt in range(4):
            if counts[i] == expected:
                return
            offset = begin + counts[i]
            req = urllib.request.Request(url, headers={'Range': f'bytes={offset}-{end}'})
            try:
                with urllib.request.urlopen(req, timeout=45) as response:
                    if response.status != 206 or response.headers.get('Content-Range') != f'bytes {offset}-{end}/{size}':
                        raise ValueError('Server did not honor the exact byte range.')
                    with parts[i].open('ab') as stream:
                        while block := response.read(min(2**20, expected-counts[i])):
                            stream.write(block)
                            counts[i] += len(block)
                if counts[i] != expected:
                    raise IOError('Incomplete range.')
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)

    try:
        # Keep byte-range partitioning stable when lowering concurrent requests.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs = [pool.submit(fetch, i) for i in range(connections)]
            while not all(f.done() for f in jobs):
                save_status('downloading')
                wait(jobs, timeout=10)
            for future in jobs:
                future.result()
        archive = job/'BeamNG.tech.download.zip'
        if archive.exists():
            raise ValueError('Assembled ZIP already exists; inspect it before resuming.')
        save_status('assembling')
        with archive.open('xb') as target:
            for part in parts:
                with part.open('rb') as source:
                    shutil.copyfileobj(source, target, length=2**20)
        if archive.stat().st_size != size:
            raise IOError('ZIP length mismatch.')
        extract_installation(archive, destination, license_file, expanded, save_status)
        # Remove only this job's exact part files after extraction and license copy.
        for part in parts:
            if part.parent != job:
                raise ValueError('Unexpected part directory.')
            part.unlink()
    except Exception as exc:
        details = {'error_type': type(exc).__name__}
        if isinstance(exc, urllib.error.HTTPError):
            details['http_status'] = exc.code
        save_status('failed', **details)
        raise RuntimeError('Installation failed; inspect local status and preserve partial files.') from None


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--license', type=Path, required=True)
    p.add_argument('--connections', type=int, choices=range(1,9), default=4)
    p.add_argument('--workers', type=int, choices=range(1,9), default=None,
                   help='Concurrent HTTP requests; keep --connections unchanged when resuming.')
    p.add_argument('--archive', type=Path, help='Recovered local ZIP; never downloaded or deleted.')
    p.add_argument('--sha256', help='Required hash of the verified local ZIP.')
    a = p.parse_args()
    if a.archive:
        if not a.sha256:
            p.error('--archive requires --sha256')
        install_from_archive(a.job, a.destination, a.license, a.archive, a.sha256)
    elif a.sha256:
        p.error('--sha256 requires --archive')
    else:
        install(a.job, a.destination, a.license, a.connections, a.workers)
