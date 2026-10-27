# Shared button feedback standard

วันที่: 2026-10-27 · สถานะ: ข้อกำหนดสำหรับนำไป implement; ยังไม่ได้เปลี่ยนพฤติกรรมแอป

อ้างอิง [button audit](button-feedback-audit.md) และ [inventory 106 ปุ่ม](button-feedback-inventory.csv), source baseline `7dd037210ca285da58ca8d4209328e5b5976a427`. เอกสารนี้กำหนดรูปแบบร่วมตามคำขอผู้ใช้ ไม่ใช่หลักฐานว่าแก้ครบแล้ว และไม่ได้เปลี่ยนข้อกำหนด permission, lease, revision, checkpoint หรือ approved release.

## 1. ข้อตกลงหลัก

| ID | ข้อกำหนด |
|---|---|
| FB-01 | ทุกคำสั่งจากผู้ใช้ต้องมีผลที่เห็นได้: งานสำเร็จ, กำลังทำ, ต้องตัดสินใจ หรือหยุดพร้อมเหตุผลและขั้นตอนถัดไป |
| FB-02 | เมื่อทำต่อไม่ได้ ข้อความต้องระบุ **action + เหตุผลจริง + สิ่งที่ทำต่อได้**; ห้ามใช้ข้อความเดียวแทนหลายสาเหตุ เช่น busy แต่บอกให้ Connect |
| FB-03 | แสดง feedback ในหน้าต่างที่ผู้ใช้กำลังทำงานอยู่; ห้ามส่งเฉพาะ workspace status ที่ถูก modal บัง |
| FB-04 | ปุ่ม disabled ต้องมีเหตุผลและวิธีปลดเงื่อนไขที่เห็นได้โดยไม่ต้อง hover หรือคลิก; tooltip เป็นข้อมูลเสริม |
| FB-05 | การรายงาน success, saved, cancelled หรือ draft preserved ต้องมีหลักฐานจากผลการทำงานจริง; timeout อาจหมายถึงไม่ทราบผล ไม่ใช่ล้มเหลวแน่นอน |
| FB-06 | ใช้มาตรฐานเดียวกันกับปุ่มและ shortcut ที่ตั้งใจเรียก action เดียวกัน; autosave/background ใช้ช่องสถานะแบบไม่ขัดจังหวะ |
| FB-07 | ไม่ให้ progress, refresh หรือ async response เก่าทับ error/ผลลัพธ์ของงานอื่น; ผูกข้อความกับเจ้าของงานและ context |
| FB-08 | ทุกข้อความ UI ที่แอปเขียนเป็น English; ชื่อ project/class/path/message ของผู้ใช้รองรับ Unicode ตามเดิม |

## 2. หน้าตาและตำแหน่งร่วม

ใช้ **แถบข้อความภายในหน้าต่างเจ้าของคำสั่ง** อยู่เหนือพื้นที่เลื่อนหรือใกล้กลุ่มปุ่มหลัก แยกจาก progress และรายงานยาว ข้อความ wrap ได้และไม่ถูกตัดเมื่อปรับขนาดหน้าต่าง แสดงระดับเป็นคำ เช่น `Action required`, `Working`, `Completed`, `Could not complete` พร้อมสีประกอบ ไม่ใช้สีอย่างเดียว.

รูปแบบเมื่อหยุด:

> **Action required — Edit classes**<br>
> No project is selected. Select a project in Project Manager, then choose Edit classes / dataset checkpoints.

รูปแบบเป็นสองส่วน: ประโยคแรกอธิบายเหตุผล ประโยคถัดไปบอกขั้นตอนหรือ control ที่ใช้ต่อได้จริง ไม่ต้องขึ้นต้นทุกข้อความว่า Error. หากต้องออกจาก modal เพื่อทำขั้นตอนถัดไป ต้องบอกให้ปิดหน้าต่างนั้นก่อน และต้องอนุญาตให้ปิดได้อย่างปลอดภัยตามงานที่กำลังทำ.

ข้อความสั้นควรจบใน 2–3 ประโยค; รายละเอียด validation หลายรายการ/path/job ID แยกส่วน Details ที่ copy ได้. ไม่แสดง token, password หรือ traceback ให้ผู้ใช้ทั่วไป. ตัวเลือก Details/Copy และแถบข้อความเป็นข้อเสนอ UI ใหม่ ยังไม่มี implementation.

