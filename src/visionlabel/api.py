import json
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool

from .contracts import (
    ClaimRequest,
    ImportRequest,
    Login,
    MemberRemove,
    MemberUpdate,
    ProjectCreate,
    Save,
    UserCreate,
    UserUpdate,
)
from .database import SCHEMA_REVISION, row, rows
from .domain import Problem, digest, uid
from .imaging import IMAGE_EXTENSIONS
from .service import Service, decode_cursor, encode_cursor, now


def create_app(root: Path):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = Service(root)
        yield
        app.state.service.close()

    # Default Swagger/ReDoc pages fetch external CDN assets; keep runtime offline.
    app = FastAPI(title="DataTracking", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    login_attempts: dict[str, deque] = defaultdict(deque)
    throttle_lock = threading.Lock()

    def service(request: Request) -> Service:
        return request.app.state.service

    def user(request: Request, srv=Depends(service)):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            raise Problem("AUTH_REQUIRED", "Sign in to continue.", 401)
        return srv.authenticate(auth[7:])

    def claim_headers(request):
        headers = {
            "id": request.headers.get("x-claim-id"),
            "token": request.headers.get("x-claim-token", ""),
            "generation": request.headers.get("x-claim-generation"),
        }
        if any(not value for value in headers.values()):
            raise Problem("VALIDATION_FAILED", "Claim ID, token and generation headers are required.")
        return headers

    def key(request):
        return request.headers.get("idempotency-key", "")

    @app.middleware("http")
    async def protocol(request: Request, call_next):
        request.state.request_id = uid()
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                size = int(request.headers.get("content-length", "0"))
            except ValueError:
                size = 6 * 1024 * 1024
            if size > 5 * 1024 * 1024:
                return JSONResponse(
                    {
                        "error": {
                            "code": "VALIDATION_FAILED",
                            "message": "Payload exceeds 5 MiB.",
                            "details": {},
                            "request_id": request.state.request_id,
                        }
                    },
                    status_code=413,
                )
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 5 * 1024 * 1024:
                    return JSONResponse(
                        {
                            "error": {
                                "code": "VALIDATION_FAILED",
                                "message": "Payload exceeds 5 MiB.",
                                "details": {},
                                "request_id": request.state.request_id,
                            }
                        },
                        status_code=413,
                    )
            request._body = bytes(data)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-API-Version"] = "1"
        response.headers["X-Schema-Version"] = "1.0.0"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Problem)
    async def problem(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request.state.request_id,
                }
            },
            status_code=exc.status,
            headers={"Retry-After": "60"} if exc.status == 429 else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        details = [{"path": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
        return await problem(
            request, Problem("VALIDATION_FAILED", "Request validation failed.", fields=details)
        )

    @app.exception_handler(OperationalError)
    async def database_error(request, exc):
        return await problem(
            request,
            Problem("DATABASE_BUSY", "Database is unavailable. Retry with the same request key.", 503),
        )

    @app.exception_handler(OSError)
    async def filesystem_error(request, exc):
        return await problem(
            request,
            Problem("STORAGE_UNAVAILABLE", "Storage is unavailable. Your draft has not been discarded.", 503),
        )

    @app.get("/api/v1/health/live")
    def live():
        return {"status": "ok"}

    @app.post("/api/v1/auth/login")
    def login(body: Login, request: Request, srv=Depends(service)):
        host = request.client.host if request.client else "unknown"
        with throttle_lock:
            queue = login_attempts[host]
            while queue and queue[0] < time.monotonic() - 60:
                queue.popleft()
            if len(queue) >= 10:
                raise Problem("RATE_LIMITED", "Too many login attempts. Wait one minute.", 429)
            queue.append(time.monotonic())
        return srv.login(body.username, body.password)

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(request: Request, who=Depends(user), srv=Depends(service)):
        with srv.db.transaction() as conn:
            conn.exec_driver_sql(
                "UPDATE auth_tokens SET revoked_at=? WHERE token_hash=?",
                (now(), digest(request.headers["authorization"][7:].encode())),
            )
            conn.exec_driver_sql(
                "UPDATE task_claims SET expires_at=?,generation=generation+1 WHERE owner_id=?",
                (now(), who["id"]),
            )

    @app.get("/api/v1/me")
    def me(who=Depends(user), srv=Depends(service)):
        with srv.db.engine.connect() as conn:
            result = srv.public_user(srv.principal(conn, who))
            result["project_roles"] = rows(
                conn,
                "SELECT project_id,role FROM project_members WHERE user_id=? ORDER BY project_id",
                (who["id"],),
            )
        return result

    @app.get("/api/v1/users")
    def users(
        limit: int = Query(100, ge=1, le=500),
        cursor: str | None = None,
        who=Depends(user),
        srv=Depends(service),
    ):
        stamp, ident = decode_cursor(cursor, "users")
        with srv.db.engine.connect() as conn:
            srv.administrator(conn, who)
            result = rows(
                conn,
                "SELECT * FROM users WHERE (created_at,id)>(?,?) ORDER BY created_at,id LIMIT ?",
                (stamp, ident, limit + 1),
            )
        page = result[:limit]
        return {
            "items": [srv.public_user(item) for item in page],
            "next_cursor": encode_cursor(page[-1]["created_at"], page[-1]["id"], "users")
            if len(result) > limit
            else None,
        }

    @app.post("/api/v1/users", status_code=201)
    def new_user(body: UserCreate, request: Request, who=Depends(user), srv=Depends(service)):
        return srv.create_user(who, body.model_dump(), key(request), request.state.request_id)

    @app.patch("/api/v1/users/{user_id}")
    def update_user(
        user_id: UUID, body: UserUpdate, request: Request, who=Depends(user), srv=Depends(service)
    ):
        return srv.update_user(who, str(user_id), body.model_dump(), key(request), request.state.request_id)

    @app.get("/api/v1/projects/{project_id}/members")
    def members(project_id: UUID, who=Depends(user), srv=Depends(service)):
        with srv.db.engine.connect() as conn:
            # SQLite needs an explicit read transaction to bind this list to its revision.
            conn.exec_driver_sql("BEGIN")
            proj = srv.authorize(conn, who, str(project_id))
            result = rows(
                conn,
                "SELECT u.id,u.username,u.display_name,u.disabled,m.role FROM project_members m JOIN users u ON u.id=m.user_id WHERE m.project_id=? ORDER BY u.username,u.id",
                (str(project_id),),
            )
        return {"items": result, "project_revision": proj["project_revision"]}

    @app.put("/api/v1/projects/{project_id}/members/{user_id}")
    def put_member(
        project_id: UUID,
        user_id: UUID,
        body: MemberUpdate,
        request: Request,
        who=Depends(user),
        srv=Depends(service),
    ):
        return srv.change_member(
            who, str(project_id), str(user_id), body.model_dump(), key(request), request.state.request_id
        )

    @app.delete("/api/v1/projects/{project_id}/members/{user_id}", status_code=204)
    def delete_member(
        project_id: UUID,
        user_id: UUID,
        body: MemberRemove,
        request: Request,
        who=Depends(user),
        srv=Depends(service),
    ):
        srv.change_member(
            who,
            str(project_id),
            str(user_id),
            body.model_dump(),
            key(request),
            request.state.request_id,
            remove=True,
        )

    @app.get("/api/v1/health/ready")
    def ready(who=Depends(user), srv=Depends(service)):
        if not who["is_admin"]:
            raise Problem("FORBIDDEN", "Administrator permission is required.", 403)
        with srv.db.engine.connect() as conn:
            revision = row(conn, "SELECT version_num FROM alembic_version")
            if not revision or revision["version_num"] != SCHEMA_REVISION:
                raise Problem("SCHEMA_MISMATCH", "Database migration is required.", 503)
        if not srv.blobs.root.is_dir():
            raise Problem("STORAGE_UNAVAILABLE", "Managed storage is unavailable.", 503)
        return {"status": "ready", "schema_version": SCHEMA_REVISION}

    @app.get("/api/v1/projects")
    def projects(
        limit: int = Query(100, ge=1, le=500),
        cursor: str | None = None,
        who=Depends(user),
        srv=Depends(service),
    ):
        stamp, ident = decode_cursor(cursor, "projects")
        with srv.db.engine.connect() as conn:
            result = rows(
                conn,
                "SELECT DISTINCT p.* FROM projects p LEFT JOIN project_members m ON m.project_id=p.id AND m.user_id=? WHERE (?=1 OR m.user_id IS NOT NULL) AND (p.created_at,p.id)>(?,?) ORDER BY p.created_at,p.id LIMIT ?",
                (who["id"], who["is_admin"], stamp, ident, limit + 1),
            )
        items = result[:limit]
        return {
            "items": items,
            "next_cursor": encode_cursor(items[-1]["created_at"], items[-1]["id"], "projects")
            if len(result) > limit
            else None,
        }

    @app.post("/api/v1/projects", status_code=201)
    def new_project(body: ProjectCreate, request: Request, who=Depends(user), srv=Depends(service)):
        return srv.create_project(who, body.model_dump(mode="json"), key(request), request.state.request_id)

    @app.get("/api/v1/projects/{project_id}")
    def project(project_id: UUID, who=Depends(user), srv=Depends(service)):
        return srv.project(who, str(project_id))

    @app.get("/api/v1/projects/{project_id}/images")
    def images(
        project_id: UUID,
        limit: int = Query(100, ge=1, le=500),
        cursor: str | None = None,
        search: str = "",
        status: str = "",
        who=Depends(user),
        srv=Depends(service),
    ):
        pid = str(project_id)
        scope = f"images/{pid}/{search}/{status}"
        stamp, ident = decode_cursor(cursor, scope)
        with srv.db.engine.connect() as conn:
            srv.authorize(conn, who, pid)
            result = rows(
                conn,
                "SELECT i.*,a.width,a.height,h.current_revision,h.state_revision,h.status FROM images i JOIN assets a ON a.sha256=i.asset_sha256 JOIN annotation_heads h ON h.image_id=i.id WHERE i.project_id=? AND i.archived=0 AND instr(lower(i.display_filename),lower(?))>0 AND (?='' OR h.status=?) AND (i.created_at,i.id)>(?,?) ORDER BY i.created_at,i.id LIMIT ?",
                (pid, search, status, status, stamp, ident, limit + 1),
            )
        items = result[:limit]
        return {
            "items": items,
            "next_cursor": encode_cursor(items[-1]["created_at"], items[-1]["id"], scope)
            if len(result) > limit
            else None,
        }

    @app.get("/api/v1/projects/{project_id}/import-sources")
    def sources(project_id: UUID, who=Depends(user), srv=Depends(service)):
        with srv.db.engine.connect() as conn:
            srv.maintain(conn, who, str(project_id))
        paths = []
        for path in srv.inbox.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                paths.append(path.relative_to(srv.inbox).as_posix())
                if len(paths) > 50000:
                    raise Problem("TOO_MANY_FILES", "Import inbox exceeds 50,000 files.")
        return {"source_alias": "inbox", "relative_paths": sorted(paths)}

    @app.get("/api/v1/projects/{project_id}/statistics")
    def statistics(project_id: UUID, who=Depends(user), srv=Depends(service)):
        return srv.statistics(who, str(project_id))

    @app.post("/api/v1/projects/{project_id}/imports", status_code=202)
    def imports(
        project_id: UUID, body: ImportRequest, request: Request, who=Depends(user), srv=Depends(service)
    ):
        return srv.import_images(
            who, str(project_id), body.model_dump(), key(request), request.state.request_id
        )

    @app.get("/api/v1/jobs/{job_id}")
    def job(job_id: UUID, who=Depends(user), srv=Depends(service)):
        with srv.db.engine.connect() as conn:
            job = row(conn, "SELECT * FROM jobs WHERE id=?", (str(job_id),))
            if not job:
                raise Problem("NOT_FOUND", "Job not found.", 404)
            srv.authorize(conn, who, job["project_id"])
        return {
            "id": job["id"],
            "type": job["type"],
            "state": job["state"],
            "progress": {"done": job["progress_done"], "total": job["progress_total"]},
            "result": json.loads(job["result_json"]) if job["result_json"] else None,
            "error": json.loads(job["error_json"]) if job["error_json"] else None,
        }

    @app.get("/api/v1/images/{image_id}")
    def image_info(image_id: UUID, who=Depends(user), srv=Depends(service)):
        with srv.db.engine.connect() as conn:
            image = srv.image(conn, who, str(image_id))
        image.pop("blob_path")
        return image

    @app.get("/api/v1/images/{image_id}/content")
    def content(image_id: UUID, request: Request, who=Depends(user), srv=Depends(service)):
        with srv.db.engine.connect() as conn:
            image = srv.image(conn, who, str(image_id))
        data = srv.blobs.read(image["blob_path"], image["asset_sha256"])
        etag = '"' + image["asset_sha256"] + '"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return Response(data, media_type=image["media_type"], headers={"ETag": etag})

    @app.get("/api/v1/images/{image_id}/annotation")
    def annotation(image_id: UUID, who=Depends(user), srv=Depends(service)):
        return srv.annotation(who, str(image_id))

    @app.put("/api/v1/images/{image_id}/annotation")
    async def save(image_id: UUID, body: Save, request: Request, who=Depends(user), srv=Depends(service)):
        # Preserve decimal text around half-even boundaries before canonical rounding.
        raw = json.loads(await request.body(), parse_float=Decimal)
        payload = body.model_dump(mode="json")
        payload["content"]["shapes"] = raw["content"].get("shapes", [])
        return await run_in_threadpool(
            srv.save,
            who,
            str(image_id),
            payload,
            claim_headers(request),
            key(request),
            request.state.request_id,
        )

    @app.post("/api/v1/images/{image_id}/claim", status_code=201)
    def claim(image_id: UUID, body: ClaimRequest, request: Request, who=Depends(user), srv=Depends(service)):
        return srv.claim(
            who, str(image_id), body.model_dump(mode="json"), key(request), request.state.request_id
        )

    @app.post("/api/v1/images/{image_id}/claim/heartbeat")
    def heartbeat(image_id: UUID, request: Request, who=Depends(user), srv=Depends(service)):
        return srv.heartbeat(who, str(image_id), claim_headers(request))

    @app.delete("/api/v1/images/{image_id}/claim", status_code=204)
    def release(image_id: UUID, request: Request, who=Depends(user), srv=Depends(service)):
        srv.release(who, str(image_id), claim_headers(request), request.state.request_id)

    @app.get("/api/v1/images/{image_id}/revisions/{revision}")
    def revision(image_id: UUID, revision: int, who=Depends(user), srv=Depends(service)):
        with srv.db.engine.connect() as conn:
            srv.image(conn, who, str(image_id))
            record = row(
                conn,
                "SELECT * FROM annotation_revisions WHERE image_id=? AND revision=?",
                (str(image_id), revision),
            )
        if not record:
            raise Problem("NOT_FOUND", "Revision not found.", 404)
        return {
            "annotation": srv.blobs.json(record["blob_path"], record["sha256"]),
            "annotation_sha256": record["sha256"],
        }

    return app
