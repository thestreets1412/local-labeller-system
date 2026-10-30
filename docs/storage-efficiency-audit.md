# Storage efficiency audit — VisionLabel / DataTracking

วันที่สำรวจ: 2026-10-28  
Source baseline: `notification-to-button` @ `9c0e8e4f85e1c10f5607a99b5a88ca3553247e16`  
สถานะ: **สำรวจและเสนอแนวทางเท่านั้น — ยังไม่แก้โปรแกรมหรือข้อมูล**

## 1. ปัญหาและขอบเขตหลักฐาน

ผู้ใช้รายงานว่าเครื่องที่บริษัทมีภาพประมาณ 5,400 ภาพ รวมประมาณ 1.5 GB
แต่โฟลเดอร์ root ที่กำหนดให้ VisionLabel โตประมาณ 10 GB ทั้งที่เพิ่งทำหนึ่งงาน
ข้อมูลเพิ่มเติมจากผู้ใช้วันที่ 2026-10-28:

| ส่วน | ขนาดที่ผู้ใช้รายงาน |
| --- | ---: |
| `inbox` | 0 KB — ผู้ใช้ลบต้นทางออกแล้ว |
| `managed/assets` | 4.63 GB |
| `managed/projects` | ประมาณ 19.2 MB |
| `export-cache` | 13.9 GB |
| `db` | 169 MB |

ยอดรวมโดยประมาณ 18.7 GB (หน่วยตามที่ผู้ใช้รายงาน ยังไม่แยก GB/GiB)
ทำให้ระบุได้ว่า export-cache เป็นส่วนใหญ่ประมาณ 74% และ inbox ไม่ใช่สาเหตุปัจจุบัน
ส่วน assets ที่มากกว่าภาพต้นทางประมาณ 1.5 GB ยังต้องตรวจ file/hash/reference inventory
ไม่สามารถสรุปว่า 3.13 GB ที่ต่างกันเป็นภาพซ้ำหรือลบได้ทั้งหมด
แผนถัดไป: [Phase 11 — Storage efficiency and retention](phase11-plan.md)

**ขอบเขตที่ผู้ใช้ยืนยันเพิ่มเติม:** Phase 11 จัดการข้อมูลเฉพาะภายใน service root
ที่กำหนดเท่านั้น ไม่สแกนหรือจัดการ AppData/client cache, โฟลเดอร์ข้างเคียง,
export หรือ backup ภายนอก root และไม่ตาม junction/symlink ออกไป
ข้อเสนอ client-cache และการลบ orphan ที่ต้องตรวจ backup ภายนอกในรายงานต้นฉบับด้านล่าง
จึงอยู่นอก Phase 11 ฉบับรีวิวแล้ว ส่วน assets ตรวจและรายงานอย่างเดียว
รายละเอียดขอบเขตและการทดสอบอยู่ในแผน Phase 11 ซึ่งมีผลเหนือข้อเสนอสำรวจเดิม

การสำรวจนี้อ่าน source ของ import, immutable storage, annotation save,
checkpoint/restore, export, desktop cache และ backup รวมถึงค้นหาจุดเขียน/คัดลอกภาพ
ไม่ได้เข้าถึงดิสก์บริษัท ไม่ได้วัดข้อมูลจริง และยังไม่ทราบจำนวน export/backup
จึงยืนยันพฤติกรรมของโค้ดและสัดส่วนโฟลเดอร์จากรายงานผู้ใช้ได้
แต่ยังไม่ทราบรายการใดใน assets/cache ที่คืนพื้นที่ได้อย่างปลอดภัย
รุ่นที่ติดตั้งที่บริษัทอาจต่างจาก baseline นี้ ต้องตรวจรุ่นประกอบด้วย

คำว่า root ต้องแยกให้ชัด: `visionlabel.launcher --root ...` กำหนด service data root
แม้ผู้ใช้จะตั้งชื่อโฟลเดอร์ว่า VisionLabel ก็ตาม ส่วน desktop cache อยู่คนละตำแหน่งโดยปริยาย
([launcher.py](../src/visionlabel/launcher.py), [cli.py](../src/visionlabel/cli.py))

