"""Start an isolated native Windows PostgreSQL test server, loopback only.

No Docker operations; never alters other databases or services. Runtime, random
credentials, server logs and backup files remain under ignored .runtime.
"""
import base64
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/".runtime"
PACKAGE_VERSION="18.4.0-beta.17"
PACKAGE_URL=f"https://registry.npmjs.org/@embedded-postgres/windows-x64/-/windows-x64-{PACKAGE_VERSION}.tgz"
PACKAGE_SHA512="AwRerliA4IGWyW5jWBvHt5vidVUSB0QQW9Tt2y7ScnmifnCb/awfxZr4BkBSTv+gNt8Djcddqs+xSF5Z6/CkTg=="


def setup():
    RUNTIME.mkdir(exist_ok=True)
    archive=RUNTIME/"postgres-windows.tgz"
    target=RUNTIME/"postgres-binaries"
    if not target.exists():
        if not archive.exists():
            urllib.request.urlretrieve(PACKAGE_URL,archive)
        assert base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()==PACKAGE_SHA512, "PostgreSQL package integrity mismatch"
        target.mkdir()
        with tarfile.open(archive) as bundle:
            bundle.extractall(target,filter="data")
    found=list(target.rglob("initdb.exe"))
    assert len(found)==1, "Expected one initdb in pinned runtime"
    binaries=found[0].parent
    data=RUNTIME/"postgres-data"
    settings_path=RUNTIME/"postgres-test.json"
    if settings_path.exists():
        settings=json.loads(settings_path.read_text())
    else:
        password=secrets.token_urlsafe(36)
        settings={"NCDAI_CASE_DATABASE_URL":f"postgresql+psycopg://ncdai_test:{password}@127.0.0.1:15432/ncdai2_test","binary_dir":str(binaries),"data_dir":str(data),"package_version":PACKAGE_VERSION,"package_sha512":PACKAGE_SHA512}
        settings_path.write_text(json.dumps(settings,indent=2)+"\n")
    password=settings["NCDAI_CASE_DATABASE_URL"].split("://",1)[1].split(":",1)[1].split("@",1)[0]
    import os
    env={**os.environ,"PGPASSWORD":password}
    def run(name,args,check=True):
        # A background PostgreSQL child may retain inherited pipe handles on
        # Windows. pg_ctl output goes to DEVNULL; server output has its own log.
        capture = name != "pg_ctl"
        proc=subprocess.run([str(binaries/(name+".exe")),*args],env=env,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.PIPE if capture else subprocess.DEVNULL,text=True,timeout=90,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if check and proc.returncode:
            # Database tooling could echo connection arguments; do not log output.
            raise RuntimeError(f"{name} failed, code {proc.returncode}; credentials suppressed")
        return proc
    if not (data/"PG_VERSION").exists():
        pwfile=RUNTIME/"postgres-init-password"
        pwfile.write_text(password)
        try:
            run("initdb",["-D",str(data),"-U","ncdai_test","--pwfile",str(pwfile),"--auth=scram-sha-256","--encoding=UTF8","--locale=C"])
        finally:
            pwfile.unlink(missing_ok=True)
        with (data/"postgresql.conf").open("a") as config:
            config.write("\n# Dedicated synthetic NCDAI verification instance\nlisten_addresses='127.0.0.1'\nport=15432\n")
    if run("pg_ctl",["status","-D",str(data)],check=False).returncode:
        run("pg_ctl",["start","-D",str(data),"-w","-t","30","-l",str(RUNTIME/"postgres-server.log")])
    import psycopg
    with psycopg.connect(host="127.0.0.1",port=15432,user="ncdai_test",password=password,dbname="postgres",autocommit=True,connect_timeout=10) as connection:
        exists=connection.execute("SELECT 1 FROM pg_database WHERE datname='ncdai2_test'").fetchone()
        if not exists:
            connection.execute("CREATE DATABASE ncdai2_test")
    print("Dedicated synthetic PostgreSQL ready on loopback port 15432; credentials stored only in ignored .runtime/postgres-test.json")


if __name__=="__main__":
    setup()
