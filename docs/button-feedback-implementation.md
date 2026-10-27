# Button feedback implementation and verification

วันที่ 2026-10-28 · branch `notification-to-button`

ดำเนินการตาม [มาตรฐานร่วม](button-feedback-standard.md) และ [inventory เดิม 106 ปุ่ม](button-feedback-inventory.csv). ตาราง [verification รายปุ่ม](button-feedback-verification.csv) ผูกชื่อปุ่มกับตำแหน่ง source ปัจจุบัน พร้อมแยก source review, automated regression และ rendered GUI evidence. ไม่ถือว่า 106 ปุ่มถูกคลิกจริงครบทุก state.

## สิ่งที่เปลี่ยน

- **ช่องแจ้งผลประจำหน้าต่าง:** Connection, New project, YOLO import, Reject, Review settings, Recovery/Conflict/Dirty navigation และ checkpoint browser มีพื้นที่ของตัวเอง. Async callback ของ Desktop จำเจ้าของข้อความตอนเริ่มงาน จึงไม่เอา error เก่าไปใส่ modal อื่นที่เพิ่งเปิด.
- **มองเห็นขณะเลื่อน:** แยก feedback ออกจาก child window ที่เลื่อนเนื้อหาใน Project Manager, Dataset, browser, Export, Team และฟอร์มหลัก. ข้อความ feedback ปรับ wrap ตามความกว้างหน้าต่าง. Workspace status และ review eligibility อยู่เหนือพื้นที่ annotation.
- **Save และ recovery:** explicit Save บอกเมื่อไม่มีภาพ/ไม่มี changes/มีงานขัดกัน; autosave no-op ไม่แจ้งซ้ำ. การเขียน recovery draft ไม่สำเร็จจะไม่เดินหน้าต่อหรือปิด dirty dialog. การ archive/discard draft แจ้งข้อผิดพลาดใน dialog. ข้อความทั่วไปไม่รับประกันว่า draft ถูกเก็บแล้วทั้งที่ยังไม่มีหลักฐาน.
- **Review:** eligibility มีเหตุผลเฉพาะ role, image state, busy, conflict และการวาดที่ยังไม่จบ; ปุ่มและ shortcut เรียก policy เดียวกัน. Other ที่ไม่มีเหตุผลแจ้งใน Reject dialog. Server ปฏิเสธ self-review แล้วบอกให้ reviewer คนอื่นตรวจ. การตั้งค่า review ต้องกรอก reason และแจ้งข้อผิดพลาดในหน้าต่างนั้น.
- **Classes/checkpoints:** busy, missing selection/preview/image, pagination สุดหน้า และรายการว่างมีคำอธิบายและทางทำต่อ. Browser แยก status จาก Dataset; เปิด/ปิดผ่าน deferred modal switch. Progress แยกจากข้อความเพื่อไม่ทับ error/cancellation. Apply มีข้อความอธิบายเมื่อยังไม่มี preview. Export checkpoint ตรวจว่าปลายทางเปิดได้ก่อนซ่อน Dataset.
- **Export:** ตรวจ project context และ prepared-client ก่อนส่งงาน. Confirmation ยังอยู่หาก busy หรือ local validation ไม่ผ่าน. ปุ่มที่ยังใช้ไม่ได้มีคำอธิบาย prerequisite; report, history, folder และ model-file actions แจ้งเมื่อขาด input. ยังคง request key สำหรับการ retry หลังขาดการตอบกลับตาม contract เดิม.
- **ปุ่มที่เหลือ:** Project Manager, folders/templates/remap, Team, Statistics, navigation, Fit/Delete/Undo/Redo และ image deletion มี feedback สำหรับ guard/no-op ที่ผู้ใช้เรียกได้. Remap สรุปจำนวนสำเร็จ/ล้มเหลว. Delete confirmation อธิบายข้อยกเว้น checkpoint restore แทนการอ้างว่าย้อนคืนไม่ได้ทุกกรณี.
- **Shortcut:** ใช้ callback เดียวกับปุ่ม; shortcut ที่รู้จักแจ้ง busy แทนหยุดเงียบ. การพิมพ์ใน input และ modal suppression ยังคงเดิม; review key-repeat ยังป้องกันส่ง review ซ้ำ.

