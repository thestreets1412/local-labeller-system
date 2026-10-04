import argparse
import getpass
import os
from pathlib import Path

from .domain import Problem


def default_root():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DataTracking"


def main():
    parser = argparse.ArgumentParser(description="DataTracking local development service")
    parser.add_argument("command", choices=["init", "serve", "samples", "backup", "restore", "verify-backup"])
    parser.add_argument("--root", type=Path, default=default_root())
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--backup-set", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn

            from .api import create_app

            uvicorn.run(create_app(args.root), host="127.0.0.1", port=args.port, workers=1, access_log=False)
        elif args.command == "samples":
            from .fixtures import create_samples

            create_samples(args.root / "inbox", args.count)
            print(f"Synthetic images ready in {args.root / 'inbox'}")
        elif args.command in ("backup", "restore", "verify-backup"):
            from .operations import backup, restore, verify_backup

            if args.command != "verify-backup" and not args.destination:
                parser.error("--destination is required.")
            if args.command == "backup":
                result = backup(args.root, args.destination)
            else:
                if not args.backup_set:
                    parser.error("--backup-set is required.")
                result = (
                    verify_backup(args.backup_set)
                    if args.command == "verify-backup"
                    else restore(args.backup_set, args.destination)
                )
            print(f"Verified {len(result['files'])} immutable files.")
        else:
            from .service import Service

            password = getpass.getpass("Administrator password (at least 12 characters): ")
            if password != getpass.getpass("Confirm password: "):
                parser.error("Passwords do not match.")
            service = Service(args.root)
            try:
                service.bootstrap(args.username, password)
            finally:
                service.close()
            print(f"Initialized local service. Import inbox: {args.root / 'inbox'}")
    except Problem as exc:
        parser.exit(1, f"{exc.code}: {exc.message}\n")
    except OSError as exc:
        parser.exit(1, f"IO_ERROR: {exc}\n")


if __name__ == "__main__":
    main()