| สถานการณ์ | รูปแบบหลัก | อายุข้อความ |
|---|---|---|
| ขาด selection/permission/ข้อมูลฟอร์ม | แถบ Action required; field error ใกล้ช่องผิดถ้ามี | คงอยู่จนแก้เงื่อนไขหรือเริ่ม action ที่เกี่ยวข้องใหม่ |
| งานกำลังทำ | Working + ชื่องาน + progress เมื่อวัดได้ | จนมีผลสุดท้าย; ไม่สร้างเปอร์เซ็นต์ที่ไม่ได้วัด |
| ทำสำเร็จแต่ผลไม่ชัด เช่น Save | Completed + สิ่งที่บันทึก/ผลที่ยืนยันได้ | จน action ถัดไปที่เกี่ยวข้อง; ไม่บังคับกด OK |
| ทำสำเร็จและเห็นผลตรงๆ เช่น Fit/Add class | การเปลี่ยนหน้าจอเพียงพอ | ไม่จำเป็นต้องเพิ่มข้อความทุกครั้ง |
| ทำไม่ได้เพราะ error | Could not complete + เหตุผล + ทางแก้/ตรวจสอบ | คงอยู่; refresh เบื้องหลังห้ามลบ |
| ต้องเลือกระหว่างข้อมูล/การเปลี่ยนถาวร | decision dialog เดิม + ผลกระทบที่ถูกต้อง | รอการตัดสินใจ; ไม่ซ้อน modal อีกชั้น |
| Cancel/Close ที่ทำตามคำสั่งได้ทันที | ปิด/กลับหน้าตามที่ขอ | ไม่ต้องแจ้งว่า Closed สำเร็จ |

ไม่ใช้ toast ที่หายเองหรือ message box สำหรับทุก prerequisite. Message box ใช้เมื่อจำเป็นต้องตัดสินใจ เช่น dirty navigation, conflict, delete confirmation. สำหรับการแจ้งธรรมดาใช้แถบในหน้าต่างเดิมเพื่อให้แก้ข้อมูลต่อได้ทันที.

## 3. เจ้าของข้อความและเส้นทางเปลี่ยนหน้าต่าง

| หน้าต่าง/พื้นที่ | พื้นที่ feedback เป้าหมาย | สิ่งที่ต้องทำตอน implement |
|---|---|---|
| Workspace | workspace status ที่มองเห็นได้เสมอ + save state | ตรวจขนาดหน้าต่าง/ความยาวข้อความ; อย่าให้ progress กลบ save error |
| Project Manager | `pm_status` | ใช้ทั้ง guard และ async result; ไม่ปิดก่อนตรวจ prerequisite |
| Dataset manager | `ds_status` | แยกข้อความผลลัพธ์ออกจาก operation progress |
| Checkpoint image browser | แถบของ browser เอง | เพิ่มพื้นที่; ห้ามส่ง error ไป `ds_status` ด้านหลังอย่างเดียว |
| Export | `export_status` + report/details | คง source/checkpoint context ให้ชัด |
| Team / Statistics | `team_status` / `statistics_status` | ใช้มาตรฐานเดียวกันทั้ง busy/validation/error |
| Connection / New project / YOLO import | แถบภายในแต่ละ dialog | แก้จุดที่ส่งไป workspace ด้านหลัง |
| Reject / Review settings | แถบภายในแต่ละ dialog | validation และ server error ต้องเห็นโดยยังไม่ปิด dialog |
| Dirty navigation / Recovery / Conflict / Delete confirmation | ข้อความภายใน dialog ที่กำลังเปิด | เก็บ dialog ไว้เมื่อขั้นตอนก่อนปิดล้มเหลว; ไม่อ้างว่าเก็บ draft แล้วหากเขียนไม่สำเร็จ |
| Native file picker | error ก่อนเปิดหรือหลังกลับในหน้าต่างเจ้าของ | Cancel กลับหน้าต่างเดิม; ใช้ลำดับ deferred modal switch เดิม |

