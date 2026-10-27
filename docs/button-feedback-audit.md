# Button feedback audit — Phase 10

Source baseline: `7dd037210ca285da58ca8d4209328e5b5976a427` on `codex/phase10-dataset-versioning`.

สำรวจจาก source วันที่ 2026-10-27; รอบนี้เป็น inventory/trace เท่านั้น ไม่แก้พฤติกรรม ไม่รัน GUI/service หรือทดสอบ runtime. ข้อความในแอปยังเป็น English.

## ขอบเขตและวิธีอ่าน

- ครบ 106 จุดประกาศ `dpg.add_button` ใน 8 ไฟล์ (นับปุ่มชื่อซ้ำตามหน้าต่าง ไม่ใช่ 106 ฟังก์ชันหรือ 106 บั๊ก). ไม่พบ `add_image_button` หรือ button context-manager เพิ่มใน `src`.
- ไล่ callback, helper ที่เรียกต่อ, guard, enabled/show และเส้นทาง success/error. เงื่อนไข server ที่ระบุเป็นหมวดของการตรวจ ไม่ใช่รายการ error code ของ backend ทั้งหมด.
- ปุ่มของ file picker ที่ Dear PyGui สร้างเองและปุ่ม X ของหน้าต่างอยู่ในส่วนเสริมท้ายรายงาน. Checkbox/combo/list/selectable/menu/HTML guide ไม่รวมในจำนวน 106.
- `S`: callback ของปุ่มมีทางหยุดเงียบ (บางทางเกิดเฉพาะ state เปลี่ยนหรือการเรียกซ้ำ ไม่ได้ยืนยันว่ากดถึงได้ในทุกสถานะ); `D`: disabled/hidden gate ต้องอธิบายสาเหตุ; `V`: ข้อความส่งไปหน้าต่างอื่น อาจถูกบัง; `M`: ข้อความรวมหลายเหตุผล/ชวนสับสน; `R`: ต้องตรวจ runtime/exception/modal เพิ่ม; `OK`: ยังไม่พบช่องว่างเด่นจาก trace ของปุ่มนั้น. Flags ซ้อนกันได้ ไม่ใช่คะแนนความรุนแรงหรือคำยืนยันว่าเห็นบั๊กทุกครั้ง.
- ไม่ถือ stale async callback, การกัน double-click หลังยืนยัน หรือการปิด dialog ตามคำสั่งเป็น silent failure โดยอัตโนมัติ. `return` ใน Python คืน None ตามปกติ ไม่ได้แปลว่าเกิดข้อผิดพลาดเสมอ.
- โค้ดที่สำรวจเป็น source ปัจจุบัน ไม่ได้ยืนยันว่า environment/wheel ของผู้ใช้โหลด source commit นี้.

## จำนวนปุ่ม

| ไฟล์ | จุดประกาศ |
|---|---:|
| dataset_ui.py | 18 |
| desktop.py | 40 |
| export_ui.py | 13 |
| image_delete_ui.py | 2 |
| project_ui.py | 18 |
| review_ui.py | 4 |
| statistics_ui.py | 2 |
| team_ui.py | 9 |
| **รวม** | **106** |

## สรุปธงจากการ trace

| ธง | จำนวนปุ่ม |
|---|---:|
| S — มีทางหยุดเงียบ | 70 |
| D — มี gate แบบ disabled/hidden ที่ต้องดูคำอธิบาย | 16 |
| V — ข้อความอาจอยู่หลังหน้าต่างอื่น | 13 |
| M — ข้อความรวมเหตุผล/ชวนสับสน | 9 |
| R — ต้องตรวจ runtime/exception เพิ่ม | 7 |
| OK — ยังไม่พบช่องว่างเด่นใน trace | 23 |

ธงซ้อนกันได้; S/D/V/M/R ไม่ใช่รายการบั๊กที่ reproduce แล้ว. ปุ่มที่มีธงอื่นนอกจาก OK มี 83 จุด แต่ไม่ควรตีความว่าต้องแก้ 83 ปุ่มทั้งหมด.

## กลไกร่วมที่มีผลต่อหลายปุ่ม

- **M** = `Desktop.message/error` → `status` ด้านล่าง workspace. Dialog Connection/New project/YOLO/Review settings/Reject/Recovery ไม่มีการย้ายข้อความนี้เข้าหน้าต่างปัจจุบันโดยอัตโนมัติ. ความเสี่ยงถูกบังมาจากโครงสร้าง UI ต้องยืนยันการมองเห็นจริง.
- **P** = `pm_status`, **DS** = `ds_status`, **E** = `export_status`/`export_report`, **T** = `team_status`, **ST** = `statistics_status`.
- **G** = `Desktop.guard`: busy/review busy/มี next_action แจ้งรอ; gesture/draft แจ้งให้จบ; dirty/pending save/saving ใช้ navigation autosave หรือ dirty dialog.
- **P-run** = `ProjectPanel.run`: manager/app busy หรือ saving หยุดเงียบ; ระหว่างทำปิดเฉพาะ remap inputs; failure ไป P. ปุ่มจำนวนมากยังดูเหมือนกดได้.
- **DS-run** = `DatasetPanel.run`: manager/app busy, saving หรือ review busy หยุดเงียบ; ปิด fields แต่ปุ่มส่วนใหญ่ยัง enabled; failure ไป DS แม้กำลังเปิด Checkpoint browser.
- **Export.set_busy** ปิด Prepare/Save/history/source ฯลฯ และมี progress; Load model/Browse/Close ไม่ได้ถูกปิดทั้งหมด.
- **Team.mutate/retry** หยุดเมื่อ busy; membership buttons disable ตาม can_manage_members; Accounts tab ซ่อนสำหรับ non-admin.
- Accept/Reject มี tooltip ที่ระบุ reviewer/maintainer, saved IN_PROGRESS และ self-review setting อยู่แล้ว แต่ไม่ได้อธิบาย busy/blocked/gesture แบบเจาะจง. การ hover tooltip ของ disabled button ต้องตรวจ runtime.
- API errors ส่วนใหญ่ผ่าน `Problem.message`; exception อื่นที่เข้า Desktop.error เหลือข้อความชื่อชนิด exception และ draft preserved. Direct callback/storage exceptions บางจุดไม่ได้ผ่าน helper นี้.

