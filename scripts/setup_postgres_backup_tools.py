"""Fetch version-pinned PostgreSQL backup clients from the Windows distributor.

The archive (~337 MB) and extracted files stay under ignored .runtime. The
download URL is fixed HTTPS; a local SHA256 fingerprint is recorded, without
claiming it is a separately published vendor checksum.
"""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/".runtime"
URL="https://get.enterprisedb.com/postgresql/postgresql-18.4-1-windows-x64-binaries.zip"


def setup():
    archive=RUNTIME/"postgres-official-18.4.zip"
    if not archive.exists():
        urllib.request.urlretrieve(URL,archive)
    destination=RUNTIME/"postgres-backup-bin"
    destination.mkdir(exist_ok=True)
    executables={"pg_dump.exe","pg_restore.exe","createdb.exe"}
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            path=Path(entry.filename)
            if path.parent.as_posix()=="pgsql/bin" and (path.name in executables or path.suffix.lower()==".dll"):
                (destination/path.name).write_bytes(bundle.read(entry))
    assert all((destination/name).exists() for name in executables)
    config=RUNTIME/"postgres-test.json"
    settings=json.loads(config.read_text())
    settings.update(backup_binary_dir=str(destination),backup_tools_url=URL,backup_tools_archive_sha256=hashlib.file_digest(archive.open("rb"),"sha256").hexdigest())
    config.write_text(json.dumps(settings,indent=2)+"\n")
    print("PostgreSQL 18.4 backup client tools prepared in ignored .runtime")


if __name__=="__main__":
    setup()