กติกา handoff: ตรวจ prerequisite ขณะหน้าต่างต้นทางยังอยู่ → หากผ่านจึงสลับหน้าต่าง → หลังสลับสำเร็จ destination เป็นเจ้าของข้อความ. หากเปิดปลายทางไม่สำเร็จ ต้องคืนต้นทางและแสดงสาเหตุพร้อมวิธีลองใหม่ ไม่ปล่อยให้ modal หายไปเฉยๆ. ข้อผิดพลาดธรรมดาไม่ควรเปิด modal ซ้อน modal.

หากผู้ใช้ปิดหน้าต่างขณะงานยังทำต่อได้ ให้เก็บผลไว้กับงานนั้นและมี summary ใน workspace **เมื่อ workspace มองเห็นได้**; ถ้ามี modal อื่นอยู่ ไม่เปิด error dialog แทรก. เมื่อกลับมายังหน้าต่างเจ้าของงานให้แสดงผลที่เก็บไว้. ถ้าปิดไม่ได้ระหว่าง commit ให้แจ้งเหตุผลและให้รอในหน้าต่างเดิม. Close ไม่เท่ากับ Cancel และห้ามอ้างว่างานถูกยกเลิกเพียงเพราะหน้าต่างปิด.

## 4. Guard, disabled และการเรียกซ้ำ

1. แยก intentional stale/internal callback ออกจากคำสั่งใหม่ของผู้ใช้. Callback เก่าที่ context เปลี่ยนแล้วทิ้งได้โดยไม่ popup; คำสั่งใหม่ที่ใช้ context เก่าต้องแจ้งให้ refresh/reselect.
2. ตรวจ connection/context ขั้นพื้นฐานก่อนใช้ข้อมูลนั้น จากนั้นตรวจ busy ที่ขัดกับคำสั่ง แล้วตรวจ selection, role, edit/review state, draft และ validation ตาม dependency ของ action. ไม่บังคับลำดับเดียวกับทุก action แต่ข้อความต้องอธิบาย blocker ที่ตรวจพบจริง.
3. แสดง blocker ที่แก้ต่อได้ก่อนหนึ่งเรื่อง; เมื่อแก้แล้วประเมินใหม่. รวม field validation หลายข้อในฟอร์มได้. อย่าอ้างว่าปลด blocker แรกแล้วรับประกันสำเร็จ เพราะ server ยังตรวจ authorization/revision/lease อีกครั้ง.
4. คำนวณ availability และเหตุผลจาก policy เดียวกับ user-dispatch guard เพื่อลดกรณีปุ่ม enabled แต่ callback เงียบ. Server ยังคงเป็นผู้ตัดสินสุดท้าย.
5. ปุ่ม disabled มีข้อความข้างกลุ่มปุ่มหรือแถบ eligibility เช่น `Accept unavailable: this image is not IN_PROGRESS. Open a saved IN_PROGRESS image to review.` อัปเดตตาม selection/state. ไม่ rely on tooltip ของ Dear PyGui ที่ disabled ซึ่งยังต้องพิสูจน์ runtime.
6. Hidden ใช้สำหรับฟังก์ชันที่ไม่ตรง task/role อย่างถาวร เช่น polygon ใน detection; permission ที่เปลี่ยนตาม project ควรมีคำอธิบายในพื้นที่ role/capabilities. ไม่ทำให้ปุ่มทุกชนิดที่ซ่อนไว้เกิด notification.
7. Double-click mutation เดิมระหว่างทำงานแสดง Working เดิม ไม่ส่ง request ซ้ำหรือสร้าง dialog ซ้ำ. Held shortcut deduplicate ตาม action/context/reason; user action ใหม่หลัง state เปลี่ยนต้องประเมินใหม่.
8. Shortcut ที่ถูก suppress เพราะกำลังพิมพ์ใน input ไม่ต้องแจ้งเตือน. Autosave ไม่แสดง Already saved และไม่ popup ทุก timer tick; save failure ต้องคงสถานะที่เห็นได้และมีวิธีแก้.
9. No-op ที่ผู้ใช้จงใจกด เช่น Save ที่ไม่มี changes, Undo stack ว่าง, Next สุดรายการ ต้องมีคำอธิบายสั้นหรือเหตุผล disabled. Cancel/Close ที่สำเร็จ, stale response และการป้องกัน duplicate request ภายใน ไม่ใช่ข้อผิดพลาดโดยอัตโนมัติ.

