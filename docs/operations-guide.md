# VisionLabel local operations guide

This build is a local development pilot. It binds to 127.0.0.1 and the desktop
currently accepts loopback HTTP only. It is not the production LAN/HTTPS release.
Do not expose its port through forwarding or a public interface. All application
text is English; filenames, project/class names and paths can contain Unicode.

## Offline installation kit

For a source checkout with package-index access, use Python 3.12.10's bundled pip:
create `.venv` once with `python -m venv .venv` (after verifying that `python` is
3.12.10 x64), then run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
from the repository root. Start with `.\.venv\Scripts\python.exe -m visionlabel.launcher`.
No uv installation is required on the destination PC. See [README](../README.md#start-locally).

The kit below is an alternative for a destination without package-index access.
Building a kit currently requires uv on the provisioning PC; installing a completed
kit on the destination requires only the specified Python and its bundled pip.

Provision on the development PC (downloads occur only during this step):

```powershell
.\.venv\Scripts\python.exe scripts/build_offline_kit.py --output dist\offline-kit
```

The output must be new. The kit contains exact hashed runtime wheels, the app wheel,
locked requirements, Python/native notices and the existing license inventory/SBOM.
Its manifest marks `production_qualified=false`. The inventory includes development
dependencies; the kit's wheels list identifies the installed runtime subset. No
Python interpreter, fonts, compiler or Ultralytics/LabelMe runtime is bundled.
Tahoma is supplied by Windows. The kit is unsigned; obtain it through a trusted
channel. Its checksum manifest detects corruption, not malicious replacement of
both files and manifest. It cannot substitute for production provenance/signing.

On a Windows x64 machine with **Python 3.12.10 already installed**, copy the complete
kit and invoke that exact interpreter (replace the example Python path):

```powershell
& 'C:\Python312\python.exe' 'D:\Transfer\offline-kit\install.py' --verify-only
& 'C:\Python312\python.exe' 'D:\Transfer\offline-kit\install.py' --target 'D:\Apps\VisionLabel'
& 'D:\Apps\VisionLabel\Start-VisionLabel.ps1' -DataRoot 'D:\VisionLabelData'
```

Installation creates a new isolated `.venv`, uses pip with `--no-index`,
`--require-hashes`, and local wheels only; it refuses existing installation targets.
It does not modify the development repository environment or install globally.
If interrupted, the target is retained for inspection without a completion manifest;
retry a new target. No machine-wide execution-policy change is required by this kit;
follow your company's script policy. Production Nuitka/installer work remains open.

First launch creates the administrator interactively. Keep passwords out of command
arguments and scripts. DataRoot holds the service database, managed assets and inbox;
keep it on a local fixed disk, outside Git, OneDrive and network shares. The inbox is
an import source: importing into a selected project copies verified immutable image
bytes into managed storage. A project does not continuously watch the inbox.

## Backup, verification and restore

Close the launcher/desktop and wait for its owned server to stop. Backup is offline:
the maintenance lock refuses a live service rather than copying its live main SQLite
file. Use the app installation's `.venv\Scripts\python.exe`, or the existing repo
`.venv\Scripts\python.exe` for a source checkout.

```powershell
.\.venv\Scripts\python.exe -m visionlabel.cli backup --root D:\VisionLabelData --destination D:\Backups\VisionLabel-20261004
.\.venv\Scripts\python.exe -m visionlabel.cli verify-backup --backup-set D:\Backups\VisionLabel-20261004
.\.venv\Scripts\python.exe -m visionlabel.cli restore --backup-set D:\Backups\VisionLabel-20261004 --destination D:\VisionLabelRestored
```

Backup and restore require **new local destination directories**. They prepare data
on the destination volume, verify SQLite integrity/foreign keys and referenced blob
hashes, then rename the complete directory into place. Ordinary failures leave no
published destination. Process termination can leave `.visionlabel-backup-*` or
`.visionlabel-restore-*` staging folders; these are not complete backups/restores.
Never use them automatically. No automatic retention/delete policy is installed.
Do not modify backup sources during verification or restore. Copy a completed backup
to protected secondary storage and verify that copy before depending on it.

The current backup covers users/projects/members, image assets, schemas and annotation
history in the implemented DB schema. It excludes inbox originals, desktop DPAPI
cache/recovery drafts and service secrets. Password hashes and audit/user metadata
are sensitive and **are included in the database**: protect backups with filesystem
ACLs and your organization's encrypted storage policy. `secrets_included=false`
means separate service-secret material is excluded, not that the database is public.
Released-version/split/export tables do not exist yet; their backup coverage must be
added when those features are implemented.

Restore verifies both source and copied bytes. It expires claims, revokes login
tokens and fails interrupted jobs. Sign in again; unsaved local drafts are not a
server backup. Start the restored directory explicitly, inspect expected projects
and annotations, then retain the previous server until the operator accepts recovery.
Never overwrite the old directory or copy a live database over it.

For scheduled maintenance, choose an agreed offline window, close the application,
run backup to a timestamped new folder, verify, and only then copy to secondary
storage. Task Scheduler automation must report a nonzero exit (including service
still running) and must not kill the process or silently skip verification. A managed
Windows service and online backup scheduler are not implemented in this build.

## Company acceptance and HTTPS deployment plan

Before company use: complete revision-bound review, approved releases, split/export
integration and migration transactions; these are code gaps, not environment tests.
The production client needs HTTPS and internal CA trust configuration, SAN/hostname
validation without `verify=False`, server-side membership enforcement, local service
account ACLs, firewall rules limited to the company subnet, and certificate rotation.
Service identity, hostname, port and CA issuance must be chosen in the company
environment. This guide does not install a reverse proxy or turn on unsupported LAN
mode. Never put the SQLite DB on SMB; any future SMB source is read-only ingestion.

Then verify on two PCs: user journeys, stale save/reconnect/revocation, Unicode/DPI,
restore on a fresh PC, blocked external egress, certificate failure/rotation, and
10-client performance. Local wheel/backup tests are not evidence of these gates.