คง backend authorization, lease, revision, idempotency และ immutable checkpoint semantics เดิม. ไม่เพิ่ม dependency, service endpoint, Python extension หรือการเข้าถึงเครือข่ายภายนอก.

## หลักฐานตรวจสอบ

| การตรวจ | ผล |
|---|---|
| `python -m pytest -q` ผ่าน Python ของ `.venv` | **358 passed**; มี Starlette/httpx deprecation warning เดิม 1 รายการ |
| Focused feedback / Phase 9 desktop / export UI / Phase 8 tools | **89 passed** หลังปรับ guard เพิ่มเติม |
| Ruff (`src tests scripts`) | ผ่าน |
| Mypy (`src/visionlabel`) | ผ่าน 49 source files |
| `scripts/button_feedback_smoke.py` | **14 checks ผ่าน** กับ Dear PyGui ที่ render จริง: modal-local error, missing role/selection, 700px layout และ scroll persistence, Login/Create project layout, Save/Fit shortcut |
| `scripts/phase10_smoke.py` | real HTTP + rendered journey ผ่าน: checkpoint, historical image/annotation, class removal, diff, frozen export, restore; ใช้ภาพสังเคราะห์ 4 ภาพ |
| Source inventory reconciliation | ชื่อ/ลำดับ/ไฟล์ของ **106 ปุ่มตรงกัน**; update current line ใน verification CSV |

เพิ่ม regression tests 30 กรณีใน `tests/test_button_feedback.py` รวมการเก็บ confirmation เมื่อยัง dispatch ไม่ได้, การกัน export ข้าม project, การไม่เดิน navigation ต่อเมื่อเขียน draft ไม่สำเร็จ, async owner routing และการแยก progress จาก error. ปรับ test doubles เดิมให้มี project identity และจำลอง DPG visibility; ปรับ assertion เดิมให้ตรวจ reason + next step แทน exact error string เก่า.

ปรับ Phase 10 smoke ให้รอ modal เปิดและ render จริงก่อน capture ภาพ และใช้ Close browser callback เพื่อกลับ Dataset; การรอแค่ network idle ไม่พิสูจน์ว่า deferred modal ปรากฏบนจอแล้ว.

ไฟล์ภาพ/JSON จาก smoke อยู่ใน `%TEMP%/visionlabel-feedback-smoke-final` และ `%TEMP%/visionlabel-feedback-phase10-smoke-final` ไม่เก็บ runtime output หรือ dataset ใน Git.

## ขอบเขตหลักฐานและการนำไปใช้

- เป็น source implementation พร้อม automated checks และ rendered callback smoke. ยังไม่ใช่การทดสอบด้วยเมาส์จริงครบ 106 ปุ่มในทุก state, high-DPI หลายเครื่อง หรือ company LAN acceptance. ดู pending physical checks ใน verification CSV.
- ตัวอย่างข้อความ 38 แบบในมาตรฐานเป็นแนวทาง; implementation ใช้ wording ตามบริบท ไม่ใช่การเพิ่ม error code ฝั่ง server ทั้ง 38 ตัว.
- Async ที่ context เก่าและการกัน double-click ภายในยังทิ้งได้ตามเดิม. Close/Cancel ที่ทำหน้าที่ปิดได้สำเร็จไม่เปิด popup เพิ่ม.
- Application wheel `visionlabel-0.1.4-py3-none-any.whl` รวมการแก้ชุดนี้และขนาดหน้าต่าง Login. Native wheel `visionlabel_native-0.1.0-cp312-cp312-win_amd64.whl` เดิมไม่มีการเปลี่ยนแปลง.
- การตรวจในเครื่องนี้ไม่ถือว่าผ่าน gate ของ approved releases หรือ company acceptance เพิ่ม.