## 5. Message catalog (ข้อความ English สำหรับนำไปใช้)

ตัวแปร `{...}` ต้องมาจาก context ที่ยืนยันแล้ว. เป็น template เสนอใช้ ไม่ใช่ backend error code ใหม่. เลือกชื่อ control ที่มีจริงใน surface นั้น; ถ้าทางแก้ต้องมีปุ่มใหม่ ต้อง implement ปุ่มนั้นก่อนใช้ copy ที่กล่าวถึงมัน.

| Key | เหตุการณ์ | ข้อความตัวอย่าง |
|---|---|---|
| F01 | ยังไม่เชื่อมต่อ | `Cannot {action}: you are not connected. Open Connection and connect to the service, then try again.` |
| F02 | ไม่มี project ใน PM | `Cannot {action}: no project is selected. Select a project in Project Manager, then try again.` |
| F03 | ไม่มี image ใน workspace | `Cannot {action}: no image is open. Open an image, then try again.` |
| F04 | busy ที่ขัดกัน | `Cannot {action} while {operation} is running. Wait for it to finish, then try again.` |
| F05 | ไม่มี maintainer role | `Cannot {action}: this project requires the maintainer role. Ask a project maintainer to grant access, then refresh the project.` |
| F06 | project archived | `Cannot {action}: this project is archived. Open an active project to continue.` |
| F07 | gesture/draft ยังไม่จบ | `Cannot {action}: an annotation is still being drawn. Finish or cancel the current drawing, then try again.` |
| F08 | ต้อง save ก่อน | `Cannot {action}: the current image has unsaved changes. Save the image, then try again.` (ถ้าอยู่ modal ให้เพิ่ม `Close this window` ก่อน Save; ถ้า guard รองรับ save-and-continue ใช้ dialog เดิม) |
| F09 | ไม่มี edit claim | `Cannot save: you do not hold an editing claim for this image. Reload the image to check its current state and editing availability.` (ใช้ recovery/conflict flow ก่อน reload หากมี draft) |
| F10 | local state ล้าหลัง | `Cannot save: the server version has changed. Choose Reload and compare to reconcile your changes before saving.` |
| F11 | save ไม่มี changes | `No changes to save. Continue editing this image or open another image.` |
| F12 | ไม่เลือก shape | `Cannot delete a shape: no shape is selected. Select a shape on the image, then choose Delete shape.` |
| F13 | undo/redo ว่าง | `Nothing to {undo_or_redo} for this image. Continue editing to create a new change.` |
| F14 | สุดรายการ | `This is the last image in the current list. Choose Previous or change the list filter to continue.` (first ใช้ Next) |
| F15 | queue ว่าง | `No images match the current queue. Change the queue filter or continue in another project.` |
| F16 | checkpoint ไม่ถูกเลือก | `Cannot {action}: no checkpoint is selected. Select a checkpoint in this window, then try again.` |
| F17 | saved preview ไม่ถูกเลือก | `Cannot resume: no saved preview is selected. Select a saved preview, then choose Resume preview.` |
| F18 | preview หมดอายุ/ล้าหลัง | `Cannot apply this preview: {verified_reason}. Prepare a new preview, review its changes, then apply it.` |
| F19 | preview ไม่มี changes | `This preview contains no changes. Adjust the input and prepare another preview if you want to make changes.` |
| F20 | จบ pagination | `There are no more items in this list. Select an item already shown, or refresh the list.` |
| F21 | review state ไม่ผ่าน | `Cannot {accept_or_reject}: this image is not IN_PROGRESS. Open a saved IN_PROGRESS image to review.` |
| F22 | ไม่มี review role | `Cannot {accept_or_reject}: your project role does not allow review. Ask a project maintainer for reviewer or maintainer access, then refresh the project.` |
| F23 | self-review ปิด | `Cannot review your own annotation: self-review is disabled for this project. Ask another project reviewer to review this image.` |
| F24 | Reject Other ว่าง | `Cannot reject: Other requires a reason. Enter a reason in this window, then choose Reject and save reason.` |
| F25 | invalid field | `Cannot {action}: {field} {validation_reason}. {specific_correction}` เช่น `Cannot create the project: the class list is not valid JSON. Enter a JSON list of class names, then choose Create.` |
| F26 | destination มีอยู่แล้ว | `Cannot save the dataset: the destination folder already exists. Choose a new folder name, then try again.` |
| F27 | source context เปลี่ยน | `Cannot {action}: the selected project or export source has changed. Refresh this window and prepare a new preview for the current source.` |
| F28 | ไม่มี selected report/account/folder | `Cannot {action}: no {item} is selected. Select a {item} in this window, then try again.` |
| F29 | ไม่มีรายการหลังโหลด | `No {items} were found for {scope}. {available_next_step}` เช่น checkpoints: `Create a new checkpoint when your saved dataset is ready.` |
| F30 | duplicate selection | `This image is already in the selection. Select another image to add, or continue with the current selection.` |
| F31 | clear ที่ว่าง | `The image selection is already empty. Select an image and choose Add selected image to begin.` |
| F32 | Connection error ใน dialog | `Could not connect: {safe_reason}. Check the service address and credentials in this window, then choose Connect again.` |
| F33 | transport error หลัง mutation ถูกส่ง | `The service response was not received, so the result is unknown. {operation_specific_reconciliation_step}` ห้ามใช้ retry ทั่วไปหากไม่มี idempotency/reconciliation ที่รองรับ |
| F34 | write recovery ไม่สำเร็จ | `Could not store the recovery draft: {safe_reason}. Check the recovery folder's access and free space, then try again before leaving this image.` |
| F35 | saving สำเร็จ | `Saved image {image_name}, revision {revision}. You can continue editing or open another image.` |
| F36 | cancel ขอแล้วแต่ยังไม่ยืนยัน | `Cancellation requested for {operation}. Wait for the service to confirm its final state.` |
| F37 | cancel ไม่ทัน commit | `The operation completed before cancellation took effect. Refresh the dataset to inspect the result.` |
| F38 | ปิดขณะต้องรอ | `Cannot close this window while {operation} is finishing. Wait for its result, then choose Close.` |