## 2. ข้อสรุปสำคัญ

1. **Canonical image storage มีการเก็บภาพไบต์เดียวกันครั้งเดียวอยู่แล้ว ภายใน service root เดียวกัน**
   ชื่อไฟล์ไม่ใช่ตัวตัดสิน ภาพเดียวกันเปลี่ยนชื่อแล้ว import ไม่ควรทำให้ส่วนนี้เพิ่มอีกหนึ่งชุด
   หลาย project ใน root เดียวกันใช้ asset เดียวกันได้ แต่คนละ service root ไม่ได้แชร์ storage
2. **Checkpoint และการ save annotation ไม่คัดลอกภาพทั้งชุด**
   เก็บ metadata/annotation และอ้างอิง hash ของภาพเดิม จึงไม่จำเป็นต้องเลิก versioning เพื่อประหยัดภาพ
3. **Prepare export ที่สำเร็จสร้าง ZIP พร้อมภาพจริง และยังไม่มีนโยบายจำกัด/ล้าง ZIP เก่า**
   การ prepare ใหม่หลังงานสำเร็จสร้าง job ใหม่ได้ แม้ข้อมูลไม่เปลี่ยน
4. **Save dataset เก็บภาพเป็นไฟล์จริงอีกหนึ่งชุดต่อ destination**
   นี่เป็นสำเนาสำหรับนำไปเทรนและย้ายเครื่องได้ แต่หลาย export version จะมีภาพเดิมซ้ำกัน
5. **Inbox ยังเก็บไฟล์ต้นทางหลัง import** จึงอาจมีภาพสองชุดตั้งแต่เริ่ม: inbox + managed assets
6. Metadata ก็โตสะสมได้ โดยเฉพาะ operation preview และ export snapshots
   ต้องวัดจริง ไม่ควรสรุปว่าเล็กเสมอเมื่อมี annotation/revision จำนวนมาก

## 3. แผนที่ storage ปัจจุบัน

| ตำแหน่ง | สิ่งที่เก็บ | ภาพซ้ำ/การสะสม | Lifecycle ที่พบ |
| --- | --- | --- | --- |
| `<root>/inbox/` | ภาพต้นทางและ label ที่นำเข้า | ซ้ำกับ managed assets หลัง import; ไฟล์ชื่อใหม่ที่ bytes เหมือนกันอาจยังอยู่ใน inbox หลายไฟล์ | Import ไม่ย้ายหรือลบต้นทาง |
| `<root>/managed/assets/sha256/` | ภาพ canonical ตาม SHA-256 | หนึ่งไฟล์ต่อ bytes เดียวกันใน root เดียวกัน | เก็บถาวร; ไม่มี automatic blob GC |
| `<root>/managed/projects/<id>/annotations/` | Annotation JSON แต่ละ revision | เก็บประวัติ annotation ไม่มี raster ฝังอยู่ | เก็บประวัติ; save เนื้อหาเดิมมี no-op path |
| `<root>/managed/projects/<id>/checkpoints/` | Snapshot JSON อ้างอิงภาพ/annotation/schema | ไม่มีภาพทั้งชุด; ขนาดเพิ่มตามรายการและจำนวน snapshot | เก็บสำหรับย้อนเวอร์ชัน |
| `<root>/managed/projects/<id>/dataset-operations/` | Preview JSON: before/target inventories, target annotation content, diff | ไม่มีภาพ แต่ preview ใหญ่หรือหลายครั้งอาจกินพื้นที่มาก | Pending operation ใช้งานได้ 24 ชั่วโมง; หมดอายุไม่ได้แปลว่าลบไฟล์ |
| `<root>/export-cache/<job-id>.zip` | Dataset archive รวมภาพที่ export ได้จริงและ label | สำเนาภาพหนึ่งชุดต่อ successful export job | ไม่พบ TTL, quota หรือ eviction ของ successful ZIP |
| `<root>/db/` | SQLite: metadata, audit, jobs, export candidates/results และข้อมูลอื่น | มี snapshot JSON ซ้ำตามการทำงาน; ต้องวัด DB และ WAL แยก | ไม่พบ cleanup policy ของ export candidates ใน source ที่สำรวจ |
| `%LOCALAPPDATA%/VisionLabel/<scope>/*.cache` | ภาพ bytes ต้นฉบับที่เข้ารหัส DPAPI | สำเนาฝั่ง client; SHA เดียวกันหนึ่งไฟล์ต่อ scope | จำกัด 1 GiB/30 วันต่อ scope เมื่อ prune ทำงาน |
| Desktop scope: `.draft`, `.archived-draft`, `.cursor` | Recovery annotation และตำแหน่งการทำงาน | ไม่ใช่ภาพ; archived drafts สะสมได้ | ไม่พบ retention ของ archived drafts |
| ปลายทาง **Save dataset** | Dataset แตก ZIP พร้อมภาพจริง | หนึ่งสำเนาต่อโฟลเดอร์ที่บันทึก | ผู้ใช้เป็นเจ้าของ output; โปรแกรมไม่ล้างให้อัตโนมัติ |
| ปลายทาง backup | DB snapshot และ managed blobs ที่อ้างอิง | แต่ละ backup เป็นสำเนาของข้อมูลที่เลือกเก็บ | ไม่ใช่ incremental backup; ไม่รวม inbox/export-cache/client cache |

