"""Run the local service and desktop together; stop the owned service on exit."""

import argparse
import getpass
import threading
import time
from pathlib import Path

import uvicorn

from .api import create_app
from .cli import default_root
from .desktop import Desktop
from .domain import Problem
from .service import Service


def main():
    parser = argparse.ArgumentParser(description="Start the local VisionLabel workspace")
    parser.add_argument("--root", type=Path, default=default_root())
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        service = Service(args.root)
    except Problem as exc:
        parser.exit(1, exc.message + "\n")
    try:
        with service.db.engine.connect() as connection:
            initialized = bool(connection.exec_driver_sql("SELECT COUNT(*) FROM users").scalar())
        if not initialized:
            print("First launch: create the local administrator account (username: admin).")
            password = getpass.getpass("Password (at least 12 characters): ")
            if password != getpass.getpass("Confirm password: "):
                parser.exit(1, "Passwords do not match.\n")
            service.bootstrap("admin", password)
    except Problem as exc:
        parser.exit(1, exc.message + "\n")
    finally:
        service.close()
    print(f"Import inbox: {args.root / 'inbox'}")
    server = uvicorn.Server(
        uvicorn.Config(create_app(args.root), host="127.0.0.1", port=args.port, workers=1, access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True, name="datatracking")
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            server.should_exit = True
            thread.join(5)
            parser.exit(1, "Could not start the local service. Check whether another instance is running.\n")
        time.sleep(0.05)
    try:
        Desktop(f"http://127.0.0.1:{args.port}").run()
    finally:
        server.should_exit = True
        thread.join(30)
        if thread.is_alive():
            print("Waiting for the current import to reach a safe checkpoint...")
            thread.join()


if __name__ == "__main__":
    main()