F33 ต้องมีทางตรวจเฉพาะ operation: save ใช้ reload-and-compare ที่รักษา draft; preview/apply ใช้ operation status และ retry identifier เดิมเมื่อ contract รองรับ; export ใช้ job/result เดิม. ถ้าไม่มีทางตรวจใน UI ต้องเพิ่ม recovery path ก่อนถือว่าการแก้ feedback ของ action นั้นครบ. ห้ามสุ่ม retry mutation หรือบอกว่าข้อมูลไม่เปลี่ยนทั้งที่ยังไม่ทราบผล.

สำหรับ delete image ให้คำยืนยันระบุผลต่อ working dataset ตามจริง และบอกข้อยกเว้นการ restore จาก checkpoint เมื่อเกี่ยวข้อง; ห้ามใช้ “cannot be undone” แบบครอบจักรวาลหรือรับประกันว่าจะ restore ได้ทุกภาพ.

## 6. Async และข้อมูลที่ข้อความต้องถือไว้

ข้อเสนอเชิง implementation: feedback event มี `code`, `severity`, `action`, `reason`, `next_step`, `owner_surface`, `context` (project/image/source ที่เกี่ยวข้อง), `operation_id` หรือ request generation, `persistence_state` และ optional details. เป็น client UI model; ไม่เพิ่ม server endpoint หรือ dependency เพียงเพื่อแสดงข้อความ.

- แยก progress ของงานออกจาก feedback/error. Error ของ operation เดิมคงอยู่จนเริ่ม retry ที่ตั้งใจทำหรือแก้เงื่อนไข; refresh unrelated ไม่ reset.
- ตรวจ context/generation ก่อน render ผล. ผลเก่ายังเก็บตาม operation ได้ แต่ห้ามแสดงเป็นผลของ project/image ใหม่.
- เก็บค่า input และ selection เมื่อ validation/error เกิดขึ้น ยกเว้น secret ที่มีนโยบายล้างอยู่แล้ว. Error ไม่ปิด dialog เอง.
- `persistence_state` แยกเป็น not_started / in_progress / confirmed_saved / confirmed_not_applied / unknown. “Draft on disk” แสดงเฉพาะเขียนสำเร็จ; draft ใน memory ไม่เท่ากับ recovery ที่ทน crash.
- การ save ล้มเหลวต้องบอกว่า saved revision ล่าสุดคืออะไรถ้าทราบ และงานใหม่ยังไม่ได้รับการยืนยัน; ไม่ใช้ข้อความ generic ว่า draft preserved กับทุก exception.
- Repeated failures ของ autosave แสดง error เดียวที่อัปเดตได้ ไม่แย่ง focus. ปลดสถานะ paused เฉพาะเมื่อ recovery/retry policy อนุญาต.