**อย่ารวมตำแหน่งนอก root เข้าในยอด 10 GB โดยอัตโนมัติ:** desktop cache อยู่ AppData
ส่วน export/backup อยู่ปลายทางที่เลือก ต้องตรวจว่าอยู่ใต้โฟลเดอร์ที่ผู้ใช้วัดจริงหรือไม่
ถ้าเป็นโฟลเดอร์ checkout/installation ให้แยก `.git`, `.venv`, wheels และ runtime data ด้วย

## 4. หลักฐานจาก source

### 4.1 ภาพชื่อใหม่ไม่ได้ทำให้ canonical storage ซ้ำ

- [service.py](../src/visionlabel/service.py), ประมาณบรรทัด 1057, 1123–1186:
  อ่านชนิดภาพจากเนื้อหา, ค้น `(project_id, asset_sha256)`, ใช้ path
  `assets/sha256/<prefix>/<sha>.<extension>` และ reuse image ID เมื่อพบภาพเดิมใน project
- [imaging.py](../src/visionlabel/imaging.py), `image_header`, บรรทัด 20 เป็นต้นไป:
  extension มาจาก header (`jpg`/`png`/`bmp`) ไม่ได้มาจากชื่อ `.jpg` เทียบ `.jpeg`
- [storage.py](../src/visionlabel/storage.py), `BlobStore.publish`, บรรทัด 57:
  หาก immutable target มีอยู่แล้วและ bytes ตรงกัน ไม่สร้างสำเนาถาวรอีกไฟล์
- ภาพดูเหมือนกันแต่ถูก encode ใหม่หรือแก้ metadata จน bytes ต่างกัน ถือเป็นคนละ asset
  ไม่ควรใช้ความคล้ายทางสายตารวมไฟล์อัตโนมัติ เพราะต้องรักษา raw bytes และหลักฐานเดิม

### 4.2 Save / checkpoint / delete

- [service.py](../src/visionlabel/service.py), บรรทัด 780–813:
  save เขียน annotation JSON ใหม่เมื่อเนื้อหาเปลี่ยน ใช้ `asset_sha256` อ้างอิงภาพเดิม
- [checkpoints.py](../src/visionlabel/checkpoints.py), บรรทัด 37, 190–202, 248–278:
  snapshot เก็บ asset/annotation paths และ hashes; checkpoint เป็น JSON
  แต่ operation preview เก็บ annotation content ของ target เพิ่มด้วย
