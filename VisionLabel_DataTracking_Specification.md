# VisionLabel + DataTracking — Product & Engineering Specification

**Spec version:** 1.0.7
**วันที่:** 3 ตุลาคม 2026 (Asia/Bangkok)  
**ภาษาเอกสาร:** ไทย; identifiers, API และ schema ใช้ภาษาอังกฤษ  
**ภาษาซอฟต์แวร์:** English-only สำหรับข้อความที่ระบบสร้างใน UI, menus, tooltips, dialogs, validation/error messages และ installer; v1 ไม่มี Thai localization หรือ language switcher ข้อมูลที่ผู้ใช้ตั้งเองยังรองรับ Unicode
**สถานะ:** Implementation baseline สำหรับสร้าง repository และพัฒนาทีละ phase  
**เจ้าของระบบ:** ทีม Computer Vision ภายในองค์กร ขนาดเริ่มต้น 2–10 คน

**สารบัญ**

1. [วัตถุประสงค์และวิธีใช้เอกสาร](#section-1)
2. [Architectural decisions ที่ห้ามเปลี่ยนโดยปริยาย](#section-2)
3. [Stack และนโยบาย license](#section-3)
4. [Product requirements](#section-4)
5. [Architecture และ data ownership](#section-5)
6. [Domain model และ workflow](#section-6)
7. [Desktop UX specification](#section-7)
8. [Directory structure](#section-8)
9. [Database schema](#section-9)
10. [Internal annotation JSON schema](#section-10)
11. [API contract](#section-11)
12. [Concurrency, atomicity และ recovery rules](#section-12)
13. [Versioning rules](#section-13)
14. [Dataset splitting](#section-14)
15. [Import/export contract](#section-15)
16. [Security, operations และ backup](#section-16)
17. [Phased implementation plan](#section-17)
18. [Tests และ verification plan](#section-18)
19. [Definition of Done](#section-19)
20. [Implementation checklist และข้อห้ามสำคัญ](#section-20)
21. [แหล่งอ้างอิงและขอบเขตการตรวจสอบ](#section-21)

<a id="section-1"></a>

## 1. วัตถุประสงค์และวิธีใช้เอกสาร

สร้าง **VisionLabel** desktop สำหรับ annotation และ **DataTracking** server สำหรับจัดการ dataset ร่วมกันผ่าน LAN โดยข้อมูลภาพลับไม่ออกจากองค์กร เป้าหมายคือทำ rectangle annotation ได้คล่อง แบ่งงานและ review ได้ ตรวจสอบย้อนหลังได้ และส่งออกชุดข้อมูลที่ใช้ฝึกซ้ำได้อย่างน่าเชื่อถือ

เอกสารนี้เป็นข้อกำหนดสำหรับการพัฒนา ไม่ได้หมายความว่าระบบถูกสร้างหรือทดสอบแล้ว คำว่า **MUST/ต้อง** เป็นเงื่อนไขบังคับ, **SHOULD/ควร** เปลี่ยนได้เมื่อมีเหตุผลบันทึกใน ADR, **MAY/อาจ** เป็นส่วนเสริม ค่า default ในเอกสารเป็นการตัดสินใจเพื่อให้เริ่มพัฒนาได้ ไม่ต้องรอเลือก stack อีกครั้ง

ลำดับความสำคัญเมื่อรายละเอียดขัดกัน: data integrity และ confidentiality → normative invariants → API/schema → UX ตัวอย่าง ทุกการเปลี่ยน baseline ต้องมี ADR และ migration/compatibility plan

### 1.1 ผลลัพธ์ที่ต้องทำได้

1. Engineer สร้างโปรเจกต์ กำหนดคลาส และนำเข้าภาพจาก storage ภายใน
2. Engineer กับ Junior เปิด desktop คนละเครื่อง เลือกหรือรับงานอัตโนมัติ โดยไม่มีการเขียนทับงานกัน
3. Annotator วาด rectangle/polygon หรือให้ classification label พร้อม autosave, undo/redo และ recovery
4. Reviewer อนุมัติหรือส่งกลับแก้ไขพร้อมเหตุผล โดย approval ผูกกับ revision ที่ตรวจจริง
5. Maintainer สร้าง immutable dataset version, ดู diff, สร้าง group-aware/stratified split และ export YOLO/classification
6. ผู้ฝึกโมเดลบันทึก version ID, manifest SHA-256, split ID/hash และ export ID/hash ไว้กับ training run ในเครื่องมือที่ใช้อยู่ได้

### 1.2 ขอบเขตและสิ่งที่ยังไม่ทำ

| อยู่ใน v1 | นอกขอบเขต v1 |
|---|---|
| Windows desktop, Python + Dear PyGui | Web annotation, mobile app |
| FastAPI service เดียว, SQLite บน local disk ของ server | Microservices, Redis, Kafka, Celery, Kubernetes |
| Rectangle, simple polygon, single-label classification | Keypoint, rotated box, polygon holes, brush masks, video timeline |
| Generic JSON, YOLO detect/segment export, classification folders | Training, inference, auto-labeling, model serving |
| Claims, optimistic locking, review, audit | Real-time collaborative editing รูปเดียวกัน |
| Immutable versions, deterministic split, QC, backup | Git-like merge หลาย working branches, full offline synchronization |
| LabelMe rectangle/polygon import, YOLO detection import | Import executable plugins หรือ source code จากเครื่องมือเดิม |

Multi-label classification มีที่รองรับใน schema แต่ v1 ไม่เปิด workflow/export นี้; API ต้องปฏิเสธการตั้งค่าที่ไม่รองรับอย่างชัดเจน ไม่ยอมรับข้อมูลแล้วละทิ้งเงียบ ๆ

<a id="section-2"></a>

## 2. Architectural decisions ที่ห้ามเปลี่ยนโดยปริยาย

| ADR | ข้อกำหนด | เหตุผล |
|---|---|---|
| A01 | Python desktop ใช้ Dear PyGui | Desktop annotation และ permissive core |
| A02 | FastAPI เป็นผู้เขียนข้อมูล canonical เพียงรายเดียว | คุม validation, identity, leases, revisions, audit |
| A03 | SQLite อยู่ local disk ของ server เท่านั้น | ห้าม desktop หรือ SMB clients เปิด DB โดยตรง |
| A04 | Shared storage เก็บไฟล์; desktop มี read-only access | ใช้รูปและ JSON จาก shared folder ได้โดยไม่เกิด last-writer-wins |
| A05 | Internal JSON เป็น generic pixel-coordinate format | ไม่ผูก canonical data กับ YOLO |
| A06 | เขียน YOLO adapter เองจาก format contract | ไม่ import/bundle `ultralytics` ใน core |
| A07 | Raw image bytes และ released versions immutable | ฝึกซ้ำและเปรียบเทียบย้อนหลังได้ |
| A08 | Asset identity ใช้ SHA-256 ของ bytes | ตรวจ duplicate/rename และ corruption |
| A09 | Lease + optimistic revision check ใช้ร่วมกัน | Lease ไม่สามารถแทน stale-write protection |
| A10 | Published artifact อ้าง immutable content เท่านั้น | ไม่มี version ที่ชี้ไป working annotation ปัจจุบัน |
| A11 | Offline หมายถึงไม่พึ่ง internet; shared editing ต้องมี server | ตัดความซับซ้อน multi-master sync |
| A12 | ใช้ permissive dependencies เท่านั้นตามข้อ 3 | คงเงื่อนไข license ของผู้ใช้ |

SQLite เองระบุข้อจำกัดของการเปิด database ผ่าน network filesystem; แบบที่เลือกจึงให้ network clients คุยผ่าน API และ DB อยู่ฝั่ง server ([SQLite network guidance](https://www.sqlite.org/useovernet.html))

<a id="section-3"></a>

## 3. Stack และนโยบาย license

### 3.1 Stack baseline

| ส่วน | เลือกใช้ | นโยบาย |
|---|---|---|
| Runtime | Python 3.12 เป็น compatibility baseline | Pin patch version ที่ตรวจสอบแล้วตอนเริ่ม implementation |
| GUI | Dear PyGui | MIT; ตรวจ wheel และ bundled components ด้วย |
| Decode/geometry | OpenCV 4.5+ และ NumPy | ใช้ build ที่ตรวจ dependency/native codecs แล้ว |
| Client HTTP | HTTPX | เลือก release ภายใต้ BSD-3-Clause |
| API/validation | FastAPI + Pydantic | เลือก releases ภายใต้ MIT |
| Persistence | SQLAlchemy + Alembic + SQLite | SQLAlchemy/Alembic MIT; SQLite public domain |
| Serving | Uvicorn | BSD-3-Clause; ไม่เปิด multi-worker ใน v1 |
| Hash/JSON | Python `hashlib`, `json` | Stdlib |
| Packaging | Nuitka standard distribution | ตรวจ Apache-2.0 ของรุ่นที่ pin และ bundled runtime |
| Storage | Server local volume ที่ expose ผ่าน SMB | Windows/SMB เป็น deployment infrastructure |
| Tests | pytest และ stdlib test utilities | ตรวจ license ของ test dependencies ใน lockfile |

Dear PyGui ระบุ MIT ใน [LICENSE](https://github.com/hoffstadt/DearPyGui/blob/master/LICENSE) และ FastAPI ระบุ MIT ใน [LICENSE](https://github.com/fastapi/fastapi/blob/master/LICENSE) ข้อกำหนดอื่นในตารางเป็น dependency selection policy; ทีมต้องตรวจไฟล์ LICENSE ของ **exact versions** และ artifacts ที่จะกระจายอีกครั้ง ไม่ถือว่าชื่อ package เพียงอย่างเดียวผ่าน gate

### 3.2 ขอบเขต permissive-only ที่ชัดเจน

- Source ของโครงการใหม่เลือก **MIT** พร้อม copyright notice ของผู้พัฒนา
- Third-party application dependencies ต้องเป็น MIT, BSD-2-Clause, BSD-3-Clause หรือ Apache-2.0
- ข้อยกเว้นเฉพาะรายการที่ผู้ใช้อนุมัติวันที่ 3 ตุลาคม 2026: certifi (MPL-2.0), typing_extensions (PSF-2.0) และส่วนประกอบ NumPy (0BSD, Zlib, CC0-1.0); ต้องเก็บ license notices และบันทึก exact versions/artifacts ใน inventory ไม่ถือว่าอนุญาต license เหล่านี้ให้ dependency อื่นโดยอัตโนมัติ
- ผู้ใช้อนุมัติเพิ่มเติมวันเดียวกัน: FreeType ที่ bundle มากับ Dear PyGui ใช้ FreeType License (FTL) พร้อม attribution/notices; ไม่เลือก GPL alternative
- ข้อยกเว้นที่เป็นส่วนหนึ่งของ baseline: Python runtime ภายใต้ PSF license และ SQLite public domain เนื่องจากเป็น runtime/DB ที่ตกลงใช้แล้ว ไม่อ้างว่าสองรายการนี้เป็น MIT/BSD/Apache ([SQLite copyright](https://www.sqlite.org/copyright.html))
- ห้าม GPL/AGPL/LGPL dependency ใน distributed core; ห้ามคัดลอก implementation จากโครงการดังกล่าวมาทำ exporter/importer
- License expression แบบ OR เลือก permissive branch ได้ถ้ามีหลักฐาน; แบบ AND ต้องตรวจทุกองค์ประกอบ
- Unknown license หรือ native library ที่ติดมากับ wheel แต่ยังไม่ตรวจ = release blocker รวมถึง image codecs, fonts, icons และ installer components
- หาก OpenCV wheel bundle dependency ไม่ผ่าน ต้องใช้ build ที่ตัดส่วนดังกล่าวออกหรือ decoder ที่ผ่าน policy; ไม่ยกเว้นอัตโนมัติ
- สร้าง lockfile, SBOM, `THIRD_PARTY_NOTICES.md`, license inventory ระบุ package/version/source/license และ build artifacts ที่ตรวจ
- ไม่ bundle model weights, Ultralytics runtime หรือ LabelMe runtime; importer เป็นเพียงการอ่าน data format
- Ultralytics มี AGPL-3.0/Enterprise options จึงแยกจาก core ตาม requirement ([official licensing](https://docs.ultralytics.com/))
- OS, GPU driver และ SMB infrastructure ไม่ได้ถูกแจกจ่ายเป็น source core แต่ต้องบันทึกเป็น deployment prerequisites

<a id="section-4"></a>

## 4. Product requirements

### 4.1 Roles และสิทธิ์

User หนึ่งคนมี project role ต่างกันได้; `admin` เป็น system role ส่วนตำแหน่งงาน Engineer/Junior ไม่กำหนดสิทธิ์โดยอัตโนมัติ

| การทำงาน | Viewer | Annotator | Reviewer | Maintainer | Admin |
|---|---|---|---|---|---|
| ดู project/version/export ที่ได้รับสิทธิ์ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Claim, annotate, submit งานที่เข้าถึงได้ | — | ✓ | ✓ | ✓ | ✓ |
| Approve/reject | — | — | ✓ | ✓ | ✓ |
| Assign/import/schema/group/archive image | — | — | — | ✓ | ✓ |
| Create version/split/export | — | — | — | ✓ | ✓ |
| Manage membership | — | — | — | ภายใน project | ✓ |
| Create users, revoke tokens, configure storage/backup | — | — | — | — | ✓ |

Reviewer ไม่อนุมัติ revision ที่ตนแก้เป็น default (`allow_self_review=false`) Maintainer เปิด self-review ได้สำหรับ solo project แต่ต้องมีเหตุผลและ audit; ไม่อนุมัติย้อนหลังให้ทุกงานโดยอัตโนมัติ Admin ไม่ bypass optimistic locking หรือ validation

### 4.2 Functional requirements และ acceptance

| ID | Requirement | Acceptance |
|---|---|---|
| PR01 | Project/task configuration | รองรับ `detection`, `segmentation`, `classification`; task type คงที่หลัง import ภาพ |
| PR02 | Stable class identities | เพิ่ม/rename/deactivate ได้ผ่าน schema version ใหม่; ไม่ reuse class ID |
| PR03 | Safe image import | ตรวจ decode, format, dimensions, SHA-256, duplicate และ group metadata ก่อน commit |
| PR04 | Image browser | Filter status/class/assignee/group; search original filename; cursor pagination |
| PR05 | Rectangle editor | Create/select/move/resize/delete, zoom/pan, bounds validation, undo/redo |
| PR06 | Polygon editor | Add/move/delete vertices, close/cancel, reject invalid polygons |
| PR07 | Classification | Single-label shortcuts; label change เป็น annotation revision |
| PR08 | Empty/skip distinction | Verified-empty ไม่เท่ากับ unlabeled; skipped ต้องมี reason |
| PR09 | Multi-user tasks | Atomic claim-next, lease heartbeat, assignments และ conflict UI |
| PR10 | Review | Submit→approve/reject ตาม revision; rejection ต้องมี comment |
| PR11 | Recovery | Autosave และ local recovery draft ไม่ทำ stale overwrite หลัง reconnect |
| PR12 | Audit/history | ระบุ actor/time/revision/object changes; restore ด้วย revision ใหม่ |
| PR13 | Version/reproducibility | Pin assets, annotations, schema, groups, approval evidence และ policy |
| PR14 | Diff/statistics/QC | Added/removed/changed รายประเภท พร้อม per-class counts |
| PR15 | Splits | Random/stratified/group/stratified_group; deterministic และไม่มี group leakage |
| PR16 | Export | YOLO detection/segmentation, classification folders; มี provenance/hash |
| PR17 | Migration | LabelMe rectangle/polygon และ YOLO detection import พร้อม dry-run |
| PR18 | Operations | LAN-only deployment, permission checks, backups และ restore drill |

### 4.3 Non-functional requirements

- ข้อมูลภาพ, annotation, filenames, telemetry, crash reports ต้องไม่ถูกส่งออก internet; app ต้องใช้งานได้เมื่อปิด internet
- ใช้งาน Windows 10/11 x64 ตามเครื่องจริงของทีม; server เป็นเครื่อง Windows ใน LAN; Linux server เป็นอนาคต ไม่ใช่ DoD v1
- ทดสอบ baseline: 4-core CPU, RAM 16 GB, SSD, 1 Gbps LAN, 10 concurrent sessions, 50,000 images/project, 1920×1080 JPEG/PNG, ≤200 shapes/image
- เป้าหมาย p95 metadata API <300 ms; annotation save <1 s รวม durable write บน local server volume; image open เมื่อ cached <300 ms และ uncached <2 s บน baseline
- UI ต้องตอบสนองระหว่าง hashing/import/export; decoding และ HTTP ทำ background work แต่ Dear PyGui UI updates กลับมา main/UI thread
- เป้าหมาย canvas ≥30 FPS กับ 200 rectangles; benchmark ต้องบันทึก hardware, image size และ run conditions ไม่อ้างเป็นการรับประกันก่อนวัด
- จำกัด v1 image ≤50 MiB และ ≤40 megapixels, annotation payload ≤5 MiB, shapes ≤10,000 และ polygon vertices ≤10,000 รวมต่อภาพ; configurable พร้อม upper limits ฝั่ง server
- Server timestamp UTC ISO-8601; UI แปลง timezone ผู้ใช้; ห้ามใช้เวลาจาก client ตัดสิน lease
- Python dependencies ต้อง pin ใน reproducible lockfile; migrations และ backup upgrade path อยู่ใน repository

<a id="section-5"></a>

## 5. Architecture และ data ownership

```text
Engineer PC                         Junior PC
VisionLabel / Dear PyGui            VisionLabel / Dear PyGui
      | HTTPS API + bearer token          |
      +----------------+-----------------+
                       v
              DataTracking / FastAPI
        auth + project + annotation + review
        claims + versions + split + export
                       |
          +------------+------------------+
          v                               v
 Local server disk                   Managed file storage
 SQLite metadata DB                  assets / revisions
 local job state                     versions / splits / exports
          |                               |
          +------- consistent backup -----+

Optional fast path: desktops read managed images via read-only SMB.
Fallback: authenticated GET image content through API.
```

### 5.1 Deployment

- รัน FastAPI/Uvicorn **หนึ่ง process/หนึ่ง worker** เป็น service; background jobs ใช้ bounded worker ภายใน service และ persistent jobs table
- SQLite file เช่น `C:\DataTracking\db\data_tracking.sqlite3` ไม่อยู่ UNC, mapped drive, synced cloud folder หรือ removable drive
- `D:\VisionData` เป็น local storage ของ server ที่แชร์ read-only เป็น `\\CV-SERVER\VisionData`; service account เป็นผู้เขียน
- หากจำเป็นต้องใช้ NAS เป็น storage ฝั่ง server ต้องทดสอบ atomic rename, durability และ failure recovery ก่อนใช้งานจริง; ไม่ย้าย SQLite ไป NAS ตามไปด้วย
- ไม่ต้องใช้ Docker, MLflow, internet service หรือ external queue
- เปิด API ผ่าน HTTPS ภายใน LAN โดยใช้ certificate ขององค์กร; HTTP อนุญาตเฉพาะ loopback development
- Bind private interface ตาม config และ firewall จำกัด LAN; ไม่เปิด public port forwarding

### 5.2 Source of truth

| ข้อมูล | Canonical | หมายเหตุ |
|---|---|---|
| Users, memberships, working state, claims, reviews, audit | SQLite | API เป็น writer เดียว |
| Original image bytes | Immutable asset blob | Address ด้วย SHA-256; DB เป็น index |
| Annotation content ของแต่ละ revision | Immutable JSON blob | DB pin revision/path/hash ไม่เก็บ shapes ซ้ำเป็นอีก source of truth |
| Working annotation pointer | SQLite `annotation_heads` | GET head อ่าน revision blob ที่ DB ชี้ |
| Released dataset | Immutable manifest + DB snapshot indexes | Manifest คือ portable contract; DB ใช้ query/access control |
| Split assignments | Immutable split manifest + DB index | สร้างจาก released version |
| Statistics/search index | Derived cache | Rebuild ได้จาก canonical records |
| Local autosave/cache | Client private disk | ไม่ canonical; ห้าม auto upload แบบ last-writer-wins |

ไม่ต้องมี mutable `current.json` ใน v1; ถ้าเพิ่มภายหลังให้เป็น derived convenience file เท่านั้น Readers ต้องไม่เดา current revision ด้วยการเลือกเลขไฟล์สูงสุด

### 5.3 Modules

`domain` ไม่ขึ้นกับ GUI/HTTP/SQLAlchemy; shared schemas ใช้ใน client/server; application services บังคับ invariants; adapters ดูแล DB/filesystem/import/export

GUI ห้ามเข้าถึง DB หรือเขียน managed storage โดยตรง แม้รันบนเครื่อง server เอง ส่วน batch importer ต้องเรียก application services เดียวกับ API ห้ามสร้าง records ข้าม validation

<a id="section-6"></a>

## 6. Domain model และ workflow

### 6.1 Identity และ project task

- ID ทุก entity เป็น UUID string; SHA-256 เป็น lowercase hex 64 ตัว ไม่ใช้ filename เป็น identity
- `asset` คือ byte content; `image` คือ project membership ของ asset; asset เดียวใช้หลาย project ได้
- `UNIQUE(project_id, asset_sha256)` ห้าม duplicate bytes สอง image ใน project เดียว; filenames เดิมหลายชื่อเก็บใน provenance records
- `group_key` เป็น opaque string ระบุหน่วยที่ห้ามแยก partition เช่น unit/lot/sequence ตาม leakage boundary จริง; project ต้องอธิบายความหมายของ key
- แต่ละ project มีหนึ่ง task: detection ใช้ rectangle; segmentation ใช้ polygon; classification ใช้ image-level label
- Generic JSON รองรับ geometry ทั้งสองชนิด แต่ server validation ใช้ project task; ไม่ผสมหลาย task ใน project v1
- Raw bytes ห้ามแก้; corrected/re-encoded image คือ asset/image ใหม่ พร้อม `replaces_image_id` ที่อ้าง image เดิมได้

### 6.2 Working state machine

```text
UNLABELED --first saved draft--> IN_PROGRESS
IN_PROGRESS --mark complete--> ANNOTATED --submit--> REVIEW_REQUIRED
REVIEW_REQUIRED --approve--> APPROVED
REVIEW_REQUIRED --reject + reason--> REJECTED
REJECTED --save correction--> IN_PROGRESS
APPROVED --explicit reopen + reason--> IN_PROGRESS
ANNOTATED --resume editing--> IN_PROGRESS
UNLABELED/IN_PROGRESS/ANNOTATED/REJECTED --skip + reason--> SKIPPED
SKIPPED --restore--> IN_PROGRESS (or UNLABELED if no revision)
```

- Claim เป็น orthogonal state ไม่เปลี่ยน annotation workflow อัตโนมัติ; เปิดดูรูปไม่สร้าง revision
- Draft อาจ incomplete ได้ แต่ geometry ทุก shape ที่ persist ต้อง valid; pending rectangle/polygon ที่ยังวาดไม่เสร็จอยู่ local UI เท่านั้น
- `ANNOTATED` หมายถึง content ผ่าน completeness checks; `REVIEW_REQUIRED` หมายถึงส่งเข้าคิวและห้ามแก้
- Submit ปลด edit lease ใน transaction เดียวกัน; reviewer ใช้ review lease เพื่อไม่ review ซ้ำคนละหน้าจอ
- `APPROVED` ห้าม save โดยตรง ต้อง reopen ก่อน; approval เดิมยังอยู่ใน history แต่ไม่มีผลกับ working head ใหม่
- `REJECTED` ต้องแสดง comment และ target revision; rejected revision ไม่ถูกลบ
- `VERIFIED_EMPTY` เป็น **content flag** `verified_empty=true` ไม่ใช่ workflow status: approved empty คือ `APPROVED` + flag นี้
- Detection/segmentation completion: มี ≥1 shape และ empty=false หรือ 0 shapes และ empty=true
- Classification completion: มี exactly 1 image label, shapes ว่าง, empty=false; absence of label ไม่ใช่ background class
- Skip ไม่ใช่ negative example และไม่เข้า released version
- Working archive/remove image เป็น soft exclusion; ประวัติและ released snapshots ยังอ่านได้

### 6.3 Revision และ state counters

`revision` เพิ่มเมื่อ annotation content เปลี่ยน; `state_revision` เพิ่มทุกครั้งที่ head/status/assignee/group/archive เปลี่ยน (ไม่รวม heartbeat) ทุก conditional mutation ต้องตรวจ counter ที่เกี่ยวข้องใน transaction เดียวกัน

Review binding คือ `(image_id, annotation_revision, annotation_sha256, schema_id)`; review ใช้ `expected_state_revision` เพิ่มเติมเพื่อกัน duplicate/stale decisions การย้อนกลับ revision เก่าทำโดย copy content มาเป็น revision ใหม่ผ่าน lease และ validation ไม่ชี้ head กลับจนเลขลดลง

<a id="section-7"></a>

## 7. Desktop UX specification

### 7.1 หน้าจอหลัก

- Connection/profile: server URL, trusted certificate, login, connection state; project selector
- ซ้าย: project/task/schema, progress, image list, filters, assignment, “Get next task”
- กลาง: image canvas, zoom/pan, bounding boxes/vertices, selected object, loading/error overlay
- ขวา: class list, object list, selected geometry, classification, review comments/QC
- ล่าง: Prev/Next, Save, Mark complete, Submit, lease owner/expiry, saved revision และ connection status
- Project tools: import wizard, members/assignment, class schema, version browser/diff, split preview, export jobs

### 7.2 Editing behavior

- Rectangle drag ได้ทุกทิศ; normalize x1<x2/y1<y2; resize handles มี hit target ที่คงขนาดบนหน้าจอเมื่อ zoom
- Coordinate conversion มี function เดียว image↔screen; original pixel coordinates ไม่เปลี่ยนเพราะ DPI, pan หรือ zoom
- Polygon click เพิ่ม vertex, Enter/double-click ปิด, Escape ยกเลิก; drag/delete vertex พร้อม validation ก่อน save
- Keep image aspect ratio; display dimensions ใช้ decoded raw raster; **ไม่ auto-rotate EXIF** ใน v1 ต้อง ignore orientation เหมือนกันทั้ง client/server และแสดง warning ตอน import ถ้ามี EXIF rotation
- ไม่มี silent clipping ฝั่ง server; UI จำกัดการลากในภาพได้ แต่ import/API invalid coordinates ต้องคืน error
- Undo/redo เป็น local command history; undo หลัง saved revision สร้าง dirty content และ save เป็น revision ใหม่
- Autosave draft debounce 2 s หลัง valid edit เมื่อถือ lease; serialize saves ต่อ image หนึ่ง request in flight; ไม่ autosubmit
- เปลี่ยนภาพขณะ dirty: save หรือเก็บ recovery draft พร้อมเตือน; ห้าม discard โดยไม่ให้ผู้ใช้เลือก
- Local draft บันทึก base revision/hash, user/project/image/schema, edits, local timestamp; recovery หลัง crash ต้อง fetch head และ claim ใหม่ก่อน save
- Conflict UI แสดง local/server revisions และทางเลือก reload/compare/manual reapply; ห้ามมี “force overwrite” ที่ bypass server checks
- Server unreachable/lease expired: ปิด shared save, เก็บ local draft; UI แสดง disconnected/read-only state

### 7.3 Shortcuts

| ปุ่ม | Action |
|---|---|
| R / P / V | Rectangle / Polygon / Select ตาม task |
| Delete | Delete selected shape/vertex |
| Ctrl+Z / Ctrl+Y | Undo / Redo |
| Ctrl+S | Save draft |
| 1–9 | Select class ตาม shortcut mapping ไม่ใช่ class ID |
| A / D | Previous / Next เมื่อไม่ได้ focus text input |
| Space + drag / wheel | Pan / Zoom about cursor |
| Escape / Enter | Cancel / Finish polygon |

Shortcuts ต้องไม่ทำงานขณะพิมพ์ comment/search; ข้อความที่ระบบสร้างทั้งหมดใช้ภาษาอังกฤษ ส่วน filenames/class names และข้อมูลที่ผู้ใช้ตั้งเองรองรับ Unicode ด้วย font ที่ผ่าน license policy; status ใช้ English text/icon ร่วมกับสี ไม่ทำ Thai localization ใน v1

<a id="section-8"></a>

## 8. Directory structure

### 8.1 Repository

```text
visionlabel/
  pyproject.toml
  dependency-lock-file
  LICENSE
  THIRD_PARTY_NOTICES.md
  README.md
  apps/
    desktop/visionlabel/{ui,canvas,commands,network,recovery}/
    server/datatracking/{api,auth,services,repositories,jobs}/
  packages/
    domain/{entities,validation,geometry,workflow,split}/
    contracts/{api_models,annotation_schema,manifest_schema}/
    storage/{blob_store,canonical_json,backup}/
    adapters/{labelme,yolo_detect,yolo_segment,classification}/
  migrations/
  tests/{unit,contract,integration,concurrency,recovery,e2e,fixtures}/
  scripts/{dev_server,bootstrap_admin,backup,restore,package}/
  docs/{spec,adr,operator,user,license_inventory}/
```

ชื่อ subdirectory เป็น module responsibility; ไม่สร้าง framework/plugin system ล่วงหน้า

### 8.2 Server และ managed share

```text
C:\DataTracking\
  config\server.toml          # ACL จำกัด service/admin; secrets แยกจากไฟล์นี้
  db\data_tracking.sqlite3   # local disk, not shared
  logs\                     # rotate; redact tokens/content
  backups\                  # backup sets; ควร replicate ไป backup storage แยก

D:\VisionData\              # \\CV-SERVER\VisionData (client read-only)
  assets\sha256\ab\<sha256>.<ext>
  projects\<project_uuid>\
    schemas\<schema_uuid>.json
    annotations\<image_uuid>\r00000001-<sha256>.json
    versions\<version_uuid>\manifest.json
    splits\<split_uuid>\manifest.json
    exports\<export_uuid>\{dataset,export_manifest.json}
  staging\<job_uuid>\        # server-only ACL, incomplete files
  quarantine\                # server-only; malformed/import failures
```

Paths ใน API/manifests เป็น storage-relative POSIX paths; desktop map storage alias ไป local UNC root ไม่เก็บ drive letter ของแต่ละเครื่องลง canonical data ห้าม `..`, absolute paths, device names, symlinks/junctions ที่หลุด root และ case-insensitive collision

SMB read-only access ให้สิทธิ์ตาม project ACL จริง หาก organization ไม่สามารถแยกสิทธิ์ไฟล์ให้เท่ากับ API ได้ ให้ปิด SMB fast path และอ่านผ่าน API; API auth ไม่ป้องกันการอ่าน share ที่เปิดกว้างอยู่แล้ว

Client cache อยู่ `%LOCALAPPDATA%\VisionLabel\cache` และ drafts อยู่ `...\recovery`; จำกัดขนาด/retention, แยก user/server/project และ purge เมื่อ logout ตาม policy; tokens เก็บ Windows credential store

<a id="section-9"></a>

## 9. Database schema

### 9.1 Conventions และ configuration

- UUID/TEXT primary keys; timestamps UTC TEXT; booleans INTEGER 0/1; counters INTEGER ≥0
- เปิด `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=FULL`, `busy_timeout=5000` ทุก connection ที่เกี่ยวข้อง
- DB transactions สั้น; ห้าม hash/copy large file หรือ await network ระหว่าง write transaction
- ORM/migrations ต้องสร้าง unique indexes, foreign keys, checks ตาม logical schema ต่อไปนี้
- Structured JSON ใน DB ใช้ TEXT และ validate ด้วย schema ก่อนเขียน; ไม่เก็บ image bytes หรือ full annotation shape payload ใน DB
- FK default `RESTRICT` สำหรับ historical data; ห้าม cascade-delete asset/revision/version ที่ถูกใช้งาน

### 9.2 Logical relational schema (normative)

Notation: `PK`, `FK table.column`, `UQ(...)`, `?` = nullable; columns ที่ไม่ได้ระบุ ? ต้อง NOT NULL. Common immutable records มี `created_at`, `created_by FK users.id`; mutable records มี `updated_at` เพิ่มด้วย ตาราง bootstrap users เป็นข้อยกเว้น created_by nullable

| Table | Columns และ constraints |
|---|---|
| `users` | `id PK, username UQ, display_name, password_hash, is_admin, disabled, created_at, updated_at`; case-fold username ก่อน unique |
| `auth_tokens` | `id PK, user_id FK users.id, token_hash UQ, expires_at, revoked_at?, created_at`; ห้ามเก็บ plaintext token |
| `projects` | `id PK, slug UQ, name, task_type, description, active_schema_id?, settings_json, project_revision, archived, created_at, created_by, updated_at` |
| `project_members` | `(project_id FK projects.id, user_id FK users.id) PK, role, created_at, created_by`; role enum ตามข้อ 4 |
| `classes` | `id PK, project_id FK projects.id, stable_key, created_at, created_by`; `UQ(project_id,stable_key)`, identity ไม่เปลี่ยน |
| `class_schemas` | `id PK, project_id FK projects.id, number, blob_path, sha256, created_at, created_by`; `UQ(project_id,number)`; immutable |
| `class_schema_entries` | `(schema_id FK class_schemas.id,class_id FK classes.id) PK, display_name, export_index, color_hex, active`; `UQ(schema_id,export_index)`; index ≥0; ห้าม class ต่าง project |
| `assets` | `sha256 PK, byte_size, media_type, extension, width, height, blob_path UQ, orientation_policy, created_at, created_by`; positive size/dimensions |
| `images` | `id PK, project_id FK projects.id, asset_sha256 FK assets.sha256, display_filename, group_key?, metadata_json, replaces_image_id? FK images.id, archived, created_at, created_by, updated_at`; `UQ(project_id,asset_sha256)` |
| `image_sources` | `id PK, image_id FK images.id, source_alias, source_relpath, import_job_id FK jobs.id, source_sha256, created_at, created_by`; provenance ไม่ใช้ path เป็น identity |
| `annotation_heads` | `image_id PK FK images.id, current_revision, status, state_revision, assignee_id? FK users.id, skip_reason?, updated_at`; current_revision=0 คือไม่มี content |
| `annotation_revisions` | `(image_id FK images.id,revision) PK, schema_id FK class_schemas.id, blob_path UQ, sha256, verified_empty, object_count, change_summary_json, created_at, created_by`; revision≥1; immutable |
| `annotation_class_counts` | `(image_id,revision,class_id FK classes.id) PK, shape_count, image_label_present`; `(image_id,revision) FK annotation_revisions`; derived index |
| `task_claims` | `image_id PK FK images.id, claim_id UQ, owner_id FK users.id, mode, generation, token_hash, acquired_at, expires_at, last_heartbeat_at`; mode=edit/review; หนึ่งแถวต่อภาพ |
| `reviews` | `id PK, image_id, annotation_revision, annotation_sha256, schema_id FK class_schemas.id, decision, comment, reviewer_id FK users.id, created_at`; composite FK ไป revision; decision=approve/reject |
| `dataset_versions` | `id PK, project_id FK projects.id, version_label, parent_version_id? FK dataset_versions.id, state, schema_id FK class_schemas.id, manifest_path?, manifest_sha256?, note, selection_policy_json, created_at, created_by, released_at?`; `UQ(project_id,version_label)`; state=BUILDING/RELEASED/FAILED |
| `dataset_version_items` | `(version_id FK dataset_versions.id,image_id FK images.id) PK, asset_sha256 FK assets.sha256, annotation_revision, annotation_sha256, schema_id FK class_schemas.id, review_id FK reviews.id, group_key?, display_filename, metadata_json`; composite FK ไป annotation revision; snapshot fields immutable |
| `split_runs` | `id PK, version_id FK dataset_versions.id, state, strategy, seed, algorithm_version, config_json, input_sha256, manifest_path?, manifest_sha256?, diagnostics_json, created_at, created_by`; state=BUILDING/READY/FAILED |
| `split_assignments` | `(split_id FK split_runs.id,image_id FK images.id) PK, partition, effective_group_key`; partition=train/val/test; membership ต้องเป็น version ของ split |
| `export_runs` | `id PK, version_id FK dataset_versions.id, split_id FK split_runs.id, state, format, config_json, exporter_version, manifest_path?, manifest_sha256?, created_at, created_by`; state=BUILDING/READY/FAILED |
| `jobs` | `id PK, project_id? FK projects.id, type, state, payload_json, progress_done, progress_total?, result_json?, error_json?, attempt, heartbeat_at?, created_at, created_by, updated_at`; queued/running/succeeded/failed/cancelled |
| `idempotency_records` | `(user_id FK users.id,route_scope,key) PK, request_sha256, response_status?, response_json?, job_id? FK jobs.id, state, expires_at, created_at`; pending/complete |
| `audit_events` | `id PK, project_id? FK projects.id, actor_id? FK users.id, action, entity_type, entity_id, request_id, before_ref_json?, after_ref_json?, detail_json, created_at`; append-only |

`projects.active_schema_id` ต้อง FK ไป class_schemas และเป็น schema ของ project เดียวกัน; circular references สร้างผ่าน migrations ตามลำดับโดย active_schema nullable เฉพาะ bootstrap ก่อนเปิดใช้งาน project

### 9.3 Constraints ที่ service/trigger ต้อง enforce เพิ่ม

1. Composite FK ของ head ใช้ conditional service check เพราะ revision=0 ไม่มี revision row; revision>0 ต้องมี row จริงและ image ตรงกัน
2. ทุก cross-table project reference ต้องอยู่ project เดียวกัน (schema/classes/images/reviews/parent versions/memberships); simple FK อย่างเดียวไม่เพียงพอ
3. `annotation_heads.current_revision` เพิ่มทีละหนึ่งเมื่อ save; unique `(image_id,revision)` กัน concurrent insert
4. Approval ต้องอ้าง hash/schema ที่ตรง revision row; release ต้องตรวจ latest effective approval ของ selected head ใน transaction
5. Claim generation เพิ่มทุก acquire/revoke; expiry ไม่ลบ row เพื่อคง fencing counter
6. Released version/items ห้าม UPDATE/DELETE ด้วย DB triggers และ service guards; BUILDING rows เขียนได้เฉพาะ job owner แล้ว freeze ตอน release
7. Immutable revision/schema/asset identity fields ห้าม UPDATE; derived counts rebuild ได้; user disable/soft archive ไม่ลบ history
8. Split READY และ assignments ห้ามแก้; export READY metadata และ manifest ห้ามแก้
9. Add indexes: images(project_id,archived), images(project_id,group_key), heads(status,assignee_id), claims(expires_at), reviews(image_id,annotation_revision,created_at), versions(project_id,state), audit(project_id,created_at,id), jobs(state,created_at)

### 9.4 Transaction example สำหรับ compare-and-swap

```sql
UPDATE annotation_heads
SET current_revision = :new_revision,
    state_revision = state_revision + 1,
    status = 'IN_PROGRESS',
    updated_at = :server_now
WHERE image_id = :image_id
  AND current_revision = :expected_revision
  AND state_revision = :expected_state_revision;
```

ต้อง execute หลัง validate claim/token/expiry/generation และ workflow ภายใน transaction เดียวกัน; require affected_rows=1 มิฉะนั้น rollback ทั้ง revision insert/head/audit/idempotency result ไม่ใช่ retry overwrite ด้วย revision ล่าสุดอัตโนมัติ

<a id="section-10"></a>

## 10. Internal annotation JSON schema

### 10.1 Canonical document ตัวอย่าง

```json
{
  "schema_version": "1.0.0",
  "project_id": "10000000-0000-4000-8000-000000000001",
  "image_id": "20000000-0000-4000-8000-000000000001",
  "asset_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "width": 1920,
  "height": 1080,
  "class_schema_id": "30000000-0000-4000-8000-000000000001",
  "revision": 7,
  "verified_empty": false,
  "image_labels": [],
  "shapes": [
    {
      "id": "40000000-0000-4000-8000-000000000001",
      "type": "rectangle",
      "class_id": "50000000-0000-4000-8000-000000000001",
      "x1": 341,
      "y1": 220,
      "x2": 501,
      "y2": 480,
      "attributes": {}
    }
  ],
  "created_by": "60000000-0000-4000-8000-000000000001",
  "created_at": "2026-10-03T03:42:00Z"
}
```

ตัวอย่าง hash ข้างต้นเป็น placeholder ไม่ใช่ checksum ของภาพจริง Shape ID คงเดิมเมื่อ edit geometry/class; clone สร้าง ID ใหม่; array order ไม่มี semantic meaning สำหรับ exporter

### 10.2 JSON Schema Draft 2020-12

Schema นี้ใช้ validate persisted document; request body ใช้ subset ของ editable fields ในข้อ 11 Server เติม identity/revision/timestamp เอง

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:visionlabel:annotation:1.0.0",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "project_id", "image_id", "asset_sha256", "width", "height", "class_schema_id", "revision", "verified_empty", "image_labels", "shapes", "created_by", "created_at"],
  "properties": {
    "schema_version": {"const": "1.0.0"},
    "project_id": {"$ref": "#/$defs/uuid"},
    "image_id": {"$ref": "#/$defs/uuid"},
    "asset_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "width": {"type": "integer", "minimum": 1},
    "height": {"type": "integer", "minimum": 1},
    "class_schema_id": {"$ref": "#/$defs/uuid"},
    "revision": {"type": "integer", "minimum": 1},
    "verified_empty": {"type": "boolean"},
    "image_labels": {"type": "array", "uniqueItems": true, "items": {"$ref": "#/$defs/uuid"}},
    "shapes": {"type": "array", "maxItems": 10000, "items": {"oneOf": [{"$ref": "#/$defs/rectangle"}, {"$ref": "#/$defs/polygon"}]}},
    "created_by": {"$ref": "#/$defs/uuid"},
    "created_at": {"type": "string", "format": "date-time"}
  },
  "allOf": [
    {
      "if": {"properties": {"verified_empty": {"const": true}}},
      "then": {"properties": {"shapes": {"maxItems": 0}, "image_labels": {"maxItems": 0}}}
    }
  ],
  "$defs": {
    "uuid": {"type": "string", "format": "uuid"},
    "coordinate": {"type": "number", "minimum": 0},
    "attributes": {
      "type": "object",
      "maxProperties": 32,
      "additionalProperties": {"type": ["string", "number", "boolean", "null"]}
    },
    "rectangle": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "type", "class_id", "x1", "y1", "x2", "y2", "attributes"],
      "properties": {
        "id": {"$ref": "#/$defs/uuid"},
        "type": {"const": "rectangle"},
        "class_id": {"$ref": "#/$defs/uuid"},
        "x1": {"$ref": "#/$defs/coordinate"},
        "y1": {"$ref": "#/$defs/coordinate"},
        "x2": {"$ref": "#/$defs/coordinate"},
        "y2": {"$ref": "#/$defs/coordinate"},
        "attributes": {"$ref": "#/$defs/attributes"}
      }
    },
    "polygon": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "type", "class_id", "points", "attributes"],
      "properties": {
        "id": {"$ref": "#/$defs/uuid"},
        "type": {"const": "polygon"},
        "class_id": {"$ref": "#/$defs/uuid"},
        "points": {
          "type": "array", "minItems": 3, "maxItems": 10000,
          "items": {
            "type": "array", "minItems": 2, "maxItems": 2,
            "prefixItems": [{"$ref": "#/$defs/coordinate"}, {"$ref": "#/$defs/coordinate"}],
            "items": false
          }
        },
        "attributes": {"$ref": "#/$defs/attributes"}
      }
    }
  }
}
```

### 10.3 Semantic validation ที่ JSON Schema เพียงอย่างเดียวทำไม่ได้

- ใช้ format checking จริงสำหรับ UUID/date-time; reject NaN/Infinity ทั้ง parser และ serializer
- Dimensions/hash/project/image ต้องตรง asset record ไม่เชื่อค่าที่ client ส่งมา
- Coordinates เป็น finite pixel numbers บน raster เดิม: `0≤x≤width`, `0≤y≤height`; image edge coordinate อนุญาตเท่ากับ width/height
- Rectangle: x1<x2, y1<y2, width/height >0; tiny boxes <2 px เป็น QC warning ไม่ใช่ invalid โดยอัตโนมัติ
- Polygon: ≥3 distinct vertices, nonzero area, no self-intersection, no repeated closing vertex, no repeated adjacent vertices, ไม่มี holes/multiple rings; normalize winding/start vertex แบบ deterministic ก่อน hash
- Shape IDs unique ภายใน document; class IDs มีจริงและ active ใน referenced schema ของ project
- Draft classification labels มี 0 หรือ 1 ได้; complete/review/release ต้อง exactly 1
- Task-specific shape type และ flag ตามข้อ 6; geometry/attribute values invalid ต้อง error พร้อม JSON path
- Attributes เป็น optional semantic extensions ตาม allowlist ของ project; v1 exporter ไม่แปลง attributes เป็น YOLO features และต้องบอกข้อจำกัดใน export manifest

### 10.4 Canonical serialization และ hashing

Raw asset hash = SHA-256 ของ original file bytes ไม่ใช่ decoded pixels; rename ไม่เปลี่ยน hash แต่ re-encode เปลี่ยน hash

JSON ใช้ serializer profile `vl-json-1`: UTF-8 ไม่ BOM, LF, `sort_keys=true`, separators `,`/`:`, ensure_ascii=false, allow_nan=false, coordinates round 6 decimal places แบบ half-even ด้วย Decimal จาก decimal text, normalize negative zero เป็น zero, sort shapes ด้วย ID และ image_labels ด้วย ID; validate geometry **หลัง rounding** ด้วย

SHA-256 คำนวณจาก exact stored bytes; hash ไม่อยู่ภายใน document ที่ hash ตัวเอง `annotation_sha256` คือ full revision document hash; geometry semantic diff คำนวณเฉพาะ editable content โดยไม่รวม revision/author/time แยกต่างหาก เปลี่ยน serializer profile ต้องเพิ่ม version ไม่ reserialize artifact เก่า

ทุก consumer ตรวจ hash จาก bytes โดยตรง ไม่ deserialize/re-encode เพื่อ verify; เก็บ golden serialization vectors เพื่อให้ผลคงเดิมเมื่ออัปเกรด Python

<a id="section-11"></a>

## 11. API contract

### 11.1 Common protocol

- Base path `/api/v1`, JSON UTF-8, HTTPS; `Authorization: Bearer <opaque_token>` ทุก endpoint ยกเว้น health และ login
- IDs เป็น UUID; datetime UTC ISO-8601; percentages ใช้ integer basis points (10,000 = 100%) เพื่อไม่ให้ float sum ambiguous
- ทุก mutation สร้าง/propagate `X-Request-ID`; server actor มาจาก token ไม่ใช่ `user_id` ใน payload
- Lists รับ `limit` default 100/max 500 และ opaque `cursor`; ตอบ `{items, next_cursor}` พร้อม stable ordering ด้วย `(created_at,id)`; filter ไม่เปลี่ยนกลาง pagination
- GET ไม่มี side effect; claim-next ใช้ POST ไม่ใช่ GET
- Metadata mutations ใช้ `expected_state_revision` หรือ `expected_project_revision`; annotation ใช้ทั้ง content revision และ state revision
- Missing required concurrency fields = 422; stale value = 409; client ต้องอ่านใหม่และให้ผู้ใช้ resolve
- `Idempotency-Key` required สำหรับ save, workflow actions, claim acquire/claim-next, review, import, version, split, export และ bulk mutations; ทุก side-effecting POST/PUT/PATCH รองรับ
- Key scope `(authenticated user, route scope, key)`; request hash รวม canonical body และ entity identity; same key/different request =409 `IDEMPOTENCY_KEY_REUSED`
- Replay completed request คืน status/body เดิมหลังตรวจ authorization ปัจจุบัน แม้ lease หมดภายหลัง; pending คืน existing job หรือ 409 `REQUEST_IN_PROGRESS` พร้อม Retry-After
- เก็บ keys ≥7 วัน และไม่น้อยกว่า job retention; retries หลัง retention ต้อง reconcile ด้วย entity/job ID ไม่ถือว่า key จะคงอยู่ตลอด
- Response headers และ OpenAPI ระบุ schema/API version; unknown fields ใน mutation payload ต้อง reject

### 11.2 Error envelope

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "Annotation changed since it was loaded.",
    "details": {
      "expected_revision": 7,
      "current_revision": 8,
      "current_state_revision": 19
    },
    "request_id": "req-123"
  }
}
```

| HTTP | Code examples | Client action |
|---|---|---|
| 400 | `INVALID_CURSOR`, `MALFORMED_JSON` | แก้ request |
| 401 | `AUTH_REQUIRED`, `TOKEN_EXPIRED` | Login ใหม่; draft ยังอยู่ |
| 403 | `FORBIDDEN`, `SELF_REVIEW_FORBIDDEN` | ไม่ retry ด้วยสิทธิ์เดิม |
| 404 | `NOT_FOUND` | รวม resource นอก project ที่ไม่มีสิทธิ์เพื่อไม่เปิดเผยข้อมูล |
| 409 | `REVISION_CONFLICT`, `STATE_CONFLICT`, `SCHEMA_CHANGED`, `LEASE_EXPIRED`, `LEASE_REVOKED`, `IDEMPOTENCY_KEY_REUSED` | Reload/reconcile; ห้าม silent retry overwrite |
| 423 | `CLAIMED_BY_OTHER` | Read-only และแสดง owner/expiry เฉพาะผู้มีสิทธิ์ |
| 422 | `VALIDATION_FAILED`, `SPLIT_INFEASIBLE`, `UNSUPPORTED_CONVERSION` | แสดง field paths/diagnostics |
| 429 | `RATE_LIMITED` | Respect Retry-After |
| 503 | `STORAGE_UNAVAILABLE`, `DATABASE_BUSY`, `READ_ONLY_MAINTENANCE` | เก็บ draft; retry bounded backoff ด้วย key เดิม |

Responses ห้ามส่ง stack trace, absolute server paths, password/token hashes หรือ contents ของ project อื่น

### 11.3 Endpoint inventory

Path ด้านล่างต่อจาก `/api/v1`; `P`=project UUID, `I`=image UUID, `V`=version UUID. Roles ใช้ข้อ 4 ประกอบ; response DTO ต้องมี IDs, relevant revisions และ server time

| Method / path | Role / request | Success contract |
|---|---|---|
| `GET /health/live` | public minimal | 200 `{status:"ok"}`; ไม่เปิดเผย paths |
| `GET /health/ready` | authenticated admin | 200 หรือ 503; DB/storage/schema readiness |
| `POST /auth/login` | username,password; rate limited | 200 token,expires_at,user; opaque random token ≥256 bits |
| `POST /auth/logout` | token | 204; revoke current token |
| `GET /me` | authenticated | 200 user + project roles |
| `POST /users` | admin; username,display_name,password | 201 user; password hash ใช้ stdlib scrypt พร้อม random salt และ calibrated work factor |
| `PATCH /users/{id}` | admin; disabled/display_name/password | 200 user; disable/revoke ต้อง revoke tokens/claims |
| `GET /projects` | membership-filtered | 200 paginated projects |
| `POST /projects` | maintainer of a project หรือ admin; name,slug,task_type,initial_classes,settings | 201 project + initial immutable schema; creator เป็น maintainer |
| `GET /projects/{P}` | project member | 200 project/settings/schema/project_revision |
| `PATCH /projects/{P}` | maintainer; allowed metadata/settings + expected_project_revision | 200 updated project; task type immutable หลัง import |
| `GET /projects/{P}/members` | member | 200 member summaries |
| `PUT /projects/{P}/members/{user_id}` | maintainer; role,expected_project_revision | 200 membership; ห้ามถอด last maintainer |
| `DELETE /projects/{P}/members/{user_id}` | maintainer; expected_project_revision | 204; revoke user's project claims |
| `GET /projects/{P}/schemas` | member | 200 schemas |
| `GET /schemas/{id}` | member | 200 immutable class schema + hash |
| `POST /projects/{P}/schemas` | maintainer; based_on_schema_id,entries,expected_project_revision | 201 new schema; activate เฉพาะ publish ผ่าน validation |
| `POST /projects/{P}/schema-migrations` | maintainer; target_schema_id,image_ids,expected revisions, class mapping,dry_run | 202 job; non-atomic bulk มี per-image result |
| `POST /projects/{P}/imports` | maintainer; source_alias,relative_paths,format,options,dry_run | 202 `{job_id}`; aliases ต้อง configured โดย admin |
| `GET /projects/{P}/images` | member; status,class_id,assignee,group,search,archived,cursor | 200 image summaries/head/QC |
| `GET /images/{I}` | member | 200 asset metadata, relative read path, head,status,state_revision,claim summary |
| `GET /images/{I}/content` | member | 200 original bytes with SHA-256 ETag; supports conditional GET |
| `PATCH /images/{I}` | maintainer; group_key,metadata/display_filename,archived,expected_state_revision | 200 updated metadata/state_revision; no image-byte replacement |
| `POST /projects/{P}/assignments` | maintainer; image_ids,assignee_id,expected state revisions | 200 per-image results; active foreign lease ต้อง explicit revoke ก่อน |
| `GET /images/{I}/annotation` | member | 200 `{annotation:null,revision:0,state_revision,...}` หรือ persisted annotation + hash/head |
| `GET /images/{I}/revisions` | member | 200 paginated history |
| `GET /images/{I}/revisions/{n}` | member | 200 immutable annotation + hash |
| `PUT /images/{I}/annotation` | annotator; claim headers + save body ข้อ 11.4 | 200 new revision/hash/status/state_revision |
| `POST /images/{I}/restore-revision` | annotator; source_revision,expected counters,valid edit claim | 200 new revision after current-schema validation |
| `POST /images/{I}/claim` | annotator/reviewer; mode,client_instance_id | 201 claim lease (423 if unavailable) |
| `POST /projects/{P}/tasks/claim-next` | annotator/reviewer; mode,optional filters | 201 `{image,claim}` หรือ 204 ไม่มีงานตรงเงื่อนไข |
| `POST /images/{I}/claim/heartbeat` | claim owner; claim headers | 200 server_time/expires_at; ไม่ต่อ lease ที่หมดแล้ว |
| `DELETE /images/{I}/claim` | owner; claim headers | 204; invalidates generation; repeated released claim returns204 |
| `POST /images/{I}/claim/revoke` | maintainer; reason,expected_generation | 200 new generation + audit |
| `POST /images/{I}/complete` | edit owner; expected_revision/state_revision | 200 ANNOTATED; lease ยังถืออยู่ |
| `POST /images/{I}/submit` | edit owner; expected counters | 200 REVIEW_REQUIRED; release lease |
| `POST /images/{I}/resume` | edit owner on ANNOTATED; expected counters | 200 IN_PROGRESS |
| `POST /images/{I}/reviews` | reviewer + review claim; decision,comment,expected counters,annotation_sha256 | 201 review + APPROVED/REJECTED; release claim |
| `POST /images/{I}/reopen` | reviewer/maintainer; reason,expected counters | 200 IN_PROGRESS; approval applicability cleared; acquire edit claim separately |
| `POST /images/{I}/skip` | edit owner; reason,expected counters | 200 SKIPPED; release claim |
| `POST /images/{I}/unskip` | annotator authorized for assignment; expected counters | 200 restored state; no automatic claim |
| `GET /projects/{P}/statistics` | member; working หรือ version_id | 200 counts/QC/cache timestamp/source revision |
| `GET /projects/{P}/audit` | reviewer/maintainer | 200 paginated audit records |
| `POST /projects/{P}/versions` | maintainer; contract ข้อ 13 | 202 job + version ID |
| `GET /projects/{P}/versions` | member | 200 versions/state/hash |
| `GET /versions/{V}` | member | 200 metadata และ released manifest URL/hash |
| `GET /versions/{V}/manifest` | member | 200 exact immutable JSON bytes; 409 if not RELEASED |
| `GET /versions/{V}/diff?target_version_id=...` | member of same project | 200 diff V→target; pagination for details |
| `POST /versions/{V}/splits` | maintainer; config ข้อ 14 | 202 split ID/job ID |
| `GET /splits/{id}` | member | 200 config,diagnostics,manifest/hash if READY |
| `GET /splits/{id}/assignments` | member | 200 paginated assignments |
| `POST /versions/{V}/exports` | maintainer; split_id,format,options | 202 export ID/job ID |
| `GET /exports/{id}` | member | 200 metadata/files/manifest/hash |
| `GET /exports/{id}/download` | member | 200 archive only when READY; integrity digest |
| `GET /jobs/{id}` | authorized project member | 200 state,progress,result,error |
| `POST /jobs/{id}/cancel` | job creator/maintainer | 200 cancellation requested; completed publication ไม่ย้อนกลับ |
| `POST /admin/backups` | admin | 202 job ID |

Password hashing parameters ต้องมี benchmark และ bounds ป้องกัน memory exhaustion; constant-time token hash comparison, login throttling, password reset admin flow และ session expiration ต้องมี tests

### 11.4 Save contract

Request `PUT /images/{I}/annotation` พร้อม `X-Claim-ID`, `X-Claim-Token`, `X-Claim-Generation` และ `Idempotency-Key`:

```json
{
  "expected_revision": 7,
  "expected_state_revision": 18,
  "class_schema_id": "30000000-0000-4000-8000-000000000001",
  "content": {
    "verified_empty": false,
    "image_labels": [],
    "shapes": [
      {
        "id": "40000000-0000-4000-8000-000000000001",
        "type": "rectangle",
        "class_id": "50000000-0000-4000-8000-000000000001",
        "x1": 340,
        "y1": 220,
        "x2": 501,
        "y2": 480,
        "attributes": {}
      }
    ]
  }
}
```

Response:

```json
{
  "image_id": "20000000-0000-4000-8000-000000000001",
  "revision": 8,
  "state_revision": 19,
  "status": "IN_PROGRESS",
  "annotation_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "saved_at": "2026-10-03T03:43:00Z"
}
```

Hash ใน response example เป็น placeholder; server ต้องคำนวณจริง Save identical editable content อาจ return current revision โดยไม่มี revision ใหม่ แต่ต้องตรวจ expected counters/lease และบันทึก idempotent response; ห้ามเปลี่ยน workflow ผ่าน no-op save

### 11.5 Claim response และ job DTO

```json
{
  "claim_id": "70000000-0000-4000-8000-000000000001",
  "claim_token": "opaque-secret-returned-only-to-owner",
  "generation": 12,
  "mode": "edit",
  "owner_id": "60000000-0000-4000-8000-000000000001",
  "server_time": "2026-10-03T03:40:00Z",
  "expires_at": "2026-10-03T03:55:00Z",
  "heartbeat_interval_seconds": 45
}
```

Claim token ใช้ random secret; DB เก็บ hash; ไม่ส่ง token ใน image summaries/logs หาก replay claim-acquisition response ต้องเก็บ secret ใน encrypted idempotency response โดย server-local key หรือออก opaque authenticated token ที่ reconstruct ได้; ห้ามลด security ด้วยการเก็บ plaintext replay response ทั่วไป

Job DTO: `{id,type,state,progress:{done,total},result,error,created_at,updated_at}`; result มี artifact ID เมื่อสำเร็จ; error ใช้ code/message/details; retries เพิ่ม attempt และไม่เผย partial artifact เป็น READY

<a id="section-12"></a>

## 12. Concurrency, atomicity และ recovery rules

### 12.1 Claim/lease algorithm

Defaults: TTL 900 s, heartbeat ทุก 45 s, UI เตือนเมื่อ heartbeat ล้มเหลว 2 ครั้ง หรือน้อยกว่า 90 s ก่อนหมด; server config เปลี่ยนได้ในช่วง 60–1800 s

1. Authenticate/authorize; check assignment และ state eligibility (`edit`: UNLABELED/IN_PROGRESS/ANNOTATED/REJECTED; `review`: REVIEW_REQUIRED)
2. ใน `BEGIN IMMEDIATE` เลือก image ที่เข้าเงื่อนไขและไม่มี unexpired claim; claim-next เลือก deterministic order ตาม assignment priority แล้ว image ID
3. UPSERT claim โดยตรวจ expiry เทียบ server time, generation +=1, สร้าง claim ID/token ใหม่
4. Commit claim + audit + idempotency result เป็นหน่วยเดียว; ส่ง lease ให้ owner
5. ทุก save/complete/submit/review/heartbeat ตรวจ owner, token hash, claim ID, generation, mode, expiry และสิทธิ์ที่ยังมีผล
6. Heartbeat ต่อ TTL เฉพาะ lease ปัจจุบันที่ยังไม่หมด; lease หมดแม้ 1 ms ต้อง acquire ใหม่ ไม่คืนชีพ lease เก่า
7. TTL หมดไม่ลบ draft/history/status; next claimant โหลด head ล่าสุด
8. Revoke/disable user/remove membership ทำให้ generation เปลี่ยนและ token เดิมใช้ไม่ได้ทันที

Server restart invalidate claims ทั้งหมดและเพิ่ม generation ก่อน ready เพื่อป้องกันใช้ stale claims/clock ambiguity; clients re-acquire แล้วตรวจ revision ก่อน replay draft หาก server wall clock กระโดดผิดปกติให้ invalidate claims และแจ้ง health warning

Same account คนละเครื่องถือเป็นคนละ claim session; ห้ามสอง client save ด้วยแค่ user ID Assignment เป็น routing preference/permission ตาม project policy ไม่ใช่ mutex

Default assignment policy: annotator claim ได้เฉพาะงานที่ assign ให้ตนหรือยัง unassigned; claim-next เลือกงานของตนก่อนงาน unassigned ส่วน reviewer claim review queue ได้ทั้ง project ที่มี role นั้น Maintainer ต้องเปลี่ยน assignment/revoke อย่างมี audit ก่อนเข้ารับ edit งานที่ assign คนอื่น หากใช้ policy แบบ open pool ให้บันทึกใน project settings อย่างชัดเจน

### 12.2 Optimistic locking

- Lease อย่างเดียวไม่พอ เพราะ delayed request อาจมาหลัง revoke; generation คือ fencing token และ revision คือ stale content protection
- Save ต้องผ่าน expected_revision + expected_state_revision; review ต้องผ่าน counters + exact annotation hash; project/schema mutation ใช้ expected_project_revision
- การอ่าน state แล้วเขียนแยก transaction ถือว่า implementation ไม่ผ่าน
- ผู้แพ้ race ได้ 409/423 ตามเหตุผล ไม่ retry ด้วยการเปลี่ยน expected revision ให้ตรงเอง
- API response lost: retry key เดิมคืน commit result เดิม; user action ใหม่ต้อง key ใหม่

### 12.3 File + DB consistency protocol

Filesystem กับ SQLite ไม่มี distributed transaction จึง **ห้าม commit DB pointer ก่อน durable file มีอยู่จริง** ลำดับข้อกำหนดนี้เป็นการทำให้รายละเอียด “save DB/JSON” จากแนวคิดเดิมปลอดภัยขึ้น

1. Preflight authorization/lease/state เพื่อ reject เร็ว; read base revision และ schema
2. Validate + canonicalize content; สร้าง candidate revision document และ hash
3. เขียน temp file ใน filesystem เดียวกับปลายทาง, flush + fsync, ตรวจ digest; publish ด้วย atomic rename ไป unique immutable path (`revision + hash`) โดยห้าม overwrite existing different content
4. เปิด short write transaction แล้ว **ตรวจสิทธิ์/lease/expiry/schema/counters ซ้ำ**; insert revision + update head via CAS + derived counts + audit + idempotency result
5. Commit SQLite แล้วตอบ success; annotation file ต้องอ่านได้และ digest ตรงก่อน commit
6. ถ้า DB transaction แพ้ race/ล้มเหลว immutable file อาจ orphan ได้แต่ห้ามมี committed pointer ไปไฟล์ที่ไม่พร้อม

ห้ามถือ write transaction ระหว่าง copying image/export; server ต้อง verify filesystem guarantees บน deployment volume จริง

| Crash/failure point | Recovery |
|---|---|
| ก่อน publish temp | ลบ stale staging หลัง grace period |
| หลัง publish file ก่อน DB commit | Unreferenced blob; quarantine/GC หลัง grace period และตรวจ references ทุกประเภท |
| หลัง DB commit ก่อน response | Replay idempotency key คืน saved revision เดิม |
| DB points to missing/corrupt file จาก disk failure/external tamper | Mark unhealthy, block affected reads/release/export, restore จาก backup; ห้ามสร้าง empty annotation แทน |
| Storage disconnected/disk full | 503, head ไม่เปลี่ยน, client เก็บ draft |
| Process restart ระหว่าง import/version/export | Job recovery ตรวจ stage/checksums และ resume safely หรือ fail ชัดเจน; ไม่ publish partial output |

Grace period default ≥7 วัน; GC ต้องถือ maintenance/GC lock และห้ามแข่งกับ active publishers/backup pins; v1 **ปิด automatic deletion ของ canonical blobs** ใช้ orphan report ก่อนจน restore/retention ผ่าน gate

### 12.4 Audit

บันทึก successful state-changing actions ใน DB transaction เดียวกับ mutation: import, assignment, claim/revoke, revision creation, class changes, submit/review/reopen/skip, release/split/export, membership และ backup events Audit ราย revision สรุป created/updated/deleted shape IDs และ class changes โดย diff เทียบ revision ก่อนหน้า ไม่เก็บ mouse move/heartbeat ทุกครั้ง

Log security failures แยกจาก dataset audit และ redact sensitive payload Audit append-only ใน application แต่ไม่กล่าวอ้างว่า tamper-proof ต่อ OS/DB admin; integrity ของ artifact ตรวจด้วย SHA-256

<a id="section-13"></a>

## 13. Versioning rules

### 13.1 Working dataset กับ released version

- มี working dataset หนึ่งชุดต่อ project; edit ไม่แก้ released data
- Version label ใช้ `vMAJOR.MINOR.PATCH`, unique ต่อ project, monotonic ตาม release policy; DB identity เป็น UUID
- แนะนำ PATCH=แก้ annotation, MINOR=เพิ่ม/ลบภาพหรือเพิ่มคลาส, MAJOR=เปลี่ยน semantics/class mapping ที่ไม่ compatible; version label ไม่ใช่หลักฐานความเท่ากัน ต้องใช้ manifest hash
- Released version ไม่มี update/delete API; deprecated display marker ถ้าต้องมีให้เก็บเป็น external catalog record ไม่แก้ manifest
- Release จาก arbitrary subset ต้องส่ง explicit image IDs/selection predicate ที่ resolve แล้ว; default `all_active_approved` และต้องรายงาน exclusions
- `all_active` strict mode ล้มเหลวถ้ามี active image ที่ยังไม่ approved แทน silently exclude
- Empty version ไม่อนุญาต; parent ต้องเป็น RELEASED ของ project เดียวกัน และเก็บ provenance ว่าต่อยอดจาก version ใด
- Export/split ต้องอ้าง RELEASED version; ห้าม export production dataset จาก live working head

### 13.2 Version creation contract

```json
{
  "version_label": "v1.0.0",
  "parent_version_id": null,
  "schema_id": "30000000-0000-4000-8000-000000000001",
  "selection": {"mode": "all_active_approved"},
  "expected_project_revision": 12,
  "note": "Initial reviewed dataset"
}
```

`schema_id` ต้องเป็น active schema ณ cutoff; ทุก selected revision ต้องใช้ schema นี้ Approval ของ schema เก่าไม่ถูกตีความเป็น schema ใหม่อัตโนมัติ

### 13.3 Consistent release protocol

1. Preflight permissions/config และ idempotency; reserve version label สร้าง BUILDING row/job
2. ใน short write transaction ตั้ง cutoff: resolve selection, ตรวจ approved/current revision, no active edit/review claim, schema match; freeze version items ด้วย asset/annotation hashes, group/metadata, review evidence, class schema และ policy snapshot
3. End transaction แล้ว working dataset แก้ต่อได้; job ใช้ frozen items เท่านั้น ไม่ query latest head ซ้ำระหว่าง build
4. ตรวจ every asset/revision file/hash และ completeness จาก frozen input; สร้าง manifest แบบ deterministic order
5. Write manifest temp→durable immutable file; final transaction ตรวจ snapshot digest ตรง original build input แล้วตั้ง RELEASED/hash/released_at และ audit
6. ถ้า failed state=FAILED พร้อม diagnostics; consumers ไม่เห็นเป็น released; retry ใช้ reserved version record เดิมและ frozen inputs หรือยกเลิกแล้วใช้ label ใหม่อย่างชัดเจน

Approval ภายหลัง cutoff ถูก reopen ไม่เปลี่ยน version ที่ snapshot approved ณ cutoff; manifest เก็บ review evidence และ capture time เพื่อให้แปลความได้

### 13.4 Manifest contract

Manifest ต้องมี `manifest_schema_version`, `serializer_profile`, project/version IDs, label, parent, captured_at, task_type, full class schema snapshot + hash, selection policy + excluded counts, immutable project policy snapshot, sorted items, stats และ builder version

แต่ละ item ต้องมี `image_id, asset_sha256, asset_relpath, byte_size, width, height, annotation_revision, annotation_sha256, annotation_relpath, schema_id, review_id, reviewer_id, approved_at, group_key, display_filename, metadata` โดยไม่มี absolute paths หรือ secrets

Manifest ไม่ embed image bytes และไม่ copy images ต่อ version; annotation revision blobs เก็บถาวรตาม references ถ้า schema เป็นไฟล์แยก ต้อง pin path+hash และ include ใน portable package ด้วย Manifest hash เก็บใน DB/sidecar ไม่ใส่ในตัวเอง

Snapshot project settings ที่มีผลต่อข้อมูล เช่น task, orientation, self-review exception, group meaning, label policy และ serializer version; ไม่ snapshot passwords, network credentials หรือ runtime-only settings

### 13.5 Class schema evolution

- `class_id` UUID และ stable_key ไม่ reuse/rename; display_name เปลี่ยนได้ผ่าน schema ใหม่
- `export_index` เริ่ม 0 เพิ่มต่อท้ายและไม่ reassign ให้ class อื่น; schema history เก็บชื่อ ณ เวลานั้น
- Deactivate ไม่ลบ record; historical schema ยัง export ได้
- เพิ่ม/rename/deactivate schema ไม่แก้ annotation เก่า; editor แจ้ง SCHEMA_CHANGED แล้วโหลดใหม่
- Annotation migration เป็น revision ใหม่และ reset approval เสมอใน v1 แม้ rename-only; bulk migration มี dry-run, mapping, per-image conflicts และ audit
- Schema ใหม่เก็บ entries รวม inactive classes เพื่อคง export indices; YOLO names ใช้ contiguous historical slots 0..max index โดย inactive slot ยังมีชื่อเดิมและไม่มี new labels ใช้ slot นั้น
- ถ้าต้องการ compact/reorder indices เป็น future explicit exporter profile ที่มี mapping แยก; v1 ไม่ทำโดยปริยาย

### 13.6 Version diff

Diff `A→B` รายงาน image IDs added/removed, annotation content changed, group/metadata changed, schema added/renamed/deactivated และ counts ของ shapes created/deleted/class/geometry changes ตาม stable shape IDs

Asset bytes ของ image ID เดิมไม่เปลี่ยนได้ตาม invariant; replacement แสดง removed+added พร้อม replaces_image_id หากมี Same asset renamed = filename metadata change ไม่ใช่ new image ความต่างเฉพาะ revision author/time ไม่ถือเป็น semantic annotation change แต่แสดงเป็น revision provenance change ได้

Full version stats กับ working stats แยกชัดเจน: total images, approved/empty counts, per-class image count, per-class object count, class imbalance, groups, format/resolution distribution และ QC warnings

<a id="section-14"></a>

## 14. Dataset splitting

### 14.1 Inputs/outputs

Split เป็น immutable artifact **แยกจาก dataset version** จึงสร้างหลาย split ของ version เดียวกันได้โดยไม่แก้ released manifest Export ต้องระบุ split ID เสมอ

```json
{
  "strategy": "stratified_group",
  "ratios_bps": {"train": 7000, "val": 2000, "test": 1000},
  "seed": 42,
  "algorithm_version": "vl-split-1",
  "require_group_key": true,
  "missing_group_policy": "error",
  "strict_class_coverage": false,
  "size_tolerance_bps": 500,
  "class_tolerance_bps": 1000,
  "pinned_assignments": []
}
```

- UI รับ test/val percentages แล้ว train=100−test−val; ส่ง basis points ≥0 รวม 10,000 และ train>0
- หาก val/test=0 partition นั้นว่างได้; nonzero partition ต้องมีอย่างน้อยหนึ่ง effective group/image มิฉะนั้น infeasible
- `size_tolerance_bps` = absolute difference ระหว่าง realized image fraction กับ requested fraction; class tolerance วัดแต่ละ class fraction ใน partition เทียบ target fraction
- Seed integer 0..2³²−1; persist algorithm version/config/input hash/assignments/diagnostics; reproducibility ต้องรวมทั้ง version+algorithm ไม่ใช่ seed อย่างเดียว
- Output มี exact assignment ทุก image ใน source version หนึ่งครั้ง, effective group key, requested/actual image & group counts, class distributions, warnings และ manifest hash

### 14.2 Strategies

| Strategy | Unit ที่สุ่ม | Balance objective |
|---|---|---|
| random | image หรือ duplicate-connected component | Total image counts |
| stratified | image/component | Single-label class proportions; detection/segmentation ใช้ class-presence vector |
| group | effective group | Total image counts; group ห้ามแตก |
| stratified_group | effective group | Total counts + class-presence distribution |

Classification default stratified ถ้าไม่มี group; ถ้ามี group ให้ default stratified_group สำหรับ manufacturing ต้องกำหนด group ก่อน release/split เป็น default policy

### 14.3 Leakage invariants

1. Asset SHA-256 เดียวกันต้องไม่ปรากฏข้าม partitions ภายใน split แม้ import จากหลาย filename
2. Project-level UNIQUE asset ป้องกัน exact duplicates ส่วน group ป้องกันหลายมุม/หลาย frame ของ unit เดียวกัน
3. สำหรับ group strategies สร้าง effective groups เป็น connected components ของ same group_key **หรือ** same asset hash; ถ้า future มี duplicate image records ห้าม dedupe หลบ invariant
4. ถ้า group_key missing และ `require_group_key=true` ต้อง reject; otherwise ต้องเลือกระหว่าง error หรือ treat-as-singleton พร้อม warning ห้ามถือ null ทั้งหมดเป็นกลุ่มเดียวแบบเงียบ ๆ
5. Random/stratified เมื่อ dataset มี group metadata ต้อง warning ชัดว่าไม่คุ้มครอง group leakage; project policy `enforce_group_split=true` บังคับ reject strategies นี้
6. Group key เป็นหนึ่ง canonical leakage boundary ต่อภาพ; ถ้าต้องรวม lot/unit/sequence ที่เชื่อมกันต้อง resolve connected grouping ก่อน split ไม่ concatenate keys แล้วคิดว่าปลอดภัยโดยอัตโนมัติ
7. Near-duplicate pixels/semantically similar scenes ไม่รับประกันตรวจพบด้วย SHA-256; ให้ใช้ group policy ที่ถูกต้องและ manual QC

### 14.4 Deterministic algorithm v1

ไม่ใช้ global random state, Python `hash()` หรือ DB query order เป็น seed/source of order

1. Sort version items ด้วย image ID; build effective group components ตาม strategy และ leakage rules
2. Compute each group's image count และ class-image presence vector (ภาพมี class นั้นนับ 1 ไม่ใช่จำนวน objects; background เป็น pseudo-class `__empty__` สำหรับ balancing)
3. Compute target image/class counts ด้วย ratios; non-group exact target integer ใช้ largest remainder โดย tie order train,val,test
4. Apply pinned assignments ก่อน ถ้า group เดียวถูก pin สอง partitions ให้ fail
5. สำหรับ random ที่ singleton ทั้งหมด: order ด้วย SHA-256(`seed|algorithm_version|image_id`) แล้ว fill target counts
6. สำหรับ stratified/group variants: sort remaining groups ด้วย rarity contribution descending, size descending แล้ว stable SHA-256 tie-break; assign group ไป partition ที่ลด normalized squared error รวม total-size และ class-vector deviation มากที่สุด (weights total=1,class=1; group strategy class weight=0)
7. จำกัด deterministic improvement passes ไม่เกิน 20 รอบ: examine single-group moves และ pair swaps ตาม stable order รับเฉพาะ strict improvement, ห้ามฝ่าฝืน pins/nonzero partition constraints
8. บันทึก realized distributions และ residual errors; ไม่กล่าวว่าเป็น global optimum หรือ exact stratification เสมอ
9. หาก nonzero partition ว่าง ให้ deterministic repair เมื่อทำได้ก่อนรายงาน infeasible

Formal objective: `sum_p ((N_p - T_p)/max(1,N))^2 + mean_c sum_p ((C_cp - T_cp)/max(1,C_c))^2` โดย class term ปิดใน group/random mode. Rarity contribution = `sum_c group_class_count[c]/max(1,total_class_count[c])`; เปลี่ยน formula/ties/normalization ต้องเพิ่ม algorithm_version

เมื่อ objective เท่ากัน ให้เลือก partition ตามลำดับ train,val,test; comparison ใช้ rational arithmetic หรือ fixed precision ที่ระบุใน algorithm implementation พร้อม golden vectors ไม่ปล่อยให้ floating-point epsilon ต่าง platform เปลี่ยนผล ถ้าไม่มี class vectors ให้ class term=0 ส่วน pinned_assignments ใช้ `{image_id, partition}` และขยายไปทั้ง effective group ก่อนตรวจ conflict

### 14.5 Imbalance, feasibility และ acceptance

- Group atomicity มีลำดับสูงกว่า percentage target; ห้าม split group เพื่อให้เปอร์เซ็นต์ตรง
- คลาสที่มีเพียง 1 group ไม่สามารถอยู่ครบ 3 partitions; strict_class_coverage=true ต้อง fail เมื่อขาด coverage; false คืน warning พร้อม per-class counts
- Strict failure จาก heuristic ต้องระบุว่า “ไม่พบ assignment ที่ผ่านด้วย algorithm นี้” ไม่กล่าวพิสูจน์ mathematically impossible เว้นแต่มี necessary condition ชัดเจน เช่น groups<nonzero partitions
- หากเกิน tolerance return diagnostics และสร้าง preview/job result เป็น FAILED/needs configuration change; maintainer ต้องสร้าง request ใหม่ด้วย explicit relaxed tolerances พร้อม reason ไม่ silently relax
- Freeze test set ข้าม versions เป็น optional v1 feature ผ่าน pinned assignments: map เดิมด้วย asset hash/group identity, ตรวจ group merge conflicts, รายงานภาพใหม่/ภาพถูกลบ; ถ้าไม่ pin การสุ่มใหม่อาจย้ายภาพเดิมได้และ UI ต้องบอก
- Test-set leakage จากการนำ test เดิมกลับไป train ต้องแสดง diff/warning เมื่อเปรียบเทียบ splits ข้าม versions; ไม่อ้างว่าการใช้ seed เดิมตรึง test set

<a id="section-15"></a>

## 15. Import/export contract

### 15.1 Managed image import

1. Maintainer เลือก configured source alias + relative paths; server ไม่รับ arbitrary absolute path จาก client
2. Scan whitelist JPEG/PNG/BMP, size limits; reject corrupt/multiframe/unsupported file และ symlink/junction escapes
3. Copy bytes ไป staging พร้อม streaming SHA-256; decode staged bytes สำหรับ dimensions/orientation; verify bytes ที่ publish ไม่ใช่ source ที่อาจเปลี่ยนขณะอ่าน
4. หาก source size/mtime เปลี่ยนระหว่าง import ให้ retry bounded หรือ report `SOURCE_CHANGED`; hash staged bytes เป็นหลักฐานจริง
5. Publish immutable asset, insert project image/head revision0/provenance ใน transaction; identical hash คืน duplicate report และไม่สร้าง second image ใน project
6. CSV metadata import รองรับ original filename→group_key/attributes โดยต้อง report filename ambiguities และ require explicit resolution
7. Dry-run สรุป new/duplicate/invalid/unsupported และ class/group mappings; execution job มี per-file outcomes; partial import ต้องรายงานชัด ไม่อ้าง atomic batch ทั้งหมด

### 15.2 LabelMe และ YOLO detection import

- อ่าน LabelMe JSON โดยเขียน parser ของระบบเอง; map rectangle 2 points → normalized bounds, polygon→simple polygon; map labels ผ่าน explicit mapping ไป class IDs
- ใช้ imagePath ที่ resolve ภายใน allowed source root และ verify dimensions; embedded imageData ปิด default; unsupported shapes (circle/line/point) ต้อง error/report ไม่ drop
- EXIF orientation ambiguity ต้องให้ผู้ใช้ resolve ผ่าน explicit preprocessing/new asset ไม่เดาแล้วเลื่อน annotation
- YOLO detection input ใช้ supplied names mapping; parse exactly5 fields, class integer valid, finite normalized values, positive width/height, bounds valid; denormalize ด้วย raw width/height แล้ว semantic validate
- Missing YOLO label file ไม่เท่ากับ verified-empty; default UNLABELED ส่วน empty label file ให้ `verified_empty=true` ได้เฉพาะ explicit import option และยังต้อง review
- Imported annotation เป็น revision1 / IN_PROGRESS หรือ ANNOTATED เมื่อผ่าน completion; ไม่ auto APPROVED; source/tool/import options บันทึก audit/provenance
- ถ้าภาพมี annotation อยู่แล้ว import ห้าม overwrite; default conflict report, update mode ต้องมี per-image lease/expected revisions และสร้าง revision ใหม่

### 15.3 YOLO detection export

ใช้รูปแบบหนึ่ง object ต่อบรรทัด `class_index x_center y_center width height` ซึ่ง normalized ด้วย dimensions ภาพ ([official detection format](https://docs.ultralytics.com/datasets/detect/))

```text
cx = ((x1 + x2) / 2) / image_width
cy = ((y1 + y2) / 2) / image_height
w  = (x2 - x1) / image_width
h  = (y2 - y1) / image_height
```

- Export class index จาก pinned schema mapping; ห้ามใช้ class array position ของ working GUI
- Default accept rectangle projects เท่านั้น; polygon→bounding box เป็น optional explicit conversion `polygon_to_bbox=true` จาก segmentation version พร้อม loss-of-information warning/provenance; default reject ไม่ silently convert
- UTF-8/LF, sorted shapes by stable ID, normalized decimals9 places; verify quantized width/height >0 และ bounds หลัง rounding; ถ้า represent ไม่ได้ให้ error ไม่เขียน zero-size box
- Verified-empty ที่ approved ต้องมี zero-byte `.txt`; no unlabeled/skipped items ใน source version
- Filename ใช้ image UUID เพื่อกัน collisions; extension จาก validated asset; เก็บ original filenames ใน export manifest

```text
dataset/
  data.yaml
  images/train/<image_uuid>.jpg
  images/val/<image_uuid>.png
  images/test/<image_uuid>.jpg
  labels/train/<image_uuid>.txt
  labels/val/<image_uuid>.txt
  labels/test/<image_uuid>.txt
```

```yaml
# ผู้ใช้ให้ dataset root เป็น working directory หรือ materialize path ผ่าน helper
path: .
train: images/train
val: images/val
test: images/test
names:
  0: sponge
  1: spring
  2: tape
```

Exporter omit `test` เมื่อ ratio=0 และรายงานถ้า val=0 ว่า training consumer อาจต้องมี validation set Export README ต้องอธิบาย relative-path resolution ของ consumer และมี helper สร้าง local absolute `path` จาก export root เมื่อใช้งานนอก root; helper ไม่แก้ canonical export manifest/artifact แต่เขียน runtime config copy

### 15.4 YOLO segmentation export

หนึ่ง polygon ต่อบรรทัด `class_index x1 y1 x2 y2 ... xn yn` โดย normalize x ด้วย width และ y ด้วย height; ≥3 vertices ([official segmentation format](https://docs.ultralytics.com/datasets/segment/))

รองรับ simple polygon จาก segmentation project เท่านั้น; rectangle→polygon ปิด v1, holes/multi-rings ไม่รองรับ Validate อีกครั้งหลัง quantization เพื่อป้องกัน vertices ซ้อนหรือ area=0; error พร้อม image/shape IDs ไม่มี silent drop ใช้ directory layout เช่น detection แต่ไม่ผสม detect/segment row format ใน export เดียว

### 15.5 Classification export

สร้างโครงสร้าง `train/<class-folder>/<image_uuid>.<ext>`, `val/...`, `test/...` ตาม folder-based classification convention ([official classification format](https://docs.ultralytics.com/datasets/classify/))

แต่ละภาพต้อง approved และมี single label; multi-label export ปฏิเสธ Folder name ใช้ zero-padded export index + sanitized stable key เช่น `0000_ok`, `0001_ng`; prefix ความกว้างคงที่อย่างน้อย 4 digits ต่อ export และ include mapping ใน manifest เพื่อไม่สับสนกับ display names ชื่อทุกคลาสปลอดภัยบน Windows และไม่ชนเมื่อ case-fold

Classification consumer อาจจัด class indices ใหม่ตามโฟลเดอร์ที่พบ; manifest ต้องระบุ `folder_name`, `internal_class_id`, `schema_export_index`, `consumer_order` แยกกัน และ exporter ตรวจ train class coverage หากมีคลาสใน val/test แต่ไม่มี train ต้อง fail เว้น explicit evaluation-only artifact profile ซึ่งอยู่นอก v1

### 15.6 Export reproducibility/publication

- Input = version manifest hash + split manifest hash + exporter version + format/options; same input ต้องได้ file contents/checksums เดิม
- Copy bytes จาก immutable asset blobs; no image re-encoding, preprocessing หรือ augmentation
- Default copy เพื่อ portable export; ห้าม hardlink export ให้ผู้ใช้แก้แล้วกระทบ canonical asset
- Export manifest ระบุทุก relative file path, bytes, SHA-256, class mapping, conversion warnings, source image/revision references และ input hashes
- Export สร้างใน staging; validate count/path/labels/hash ครบแล้ว atomic publish directory และ mark READY ใน DB
- Zip reproducibility ถ้าให้ downloadable archive: sort entries, fixed timestamps, stable permissions/compression config; otherwise ระบุว่ารับประกัน file-level hashes ไม่ใช่ zip bytes
- ไม่มี metadata ล่าสุดจาก working project หลุดเข้า export; changed class name/group หลัง release ไม่กระทบ export เดิม

<a id="section-16"></a>

## 16. Security, operations และ backup

### 16.1 Confidentiality และ access

- No telemetry, cloud sync, auto update check หรือ external font/CDN fetch; dependency downloads เป็น provisioning step แยกจาก runtime ใน restricted network
- Roles enforce ทุก endpoint และ job ตอนทำงานจริง; resource IDs ไม่ใช่ authorization หากสิทธิ์ถูก revoke ระหว่าง job ให้หยุดก่อน publication และบันทึก outcome
- API image/content/export download ต้องตรวจ project membership; storage URLs ไม่เป็น public static mount
- Secrets เก็บ OS-protected store/service environment ที่ ACL จำกัด; redact Authorization, claim tokens และ password fields ใน logs
- Image decode ทำ background worker ที่มี memory/time/pixel limits; reject decompression bombs และ malformed data โดยไม่ crash GUI/service
- Path normalization ต้องตรวจ containment หลัง resolve และตรวจ reparse points บน Windows; zip imports ถ้ามีในอนาคตต้องมี zip-slip/size limits ก่อนเปิดใช้
- Local drafts/cache เป็นข้อมูลลับเช่นเดียวกับต้นฉบับ: OS user ACL, disk encryption ตามองค์กร, retention default30 วัน และ clear-cache action
- API rate limits และ file size limits บังคับฝั่ง server; ไม่พึ่ง UI validation

### 16.2 Health/logging/jobs

- Liveness หมายถึง process ตอบได้; readiness ตรวจ DB schema/storage writable/critical corruption/maintenance
- Structured logs มี request_id/job_id/entity IDs/latency/error code; ไม่ log full image paths หรือ annotation payload เป็น default
- Metrics local-only: save latency, conflicts, expired leases, queue depth, disk free, failed integrity checks, backup age
- Persistent jobs ใช้ bounded concurrency: default 1 heavy job เพื่อไม่ทำ annotation latency เสีย; import/export hashing ทำ streaming
- Job cancel เป็น cooperative; artifacts ที่ publish สำเร็จแล้วไม่ rollback/delete; job recovery หลัง restart ตรวจ committed result ก่อน execute ซ้ำ
- Schema migration ต้อง backup ก่อน, exclusive maintenance mode, version check และ fail-fast เมื่อ client/server incompatible

### 16.3 Backup contract

เป้าหมายเริ่มต้น RPO≤24 ชั่วโมง, RTO≤4 ชั่วโมง สำหรับ dataset baseline; ต้องวัดด้วย restore drill และปรับเมื่อขนาดจริงโต ห้ามอ้างว่าเพียง copy `.sqlite3` ขณะ WAL ทำงานเท่ากับ consistent backup

Backup v1 ใช้ maintenance window แบบเข้าใจง่าย:

1. เข้าสู่ read-only maintenance; หยุดรับ mutations, drain active transactions/jobs ถึง safe checkpoint และ invalidate leases
2. ใช้ SQLite online backup API เพื่อสร้าง consistent DB snapshot; ไม่ copy เฉพาะ main DB file ที่อาจขาด WAL
3. จาก snapshot enumerate all referenced assets, annotation/schema blobs, version/split/export manifests และ required export files; ไม่มี GC ระหว่าง backup
4. Copy files พร้อม checksums ไป backup set บน storage แยก; immutable blobs deduplicate ได้แต่ backup manifest ต้องอ้างครบ
5. เก็บ backup manifest, DB checksum, schema/app version, config ที่ไม่ใช่ secrets; backup secrets/keys แยกแบบ encrypted ตาม operator procedure
6. Verify DB integrity/foreign keys และ every referenced file; mark COMPLETE ต่อเมื่อครบ ถ้าขาดให้ FAILED ไม่แทนที่ latest good backup
7. ออกจาก maintenance; clients re-acquire leases หลัง reload

Default schedule nightly และก่อน migration/release ใหญ่; retention7 daily +4 weekly +3 monthly ปรับตาม storage; backup ที่แชร์ physical disk เดียวอย่างเดียวไม่ผ่าน DoD

### 16.4 Restore และ integrity

- Restore ไป directory ใหม่ ห้ามเขียนทับ live server ระหว่างทดลอง; verify backup manifest/checksums ก่อน start
- Run SQLite `integrity_check`, `foreign_key_check`, referenced-blob validation และ known golden export regeneration
- Claims ทั้งหมด invalidate; running jobs reconcile; tokens อาจ revoke ทั้งหมดเมื่อ restore เพื่อป้องกัน session resurrection
- เปรียบเทียบ manifest hashes ของ released versions ก่อน/หลัง restore ต้องตรง; API health ready ต่อเมื่อ checks ผ่าน
- Server ตรวจ hash ทุก asset ตอน ingest/release/export/backup; background integrity scan อย่างน้อยสัปดาห์ละครั้ง; cache hits อาจใช้ size/mtime เร่ง read แต่ไม่แทน cryptographic verification ใน integrity gates
- Corrupt blob quarantine และ restore ด้วย hash เดิมจาก backup; ไม่แก้ bytes แล้วคง SHA-256 filename เดิม

<a id="section-17"></a>

## 17. Phased implementation plan

แบ่ง phase ตาม functional slices ที่ใช้งานและตรวจสอบได้ ปรับจากลำดับ brainstorm โดยวาง API/storage/hash/review invariants ตั้งแต่ต้น เพื่อไม่ให้ prototype ที่เขียนไฟล์ตรงกลายเป็นฐานของ multi-user system โดยไม่ตั้งใจ

**ลำดับความสำคัญที่ยืนยันกับผู้ใช้:** เน้น rectangle annotation ที่ใช้งานคล่องก่อน โดย Phase 1 ทำ import→claim→rectangle→save→reload แล้วปรับ create/select/move/resize/delete, zoom/pan, shortcuts, undo/redo และ autosave/recovery ให้พร้อมใช้งาน ก่อนขยายไป workflow ของ phase ถัดไป ข้อกำหนด classification และ exit gate เดิมของ Phase 1 ยังคงอยู่

### Phase 0 — Contracts และ foundation

**Deliverables:** repository, pinned environment/license inventory, domain/schema package, migrations skeleton, storage abstraction, config, architectural tests, synthetic fixtures, decision records

**งาน:** กำหนด image coordinate/orientation policy, serialization vectors, ID/class schema rules, state machine และ error contracts; implement geometry validators และ hash/storage helpers

**Exit gate:** sample JSON ผ่าน schema+semantic tests; invalid shapes ถูก reject; license inventory ไม่มี unknown ใน baseline ที่เลือก; DB path check reject UNC/mapped-network location; README รัน dev server/client skeleton ได้

### Phase 1 — Rectangle workflow ใช้งานจริงแบบหนึ่งคน

**Depends on:** Phase0

**Deliverables:** Dear PyGui canvas, FastAPI local service, SQLite schema/core auth, project/class creation, safe image import, browser, rectangle CRUD, classification single-label, save/load/autosave/undo/recovery

**งาน:** ทุก save ผ่าน API แม้ single-user; SHA-256 ingest, immutable revisions, expected counters และ file-before-DB protocol ทำตั้งแต่ phase นี้ Lease ใช้จริงแม้มี client เดียว ไม่สร้าง direct filesystem writer ชั่วคราว

**Exit gate:** import100 synthetic images, annotate rectangle/classification, close/reopen แล้วข้อมูลตรง; zoom/pan/DPI ไม่เลื่อน coordinates; simulated crash ไม่เสีย committed data; rectangle workflow เป็นจุดผ่านหลักก่อนเริ่ม polygon

### Phase 2 — Team workflow และ review

**Depends on:** Phase1

**Deliverables:** LAN deployment, users/roles, assignments, atomic claim-next, heartbeat/revoke, revision conflict UI, complete/submit/approve/reject/reopen, audit browser

**งาน:** เพิ่ม permissions matrix, two-client race tests, stale token/generation rejection, reviewer queue และ self-review policy; read-only SMB mapping + API fallback

**Exit gate:** Engineer/Junior ทำงานสองเครื่องได้จริง; same-image race มีผู้ชนะคนเดียว; stale save ไม่ overwrite; expired claim recover ได้; reviewer reject แล้ว annotator แก้/submit ใหม่ได้; unauthorized project inaccessible ผ่าน API และ share

### Phase 3 — Polygon, QC และ immutable dataset versions

**Depends on:** Phase2

**ลำดับงานที่ผู้ใช้ปรับ:** ผู้ใช้ทดสอบ account/membership increment ของ Phase2 แล้ว และขอเริ่ม Phase3 บนคอมส่วนตัว โดยยอมให้เลื่อนเฉพาะการทดสอบที่ทำไม่ได้ในบ้าน (สองเครื่อง/LAN/SMB) ไปทดสอบที่บริษัท งาน implementation ที่ยังค้างใน Phase2 ไม่ถือว่าเสร็จ เริ่ม polygon และ working QC ที่เป็นอิสระก่อนได้ แต่ reviewed segmentation และ immutable approved release ยังต้องเชื่อม PR10 review evidence ให้ครบ รายละเอียด requirement IDs และงานค้างอยู่ใน `docs/phase3-plan.md`

**Deliverables:** polygon editor/validation, reviewed segmentation, QC/statistics, class schema migration, immutable release pipeline, version browser/diff และ snapshot manifests

**งาน:** ตรึง revision/schema/group/approval evidence; failure recovery ระหว่าง publish; initial backup/restore command ต้องมีสำหรับข้อมูลจริง

**Exit gate:** release v1 แล้วแก้ working data สร้าง v2; v1 bytes/hashes ไม่เปลี่ยน; diff ตรง golden fixture; corrupt/missing asset บล็อก release; schema migration ไม่ทำให้ old labels เปลี่ยนความหมาย

### Phase 4 — Reproducible splitting

**Depends on:** Phase3

**ลำดับงานที่ผู้ใช้ปรับเพิ่มเติม:** ผู้ใช้ขอเริ่ม Phase4 ต่อก่อน immutable release ใน Phase3 เสร็จ จึงทำ deterministic split engine และ standalone diagnostics preview ที่ทดสอบด้วย frozen synthetic projection ได้ก่อน โดย preview ไม่ใช่ canonical split และไม่ยืนยัน release provenance งาน PR15 ส่วน GUI, released-version verification และ immutable persistence ยังต้องเชื่อม PR10/PR13 ให้ครบก่อนใช้กับ dataset จริง รายละเอียดอยู่ใน `docs/phase4-plan.md`

**Deliverables:** random/stratified/group/stratified_group, seed/ratios UI, group validation, diagnostics preview, immutable split manifests, optional pinned test assignments

**งาน:** deterministic algorithm/golden assignments, rare-class infeasibility, leakage tests, tolerance handling และ split comparison

**Exit gate:** rerun inputs เดิมได้ assignments/hash เดิม; no group/hash leakage; actual percentages/class counts แสดงครบ; infeasible constraints ไม่ถูก relax เงียบ ๆ

### Phase 5 — Export และ legacy migration

**ลำดับงานที่ผู้ใช้ปรับเพิ่มเติม:** เริ่ม PR16 format conversion และ PR17 legacy dry-run ที่ทดสอบแยกได้ก่อน โดยรายงาน preview ไม่ใช่ canonical export/import งาน released-version verification, immutable split integration, publication และ canonical import ยังต้องทำครบก่อนผ่าน Phase5 exit gate ดู `docs/phase5-plan.md`

**Depends on:** Phase4

**Deliverables:** YOLO detect/segment, classification export, LabelMe/YOLO detection import, dry-run/mapping, export provenance/portable artifact

**งาน:** exact format validation, normalized-coordinate golden files, empty image handling, stable class mapping, collision-safe filenames, staged publication

**Exit gate:** fixture export parse ด้วย independent validator ได้; conversion geometry round-trip ภายใน tolerance; exported bytes ตรง pinned version; no runtime/import dependency on Ultralytics/LabelMe; legacy import report ไม่มี silent data loss

### Phase 6 — Production hardening และ handover

**ลำดับงานที่ผู้ใช้ปรับเพิ่มเติม:** ผู้ใช้ขอเริ่ม Phase6 ต่อ จึง harden backup/restore และทำ offline development wheel kit พร้อมคู่มือที่ทดสอบบนเครื่องนี้ได้ก่อน ไม่ถือว่างาน integration ใน Phase2–5, Nuitka production packaging หรือ global DoD ผ่านแล้ว รายการงานค้างและหลักฐานอยู่ใน `docs/phase6-plan.md`

**Depends on:** Phase5

**Deliverables:** Nuitka Windows packages, service scripts, HTTPS setup guide, backup scheduling/restore drill, offline installer instructions, license/SBOM bundle, operator/user guides, performance report

**งาน:** Windows clean-machine test, English UI/font/DPI/Unicode paths, 10-client load, disk-full/disconnect/restart tests, cache/secret policies, migration rehearsal

**Exit gate:** global DoD ข้อ 19 ผ่าน; Engineer และ Junior ทำ end-to-end acceptance journey บนสองเครื่อง; blocked egress test ยืนยันไม่มี external runtime calls; restore บนเครื่องใหม่แล้ว version hashes ตรง

### Phase 7 — Model prediction import และ BMP

**Phase 7 ที่ผู้ใช้เพิ่ม — Model prediction import และ BMP:** รับ YOLO detection `.txt`
รูปแบบ `class x_center y_center width height` จับคู่ชื่อเดียวกับภาพในโฟลเดอร์เดียวกัน
เช่น `spring_img.bmp`/`spring_img.txt` โดยมี explicit class mapping, GUI preview/import,
รายงานทุกภาพ และสร้าง revision ผ่าน service/lease เพื่อเปิดแก้กรอบต่อได้จริง
ไม่ต้องแปลงผ่าน LabelMe; ไม่ overwrite annotation เดิม; prediction เป็น IN_PROGRESS
ไม่ auto approve รองรับ BMP เพิ่มจาก PNG/JPEG โดยเก็บ raw bytes และ original raster
พิกัดเดิม แผนและหลักฐานอยู่ใน `docs/phase7-plan.md` งานค้าง Phase2–6 ยังต้องทำต่อ

**Exit gate:** PNG/JPEG/BMP import และ decode ได้; preview → import YOLO → เปิดกรอบ →
แก้ไข → save/reload ผ่านจริง; mapping ถูกต้อง; missing/empty แยกกัน;
import ซ้ำหรือภาพที่มี annotation/lease อยู่ต้องไม่เขียนทับงานเดิม

### Phase execution rule สำหรับ Codex

ทำทีละ phase จน exit gate ผ่านก่อนขึ้น phase ถัดไป สร้าง vertical slice ที่รันจริง ไม่สร้าง mock UI ที่บอกว่าสำเร็จทั้งที่ยังไม่ persist ห้ามเพิ่ม infrastructure นอก baseline เพื่อหลบ transaction/locking design การเลื่อน requirement ต้องระบุ ID, เหตุผล และ phase ใหม่อย่างชัดเจน

<a id="section-18"></a>

## 18. Tests และ verification plan

### 18.1 Test layers

| Layer | Test cases ขั้นต่ำ | หลักฐาน |
|---|---|---|
| Domain/unit | rectangle boundaries/degenerate, polygon intersection/winding, task constraints, class identity, workflow transitions, coordinate transforms | deterministic tests + edge fixtures |
| Schema/contract | JSON Schema, unknown fields, required counters, finite numbers, API errors, pagination, OpenAPI models | fixtures validate ทั้ง client/server |
| Storage/integration | ingest/hash/dedupe, annotation persistence, composite FK/project checks, schema migration | temp DB + real filesystem |
| Concurrency | claim race, save race, review race, revoke/expiry/heartbeat/restart, assignments | barriers/latches บังคับ interleavings ไม่ใช้ sleep เดา timing |
| Failure recovery | kill before/after file publish/DB commit/response, disk full, missing blob, storage outage, job restart | fault injection + invariant queries |
| Versioning | cutoff consistency, immutable released files, schema/group metadata pin, added/removed/diff | golden manifests/diffs |
| Split | coverage, ratio validation, deterministic shuffle, groups/null/rare classes/pins/ties | golden assignments + property tests |
| Adapters | LabelMe unsupported shapes, YOLO bounds/empty/missing labels, detect/segment/classify golden export | independent parser + normalized round-trip |
| Security | RBAC/cross-project IDs, token revoke, path traversal/junction, oversized decode, log redaction | negative tests |
| Desktop | rectangle/polygon/classification, dirty navigation, shortcuts/text focus, DPI/zoom, conflict/recovery | automated where stable + manual checklist |
| Operations | backup/restore/migration, packaging/clean install, blocked external egress | recorded rehearsal |
| Performance | p95/API/UI/import memory, concurrent10sessions | benchmark report ตามข้อ 4.3 |

### 18.2 Critical executable scenarios

**T01 — Simultaneous claim:** client A/B เริ่ม claim ภาพเดียวกันด้วย barrier; ต้องมี 201 หนึ่งรายการ อีกคน 423; active claim count=1

**T02 — Stale write:** A โหลด revision7, server มี revision8 แล้ว; A save expected7 ต้อง 409 และ revision8/hash ไม่เปลี่ยน

**T03 — Expired/revoked lease:** A lease หมด/revoked, B ได้ generation ใหม่; delayed A save/heartbeat ต้อง 409 แม้ A user เป็น maintainer

**T04 — Crash boundaries:** inject crash ทุก boundary ในข้อ 12.3; restart แล้ว committed head อ่านได้ checksum ตรง; orphan ไม่กลายเป็น head เอง

**T05 — Lost response/idempotency:** servercommitrevision8 แต่ response หาย; retry key/body เดิมต้องคืน revision8 ไม่สร้าง 9; key เดิม body ต่างต้อง 409

**T06 — Review race:** reviewer โหลด r7 แล้วมีการ reopen/แก้; approve r7 ด้วย stale counters ต้อง 409; ห้าม approved status ผูก r8 โดยผิดพลาด

**T07 — Empty distinction:** draft shapes=[]/empty=false submit ไม่ได้; complete empty=true→review→approved export เป็น empty txt; skipped ไม่เข้า version

**T08 — Immutable release:** releaseV1, renameclass/แก้ annotation/เปลี่ยน group/archiveimage ใน working; re-exportV1 ให้ hashes/classnames/assignment เดิม

**T09 — Consistent cutoff:** modify หลายภาพขณะ release; version items ต้องมาจาก cutoff เดียวและ release ไม่อ่าน head ใหม่ระหว่าง hashing

**T10 — SHA identity:** renamefile เดิม import ซ้ำไม่เพิ่ม image; re-encode ภาพเดียวกัน hash ใหม่ถือ new asset; ห้ามอนุมาน pixel equivalence จาก hash

**T11 — Split leakage:** fixture unit A มี 20frames, B มี 5, C มี 1; unit ไม่แตก; null policy/error ถูกต้อง; extreme ratios แสดง diagnostics

**T12 — Split reproducibility:** same manifest/config/algorithm ข้าม process และ DB insertion order ต่างกัน assignments เหมือนกัน; seed เปลี่ยนไม่จำเป็นต้องเปลี่ยนทุก assignment แต่ต้องไม่มี nondeterminism

**T13 — Rare classes:** class มี 1group, require ครบ 3partitions → fail พร้อมเหตุผล; relaxed policy ให้ warning ไม่ claim ว่า stratified สมบูรณ์

**T14 — Rectangle export golden:** image100×200, box(10,20,50,100) → `class 0.3 0.3 0.4 0.4` ตาม precisionprofile; inverse conversion error≤1e-5px สำหรับ fixture นี้

**T15 — Polygon export:** ≥3validvertices, correctx/y normalization; self-intersection/hole/roundingcollapse ถูก reject ไม่มี silentbbox conversion

**T16 — Class mapping:** class UUID เดิม/export_index เดิมหลัง rename/deactivate; releasedoldschema ยัง exportnames เดิม; classificationfolderconsumer mapping ชัดเจน

**T17 — Authorization/path safety:** userprojectA เข้าถึง image/exportprojectB ไม่ได้; `../`, UNCabsolute, encodedtraversal, junctionescapes ถูก reject ทั้ง import/download

**T18 — Backup restore:** restorecompletebackup ใน freshdir แล้ว integrity/FK/hash ผ่าน, noactiveclaims, releasedexports reproduce ได้

**T19 — Real two-PC workflow:** Engineer สร้าง project/assign; Juniorannotate/submit; Engineerrejectcomment; Junior แก้; Engineerapprove/release/split/export; ทุก action หา audit ได้

**T20 — Offline/confidentiality:** ปิด internet แต่ LAN ใช้ได้ทุก workflow; serverdown เก็บ localdraft; reconnect ไม่ autooverwrite; logs ไม่มี secret/content

### 18.3 Fixtures และ quality gates

- สร้าง synthetic images เอง ไม่มี confidential production data ใน repository/CI
- Fixture ชุดหลัก≥30 ภาพ, 3classes, classimbalance, 6groups, verifiedempty, rejected, corruptfile, duplicatebytes/differentnames, Unicode paths และ EXIFrotation; Unicode fixtures ทดสอบข้อมูลผู้ใช้ ไม่ใช่ภาษาของ UI
- Property tests: shape coordinates อยู่ bounds, deterministic serializer, no split overlap, union(partitions)=versionitems, group/hash หนึ่ง partition, roundtrip ไม่สลับ class
- ห้ามทดสอบ export ด้วยการเรียก productionfunction เดียวกันแล้วเทียบตัวเอง; independent parser/golden expectedfiles ต้องตรวจ behavior
- ไม่ติดตั้ง Ultralytics ใน core CI เพื่อ verify format; downstream consumer smoke test ทำแยกจาก distributedcore ได้เมื่อองค์กรอนุญาตและไม่ใช่ license bypass
- Required checks: formatting/lint/type checks ตาม tooling ที่ pin, unit/contract/integration/concurrency/recovery tests, dependency/licensegate, package smoke test; รายงาน knownfailures ตรงไปตรงมา
- ทุก release ต้องแนบ manual desktop/restore results; percentcoverage อย่างเดียวไม่แทน criticalscenario gates

<a id="section-19"></a>

## 19. Definition of Done

### 19.1 Feature-level DoD

- [ ] Requirement ID และ phase ชัดเจน; UI/API/DB behavior ตรง contract
- [ ] Happy path, validation, authorization, stale/concurrent state และ failure paths ที่เกี่ยวข้องผ่าน
- [ ] ไม่มี silentoverwrite, silentdrop หรือ silentlossyconversion
- [ ] Canonical writes ผ่าน service และมี audit/idempotency ตาม scope
- [ ] Migration/backward compatibility และ docs อัปเดตเมื่อ schema/API เปลี่ยน
- [ ] ไม่มี newdependency ที่ยังไม่ผ่าน licenseinventory
- [ ] UI แสดง loading/saved/error/conflict จริงตาม server state

### 19.2 v1 product DoD

- [ ] Engineer/Junior ใช้บนสองเครื่องใน LAN ได้ตั้งแต่ import จน export ตาม T19
- [ ] Rectangle ใช้งานคล่อง, polygonvalid, classificationsingle-label ทำงานครบ; shortcuts/undo/autosave/recovery ผ่าน
- [ ] DB อยู่ serverlocaldisk; desktop ไม่มี DBcredentials/directwrite และไม่มี canonicalsharewritepermission
- [ ] Claim/lease/fencing/optimisticlocking ผ่าน race/crash tests ไม่มี last-writer-wins
- [ ] Review ผูก exactrevision/hash/schema; rejected/empty/skipped แยกกันถูกต้อง
- [ ] Immutableassets/revisions/releases และ classschema ไม่เปลี่ยนย้อนหลัง; history/diff/query ได้
- [ ] Split reproducible, group-aware/stratified, ไม่มี group/hashleakage และแสดง ratio/coverage ข้อจำกัด
- [ ] YOLOdetect/segment/classificationexport ผ่าน independentvalidation และมี provenance/checksums
- [ ] LabelMe/YOLO detectionimport มี dry-run และ loss/conflict reports
- [ ] Backup/restore บน freshlocation ผ่านและ releasedhashes ตรง; operators ทำตาม guide ได้
- [ ] PackagedWindowsclient/server ใช้ English-only application text และผ่าน cleanmachine/offlineLAN tests, Unicode paths และ DPI
- [ ] Permission/secret/path/sizevalidation ผ่าน; noexternalruntimeegress
- [ ] License/SBOM/notice/lockeddependencies ครบ; ไม่มี copyleft หรือ unknownlicense ใน distributedcore
- [ ] Performance ตาม baseline วัดแล้วและผ่าน หรือมี approvedADR ปรับ target พร้อมข้อมูลจริงก่อน productionrelease
- [ ] README, userguide, operatorguide, recoveryrunbook, API/OpenAPI, changelog และ knownlimitations พร้อมส่งต่อ

### 19.3 Handover artifacts

1. Source repository + taggedrelease + reproducibledependencylock
2. Desktop/server packages + checksums + setup/uninstall instructions
3. OpenAPI document, annotation/manifest/split/export JSON Schemas และ migration scripts
4. Synthetic sampleproject และ goldenreleaseddataset/export
5. Test/benchmark/license reports, SBOM และ THIRD_PARTY_NOTICES
6. Backup/restore/incident guides พร้อมผล restore drill

<a id="section-20"></a>

## 20. Implementation checklist และข้อห้ามสำคัญ

### 20.1 เริ่ม repository ตามลำดับนี้

1. อ่านเอกสารทั้งหมด สร้าง requirement-to-test matrix และ ADR จากข้อ 2
2. สร้าง contracts/domain ก่อน GUI/ORM; pin serializer,geometry,workflow behavior
3. สร้าง schema migration และ storage protocol พร้อม crash tests
4. ทำ verticalslice: import หนึ่งภาพ→claim→rectangle→save→reload
5. เพิ่ม team/review ก่อนเปิดใช้ข้อมูลร่วมกันจริง
6. ทำ release/split/export ด้วย immutableinputs และ goldenfixtures
7. แพ็ก/restore/ทดสอบสองเครื่อง แล้วจึงประกาศ v1 พร้อมใช้

### 20.2 ห้ามทำ

- ห้ามให้ GUI เขียน annotation JSON/SQLite ลง sharedfolder โดยตรง
- ห้าม save ทับไฟล์ revision เดิมหรือปล่อย releasedmanifest ชี้ workinghead
- ห้ามถือว่า filename/path/mtime เป็น assetidentity
- ห้ามใช้ claim โดยไม่ตรวจ revision หรือใช้ revision โดยไม่ตรวจ claimgeneration ใน sharedediting
- ห้าม approve โดยไม่ตรวจ revision/hash และสิทธิ์ review
- ห้ามสุ่ม split แบบ image-level โดยไม่แจ้งเมื่อ group policy จำเป็น
- ห้าม normalizecoordinates เป็น canonicalformat แล้วทิ้ง pixelgeometry เดิม
- ห้าม silentlyrenumberclasses หรือ ignoreunknownimport shapes
- ห้ามเพิ่ม Ultralytics/LabelMe runtime เข้า core เพื่อความสะดวก
- ห้ามทำ microservices/full-offlinesync/trainingmodule ก่อน baseline ครบ

<a id="section-21"></a>

## 21. แหล่งอ้างอิงและขอบเขตการตรวจสอบ

ตรวจเอกสารต้นทางวันที่ 3 ตุลาคม 2026 ลิงก์เหล่านี้ใช้ยืนยัน format/architecture considerations และ license บางรายการ ส่วน schema, API, algorithms, thresholds และ phase gates ในเอกสารนี้เป็น**ข้อกำหนดการออกแบบของ VisionLabel/DataTracking** ไม่ใช่ข้ออ้างว่าต้นทางกำหนดไว้เช่นเดียวกัน

| แหล่งข้อมูล | ใช้ประกอบ |
|---|---|
| [Dear PyGui LICENSE](https://github.com/hoffstadt/DearPyGui/blob/master/LICENSE) | MIT ของ GUIlibrary |
| [FastAPI LICENSE](https://github.com/fastapi/fastapi/blob/master/LICENSE) | MIT ของ APIframework |
| [SQLite over a network](https://www.sqlite.org/useovernet.html) | เหตุผลให้ DB อยู่ localdisk หลัง API |
| [SQLite copyright](https://www.sqlite.org/copyright.html) | Public-domain status ซึ่งแยกจาก MIT/BSD/Apache |
| [Ultralytics documentation](https://docs.ultralytics.com/) | Licensing options และเหตุผลไม่ bundle runtime |
| [YOLO detection datasets](https://docs.ultralytics.com/datasets/detect/) | Detectionlabel/layoutcontract |
| [YOLO segmentation datasets](https://docs.ultralytics.com/datasets/segment/) | Polygonexportcontract |
| [Classification datasets](https://docs.ultralytics.com/datasets/classify/) | Folder-basedclassificationformat |

ก่อนเลือก exact dependency versions ให้ตรวจ LICENSE/SBOM ของ artifacts จริงตาม Phase0; เอกสารนี้ไม่ล็อกหมายเลข release ของ third-partylibrary ที่ยังไม่ได้ build/test ใน environment ของทีม