## 7. การครอบคลุมปุ่มและลำดับนำไปใช้

ทุกปุ่มใน inventory อยู่ภายใต้ FB-01 ถึง FB-08 โดยแต่ละ action ใช้เฉพาะเงื่อนไขที่เกี่ยวข้อง ไม่จำเป็นต้องใส่ทุก message ให้ทุกปุ่ม. การจัดกลุ่มต่อไปนี้ครอบคลุม BTN-001 ถึง BTN-106; อ่าน conditions รายปุ่มจาก inventory ประกอบ.

| Inventory IDs | กลุ่ม | จุดเน้น / catalog |
|---|---|---|
| BTN-001–018 | Dataset/checkpoint/browser | F02, F04–08, F16–20, F27, F29, F33, F36–38; browser มีพื้นที่ของตัวเอง |
| BTN-019–025, BTN-037–039 | เปิดหน้าต่าง/import/queue | F01–08, F15, F27, F29; ตรวจต้นทางก่อน handoff |
| BTN-026–036 | Annotation/navigation/save | F03–04, F07–14, F33–35; แยก explicit save กับ autosave |
| BTN-040–043 | Review entry/history/settings | F03–05, F07–08, F21–23, F29; dynamic eligibility |
| BTN-044–046 | Connection/Create | F04, F25, F32–33; local feedback ภายในฟอร์ม |
| BTN-047–054 | Dirty/recovery/conflict | F09–10, F33–34; ไม่ปิด dialog เมื่อรักษาข้อมูลไม่สำเร็จ |
| BTN-055–058 | YOLO dialog | F02, F04, F25, F33; input/error ใน dialog |
| BTN-059–071 | Export | F04–08, F20, F25–29, F33, F38; แยก prepare/save/confirmation และรักษา token จน dispatch สำเร็จ |
| BTN-072–073 | Delete confirmation | F04–06, F33; ยืนยันผลจริง, cancel/double-click ไม่ spam |
| BTN-074–091 | Project Manager | F02, F04–05, F18–19, F25, F28–31, F33; remap รายงาน partial success |
| BTN-092–095 | Reject/Review settings dialogs | F04, F21–25, F33; ไม่ส่ง error ไป workspace ด้านหลัง |
| BTN-096–097 | Statistics | F02, F04, F29; loading/empty/error ในหน้าต่าง |
| BTN-098–106 | Team/accounts | F04–05, F25, F28, F33, F38; แยก project role กับ system-admin permission |

ลำดับเสนอสำหรับ implementation รอบถัดไป:

1. สร้าง feedback model/renderer และ owner routing รวม rule สำหรับ progress, async และ disabled reason; พิสูจน์กับ Project Manager → Dataset และ Connection dialog ก่อน.
2. Annotation/save/review/recovery: ให้เหตุผลตรง state และป้องกันคำกล่าวเรื่องข้อมูลที่ไม่จริง; ตรวจ shortcut/autosave ไม่รบกวนงาน.
3. Dataset/export/project/team/statistics: เพิ่ม guard feedback, pagination/empty states, validation และ retry/reconciliation เฉพาะ action.
4. ใช้ inventory ตรวจครบ 106 ปุ่มพร้อม native picker/titlebar Close; บันทึกผล runtime, rebuild wheel เฉพาะเมื่ออนุมัติและทำ implementation เสร็จ.

ยังไม่สร้าง Phase ใหม่ ไม่เปลี่ยนประวัติว่า Phase 10 ผ่าน gate เพิ่ม และไม่อนุมานว่าธง 83 รายการใน audit คือ 83 บั๊กที่ต้องใส่ popup.

## 8. Acceptance scenarios สำหรับ implementation