- [checkpoints.py](../src/visionlabel/checkpoints.py), บรรทัด 214, 245:
  expiry ตรวจสิทธิ์ใช้งาน pending operation ไม่ได้ลบ payload บนดิสก์
- [service.py](../src/visionlabel/service.py), บรรทัด 509–528:
  delete image ทำ archive/tombstone และระบุ `evidence_retained`; ไม่ใช่การคืนพื้นที่ภาพทันที
- [phase10-plan.md](phase10-plan.md) ระบุการรักษา checkpoint/pending operation references
  และยังไม่มี automatic blob garbage collection

### 4.3 Export เป็นจุดสะสมภาพที่ยืนยันจากโค้ดได้

- [export_ui.py](../src/visionlabel/export_ui.py), `prepare`, บรรทัด 659–741:
  หลังสำเร็จ reset `request_key` จึงสร้าง key ใหม่ในการ prepare ครั้งถัดไป
- [working_export.py](../src/visionlabel/working_export.py), `start_export`, บรรทัด 159 เป็นต้นไป:
  idempotency ป้องกัน retry ของ key เดิม แต่ไม่มี semantic reuse ของทุกงานที่ input เหมือนกัน
- บรรทัด 447, 468, 483–496: สร้าง `<job-id>.zip` ด้วย `ZIP_STORED`
  และเขียน raw image bytes ลง archive ไม่ใช่แค่ manifest อ้างอิงภาพ
  แต่ละภาพอยู่ partition เดียว: train/val/test ไม่ได้คูณภาพเป็นสามชุดภายใน export เดียว
- เมื่อ prepare สำเร็จแล้ว แม้ยังไม่ Save dataset ก็มี archive อยู่บน server
  หากหยุดอยู่ที่ review confirmation ก่อนเริ่ม job จะมี snapshot metadata แต่ยังไม่มี ZIP ชุดนั้น
- บรรทัด 636–651: `EXPORT_EXPIRED` คือการตอบเมื่อไม่พบไฟล์ ไม่ใช่หลักฐานว่ามี timer ลบ ZIP
- บรรทัด 606 ใน failure cleanup ลบ partial/archive ของงานล้มเหลว ไม่ใช่ retention ของงานสำเร็จ

### 4.4 พื้นที่ชั่วคราวระหว่าง export

- [client.py](../src/visionlabel/client.py), `download_export`, บรรทัด 75:
  ดาวน์โหลด ZIP ใน `.visionlabel-download-*` ข้าง destination
- [working_export.py](../src/visionlabel/working_export.py), `_extract_verified_archive`, บรรทัด 667:
  แตกลง `.visionlabel-export-*` แล้ว rename โฟลเดอร์ dataset ไป destination
- เมื่อจบปกติ ZIP ชั่วคราวถูกเก็บกวาด และ rename ไม่สร้าง dataset สำเนาถาวรอีกชุด
  ระหว่างทำงาน client ต้องมีพื้นที่ประมาณ **ZIP + dataset ที่แตก**
  ถ้า server/client อยู่ volume เดียวกัน ยังมี server ZIP อีกชุดอยู่ด้วย
- Import ใช้ `decode-job-*` scratch และ cleanup ใน finally
  ([service.py](../src/visionlabel/service.py), บรรทัด 923, 998)
  Desktop decode ใช้ temporary input แล้วลบใน finally ไม่ได้เก็บ RGBA ของทุกภาพลงดิสก์
- การปิด process แบบฉับพลันอาจทิ้ง temporary files; ยังไม่พบ startup scavenger
  สำหรับ directory เหล่านี้ ต้องตรวจจำนวน/ขนาดจริงก่อนให้ความสำคัญ

### 4.5 Client cache และ backup

- [client.py](../src/visionlabel/client.py), บรรทัด 153–250:
  cache scope ผูก server URL + user ID; cap 1 GiB ไม่ใช่ global cap ของทุก scope
  prune ทำเมื่อเปิด store และเพิ่ม cache ใหม่ อายุ/ลำดับใช้ file mtime ไม่ใช่ last access
