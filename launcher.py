#!/usr/bin/env python3
"""
Custom Minecraft Launcher - FINAL WORKING VERSION
"""
import json, hashlib, requests, subprocess, os, zipfile, sys, uuid, shutil, glob
from pathlib import Path

# ABSOLUTE PATH TO launcher_data
LAUNCHER_DIR = Path(__file__).parent / "launcher_data"
LAUNCHER_DIR.mkdir(exist_ok=True)

JAVA_EXE = "jdk-21/bin/java.exe"
if not JAVA_EXE:
    raise RuntimeError("Java 21 not found! Download: https://adoptium.net/")

MAX_RAM = "2G"
VERSION_ID = "1.21"
USERNAME = "Player"

def sha1_hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def download_file(url: str, path: Path, sha1: str = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and sha1 and sha1_hash(path).lower() == sha1.lower():
        return
    print(f"Downloading {path.name}...")
    r = requests.get(url, stream=True, timeout=30)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    if sha1 and sha1_hash(path).lower() != sha1.lower():
        path.unlink()
        raise ValueError("SHA1 mismatch")

def get_version_manifest():
    return requests.get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json").json()

def select_version(manifest, vid):
    for v in manifest["versions"]:
        if v["id"] == vid: return v
    raise ValueError(f"Version {vid} not found")

def download_version_json(vinfo):
    p = LAUNCHER_DIR / "versions" / f"{vinfo['id']}.json"
    if not p.exists():
        download_file(vinfo["url"], p)
    return json.load(p.open())

def download_client(vjson):
    c = vjson["downloads"]["client"]
    p = LAUNCHER_DIR / "versions" / f"{vjson['id']}.jar"
    download_file(c["url"], p, c["sha1"])
    return p

def download_libraries(vjson):
    libs_dir = LAUNCHER_DIR / "libraries"
    natives_dir = LAUNCHER_DIR / "natives" / vjson["id"]
    natives_dir.mkdir(parents=True, exist_ok=True)
    cp = []
    for lib in vjson["libraries"]:
        if "downloads" not in lib: continue
        a = lib["downloads"].get("artifact")
        if a:
            p = libs_dir / a["path"]
            download_file(a["url"], p, a["sha1"])
            if not any(r.get("action")=="disallow" for r in lib.get("rules",[])):
                cp.append(str(p))
        cls = lib["downloads"].get("classifiers", {})
        key = {"windows":"natives-windows","darwin":"natives-osx","linux":"natives-linux"}.get(sys.platform)
        if key and key in cls:
            n = cls[key]
            np = libs_dir / n["path"]
            download_file(n["url"], np, n["sha1"])
            with zipfile.ZipFile(np) as z:
                z.extractall(natives_dir)
    return cp, str(natives_dir)

def download_assets(vjson):
    ai = vjson["assetIndex"]
    ip = LAUNCHER_DIR / "assets" / "indexes" / f"{ai['id']}.json"
    download_file(ai["url"], ip, ai["sha1"])
    idx = json.load(ip.open())
    odir = LAUNCHER_DIR / "assets" / "objects"
    for h in idx["objects"].values():
        sub = h["hash"][:2]
        url = f"https://resources.download.minecraft.net/{sub}/{h['hash']}"
        p = odir / sub / h["hash"]
        download_file(url, p, h["hash"])

def launch(client_jar, cp, ndir, token, uuid_, user, vid, vjson):
    gdir = LAUNCHER_DIR / "game"; gdir.mkdir(exist_ok=True)
    mc = vjson.get("mainClass", "net.minecraft.client.main.Main")
    full_cp = os.pathsep.join(cp + [str(client_jar)])

    argfile = LAUNCHER_DIR / "launch_args.txt"
    with open(argfile, "w", encoding="utf-8") as f:
        f.write(f"-Xmx{MAX_RAM}\n")
        f.write("-XX:+UnlockExperimentalVMOptions\n")
        f.write("-XX:+UseG1GC\n")
        f.write(f"-Djava.library.path={ndir}\n")
        f.write(f"-cp\n{full_cp}\n")
        f.write(f"{mc}\n")
        f.write(f"--username\n{user}\n")
        f.write(f"--version\n{vid}\n")
        f.write(f"--gameDir\n{str(gdir)}\n")
        f.write(f"--assetsDir\n{str(LAUNCHER_DIR/'assets')}\n")
        f.write(f"--assetIndex\n{vjson['assetIndex']['id']}\n")
        f.write(f"--accessToken\n{token}\n")
        f.write(f"--uuid\n{uuid_}\n")
        f.write(f"--userType\nlegacy\n")

    abs_argfile = str(argfile.resolve())
    print(f"\nLaunching Minecraft...")
    print(f"Argfile: {abs_argfile}")
    print(f"Command: \"{JAVA_EXE}\" \"@{abs_argfile}\"")

    # FINAL: shell=True + quoted command
    subprocess.run(f'"{JAVA_EXE}" "@{abs_argfile}"', cwd=str(LAUNCHER_DIR.parent), shell=True)

def main():
    global VERSION_ID, USERNAME
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=VERSION_ID)
    parser.add_argument("--username", default=USERNAME)
    args = parser.parse_args()
    VERSION_ID = args.version
    USERNAME = args.username

    # SET CWD EARLY
    os.chdir(LAUNCHER_DIR.parent)

    manifest = get_version_manifest()
    vinfo = select_version(manifest, VERSION_ID)
    vjson = download_version_json(vinfo)
    client = download_client(vjson)
    cp, ndir = download_libraries(vjson)
    download_assets(vjson)
    token = "0"
    uuid_ = str(uuid.uuid4())
    launch(client, cp, ndir, token, uuid_, USERNAME, VERSION_ID, vjson)

if __name__ == "__main__":
    main()