## รายการครบทุกปุ่ม

### dataset_ui.py

| ID / ปุ่ม / จุดประกาศ | Callback | เงื่อนไขและเหตุผลหยุด | Feedback ปัจจุบัน | สังเกต |
|---|---|---|---|---|
| BTN-001 **Refresh** [L71](../src/visionlabel/dataset_ui.py#L71) | `lambda: self.refresh()` | project, manager ไม่ busy; Older ต้องมี next_before; ผ่าน DS-run | missing/busy/ไม่มีหน้าเก่าเงียบ; ผ่านเติมรายการ+DS ให้เลือก checkpoint; error DS | S |
| BTN-002 **Older** [L72](../src/visionlabel/dataset_ui.py#L72) | `lambda: self.refresh(True)` | project, manager ไม่ busy; Older ต้องมี next_before; ผ่าน DS-run | missing/busy/ไม่มีหน้าเก่าเงียบ; ผ่านเติมรายการ+DS ให้เลือก checkpoint; error DS | S |
| BTN-003 **Inspect images** [L75](../src/visionlabel/dataset_ui.py#L75) | `lambda: self.inspect()` | manager ไม่ busy; Inspect ต้องเลือก checkpoint; Next ต้องมี next_offset; ผ่าน DS-run | ไม่มี checkpoint แจ้ง DS; busy/สุดหน้าเงียบ; ผ่านเปิด browser/list; Next error ลง DS ของหน้าต่างด้านหลัง | S,V |
| BTN-004 **Compare with** [L76](../src/visionlabel/dataset_ui.py#L76) | `lambda: self.compare()` | manager ไม่ busy; ต้องเลือก checkpoint; ผ่าน DS-run | missing selection/error แจ้ง DS; busy เงียบ; ผ่าน JSON diff ใน report | S |
| BTN-005 **Export checkpoint** [L80](../src/visionlabel/dataset_ui.py#L80) | `lambda: self.export()` | manager ไม่ busy; checkpoint; workspace project ต้องตรง; ผ่าน DS-run และ Export.open | missing selection/project mismatch แจ้ง DS; busy เงียบ; ผ่านปิด Dataset เปิด Export; Export.open rejection ส่ง M; modal handoff ควรตรวจภาพจริง | S,V,R |
| BTN-006 **Preview restore to working data** [L81](../src/visionlabel/dataset_ui.py#L81) | `lambda: self.prepare('restore')` | project, manager ไม่ busy; ไม่ dirty/saving/gesture/draft; Restore ต้องเลือก checkpoint; ผ่าน DS-run; serverตรวจ role/archive/label/message/schema/mapping | missing/busy เงียบ; unsaved/selection/error แจ้ง DS; ผ่าน preview summary+enable Apply | S |
| BTN-007 **Preview new checkpoint** [L84](../src/visionlabel/dataset_ui.py#L84) | `lambda: self.prepare('checkpoint')` | project, manager ไม่ busy; ไม่ dirty/saving/gesture/draft; Restore ต้องเลือก checkpoint; ผ่าน DS-run; serverตรวจ role/archive/label/message/schema/mapping | missing/busy เงียบ; unsaved/selection/error แจ้ง DS; ผ่าน preview summary+enable Apply | S |
| BTN-008 **Find saved previews** [L88](../src/visionlabel/dataset_ui.py#L88) | `lambda: self.find_pending()` | project, manager ไม่ busy; ผ่าน DS-run; server maintain | missing/busy เงียบ; ผ่านรายการ+ข้อความ expiry; รายการว่างยังใช้ข้อความทั่วไป ไม่ระบุไม่มี previews | S,M |
| BTN-009 **Resume preview** [L90](../src/visionlabel/dataset_ui.py#L90) | `lambda: self.resume_preview()` | manager ไม่ busy; เลือก pending preview ที่มีในรายการ | busy/ไม่มี preview เงียบ; ผ่านเติม label/message/report และ enable Apply | S |
| BTN-010 **Add class** [L101](../src/visionlabel/dataset_ui.py#L101) | `lambda: self.add_class()` | project, manager ไม่ busy | missing/busy เงียบ; ผ่านเพิ่มแถวและ invalidate Apply | S |
| BTN-011 **Refresh class usage** [L102](../src/visionlabel/dataset_ui.py#L102) | `lambda: self.usage()` | project, manager ไม่ busy; ผ่าน DS-run | missing/busy เงียบ; ผ่านจำนวน labels/images ต่อคลาสใน ds_usage; error DS | S |
| BTN-012 **Preview class changes** [L104](../src/visionlabel/dataset_ui.py#L104) | `lambda: self.prepare('schema')` | project, manager ไม่ busy; ไม่ dirty/saving/gesture/draft; Restore ต้องเลือก checkpoint; ผ่าน DS-run; serverตรวจ role/archive/label/message/schema/mapping | missing/busy เงียบ; unsaved/selection/error แจ้ง DS; ผ่าน preview summary+enable Apply | S |
| BTN-013 **Apply preview / retry** [L109](../src/visionlabel/dataset_ui.py#L109) | `lambda: self.apply()` | มี preview, manager ไม่ busy; ไม่ dirty/saving; ผ่าน DS-run; server expiry/generation/claim/permission/blob validation | no preview/busy เงียบ; dirty/saving แจ้ง DS; progress+result/retry instruction; mutation ปิด modal reload project | S,D |
| BTN-014 **Cancel preview / operation** [L115](../src/visionlabel/dataset_ui.py#L115) | `lambda: self.cancel()` | ต้องมี preview เพื่อส่ง cancel; ไม่มี preview เรียก invalidate | ไม่มี preview เงียบ/disable Apply; มี preview แจ้ง Cancelled หรือ Already committed/error DS; อนุญาตระหว่างทำงาน | S |
| BTN-015 **Close** [L116](../src/visionlabel/dataset_ui.py#L116) | `lambda: dpg.hide_item('dataset_manager')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |
| BTN-016 **View image and annotation** [L129](../src/visionlabel/dataset_ui.py#L129) | `lambda: self.view_image()` | manager ไม่ busy; เลือก record; ผ่าน DS-run; app.store ใช้ decode | busy/ไม่มี record เงียบ; ผ่าน raster/annotation ใน browser; error ไป DS ที่หน้าต่างหลัง browser; store ไม่มีไม่มี precheck เฉพาะ | S,V,R |
| BTN-017 **Next images** [L130](../src/visionlabel/dataset_ui.py#L130) | `lambda: self.inspect(next_page=True)` | manager ไม่ busy; Inspect ต้องเลือก checkpoint; Next ต้องมี next_offset; ผ่าน DS-run | ไม่มี checkpoint แจ้ง DS; busy/สุดหน้าเงียบ; ผ่านเปิด browser/list; Next error ลง DS ของหน้าต่างด้านหลัง | S,V |
| BTN-018 **Close** [L131](../src/visionlabel/dataset_ui.py#L131) | `lambda: dpg.hide_item('checkpoint_browser')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |

### desktop.py

| ID / ปุ่ม / จุดประกาศ | Callback | เงื่อนไขและเหตุผลหยุด | Feedback ปัจจุบัน | สังเกต |
|---|---|---|---|---|
| BTN-019 **Connection** [L161](../src/visionlabel/desktop.py#L161) | `lambda: self.show_connection()` | ถ้า dirty ผ่าน G; มิฉะนั้นเปิดได้ | เปิด Connection; G แจ้งรอ/จบ gesture หรือเปิด dirty dialog | OK |
| BTN-020 **Project Manager** [L162](../src/visionlabel/desktop.py#L162) | `lambda: self.guard(self.project_manager.open)` | ผ่าน G; ต้อง login; ProjectPanel.refresh ผ่าน P-run | G/M แจ้งรอ/จบ gesture/Connect; dirty dialog ถ้าต้องตัดสินใจ; ผ่านเปิด PM/refresh | OK |
| BTN-021 **Import inbox** [L165](../src/visionlabel/desktop.py#L165) | `lambda: self.import_inbox()` | ต้องมี project และไม่มี import job; server ตรวจสิทธิ์/schema/ไฟล์ | M: Choose a project first, and wait for any active import; Scanning/queued และผล job/report; error ผ่าน M | M |
| BTN-022 **Import YOLO labels** [L166](../src/visionlabel/desktop.py#L166) | `lambda: self.show_yolo_import()` | ต้องเป็น detection project | M แจ้งเลือก detection; ผ่านแล้วเปิด mapping dialog | OK |
| BTN-023 **Reload / reconnect** [L167](../src/visionlabel/desktop.py#L167) | `lambda: self.guard(self.reload)` | ผ่าน G; ต้องมี image; open_image ไม่ busy/saving/review-busy | ไม่มี image เงียบแม้ชื่อปุ่มสื่อ reconnect; ถ้ามีภาพโหลด head/claim ใหม่ และแสดงสถานะ/error M | S,M |
| BTN-024 **Team & users** [L168](../src/visionlabel/desktop.py#L168) | `lambda: self.guard(self.team.open)` | ผ่าน G; ต้อง login | G/M แจ้งก่อนเปิด; Team.open ขาด login แจ้ง M; ผ่านเปิด Team/Loading ที่ T | OK |
| BTN-025 **Resume queue** [L197](../src/visionlabel/desktop.py#L197) | `self.review.resume` | ต้องมี store/project และภาพปลายทางในคิว; ผ่าน G | ไม่มี project/store/คิวว่างเงียบ; มีเป้าหมายเปิดภาพ | S |
| BTN-026 **Rectangle [R]** [L203](../src/visionlabel/desktop.py#L203) | `lambda: self.set_mode('rectangle')` | tool ต้องตรง task; classification ไม่รับ; polygon draft ต้องจบก่อน | task ไม่ตรง return เงียบ; draft แจ้ง M; ผ่านแล้ว M อธิบายเครื่องมือ; Rectangle/Polygon ซ่อนตาม task | S |
| BTN-027 **Polygon [P]** [L208](../src/visionlabel/desktop.py#L208) | `lambda: self.set_mode('polygon')` | tool ต้องตรง task; classification ไม่รับ; polygon draft ต้องจบก่อน | task ไม่ตรง return เงียบ; draft แจ้ง M; ผ่านแล้ว M อธิบายเครื่องมือ; Rectangle/Polygon ซ่อนตาม task | S |
| BTN-028 **Select [V]** [L214](../src/visionlabel/desktop.py#L214) | `lambda: self.set_mode('select')` | tool ต้องตรง task; classification ไม่รับ; polygon draft ต้องจบก่อน | task ไม่ตรง return เงียบ; draft แจ้ง M; ผ่านแล้ว M อธิบายเครื่องมือ; Rectangle/Polygon ซ่อนตาม task | S |
| BTN-029 **Fit [F]** [L215](../src/visionlabel/desktop.py#L215) | `lambda: self.fit()` | ต้องมี image จึง fit ได้ | เปลี่ยน zoom แล้ว render; ไม่มีภาพเพียง render ไม่มีคำอธิบาย | S |
| BTN-030 **Delete shape** [L235](../src/visionlabel/desktop.py#L235) | `lambda: self.delete_selected(whole_shape=True)` | ต้องมี image; ไม่ busy; can_edit; shape ที่เลือกถ้าจะลบ | guard เงียบ; ไม่มี selection อาจ edited/render แต่ไม่มีสิ่งถูกลบ; polygon draft ลบจุดล่าสุด | S |
| BTN-031 **Undo** [L241](../src/visionlabel/desktop.py#L241) | `lambda: self.undo()` | image, ไม่ busy, can_edit; undo history หรือ polygon draft | guard/stack ว่างไม่มีคำอธิบาย; เปลี่ยน geometry เมื่อมีประวัติ | S |
| BTN-032 **Redo** [L242](../src/visionlabel/desktop.py#L242) | `lambda: self.redo()` | image, ไม่ busy, can_edit; ไม่มี polygon draft; redo history | guard/stack ว่างเงียบ; draft มี M ให้จบก่อน | S |
| BTN-033 **Previous [A]** [L249](../src/visionlabel/desktop.py#L249) | `lambda: self.navigate(-1)` | ต้องมี images และ index เป้าหมายต่างจากเดิม; ผ่าน G/open_image | ไม่มีภาพหรือสุดขอบคิวเงียบ; เปิดภาพ/สถานะโหลดเมื่อไปต่อได้ | S |
| BTN-034 **Next [D]** [L250](../src/visionlabel/desktop.py#L250) | `lambda: self.navigate(1)` | ต้องมี images และ index เป้าหมายต่างจากเดิม; ผ่าน G/open_image | ไม่มีภาพหรือสุดขอบคิวเงียบ; เปิดภาพ/สถานะโหลดเมื่อไปต่อได้ | S |
| BTN-035 **Delete image...** [L251](../src/visionlabel/desktop.py#L251) | `self.image_deletion.request` | ต้องมี image/head; ไม่ busy/saving/review-busy/blocked; project maintainer และไม่ archived | กลุ่มเงื่อนไขแรกเงียบ; role/archive แจ้ง M; ผ่านเปิด confirmation; ข้อความ cannot be undone ไม่อธิบาย checkpoint restore | S,M |
| BTN-036 **Save [Ctrl+S]** [L252](../src/visionlabel/desktop.py#L252) | `lambda: self.save()` | ต้องมี image, ไม่ busy/saving; ไม่มี polygon draft; ไม่ blocked, มี edit claim; ต้อง dirty หรือ pending save | ไม่มีภาพ/busy/saving/ไม่มีอะไรเปลี่ยนเงียบ; draft/claim แจ้ง M; Saving/Saved revision; conflict dialog หรือ validation M | S,M |
| BTN-037 **Last import report** [L254](../src/visionlabel/desktop.py#L254) | `lambda: dpg.show_item('import_report')` | ไม่มี precondition | เปิด Last import report; ก่อน import แสดงค่าเริ่มต้น No import has completed in this session. | OK |
| BTN-038 **Statistics / QC** [L255](../src/visionlabel/desktop.py#L255) | `lambda: self.statistics.open()` | ต้องมี project | ขาด project แจ้ง M; ผ่านเปิด Statistics และเริ่ม Refresh (ST) | OK |
| BTN-039 **Export YOLO** [L256](../src/visionlabel/desktop.py#L256) | `lambda: self.exports.open()` | ต้องมี maintainer project; ไม่ dirty/saving/polygon draft; ถ้า export เก่ากำลังทำต้อง project เดิม | M ระบุ role, รองานก่อนหน้า หรือให้ save; ผ่านเปิด Export; ใช้ข้อความรวมบางเงื่อนไข | M |
| BTN-040 **Accept [S]** [L258](../src/visionlabel/desktop.py#L258) | `lambda: self.review.request('accept')` | eligible: project/can_review/head IN_PROGRESS, ไม่ blocked/busy/review-busy/gesture; accept ผ่าน G; server ตรวจ lease/revision/self-review | ปุ่ม disable ตาม eligible; มี tooltip ทั่วไป; request แจ้ง M แบบรวม; Saving review/Review saved หรือ M error; decide ยังหยุดเงียบเมื่อ eligibility เปลี่ยน/dirty | S,D,M |
| BTN-041 **Reject [X]** [L263](../src/visionlabel/desktop.py#L263) | `lambda: self.review.request('reject')` | eligible: project/can_review/head IN_PROGRESS, ไม่ blocked/busy/review-busy/gesture; accept ผ่าน G; server ตรวจ lease/revision/self-review | ปุ่ม disable ตาม eligible; มี tooltip ทั่วไป; request แจ้ง M แบบรวม; Saving review/Review saved หรือ M error; decide ยังหยุดเงียบเมื่อ eligibility เปลี่ยน/dirty | S,D,M |
| BTN-042 **Review history** [L269](../src/visionlabel/desktop.py#L269) | `self.review.show_history` | ต้องมีภาพ; ผล async ต้องยังตรงภาพ | ไม่มีภาพเงียบ; ผ่านแล้วเปิด history รวมข้อความเมื่อไม่มีประวัติ; error M; ไม่มี loading เฉพาะปุ่ม | S |
| BTN-043 **Review settings** [L270](../src/visionlabel/desktop.py#L270) | `self.review.show_settings` | ต้องมี project และ can_manage_members | ขาด project/role เงียบ; ผ่านแล้วเปิด Review settings | S |
| BTN-044 **Connect** [L301](../src/visionlabel/desktop.py#L301) | `lambda: self.connect()` | ไม่ busy/saving/review-busy; URL/credentials ถูกต้อง | busy เงียบ; Connecting/Connected/error ส่ง M หลัง Connection modal; สำเร็จปิด modal | S,V |
| BTN-045 **Cancel** [L302](../src/visionlabel/desktop.py#L302) | `lambda: dpg.hide_item('connection')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |
| BTN-046 **Create** [L320](../src/visionlabel/desktop.py#L320) | `lambda: self.create_project()` | login และไม่ busy; classes parse ได้; server validate/authorize | ไม่ login หรือ busy ใช้ข้อความ Connect เดียวกัน; parse/API error ส่ง M หลัง modal; สำเร็จปิดและ load project | V,M |
| BTN-047 **Save and continue** [L331](../src/visionlabel/desktop.py#L331) | `lambda: self.save_then_continue()` | ใช้เงื่อนไข Save; dirty_save enable เมื่อไม่ blocked และมี edit claim | disabled ไม่มีเหตุผลเฉพาะข้างปุ่ม; Save ใช้ M ซึ่งอาจหลัง dirty dialog; สำเร็จไปต่อ | S,D,V |
| BTN-048 **Keep local recovery draft and continue** [L334](../src/visionlabel/desktop.py#L334) | `lambda: self.keep_then_continue()` | ต้องมี draft context ถ้าจะเก็บ; next_action ถ้าจะไปต่อ | persist_draft อาจไม่ทำอะไรถ้าขาด context; ปิด dialog และเรียก next_action; storage exception ก่อนปิดไม่มี catch เฉพาะ | R |
| BTN-049 **Cancel** [L337](../src/visionlabel/desktop.py#L337) | `lambda: self.cancel_navigation()` | ไม่มี precondition | ล้าง next_action และปิด dirty dialog | OK |
| BTN-050 **Restore draft for editing** [L349](../src/visionlabel/desktop.py#L349) | `lambda: self.restore_draft()` | can_edit; recovery ต้องมี (assert); enable เฉพาะ base ตรง+claim+can_edit | role แจ้ง M หลัง recovery modal; disabled ไม่มีสาเหตุเฉพาะ; สำเร็จใช้ draft/ปิด dialog/dirty | D,V,R |
| BTN-051 **Use server version; keep draft on disk** [L352](../src/visionlabel/desktop.py#L352) | `lambda: self.dismiss_recovery()` | store/image ใช้ archive draft ถ้ามี | ปิด dialog ใช้ server version; archive failure ไม่มี catch เฉพาะ | R |
| BTN-052 **Discard recovery draft** [L355](../src/visionlabel/desktop.py#L355) | `lambda: self.discard_recovery()` | store/image ต้องมี (assert) | ลบ local draft แล้วปิด dialog; assertion/storage failure ไม่มี feedback เฉพาะ | R |
| BTN-053 **Reload and compare** [L361](../src/visionlabel/desktop.py#L361) | `lambda: self.keep_then_reload()` | persist draft, image ถ้าจะ reload; open_image ไม่ busy/saving/review-busy | ปิด conflict แล้ว reload; ไม่มี image หรือ open_image guard อาจเงียบ; storage error ไม่มี catch เฉพาะ | S,R |
| BTN-054 **Keep editing locally** [L362](../src/visionlabel/desktop.py#L362) | `lambda: dpg.hide_item('conflict_dialog')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |
| BTN-055 **Load model names** [L391](../src/visionlabel/desktop.py#L391) | `lambda: load_import_model(self)` | path อ่านได้; YAML <=1 MiB และ parse names ได้ | mapping เปลี่ยน; success/error ไป M หลัง YOLO modal | V |
| BTN-056 **Preview** [L400](../src/visionlabel/desktop.py#L400) | `lambda: self.start_yolo_import(True)` | project; mapping ไม่ว่าง indices ไม่ซ้ำ/เป็นจำนวนเต็ม/class ถูก; ผ่าน import_inbox | ไม่มี project เงียบ; mapping error M หลัง modal; ผ่านแล้วปิด modalและ scan/queue/report | S,V |
| BTN-057 **Import predictions** [L401](../src/visionlabel/desktop.py#L401) | `lambda: self.start_yolo_import(False)` | project; mapping ไม่ว่าง indices ไม่ซ้ำ/เป็นจำนวนเต็ม/class ถูก; ผ่าน import_inbox | ไม่มี project เงียบ; mapping error M หลัง modal; ผ่านแล้วปิด modalและ scan/queue/report | S,V |
| BTN-058 **Cancel** [L402](../src/visionlabel/desktop.py#L402) | `lambda: dpg.hide_item('yolo_dialog')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |

### export_ui.py

| ID / ปุ่ม / จุดประกาศ | Callback | เงื่อนไขและเหตุผลหยุด | Feedback ปัจจุบัน | สังเกต |
|---|---|---|---|---|
| BTN-059 **Use current saved working data** [L153](../src/visionlabel/export_ui.py#L153) | `lambda: self.use_working_source()` | ไม่ export busy (ปุ่ม disable ระหว่าง busy) | silent guard แต่ disabled; ผ่านเปลี่ยน Source/ล้าง mapping+Settings changed | D |
| BTN-060 **Load model names / compare** [L171](../src/visionlabel/export_ui.py#L171) | `self.load_model` | ไม่ export busy; model path อ่านได้ <=1 MiB; names/mapping ถูก | busy เงียบและปุ่มไม่มี tag ใน set_busy; ผ่าน mapping+E คำแนะนำ; failure E/report | S |
| BTN-061 **Previous failures** [L173](../src/visionlabel/export_ui.py#L173) | `lambda: self.load_history()` | ไม่ busy; workspace project ตรง project_id; Older enable เมื่อ cursor | guard เงียบ; disabled busy/ไม่มีหน้าเก่า; ผ่าน E จำนวน failed jobs หรือ error E | S,D |
| BTN-062 **Older** [L178](../src/visionlabel/export_ui.py#L178) | `lambda: self.load_history(True)` | ไม่ busy; workspace project ตรง project_id; Older enable เมื่อ cursor | guard เงียบ; disabled busy/ไม่มีหน้าเก่า; ผ่าน E จำนวน failed jobs หรือ error E | S,D |
| BTN-063 **Load selected report** [L185](../src/visionlabel/export_ui.py#L185) | `self.load_report` | ไม่ busy; report_client/current project ตรง; เลือก job | guard/ไม่เลือก job เงียบ; disabled busy เท่านั้น; ผ่าน report/error E | S |
| BTN-064 **1. Prepare export / retry** [L204](../src/visionlabel/export_ui.py#L204) | `lambda: self.prepare()` | ไม่ busy; มี workspace project; valid mapping/percent/seed; server snapshot/files/review | busy/no project เงียบ (busy disable); validation E; progress; review confirmation หรือ Ready/report/error E | S,D |
| BTN-065 **Export anyway** [L210](../src/visionlabel/export_ui.py#L210) | `self.confirm_review` | ปุ่มแสดงเมื่อมี review_confirmation; เรียก prepare(token) | ซ่อน confirm controls แล้ว Prepare; token ถูกล้างและ prepare ยังหยุดได้หาก busy/no project | S |
| BTN-066 **Cancel review confirmation** [L213](../src/visionlabel/export_ui.py#L213) | `self.cancel_review` | ปุ่มแสดงเมื่อ review confirmation | ซ่อน controls, E: Export cancelled. Prepare again... | OK |
| BTN-067 **Open image / select shape** [L229](../src/visionlabel/export_ui.py#L229) | `self.open_issue` | failed_report, ไม่ busy; client/project ตรง; issue number ถูก; ผ่าน G/open_image | busy/no report guard เงียบแต่ disabled; mismatch/number error E; ผ่านเปิดภาพ/M รายงาน revision/selection/lease | D |
| BTN-068 **Save error report to parent folder** [L236](../src/visionlabel/export_ui.py#L236) | `self.save_error_report` | ต้อง failed_report; parent folder เขียนได้ | no report เงียบแต่ปุ่ม disabled ตาม failure/invalidate; ผ่าน E saved path; I/O error E | D |
| BTN-069 **Browse parent folder...** [L243](../src/visionlabel/export_ui.py#L243) | `self.browse_folder` | ไม่มี busy guard; valid parent ใช้เป็น default ถ้ามี | ปิด Export แล้วเปิด picker แบบ deferred; Cancel/choose กลับ Export; ไม่มี silent precondition | OK |
| BTN-070 **2. Save dataset to folder** [L254](../src/visionlabel/export_ui.py#L254) | `lambda: self.save()` | prepared และไม่ busy; folder name/parent/destination ถูก | no prepared/busy เงียบแต่ disabled; invalid E; progress ดาวน์โหลด/hash/extract; Complete path หรือ failure E | D |
| BTN-071 **Close** [L263](../src/visionlabel/export_ui.py#L263) | `lambda: dpg.hide_item('export_dialog')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |

### image_delete_ui.py

| ID / ปุ่ม / จุดประกาศ | Callback | เงื่อนไขและเหตุผลหยุด | Feedback ปัจจุบัน | สังเกต |
|---|---|---|---|---|
| BTN-072 **Yes, delete image** [L26](../src/visionlabel/image_delete_ui.py#L26) | `self.confirm` | ต้อง pending delete request; server maintain/revision/claim | ไม่มี pending เงียบ (กัน double-click); ผ่านปิด dialog/M Deleting/ผล; failure ส่ง M; ดูจุดเริ่ม Delete image ใน Desktop | OK |
| BTN-073 **No, keep image** [L27](../src/visionlabel/image_delete_ui.py#L27) | `self.cancel` | ไม่มี precondition | ล้าง pending/busy และปิด confirmation; เห็นผลการยกเลิก | OK |

### project_ui.py

| ID / ปุ่ม / จุดประกาศ | Callback | เงื่อนไขและเหตุผลหยุด | Feedback ปัจจุบัน | สังเกต |
|---|---|---|---|---|
| BTN-074 **Refresh** [L40](../src/visionlabel/project_ui.py#L40) | `lambda: self.refresh()` | ผ่าน P-run | โหลด tree/รายการและ P: Projects refreshed; busy เงียบ ไม่มี loading เฉพาะ | S |
| BTN-075 **New project** [L47](../src/visionlabel/project_ui.py#L47) | `self.new_project` | manager ไม่ busy | busy เงียบ; ปิด PM และเลื่อนเปิด New project | S |
| BTN-076 **Save project metadata** [L64](../src/visionlabel/project_ui.py#L64) | `self.save_project` | selected project, ไม่ manager busy; ผ่าน P-run; server maintainer/revision/metadata | ขาด selection/busy เงียบ; สำเร็จ refresh; server error P | S |
| BTN-077 **Open selected project** [L65](../src/visionlabel/project_ui.py#L65) | `self.open_selected` | selected project, ไม่ manager busy; ผ่าน G/load_project | ขาด selection/busy เงียบ; ผ่านปิด PM แล้วเปิด project | S |
| BTN-078 **Create folder** [L80](../src/visionlabel/project_ui.py#L80) | `lambda: self.save_folder(True)` | Create ไม่ต้อง selected folder; Rename/Delete ต้องเลือก fid; ผ่าน P-run; server role/name/tree/revision/empty validation | Rename/Delete ไม่เลือก folder เงียบ; P-run busy เงียบ; ผ่าน refresh; error P | S |
| BTN-079 **Rename / move folder** [L81](../src/visionlabel/project_ui.py#L81) | `lambda: self.save_folder(False)` | Create ไม่ต้อง selected folder; Rename/Delete ต้องเลือก fid; ผ่าน P-run; server role/name/tree/revision/empty validation | Rename/Delete ไม่เลือก folder เงียบ; P-run busy เงียบ; ผ่าน refresh; error P | S |
| BTN-080 **Delete empty folder** [L84](../src/visionlabel/project_ui.py#L84) | `lambda: self.save_folder(False, True)` | Create ไม่ต้อง selected folder; Rename/Delete ต้องเลือก fid; ผ่าน P-run; server role/name/tree/revision/empty validation | Rename/Delete ไม่เลือก folder เงียบ; P-run busy เงียบ; ผ่าน refresh; error P | S |
| BTN-081 **Edit classes / dataset checkpoints** [L88](../src/visionlabel/project_ui.py#L88) | `lambda: self.datasets.open()` | manager ไม่ busy; selected project; can_manage_members | busy เงียบ; ไม่มี selection/role แจ้ง P แล้วคง PM; ผ่านเลื่อนเปิด Dataset modal และ refresh ผ่าน DS-run | S |
| BTN-082 **Save active classes as template** [L100](../src/visionlabel/project_ui.py#L100) | `self.save_template` | ต้อง selected project; ผ่าน P-run; server maintainer/template name | ไม่มี project/busy เงียบ; refresh templates หรือ error P | S |
| BTN-083 **New project from template** [L104](../src/visionlabel/project_ui.py#L104) | `self.new_from_template` | template ที่เลือกต้องอยู่ในรายการ; manager ไม่ busy | ไม่มี template/busy เงียบ; ผ่านกรอก classes/task และเปิด New project | S |
| BTN-084 **Checkpoints: create / browse / export / restore** [L110](../src/visionlabel/project_ui.py#L110) | `lambda: self.datasets.open()` | manager ไม่ busy; selected project; can_manage_members | busy เงียบ; ไม่มี selection/role แจ้ง P แล้วคง PM; ผ่านเลื่อนเปิด Dataset modal และ refresh ผ่าน DS-run | S |
| BTN-085 **Refresh working / schema / export history** [L114](../src/visionlabel/project_ui.py#L114) | `self.load_versions` | selected project; ผ่าน P-run | ไม่มี project/busy เงียบ; ผ่านแสดง working/schema/export history; error P | S |
| BTN-086 **Load images** [L126](../src/visionlabel/project_ui.py#L126) | `self.load_images` | selected project; ผ่าน P-run | ไม่มี project/busy เงียบ; ผ่านเติม image picker; เกิน 200 แจ้ง P ให้ค้นแคบลง; error P | S |
| BTN-087 **Add selected image** [L135](../src/visionlabel/project_ui.py#L135) | `self.add_image` | manager ไม่ busy; ต้องมีภาพใน picker | busy/ไม่มีภาพเงียบ; ผ่านเพิ่ม ID ไม่ซ้ำและ invalidate preview; เลือกภาพซ้ำรายการไม่เปลี่ยน | S |
| BTN-088 **Clear image selection** [L136](../src/visionlabel/project_ui.py#L136) | `self.clear_images` | manager ไม่ busy | busy เงียบ; ผ่านล้าง selection/invalidate preview; ว่างอยู่แล้วไม่มีการเปลี่ยนให้เห็น | S |
| BTN-089 **Preview remap** [L153](../src/visionlabel/project_ui.py#L153) | `self.preview_remap` | selected project, ไม่ manager busy; mapping parse; ผ่าน P-run; serverตรวจ image list/role | missing/busy เงียบ; malformed/selection changed/error แจ้ง P; ผ่าน report+enable Apply เมื่อ changed_images>0 | S |
| BTN-090 **Apply preview / retry failed items** [L157](../src/visionlabel/project_ui.py#L157) | `self.apply_remap` | preview, ไม่ manager busy; ผ่าน P-run; claims/revisions/role ตรวจรายภาพ | disabled ไม่มี preview/ไม่มี change ไม่มีเหตุผลเฉพาะ; busy เงียบ; ผ่านมี per-image result และ Remap finished; error P | S,D |
| BTN-091 **Close** [L164](../src/visionlabel/project_ui.py#L164) | `lambda: dpg.hide_item('project_manager')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |

### review_ui.py

| ID / ปุ่ม / จุดประกาศ | Callback | เงื่อนไขและเหตุผลหยุด | Feedback ปัจจุบัน | สังเกต |
|---|---|---|---|---|
| BTN-092 **Reject and save reason** [L29](../src/visionlabel/review_ui.py#L29) | `lambda: self.reject()` | reason Other ต้องมี detail; ผ่าน G/decide ซึ่งต้อง eligible และ saved/ไม่ dirty | Other ไม่มี detail แจ้ง M หลัง reject modal; ผ่านปิด dialog/Saving review; decide guard อาจเงียบ | S,V |
| BTN-093 **Cancel** [L30](../src/visionlabel/review_ui.py#L30) | `lambda: dpg.hide_item('review_reject')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |
| BTN-094 **Save setting** [L36](../src/visionlabel/review_ui.py#L36) | `self.save_setting` | ไม่ review busy; project; server maintainer/revision/reason | busy/no project เงียบ; สำเร็จปิด dialog; server error M หลัง Review settings; ไม่มี saving message เฉพาะ | S,V |
| BTN-095 **Cancel** [L37](../src/visionlabel/review_ui.py#L37) | `lambda: dpg.hide_item('review_settings')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |

### statistics_ui.py

| ID / ปุ่ม / จุดประกาศ | Callback | เงื่อนไขและเหตุผลหยุด | Feedback ปัจจุบัน | สังเกต |
|---|---|---|---|---|
| BTN-096 **Refresh** [L27](../src/visionlabel/statistics_ui.py#L27) | `lambda: self.refresh()` | ไม่ statistics busy; workspace project | missing/busy เงียบ; ST Reading saved annotations; ผ่านตาราง/QC/time; changed project/error มี ST | S |
| BTN-097 **Close** [L31](../src/visionlabel/statistics_ui.py#L31) | `lambda: dpg.hide_item('statistics')` | ไม่มี precondition ใน callback | ซ่อนหน้าต่างทันที; ไม่ใช่คำสั่ง cancel งาน service ที่กำลังทำ | OK |

### team_ui.py

| ID / ปุ่ม / จุดประกาศ | Callback | เงื่อนไขและเหตุผลหยุด | Feedback ปัจจุบัน | สังเกต |
|---|---|---|---|---|
| BTN-098 **Refresh** [L31](../src/visionlabel/team_ui.py#L31) | `lambda: self.refresh()` | ไม่ team busy | busy เงียบ; T Loading/Loaded และ role explanation; error T | S |
| BTN-099 **Retry last request** [L32](../src/visionlabel/team_ui.py#L32) | `lambda: self.retry()` | ไม่ busy; มี pending retryable | guard เงียบแต่ retry button enable เฉพาะ pending Problem status>=500; T Saving/refresh/error | D |
| BTN-100 **Close** [L35](../src/visionlabel/team_ui.py#L35) | `lambda: self.close()` | ไม่ busy | busy แจ้ง T รอ; ผ่านล้าง password/pending และปิดหน้าต่าง | OK |
| BTN-101 **Add / update role** [L62](../src/visionlabel/team_ui.py#L62) | `lambda: self.member(False)` | มี project และ user ID; mutate/retry ไม่ busy; server role/revision | missing project/ID แจ้ง T; busy ผ่าน mutate เงียบ; ปุ่ม disabled ถ้าไม่มี can_manage_members; success refresh/error T | S,D |
| BTN-102 **Remove from project** [L67](../src/visionlabel/team_ui.py#L67) | `lambda: self.member(True)` | มี project และ user ID; mutate/retry ไม่ busy; server role/revision | missing project/ID แจ้ง T; busy ผ่าน mutate เงียบ; ปุ่ม disabled ถ้าไม่มี can_manage_members; success refresh/error T | S,D |
| BTN-103 **New account form** [L88](../src/visionlabel/team_ui.py#L88) | `lambda: self.clear_user()` | Accounts tab แสดงเฉพาะ admin; ไม่มี busy guard | ล้าง selected user/form; ถ้าว่างอยู่แล้วไม่มีคำอธิบายใหม่ แต่เป็น reset form | OK |
| BTN-104 **Create account** [L89](../src/visionlabel/team_ui.py#L89) | `lambda: self.create_user()` | Accounts admin tab; ต้องไม่ selected_user; mutate ไม่ busy; server validate | selected_user แจ้ง New account form ที่ T; busy เงียบ; T Saving/refresh/error | S |
| BTN-105 **Update selected account** [L90](../src/visionlabel/team_ui.py#L90) | `lambda: self.update_user()` | Accounts admin tab; ต้อง selected_user; mutate ไม่ busy; server revision/role | missing selection แจ้ง T; busy เงียบ; T Saving/refresh/error | S |
| BTN-106 **Use selected account for project role** [L91](../src/visionlabel/team_ui.py#L91) | `lambda: self.use_user()` | Accounts admin tab; ต้อง selected_user | ไม่มี selection เงียบ; ผ่านใส่ member ID+T เลือก role ต่อ | S |

## สิ่งที่ควรให้ความสำคัญก่อน (ข้อเสนอ ยังไม่ลงมือแก้)

1. **Save และข้อมูลที่แก้แล้ว:** แยกไม่มีภาพ / กำลังบันทึก / ไม่มีการเปลี่ยน / edit lease ไม่พร้อม; shared Save ใช้ทั้งปุ่มและ autosave จึงห้ามเติม popup ทุกครั้ง. ตรวจ feedback ของ recovery และ dirty dialog ให้ผู้ใช้รู้ว่าข้อมูลเก็บที่ใด.
2. **สิทธิ์/selection:** Review settings/history, Project metadata/template/history, Dataset resume/view, Team use account ควรบอกสิ่งที่ยังขาด. Disabled ต้องมีเหตุผลที่ผู้ใช้เข้าถึงได้.
3. **สถานะ busy:** P-run/DS-run/Team.mutate เป็นจุดร่วม; ต้องแสดงว่างานใดกำลังทำ และควบคุมปุ่มให้สอดคล้อง. อย่าใช้ข้อความ Connect เมื่อเหตุผลจริงคือ busy.
4. **ปลายทางข้อความ:** Reject validation, Review settings failure, YOLO model/mapping, Connection/Create, Recovery และ Checkpoint browser อาจแจ้งไปด้านหลัง modal. การมี message call จึงยังไม่เพียงพอ.
5. **รายการว่าง/ขอบเขต:** Previous/Next ที่ขอบ, Dataset Older/Next images, Resume queue, Load selected report และ empty previews ต้องแยกไม่มีข้อมูลกับกำลังโหลด.
6. **modal transition:** ปุ่ม dataset entry ใช้ deferred open แล้ว; checkpoint→Export และเปิด browser ซ้อน modal ยังควรตรวจเส้นทางจริง ไม่สรุปว่าเสียจาก static analysis เพียงอย่างเดียว.
7. **ข้อความการลบภาพ:** confirmation ระบุ permanently/cannot be undone แต่ Phase 10 มี controlled restore จาก checkpoint ก่อนลบ ต้องแยกขอบเขตคำอธิบายในการแก้ UX รอบถัดไป.

## Widgets ที่ framework สร้างและเส้นทางอื่น

| จุด | เงื่อนไข/ผล | Feedback / ขอบเขต |
|---|---|---|
| Export directory picker: choose/OK | `choose_folder` ใส่ file_path_name แล้ว `cancel_folder` | ปิด picker/เลื่อนเปิด Export; built-in validation ไม่ได้ตรวจในรอบ source audit |
| Export directory picker: Cancel | `cancel_folder` | กลับ Export แบบ deferred |
| ปุ่ม X ของหน้าต่าง | ตาม Dear PyGui window configuration; main/Connection/dirty/recovery/Delete confirmation ใช้ no_close=True | ไม่ใช่ explicit add_button; ต้องตรวจว่าสัมพันธ์กับ close/cancel callback และ pending jobs อย่างไรใน runtime |
| A/D, Ctrl+S, S/X, R/P/V/F, Undo/Redo/Delete | เรียกหลาย action เดียวกับปุ่ม | `key_press` มี silent suppression เมื่อ modal/input active/busy เพื่อไม่รบกวนการพิมพ์; ไม่ควรเพิ่ม notification ทุก key event |
| การเลือก project/image/class และ checkbox | selectable/combo callbacks | อยู่นอก button count; ยังใช้ shared guards/message paths ที่สำรวจ |
| Launcher | terminal/CLI เปิด service+desktop | ไม่พบปุ่ม GUI ที่ประกาศใน launcher.py |

## ผลลัพธ์และขั้นต่อไป

ครบรายการและ callback trace สำหรับ explicit buttons 106/106 จุด. ยังไม่ใช่การรับรอง UI runtime หรือการตรวจทุก server error combination. ไม่แก้ source, wheel หรือคู่มือการใช้งานในรอบนี้.

ไฟล์คู่กัน `button-feedback-inventory.csv` มี ID, source line, callback, tag, initial enabled/show, conditions, feedback และ flags สำหรับกรองงาน. เลขบรรทัดผูกกับ baseline commit ด้านบน.

รอบแก้ควรเริ่มจาก reason สำหรับ action ที่กดเอง, feedback ภายในหน้าต่างที่เปิดอยู่ และ busy state ที่สื่อสารได้ โดยรักษา autosave/keyboard/background callbacks ให้ทำงานได้โดยไม่แจ้งซ้ำ. ต้องเลือก acceptance scenarios ก่อนปรับจริง.