- [desktop.py](../src/visionlabel/desktop.py), บรรทัด 508:
  reconnect สำเร็จล้าง cache ของ previous store ถ้ามี แต่ไม่ได้กวาดทุก scope ที่เคยใช้
- [operations.py](../src/visionlabel/operations.py), `references` และ `_backup_snapshot`, บรรทัด 49, 88:
  backup DB และ assets/schemas/annotation revisions/checkpoints/operations ที่อ้างอิง
  ไม่รวม export-cache หรือ inbox; แต่ละ backup คัดลอก managed files จริง

## 5. ตัวอย่างการเพิ่มพื้นที่ — ไม่ใช่ผลวัดบริษัท

สมมติ export รวมภาพครบประมาณ 1.5 GB:

| รายการ | ตัวอย่างพื้นที่ |
| --- | ---: |
| Inbox | 1.5 GB |
| Managed assets | 1.5 GB |
| Prepare สำเร็จ 4 jobs ที่ยังเก็บ ZIP อยู่ | ประมาณ 6 GB |
| รวมเฉพาะสามรายการใน service root | ประมาณ 9 GB + metadata |

ตัวอย่างนี้แสดงว่า **งานเดียวก็โตหลายเท่าได้** หากมี export archive สะสม
ไม่ได้ยืนยันว่าผู้ใช้ prepare สี่ครั้ง หรือ metadata จริงมีขนาด 1 GB
ถ้ามี saved dataset/backup ใต้โฟลเดอร์ที่วัด ก็ต้องบวกตามตำแหน่งจริง
ถ้าไม่เคย prepare สำเร็จ สมมติฐาน export-cache ต้องลดความสำคัญและตรวจส่วนอื่นแทน

ขนาดควรแยก GB (ฐานสิบ) / GiB (ฐานสอง) และ logical size / size on disk
ไฟล์ annotation เล็กจำนวนมากอาจมี allocation overhead จึงไม่ควรใช้เฉพาะขนาดภาพประมาณการ

## 6. แนวทางปรับปรุงที่เสนอ — ยังไม่อนุมัติ implementation

### ลำดับ 1: ลดการสะสมสำเนาที่สร้างใหม่ได้

| ID | ข้อเสนอ | ประโยชน์และเงื่อนไข |
| --- | --- | --- |
| STOR-01 | Storage usage report: แยก inbox, unique assets, shared assets, annotation/history, export cache, temp, DB และ client cache | รู้ตำแหน่งที่กินพื้นที่จริง พร้อม bytes, file count, อายุ, reclaimable estimate; project ที่แชร์ asset ต้องไม่บวกขนาดภาพซ้ำ |
| STOR-02 | Export-cache retention พร้อม quota/age, pin และรายการ preview ก่อน cleanup | ผลตอบแทนสูงถ้า ZIP สะสม; ห้ามลบงานกำลัง build/download; เก็บ export provenance/manifest และบอกผู้ใช้ว่า cache หมดอายุอย่างไร |
| STOR-03 | Reuse prepared export เมื่อ frozen input และตัวเลือกเท่ากัน | ป้องกัน prepare ซ้ำคูณพื้นที่; key ต้องรวม image/annotation/schema/review identities, mapping, split options/algorithm และ converter version; ตรวจ authorization ทุกครั้ง |
| STOR-04 | แยกการ validate/preview ออกจากการ materialize ZIP | Preview ไม่จำเป็นต้องเก็บภาพทั้งชุด; ZIP สร้างเมื่อต้อง download พร้อมรักษา frozen snapshot และ checksum verification |

**Retention ไม่ควรกลายเป็นการเปลี่ยนผล export ย้อนหลัง:** ต้องรักษา manifest, source hashes,
schema/mapping, splits และ converter version ก่อนทำให้ ZIP เป็น cache ที่ลบได้
ถ้ารุ่น converter เก่าไม่มีแล้ว ห้ามอ้างว่าสร้าง bytes เดิมกลับมาได้
ควรมี pinned export สำหรับงานที่ต้องเก็บ artifact เดิม และอธิบาย unavailable/rebuild/new export ให้ชัด
ห้ามใช้ข้อมูล working ปัจจุบันแทน frozen snapshot โดยเงียบ ๆ