| ID | ทดลอง | ผลที่ต้องเห็น |
|---|---|---|
| AT-01 | กด Edit classes โดยไม่เลือก project | PM ยังอยู่; บอกเหตุผลและให้เลือก project ใน PM |
| AT-02 | เปิด Classes โดยไม่มี maintainer role | บอก role ที่ขาดและให้ขอ project access; admin อย่างเดียวไม่ผ่าน |
| AT-03 | ใส่ address ผิดแล้ว Connect | เห็น error/วิธีแก้ใน Connection, ช่องกรอกยังแก้ได้ |
| AT-04 | กด action ขณะมีงานขัดกัน | บอกชื่องานที่ต้องรอ; ไม่ส่ง request ซ้ำและไม่บอกให้ Connect โดยผิดเหตุ |
| AT-05 | Save ไม่มี image / ไม่มี changes | เหตุผลสองกรณีต่างกัน; autosave no-change ไม่ spam |
| AT-06 | Delete ไม่มี shape / Undo stack ว่าง / Next สุดรายการ | มีเหตุผลสั้นหรือ disabled explanation ที่เห็นได้ |
| AT-07 | Accept ไม่ผ่าน state / role / self-review | ข้อความตรง blocker จริง; ไม่เหมารวม tooltip เดียว |
| AT-08 | Reject Other แต่ไม่กรอกเหตุผล | แจ้งใน Reject dialog และยังกรอกต่อได้ |
| AT-09 | Inspect checkpoint แล้วโหลดภาพ error | error ใน browser ที่อยู่บนสุด; ไม่ฝากไว้ DS ด้านหลัง |
| AT-10 | preview expired หรือ generation เปลี่ยน | บอกให้ prepare ใหม่; ไม่ apply preview เก่า |
| AT-11 | server บันทึกแล้วแต่ response ขาดหาย | แสดง unknown; ใช้ reconciliation/idempotency เดิม; ไม่สร้าง mutation ซ้ำ |
| AT-12 | เขียน recovery draft ไม่ได้ | ไม่บอก preserved/saved; ไม่เดินต่อจนเส้นทางรักษาข้อมูลสำเร็จหรือผู้ใช้เลือกทางออกที่มีข้อมูลครบ |
| AT-13 | error แล้ว background progress/refresh มาถึง | error ยังอ่านได้; progress ไม่ทับข้อความ |
| AT-14 | เปลี่ยน project ระหว่างรอ response | ผลเก่าไม่กลายเป็นผลของ project ใหม่ |
| AT-15 | Close งานที่ทำต่อได้ / งานที่ยังปิดไม่ได้ | แบบแรกเก็บผลและบอกเมื่อกลับมา; แบบหลังแจ้งใน dialog; ไม่อ้าง Cancel |
| AT-16 | การเปิด modal ปลายทางล้มเหลว | คืนต้นทางพร้อมเหตุผล/ทางแก้; ไม่เหลือแค่หน้าต่างหาย |
| AT-17 | ปุ่ม disabled และหน้าต่างขนาดเล็ก/DPI สูง | อ่านเหตุผลและขั้นตอนถัดไปได้โดยไม่ hover; แถบไม่ถูก content scroll ซ่อน |
| AT-18 | กด shortcut ค้าง / พิมพ์ใน textbox / autosave retry | ไม่มี popup ซ้ำหรือแย่ง focus; failure สำคัญยังมองเห็น |
| AT-19 | Cancel request แข่งกับ commit | แสดง cancelled เฉพาะเมื่อยืนยัน; ถ้า commit แล้วบอก completed |
| AT-20 | remap บางภาพสำเร็จ บางภาพล้มเหลว | แสดงจำนวนแต่ละผลและวิธี retry failed items; ไม่บอกว่าสำเร็จทั้งหมด |

เกณฑ์ส่งมอบ: unit tests ของ decision/routing ที่สำคัญ, integration ของ error/retry ที่กระทบข้อมูล, และ manual Dear PyGui smoke ของ modal visibility/disabled/layout. ทุกปุ่มต้องบันทึก runtime disposition ว่า tested, not applicable หรือ pending พร้อมเหตุผล; source trace อย่างเดียวไม่ยืนยันว่า user มองเห็นข้อความจริง.

รอบเอกสารนี้ตรวจความครอบคลุม ID และความสอดคล้องกับ audit เท่านั้น; acceptance ข้างต้นยังไม่ได้รัน.
