"""Admin root-only storage endpoints; no endpoint accepts an external path."""

import json
from uuid import UUID

from fastapi import Depends, Query, Request
from pydantic import Field, StrictBool
from starlette.responses import StreamingResponse

from .contracts import StrictModel
from .database import row
from .domain import Problem, canonical, uid
from .storage_inventory import scan_storage


class Selection(StrictModel):
    artifact_ids: list[UUID] = Field(max_length=500)


class ReportRequest(StrictModel):
    pass


class Apply(StrictModel):
    token: UUID


class Pin(StrictModel):
    pinned: StrictBool


class Policy(StrictModel):
    expected_generation: int = Field(ge=1, strict=True)
    max_bytes: int = Field(ge=1024**2, le=1024**5, strict=True)
    max_age_days: int = Field(ge=1, le=3650, strict=True)
    automatic_enabled: StrictBool
    preview_token: UUID | None = None


class ProtectedDownload(StreamingResponse):
    """Release the lease even if ASGI streaming is cancelled or send raises."""

    def __init__(self, manager, actor, job_id):
        self.lease = manager.download(actor, job_id)
        stream = self.lease.__enter__()

        def chunks():
            while data := stream.read(1024**2):
                yield data

        try:
            super().__init__(
                chunks(),
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="dataset-{job_id}.zip"'},
            )
        except BaseException:
            self.lease.__exit__(None, None, None)
            raise

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.lease.__exit__(None, None, None)


def install_storage_routes(app, user, service):
    @app.get("/api/v1/storage/usage")
    def usage(
        deep: bool = False,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        who=Depends(user),
        srv=Depends(service),
    ):
        srv.export_cache.admin(who)
        result = scan_storage(srv.root, deep=deep, boundary=srv.export_cache.boundary)
        result["asset_count"] = len(result["assets"])
        result["assets"] = result["assets"][offset : offset + limit]
        return result

    @app.post("/api/v1/storage/reports")
    def report(body: ReportRequest, deep: bool = True, who=Depends(user), srv=Depends(service)):
        srv.export_cache.admin(who)
        boundary = srv.export_cache.boundary
        result = scan_storage(srv.root, deep=deep, boundary=boundary)
        # No filenames/class content leave the service in the default report.
        for asset in result["assets"]:
            asset.pop("path", None)
        ident = uid()
        relative = f"reports/storage/{ident}.json"
        boundary.mkdir("reports/storage")
        with boundary.open_new(relative) as stream:
            stream.write(canonical(result))
        return {"id": ident, "relative_path": relative, "root": str(boundary.root)}

    @app.get("/api/v1/storage/reports/{report_id}")
    def read_report(report_id: UUID, who=Depends(user), srv=Depends(service)):
        srv.export_cache.admin(who)
        with srv.export_cache.boundary.open_read(f"reports/storage/{report_id}.json") as stream:
            return json.load(stream)

    @app.get("/api/v1/storage/export-cache")
    def listing(
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        who=Depends(user),
        srv=Depends(service),
    ):
        cache = srv.export_cache
        cache.admin(who)
        with cache.lock:
            items = cache.artifacts()
            return {
                "root": str(cache.boundary.root),
                "root_identity": cache.boundary.identity,
                "policy": cache.policy(),
                "items": items[offset : offset + limit],
                "count": len(items),
                "last_error": cache.last_error,
                "cached_bytes": sum(
                    a["bytes"] for a in cache.accounted_artifacts() if a["state"] != "EVICTED"
                ),
            }

    @app.post("/api/v1/storage/export-cache/adopt")
    def adopt(who=Depends(user), srv=Depends(service)):
        return srv.export_cache.adopt(who)

    @app.post("/api/v1/storage/export-cache/preview")
    def preview(body: Selection, who=Depends(user), srv=Depends(service)):
        return srv.export_cache.preview(who, [str(x) for x in body.artifact_ids])

    @app.post("/api/v1/storage/export-cache/apply")
    def apply(body: Apply, request: Request, who=Depends(user), srv=Depends(service)):
        return srv.export_cache.apply(who, str(body.token), request.headers.get("idempotency-key", ""))

    @app.patch("/api/v1/storage/export-cache/{artifact_id}")
    def pin(artifact_id: UUID, body: Pin, who=Depends(user), srv=Depends(service)):
        return srv.export_cache.pin(who, str(artifact_id), body.pinned)

    @app.patch("/api/v1/storage/policy")
    def policy(body: Policy, who=Depends(user), srv=Depends(service)):
        return srv.export_cache.update_policy(who, body.model_dump(mode="json"))

    @app.post("/api/v1/storage/policy/preview")
    def preview_policy(body: Policy, who=Depends(user), srv=Depends(service)):
        return srv.export_cache.preview_policy(who, body.model_dump(mode="json"))

    @app.post("/api/v1/working-exports/{job_id}/reprepare", status_code=202)
    def reprepare(job_id: UUID, request: Request, who=Depends(user), srv=Depends(service)):
        from .service import now
        from .working_export import FORMAT_VERSION, run_export

        key = request.headers.get("idempotency-key", "")
        with srv.db.transaction() as conn:
            source = row(
                conn,
                "SELECT * FROM jobs WHERE id=? AND type='working-export' AND state='succeeded'",
                (str(job_id),),
            )
            if not source:
                raise Problem(
                    "NOT_FOUND", "Saved export snapshot not found. Select a checkpoint instead.", 404
                )
            srv.maintain(conn, who, source["project_id"])
            route = f"reprepare/{job_id}"
            replay = srv.replay(conn, who, route, key, {})
            if replay:
                return replay
            snapshot = json.loads(source["payload_json"])
            # Lineage belongs to the audit/response, not frozen dataset identity.
            snapshot.pop("source_job_id", None)
            snapshot["format_version"] = FORMAT_VERSION
            ident = uid()
            conn.exec_driver_sql(
                "INSERT INTO jobs (id,project_id,created_by,type,state,payload_json,progress_total,created_at,updated_at) VALUES (?,?,?,'working-export','queued',?,?,?,?)",
                (
                    ident,
                    source["project_id"],
                    who["id"],
                    canonical(snapshot).decode(),
                    len(snapshot["records"]),
                    now(),
                    now(),
                ),
            )
            result = {"job_id": ident, "source_job_id": str(job_id), "format_version": FORMAT_VERSION}
            srv.remember(conn, who, route, key, {}, result, 202)
            srv.audit(
                conn,
                who,
                "working_export.reprepared",
                ident,
                source["project_id"],
                result,
                request.state.request_id,
            )
        srv.pool.submit(run_export, srv, who, ident, snapshot, request.state.request_id)
        return result