### ลำดับ 2: ลดสำเนาตอนนำเข้าและฝั่ง desktop

- **STOR-05 — Inbox lifecycle:** เสนอ import แบบนำไฟล์ที่ตรวจสำเร็จออกจาก inbox
  โดยเลือกนโยบายชัดเจน ไม่ลบต้นทางของผู้ใช้โดยปริยาย ต้อง publish + commit + verify สำเร็จก่อน
  รองรับ crash/retry, concurrent imports, paired YOLO labels และไฟล์ที่ยัง copy ไม่เสร็จ
  หรือเพิ่ม direct ingestion ที่ไม่บังคับ staging สำเนาทั้งชุดใน inbox เป็นงานถัดไป
- **STOR-06 — Global client cache budget / temporary cleanup:** จำกัดพื้นที่รวมทุก scope ของ
  Windows user, แสดง cache usage และ Clear image cache ที่แยกจาก recovery drafts;
  temporary cleanup ต้องตรวจ active job/ownership/age ก่อน ไม่ลบตามชื่อ wildcard อย่างเดียว
- **STOR-07 — Expired preview/candidate retention:** เก็บหลักฐานขั้นต่ำที่จำเป็น แล้วจัดการ
  payload ของ preview/confirmation ที่หมดอายุหรือยกเลิกแบบมี audit และ reference checks
  ประโยชน์ขึ้นกับปริมาณ metadata จริง ให้ทำหลังวัด

### ลำดับ 3: หลาย training versions ใช้ภาพร่วมกัน

- **STOR-08 — Optional shared training asset pool:** ออกแบบโหมด local workspace
  ให้เก็บภาพตาม hash ร่วมกัน ส่วนแต่ละ version เก็บ labels/schema/split manifest แยก
  และมีคำสั่ง materialize portable dataset เมื่อต้องย้ายเครื่อง
- ต้องทดลองกับ training loader ที่ใช้งานจริง โดยเฉพาะการจับคู่ image path กับ label path
  และกรณี label/class mapping เปลี่ยนแต่ภาพเดิม ห้ามแชร์ mutable label ระหว่าง versions
- ไม่ควรเชื่อมไฟล์ output ที่ผู้ใช้/เครื่องมือเทรนแก้ได้เข้ากับ canonical asset แบบที่การเขียน
  output ไปเปลี่ยนต้นฉบับได้ ต้องออกแบบ isolation และทดสอบการแก้/ย้าย/ลบไฟล์ก่อน
- คง portable export เป็นทางเลือก เพราะ dataset ที่อาศัย pool ไม่ใช่โฟลเดอร์ย้ายเดี่ยวแล้วใช้ได้ทันที

### งานที่ไม่ควรเริ่มเป็นอันดับแรก

- ไม่สร้าง dedup by hash อีกระบบซ้อน canonical assets เพราะมีอยู่แล้ว
- ไม่ลดคุณภาพ/encode ภาพต้นฉบับใหม่เพื่อให้เล็กลง: เปลี่ยน bytes และ identity ของหลักฐาน
- ไม่ลบภาพที่หายไปจาก current project โดยอาศัย current image list อย่างเดียว
  เพราะ checkpoint, revision history, frozen export หรือ pending operation อาจยังต้องใช้
- Blob GC และ incremental backup เป็นงานแยกภายหลัง ต้องมี reference/retention model
  และ backup/restore verification; backup สำรองข้อมูลเป็นคนละหน้าที่กับ cache
- STOR IDs เป็นข้อเสนอจากรอบสำรวจ; ตามคำขอถัดมาของผู้ใช้ ได้จัด scope และรายการที่เลื่อนไว้ใน Phase 11 แล้ว

## 7. “เก็บภาพชุดเดียว” ทำได้แค่ไหน

**ภายใน canonical storage ทำอยู่แล้ว:** ภาพ 1.5 GB ที่ bytes ไม่ซ้ำกันควรใช้ประมาณ
1.5 GB สำหรับ raw assets ใน service root นั้น แม้มีหลาย checkpoint หรือหลาย project ที่ใช้ภาพเดิม
บวก annotations, DB และประวัติที่จำเป็น

เป้าหมายที่เหมาะสมคือ **ภาพ canonical หนึ่งชุด + metadata ของแต่ละ version + cache ที่มีเพดาน**
ไม่ใช่เก็บเฉพาะไฟล์ภาพแล้วทิ้ง annotation/history
Inbox และ portable training outputs จะยังเป็นสำเนาอีกชุดตาม workflow ที่เลือก
จึงไม่ควรรับประกันว่าพื้นที่รวมทั้งหมดจะเหลือเท่าขนาดภาพต้นฉบับพอดี

## 8. ข้อมูลที่ยังต้องตรวจจากบริษัท

ขนาดแยกโฟลเดอร์ได้รับแล้วตามส่วนที่ 1 ไม่ต้องขอให้ผู้ใช้วัดซ้ำ
ขั้นถัดไปควรให้ storage report ใน Phase 11 ตรวจรายละเอียดต่อไปนี้
โดยไม่ต้องส่งรูปหรือข้อมูล confidential:

1. Exact root path และ app version ที่ใช้; เป็น service root หรือ parent ที่รวมอย่างอื่นด้วย
2. จำนวน/ขนาดภาพตาม hash, project membership และ history references ภายใน `managed/assets`
3. จำนวน ZIP และขนาดรวมใน `export-cache`; จำนวน Prepare/Save dataset โดยประมาณถ้าจำได้
4. Saved datasets และ backups อยู่ที่ใด อยู่ใต้ root ที่วัดหรือไม่
5. ขนาด desktop cache วัดแยกเฉพาะเมื่อต้องอธิบายพื้นที่ทั้งเครื่อง

ใช้ข้อมูลนี้จัดลำดับ STOR-02/05/07 ตาม bytes ที่คืนได้จริง
หาก `managed/assets` ใหญ่ผิดจาก unique inputs ค่อยตรวจ hash inventory, หลาย service roots,
ภาพที่ bytes ต่างกัน และ assets ที่ยังต้องเก็บเพื่อประวัติ

## 9. หลักฐานที่ต้องมีหากอนุมัติให้พัฒนาต่อ

- Import ภาพเดียวกันต่างชื่อ/ต่าง project ใน root เดียวกัน: physical asset ไม่เพิ่ม
- แก้ annotation, สร้าง checkpoint, restore: raw asset bytes ไม่เพิ่มและย้อนกลับได้ครบ
- Prepare input เดิมซ้ำ: cache reuse; เปลี่ยน annotation/mapping/split/converter: แยกผลถูกต้อง
- Cache cleanup ไม่ทำลาย active download, checkpoint restore หรือ export provenance
- Inbox cleanup ไม่สูญข้อมูลเมื่อ commit ล้มเหลว, process ถูกปิด, source เปลี่ยน หรือ import ซ้อนกัน
- วัด steady-state และ peak disk ของ workload ที่ใกล้ 5,400 ภาพ โดยใช้ synthetic data
  พร้อมรายงานแยก per volume และทดสอบ restore หลัง retention

ผู้ใช้ขอจัดทำ phase ใหม่แล้ว: ข้อเสนอได้รับการจัดลำดับใน `phase11-plan.md`
ยังไม่ได้อนุมัติให้เริ่ม implementation หรือ cleanup ข้อมูลจริง

รอบสำรวจนี้ไม่ได้รัน application tests หรือสร้าง dataset เพิ่ม เพราะไม่มี code change
ได้รับขนาดโฟลเดอร์จากผู้ใช้ แต่ยังไม่ได้เข้าถึงดิสก์บริษัท มีเฉพาะรายงานและแผนเอกสาร
ไม่มีการ cleanup, commit หรือ push
