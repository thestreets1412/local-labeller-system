# สรุปการทดสอบที่ยังเหลือ — VisionLabel / DataTracking, Phase 0–8

ปรับปรุงวันที่ 6 ตุลาคม 2026: เพิ่ม Phase 8 working YOLO export บนฐานโค้ด `89ceed8` พร้อมผลทดสอบของงาน Phase 8 รอบนี้

## 1. วิธีอ่านรายงานนี้

รายงานนี้เทียบคำยืนยันของผู้ใช้ในบทสนทนากับแผนและหลักฐานที่เก็บไว้ใน repository ส่วน Phase 0–7 อ้างอิงผลเดิม; Phase 8 มีการทดสอบใหม่ตามบันทึกท้ายรายงาน ข้อที่ระบุว่า **ยังไม่ยืนยัน** หมายถึงยังไม่มีหลักฐานยืนยันเป็นรายกรณี ไม่ได้หมายความว่าผู้ใช้ไม่เคยลอง หรือโปรแกรมมีปัญหา

การขอเริ่ม Phase ถัดไปไม่ถือเป็นการรับรองว่า Phase ก่อนหน้าผ่านทุกข้อ โดยเฉพาะงานที่ตกลงให้ทำเฉพาะส่วนอิสระก่อน

| สถานะ | ความหมาย |
|---|---|
| ผู้ใช้ยืนยันแล้ว | มีคำยืนยันในบทสนทนา แต่ครอบคลุมเฉพาะสิ่งที่ระบุ |
| พร้อมลองที่บ้าน | ฟังก์ชันมีแล้ว ทดสอบบน Windows เครื่องเดียวได้ |
| รอเครื่อง/สภาพแวดล้อมบริษัท | ต้องมีเครื่องอื่น อุปกรณ์หรือข้อมูลหน้างาน และระบบที่เกี่ยวข้องต้องพร้อมก่อน |
| รอพัฒนา | ยังไม่มีฟังก์ชันหรือการเชื่อมต่อครบ จึงยังใช้ขั้นตอนนี้รับรองผลไม่ได้ |
| มีหลักฐานฝั่งพัฒนา | มี automated test หรือ rendered smoke ในเอกสาร ไม่แทนการลองเมาส์จริงหรือการรับรองหน้างาน |

**ข้อจำกัดปัจจุบัน:** Client รับเฉพาะ HTTP บน loopback และ Server ผูกกับ `127.0.0.1` การ clone ที่บริษัทไม่ได้ทำให้ต่อ Server ข้ามเครื่องได้ทันที งาน LAN/HTTPS/SMB ต้องพัฒนาต่อก่อน ส่วนการเปิด Client สองหน้าต่างบนเครื่องเดียวทำได้เพื่อทดสอบบางกรณีของสิทธิ์และการแย่งแก้ไข

## 2. สรุปแต่ละ Phase

| Phase | ผู้ใช้ยืนยันแล้ว | สิ่งที่ยังต้องลอง/รับรอง | สถานะจบ Phase |
|---|---|---|---|
| 0 — Foundation | มี Python 3.12.10, `.venv`, Git repo | การติดตั้งบนเครื่องใหม่, ข้อจำกัดที่เก็บ DB, ตรวจชุด license ที่จะแจกจริง | มีหลักฐานทางเทคนิค; การแจกจริงต้องตรวจใน Phase 6 |
| 1 — Rectangle / Classification | สร้าง admin/project, วาดกรอบ, เลือกคลาส, shortcut, classification, zoom/pan/drag/fit, ปิดเปิดแล้วข้อมูลอยู่, DPI บนเครื่องผู้ใช้ | กรณีย่อยเรื่อง resize/undo/autosave/recovery, crosshair, Unicode และ DPI ทุกระดับ | ผู้ใช้รับ milestone การใช้งานในเครื่องแล้ว; coverage รายละเอียดด้านล่างยังเปิด |
| 2 — Team / Review | ลองส่วน account/membership แล้ว และรายงานว่าเพิ่มคนเข้า project ยังสับสน | Member picker ที่ปรับใหม่, บทบาท/ถอนสิทธิ์, สอง Client; workflow ทีมและ LAN | ยังไม่จบ มี implementation ค้าง |
| 3 — Polygon / QC / Versions | ยังไม่มีคำยืนยันรายฟังก์ชัน | Polygon และ working QC พร้อมลอง; schema migration/release/version diff รอพัฒนา | ยังไม่จบ |
| 4 — Split | ยังไม่มีคำยืนยัน | ทดลอง split preview ผ่าน CLI; GUI และ split ที่ผูก released version รอพัฒนา | ยังไม่จบ |
| 5 — Export / Migration | ยังไม่มีคำยืนยัน | Format preview และ legacy dry-run พร้อมลอง; export จาก approved release และ LabelMe import เข้า project รอพัฒนา; working export มีใน Phase 8 | ยังไม่จบ; YOLO import จริงเพิ่มใน Phase 7 และ working export เพิ่มใน Phase 8 |
| 6 — Operations | ยังไม่มีคำยืนยัน | Backup/restore, offline kit, เครื่องใหม่, performance และ failure drills | ยังไม่จบ; production packaging และระบบอื่นยังค้าง |
| 7 — YOLO Predictions / BMP | ผู้ใช้ยืนยัน import prediction และแก้กรอบกับงานจริงที่บริษัทได้ (6 ต.ค. 2026) | ยังต้องยืนยัน preview/reload, mapping, empty/missing/conflicts และชนิด BMP รายละเอียด | ยืนยัน import/edit กับงานจริงแล้ว; กรณีย่อยอื่นยังเปิด |
| 8 — Working YOLO Export | ยังไม่มีคำยืนยันจากผู้ใช้ | ส่งออกทั้งสาม task, % split, destination, การย้าย dataset และเทรนจริงใน Ultralytics | มี automated/API/GUI evidence; รอผู้ใช้รับรอง training environment จริง |

## 3. เตรียมพื้นที่ทดสอบแยกจากงานจริง

ใช้โฟลเดอร์ใหม่บนดิสก์ local เช่น `D:\VisionLabel-UAT` ซึ่งอยู่นอก Git และไม่ใช่ OneDrive/SMB ถ้าชื่อนี้มีข้อมูลอยู่แล้วให้เลือกชื่อใหม่ ไม่ต้องล้างข้อมูลเดิม

รัน PowerShell จาก `D:\Python\local-labeller-system` ปิด launcher/service เดิมก่อน เพื่อไม่ให้แย่งพอร์ต `8765`:

```powershell
# สร้างภาพสังเคราะห์ 100 ภาพใน inbox ของพื้นที่ทดสอบ
.\.venv\Scripts\python.exe -m visionlabel.cli samples --root D:\VisionLabel-UAT --count 100

# เริ่มใช้งาน และสร้าง admin เมื่อเปิด DataRoot ใหม่ครั้งแรก
.\.venv\Scripts\python.exe -m visionlabel.launcher --root D:\VisionLabel-UAT
```

ตั้ง password อย่างน้อย 12 ตัวอักษร สร้าง project `UAT-Detection` แบบ `detection` และคลาส `Spring,Defect` ใช้ project แยกสำหรับ `classification` และ `segmentation` ประเภทงานของ project ไม่ได้เปลี่ยนตามเครื่องมือที่กด

ทุกคำสั่งที่มี `--root` ในรายงานต้องใช้ DataRoot เดียวกับที่กำลังทดสอบ ปลายทาง backup/restore, kit และไฟล์รายงานต้องเป็นชื่อใหม่ หากมีอยู่แล้วให้เปลี่ยนชื่อ

บันทึกอย่างน้อย: รหัสกรณี, วันที่, commit/build, Windows Scale, ชื่อภาพทดสอบ, ผลที่ได้ และภาพหน้าจอเมื่อผิดจากที่คาด อย่าใส่ password หรือข้อมูลโรงงานที่เป็นความลับลง Git

## 4. Phase 0 — Foundation และการเตรียมเครื่อง

เรื่อง JSON schema, serializer, geometry validation และ path validation มีหลักฐาน automated tests แล้ว ผู้ใช้ไม่จำเป็นต้องตรวจ byte ของ JSON ด้วยมือเพื่อเริ่มลอง editor

| รหัส / สถานะ | วิธีทดสอบที่ยังต้องยืนยัน | ผลที่ควรได้ |
|---|---|---|
| P0-01 พร้อมลอง | ใช้ DataRoot ใหม่ตามข้อ 3 เปิด launcher สร้าง admin แล้วล็อกอิน | เปิด service และ desktop ได้ สร้าง project และ import ภาพได้โดยไม่ติดตั้ง package แบบ global |
| P0-02 รอเครื่องบริษัทที่มี mapped drive/UNC | ให้ผู้พัฒนาหรือ IT ใช้ **path ทดสอบใหม่** บน network share เป็น `--root` ขณะเริ่ม service ห้ามใช้ DB งานจริง | ปฏิเสธการวาง DB บน network path อย่างชัดเจน; ไม่ถือว่า network share เป็นที่เก็บ SQLite ที่รองรับ |
| P0-03 รอชุดแจกจริง | เมื่อสร้าง installer/kit ที่จะใช้จริง ตรวจ dependency และ native notices กับรายการที่ bundle | ไม่มี license ที่ไม่ทราบที่มา; มี notices สำหรับข้อยกเว้นที่ผู้ใช้อนุญาตไว้ |

P0-03 มี inventory อยู่แล้ว แต่ไม่ใช้ inventory ของ wheel ปัจจุบันรับรอง Nuitka build ที่ยังไม่ได้สร้าง รายการข้อยกเว้นอยู่ใน `AGENTS.md` และ `THIRD_PARTY_NOTICES.md`

## 5. Phase 1 — Rectangle, Classification และ Recovery

**ยืนยันแล้ว:** สร้าง admin/project, วาด rectangle, กำหนดคลาส, shortcut โดยรวม, classification, zoom/pan/drag/fit, ปิดเปิดแล้วข้อมูลคงเดิม และ DPI ใช้ได้บนเครื่องผู้ใช้ อย่างไรก็ตามยังไม่ได้ระบุเปอร์เซ็นต์ Scale หรือทุกกรณีย่อย

### 5.1 พร้อมลองที่บ้าน

| รหัส | ขั้นตอน | ผลที่ควรได้ |
|---|---|---|
| P1-01 Import 100 ภาพ / inbox | ใน project ใหม่ กด **Import inbox** ตรวจ **Last import report** แล้วกดซ้ำ จากนั้นสร้าง project อีกอันแล้ว import จาก inbox เดิม | ครั้งแรกได้ 100 ภาพถ้าใช้ชุดใหม่; ครั้งซ้ำใน project เดิมรายงาน duplicate ไม่เพิ่มซ้ำ; project ที่สองรับภาพเดิมได้ การ import เป็นการสั่ง scan ไม่ใช่ folder watcher |
| P1-02 Rectangle ครบวงจร | กด **R** ลากทั้งซ้ายบน→ขวาล่างและอีก 3 ทิศ กด **V** เลือก/ย้าย ลากทั้งมุมและขอบ resize ลองชิดขอบภาพ ลบแล้ว undo/redo จากนั้น Ctrl+S และปิดเปิด | กรอบไม่กลับด้าน/หลุดภาพ, selection และ handle ตรงตำแหน่ง, undo/redo คืนรูปทรงถูก, reload ได้ผลที่ save ไว้ |
| P1-03 Crosshair | เข้า Rectangle เลื่อนเมาส์บนภาพ/นอกภาพ เปลี่ยนเป็น Select แล้ว Space+drag | กากบาทและเส้นแนวนอน/ตั้งครอบคลุมส่วนภาพที่มองเห็นใน Rectangle; ไม่ค้างบนพื้นที่อื่นหรือขณะ pan/Select |
| P1-04 Shortcut กับช่องพิมพ์ | คลิกช่อง search หรือช่องชื่อ project/class แล้วพิมพ์ตัวอักษร `a d r v f` และตัวเลข ทดลอง shortcut อีกครั้งหลังกลับ canvas | ระหว่างพิมพ์ไม่เปลี่ยนภาพ/เครื่องมือ/คลาสโดยไม่ตั้งใจ; เมื่ออยู่ canvas shortcut ทำงานตามปกติ |
| P1-05 Autosave / dirty navigation | แก้กรอบ รออย่างน้อยประมาณ 2 วินาที ตรวจสถานะ save และ revision; อีกครั้งแก้แล้วกด A/D ทันที ทดลองตัวเลือก save/เก็บ draft/cancel ทีละรอบ | revision เพิ่มหลัง server ยืนยัน; การเปลี่ยนภาพไม่ทิ้งงานเงียบ ๆ; cancel อยู่ภาพเดิม และ draft กู้คืนได้ตามเงื่อนไข |
| P1-06 Empty / classification | ใน detection ใช้ภาพไม่มีกรอบ: ภาพหนึ่งเลือก **Verified empty** อีกภาพปล่อยยังไม่ label; ใน classification เลือกคลาส แล้วเปลี่ยนคลาสและ save/reload | Empty แยกจาก unlabeled; classification มีคลาสเดียวต่อภาพและคืนค่าล่าสุดหลัง reload |
| P1-07 Scale / Unicode | ทดสอบ Windows Scale 100%, 125%, 150%, 200% ที่เครื่องรองรับ เปิดแอปใหม่เมื่อจำเป็น ใช้ภาพ/คลาสชื่อไทย ปรับขนาดหน้าต่าง แล้ว zoom/pan/resize กรอบเดิม | ข้อความอ่านได้ ปุ่มไม่หาย เมาส์/handle ตรงกรอบ พิกัดภาพไม่เลื่อน; บันทึกค่าที่ลองจริง ค่าที่ลองไม่ได้ให้ระบุ N/A |
| P1-08 Browser / ภาพใหญ่ | Import ภาพเกินหนึ่งหน้า ค้นชื่อและเปลี่ยน status filter; เปิดภาพใหญ่กว่า 2048 px แล้ว fit/zoom/save/reload | เปลี่ยนหน้า/ค้นหาได้ ไม่ค้างรายการผิด project; preview อาจย่อเพื่อแสดงผล แต่พิกัดกรอบยังอ้าง raster ต้นฉบับ |

### 5.2 P1-09 หยุด Server แล้วกู้ draft — พร้อมลองบนข้อมูลทดสอบ

ใช้ Server แยกจาก Client เพื่อหยุดเฉพาะ Server ได้ ปิด launcher เดิมก่อน ถ้า DataRoot ยังไม่เคย initialize ให้รัน `init` เพียงครั้งแรก:

```powershell
# เฉพาะ DataRoot ใหม่ที่ยังไม่มี admin
.\.venv\Scripts\python.exe -m visionlabel.cli init --root D:\VisionLabel-UAT

# Terminal A
.\.venv\Scripts\python.exe -m visionlabel.cli serve --root D:\VisionLabel-UAT

# Terminal B
.\.venv\Scripts\python.exe -m visionlabel.desktop --server http://127.0.0.1:8765
```

1. เปิดภาพที่ save แล้ว จด revision และตำแหน่งกรอบ
2. ใน Terminal A กด Ctrl+C หยุด service โดยไม่ปิด Client แก้กรอบเพิ่ม
3. ควรเห็นการ save ล้มเหลว/ต้อง reconnect และงานในเครื่องยังคงอยู่ ไม่แสดงว่าสำเร็จแล้ว
4. เริ่ม Server ด้วยคำสั่งเดิม ใช้ **Reload / reconnect** แล้วเลือก restore draft เมื่อระบบแจ้งว่าฐาน revision ตรงกัน
5. Save และเปิดภาพใหม่ กรอบที่กู้ต้องอยู่ครบ และ revision เพิ่มหลังบันทึกสำเร็จ

กรณี draft เก่า: หลังหยุด Server ให้ปิด Client A เพื่อเก็บ draft เริ่ม Server แล้วเปิด Client B ล็อกอินด้วยอีกบัญชีที่เป็น annotator ของ project แก้ภาพเดียวกันและ save จากนั้นปิด B เปิด A ด้วยบัญชีเดิมและ reconnect ระบบต้องแสดงความต่างของ draft เก่ากับข้อมูลใหม่ ไม่เขียนทับงาน B อัตโนมัติ ให้เทียบและนำการแก้กลับมาด้วยมือ

**P1-10 Crash จริงยังไม่ยืนยันโดยผู้ใช้:** ทำเฉพาะ DataRoot ทดสอบและ process ที่ระบุได้แน่นอน Save ให้ server ยืนยันก่อน แล้วจบ process ทดสอบผ่าน Task Manager เปิดใหม่และตรวจ committed revision ต้องอยู่ครบ งานที่ยังไม่ save อาศัย draft และต้องแยกจาก committed data การทดสอบจังหวะ crash ก่อน/หลัง DB commit แบบแม่นยำเป็นงานผู้พัฒนาที่มี automated evidence แล้ว ไม่จำเป็นต้องจำลองด้วยมือบนข้อมูลจริง

## 6. Phase 2 — บัญชี สมาชิก และการทำงานเป็นทีม

ผู้ใช้ลอง increment บัญชี/สมาชิกแล้ว แต่ยังไม่มีคำยืนยันหลังปรับวิธีเลือกคนจาก dropdown และไม่ได้ยืนยัน negative cases ด้านสิทธิ์ครบ

### 6.1 พร้อมลองที่บ้าน

| รหัส | ขั้นตอน | ผลที่ควรได้ |
|---|---|---|
| P2-01 เพิ่มสมาชิก | Admin เปิด **Team & users → Accounts (administrator) → New account form** สร้าง user; ไป **Project members** เลือก **User**, `annotator`, **Add / update role** | หา account ที่เพิ่งสร้างเจอ เพิ่มเข้า project ได้โดยไม่ต้องคัดลอก UUID สำหรับ admin |
| P2-02 Account ไม่เท่ากับ membership | สร้าง user ใหม่แต่ยังไม่เพิ่มสมาชิก ล็อกอินผ่าน **Connection** แล้วกลับ admin เพิ่มสมาชิกและล็อกอินใหม่ | ก่อนเพิ่มสมาชิกเข้าถึง project นั้นไม่ได้ หลังเพิ่มแล้วเข้าถึงได้; ไม่เห็น project อื่นที่ไม่ได้รับสิทธิ์ |
| P2-03 Viewer / Annotator | ให้ user เป็น viewer เปิดภาพแล้วลองแก้/save; เปลี่ยนเป็น annotator และ reconnect แล้วลองใหม่ | Viewer อ่านได้แต่แก้/save ไม่ได้; annotator ทำ annotation ได้ แต่ไม่มีสิทธิ์จัดการบัญชีหรือ import แบบ admin/maintainer |
| P2-04 ถอนสิทธิ์ขณะเปิดภาพ | เปิด desktop สองหน้าต่างต่อ Server เดียว: A เป็น annotator เปิดภาพ; B เป็น admin เปลี่ยน A เป็น viewer หรือเอาออกจากสมาชิก แล้วให้ A ลอง save | สิทธิ์/lease เดิมใช้ save ไม่ได้ งานกลางไม่ถูกเขียนทับ และมีทางเก็บงานในเครื่อง/กลับมาโหลดใหม่ |
| P2-05 Reset / disable / revoke | ใช้บัญชีทดลอง: Admin reset password, disable หรือ revoke sessions ทีละกรณี ระหว่างบัญชีนั้นล็อกอินในอีกหน้าต่าง จากนั้นลองอ่าน/บันทึกที่ต้องยืนยันสิทธิ์ | Session เดิมใช้งานต่อไม่ได้ ต้องล็อกอินใหม่; password เก่าหลัง reset ใช้ไม่ได้; re-enable ไม่คืนชีพ session เก่า |
| P2-06 ป้องกันตัดสิทธิ์คนสุดท้าย | ใน project ทดลอง ลองเอา maintainer ที่เหลือคนสุดท้ายออก และลอง disable admin ที่ active อยู่คนสุดท้าย | ปฏิเสธชัดเจนและยังมีผู้ดูแลเหลืออยู่ ไม่ใช่การทดสอบลบบัญชีงานจริง |
| P2-07 สอง Client แย่งภาพ | เปิด desktop สองหน้าต่างด้วย annotator คนละบัญชีบน Server เดียว เปิดภาพเดียวกันเกือบพร้อมกัน ให้ผู้ที่ถือสิทธิ์แก้ไข save | มีผู้ถือ lease แก้ไขได้คนเดียว อีกหน้าต่างต้องแจ้ง conflict/ไม่ให้ save ทับ; ไม่ถือเป็นการทดสอบ LAN สองเครื่อง |

เปิด Client หน้าต่างที่สองด้วยคำสั่ง desktop ใน P1-09 โดยไม่เริ่ม Server ซ้ำ ข้อ P2-07 เป็นการสังเกตผ่าน UI; การแข่งขันพร้อมกันระดับ transaction มี automated test ของผู้พัฒนา

### 6.2 รอพัฒนาก่อน แล้วจึงทดสอบตามนี้

| รหัส / Requirement | สิ่งที่ยังขาด | วิธีทดสอบเมื่อพร้อม / ผลที่ควรได้ |
|---|---|---|
| P2-08 PR04/PR09 | Assignment, atomic claim-next, reassign และ assignee filter | Admin มอบงานให้ A; A/B กดงานถัดไปพร้อมกัน ต้องเลือกงานตามลำดับที่กำหนดและไม่แจกภาพเดียวกันให้สองคน; reassign แล้วสิทธิ์เก่า save ไม่ได้ |
| P2-09 PR08/PR10 | Complete/submit/approve/reject/reopen, reviewer queue, skip reason | Junior submit → Reviewer reject พร้อม comment → Junior แก้และ submit ใหม่ → Reviewer approve; approval ต้องผูก revision ล่าสุด, reject ไม่มีเหตุผลไม่ได้, default ไม่ให้ approve งานตัวเอง; skip ต้องมี reason |
| P2-10 PR12 | History/audit browser และ restore revision | แก้หลาย revision ตรวจ actor/เวลา/สิ่งที่เปลี่ยน แล้ว restore รุ่นเก่า ต้องเกิด revision ใหม่และยังเก็บประวัติเดิม |
| P2-11 PR18 รอพัฒนาและบริษัท | LAN HTTPS, client trust, read-only SMB/API fallback | ใช้ Server กับ Client คนละ PC เข้าโดย hostname/certificate ที่ถูกต้อง ทดสอบสิทธิ์ API/share, share ใช้ไม่ได้แล้ว fallback ตามนโยบาย, certificate ผิดต้องถูกปฏิเสธ และไม่ต้องปิด TLS verification |

**Exit gate ที่ยังไม่ผ่าน:** Engineer/Junior ทำ workflow review บนสองเครื่องจริง รวม race, stale save, lease หมดอายุและ unauthorized project/share ขณะนี้ยังไม่สามารถผ่านได้ด้วยการ clone เพียงอย่างเดียว

## 7. Phase 3 — Polygon, Working QC และ Dataset Versions

### 7.1 พร้อมลองที่บ้าน

| รหัส | ขั้นตอน | ผลที่ควรได้ |
|---|---|---|
| P3-01 วาด polygon | สร้าง project `segmentation`, import ภาพ, กด **P** คลิกจุด 3 จุดขึ้นไป ปิดด้วย Enter, double-click และคลิกจุดแรกแยกคนละรอบ; Esc ยกเลิกอีกหนึ่งรอบ | แต่ละวิธีปิด polygon ได้ ไม่เพิ่มจุดซ้ำผิดรูป; Esc ยกเลิกเฉพาะที่กำลังวาด |
| P3-02 แก้ vertices | กด **V** เลือก/ย้ายรูป ลากจุด double-click ขอบเพิ่มจุด เลือกจุดแล้ว Delete ใช้ **Delete shape** ลบทั้งรูป และ undo/redo | จุด/รูปที่เปลี่ยนตรงตามคำสั่ง ตรวจซ้ำที่ zoom และ Scale ที่ใช้จริง |
| P3-03 รูปไม่ถูกต้อง / ยังวาดไม่จบ | ลองทำ polygon ไขว้ตัวเองหรือพื้นที่เป็นศูนย์; เริ่มรูปใหม่แต่ยังไม่ปิด แล้ว save/เปลี่ยนภาพ | ไม่บันทึกรูปผิด; vertex edit ที่ผิดคงรูป valid ก่อนหน้าไว้; ต้อง finish/cancel ก่อน navigation/save และ autosave ไม่ส่งจุดที่ยังไม่จบ |
| P3-04 Save/recovery | วาดรูปที่จบแล้ว save, ปิดเปิด, ลองหยุด Server/reconnect ตาม P1-09 | รูปที่จบและ save แล้วอยู่ครบ; recovery ใช้กติกา revision เดิม จุด polygon ที่ยังวาดไม่จบไม่อยู่ใน crash recovery |
| P3-05 Working QC | ใช้ detection project ใหม่ที่มี 3 ภาพ: ภาพ A มี Spring 2 กรอบ, B เป็น Verified empty, C ยัง unlabeled Save แล้วเปิด **Statistics / QC** และ Refresh | Spring มี 1 ภาพแต่ 2 objects; empty 1, unlabeled 1; แก้ canvas โดยยังไม่ save ต้องไม่ถูกนับจน save/refresh |
| P3-06 QC เพิ่มเติม | ลอง classification โดยเลือกคลาสเดียว เปิด QC; ลองกรอบเล็กมากและภาพไม่มี group; สลับ project ก่อนเปิดภาพ | Classification นับ image presence ไม่ใช่ geometry object; มี warning ที่ตรงข้อมูล; ไม่ค้างภาพจาก project เก่า รายการ warning บน UI จำกัด 200 แถวแต่แสดงจำนวนรวม |

### 7.2 รอพัฒนา

| รหัส / Requirement | ขั้นตอนรับรองในอนาคต | ผลที่ต้องได้ |
|---|---|---|
| P3-07 PR02 | เพิ่ม/rename/deactivate class ผ่าน schema ใหม่ ทดลอง mapping และ dry-run แล้วเปิด annotation รุ่นเก่า | Class ID คงที่ ไม่ reuse และ label เก่าไม่เปลี่ยนความหมาย |
| P3-08 PR10/PR13 | Review ให้ผ่าน สร้าง release v1 จด manifest/hash; แก้ working data แล้วสร้าง v2 | v1 bytes/hash และ approval evidence ไม่เปลี่ยนตาม working data; ไม่มีการ release งานที่ขาด review ตามนโยบาย |
| P3-09 PR14 | เปิด version browser/diff/statistics เทียบ v1/v2 ที่รู้ล่วงหน้าว่าเพิ่ม/ลบ/แก้อะไร | Diff และ per-class counts ตรงรายการที่เตรียมไว้ |
| P3-10 PR13 งานผู้พัฒนา | ใช้สำเนาข้อมูลทดสอบทำ asset ขาด/เสีย และหยุด process ระหว่าง release publication | Release ไม่สำเร็จเงียบ ๆ, ไม่มี partial artifact ที่ถูกแสดงว่า RELEASED; เริ่มใหม่แล้วกู้/รายงานงานค้างได้ |

Exit gate เรื่อง immutable release ยังรอ implementation; polygon/QC ที่ผ่านไม่ได้แปลว่า Phase 3 จบ

## 8. Phase 4 — Split Engine

### P4-01 พร้อมลอง: preview และผลซ้ำเดิม

ใช้ output ชื่อใหม่ทุกครั้ง จาก repository root:

```powershell
.\.venv\Scripts\python.exe -m visionlabel.split_preview --input tests/fixtures/splitting/source.json --config tests/fixtures/splitting/config.json --output "$env:TEMP\vl-uat-split-a.json"
.\.venv\Scripts\python.exe -m visionlabel.split_preview --input tests/fixtures/splitting/source.json --config tests/fixtures/splitting/config.json --output "$env:TEMP\vl-uat-split-b.json"
Get-FileHash "$env:TEMP\vl-uat-split-a.json", "$env:TEMP\vl-uat-split-b.json" -Algorithm SHA256
```

**ควรได้:** Fixture 16 ภาพ/8 กลุ่มแบ่ง train 8, val 4, test 4; แต่ละคลาสนับภาพได้ 4/2/2 และ hash ของรายงานทั้งสองตรงกัน ดู assignments ว่า group เดียวกันไม่ข้าม partition และ asset hash เดียวกันไม่ข้าม partition รายงานต้องระบุ `canonical_split=false`, `provenance_verified=false` แม้สถานะ constraints ผ่าน

| รหัส / สถานะ | วิธีทดสอบ | ผลที่ควรได้ |
|---|---|---|
| P4-02 พร้อมลองสำหรับผู้ที่แก้ JSON ได้ | Copy config ไป TEMP ปรับ strategy เป็น `random`, `stratified`, `group`, `stratified_group` ทีละแบบ รันซ้ำด้วย config เดิมและ output ใหม่ | แบบเดียวกัน/input เดิม/seed เดิมให้ bytes เดิม; config บางแบบอาจไม่ผ่าน constraints และต้องรายงานตรง ๆ ไม่ใช่ทุกแบบต้องได้ 8/4/4 หากแก้ข้อกำหนดอื่น |
| P4-03 พร้อมลอง | ในสำเนา config ทำ ratio รวมไม่เท่ากับ 10000; อีกกรณีใช้ config ถูกต้องแต่เงื่อนไขเข้มจนทำไม่ได้ ตรวจ exit code ทันทีด้วย `$LASTEXITCODE` | Invalid config exit 1; constraints ไม่ผ่านแต่มีรายงาน exit 2; ผ่าน exit 0 ไม่มีการผ่อน tolerance เงียบ ๆ |
| P4-04 งานผู้พัฒนา/ผู้ใช้ขั้นสูง | ใช้สำเนา source/config เตรียม pins ที่ชนกันใน group เดียว, group หาย, rare class และ asset ซ้ำคนละ image ID; เทียบ preview โดยใช้ `--compare-input` และ `--compare-preview` คู่กัน | ไม่เกิด group/hash leakage; รายงาน pin conflict/missing-group/infeasible ตามกรณี และชี้ old-test ที่ย้ายเข้า train ได้ วิธีสร้าง fixture รายละเอียดดู `tests/test_splitting.py` |
| P4-05 รอพัฒนา | เลือก released version ใน GUI กำหนด seed/ratio/pins สร้าง canonical split แล้วแก้ working data และเปิด split เดิม | Split ผูก immutable version, ไม่เปลี่ยนตาม working data; job/retry/backup/restore ครบ |

ยังไม่มีปุ่มแบ่ง dataset ใน desktop และ preview ไม่ใช่ชุด train/val/test พร้อมเทรน ค่า seed เดิมเพียงอย่างเดียวก็ไม่รับประกัน test set เดิมเมื่อ source เปลี่ยน

## 9. Phase 5 — Export Format และ Legacy Migration

### P5-01 พร้อมลอง: format preview

```powershell
.\.venv\Scripts\python.exe -m visionlabel.format_preview export-preview --input tests/fixtures/formats/export-preview.json --output "$env:TEMP\vl-uat-format.json"
```

เปิด JSON ผลลัพธ์ Fixture เป็นภาพ 100×200 กรอบ `(10,20)–(30,60)` คลาส OK มี export index 2 จึงควรได้ข้อความ:

```text
2 0.200000000 0.200000000 0.200000000 0.200000000
```

ตรวจว่าไม่ได้ใช้ตำแหน่งคลาสใน UI แทน index และรายงานมี `canonical_export=false`, `provenance_verified=false` ไฟล์นี้เป็นรายงานข้อความ/geometry ไม่ใช่ image dataset สำหรับ training

### P5-02 พร้อมลอง: legacy dry-run โดยไม่เขียนเข้า project

เตรียม folder ใหม่ `D:\VisionLabel-Legacy-UAT` มี `example.bmp` และ `example.txt` ที่เป็น YOLO detection จากนั้นสร้าง `request.json` ดังนี้ UUID นี้เป็นเพียง candidate class สำหรับทดสอบ parser:

```json
{
  "format": "yolo-detection",
  "task": "detection",
  "mapping": {"0": "10000000-0000-4000-8000-000000000001"},
  "empty_is_verified": false,
  "items": [{"image": "example.bmp", "label": "example.txt"}]
}
```

```powershell
.\.venv\Scripts\python.exe -m visionlabel.format_preview import-dry-run --source-root D:\VisionLabel-Legacy-UAT --input D:\VisionLabel-Legacy-UAT\request.json --output "$env:TEMP\vl-uat-legacy.json"
```

**ควรได้:** รายงาน candidate กรอบ/mapping/source hashes ที่ตรงข้อมูล พร้อม `canonical_import=false`, `database_conflicts_checked=false` ไม่มีภาพหรือ annotation เพิ่มใน project

สำหรับ LabelMe ให้ใช้ JSON ที่อ้างภาพข้างไฟล์ผ่าน `imagePath`, ตั้ง `format` เป็น `labelme`, task ให้ตรง rectangle/polygon, map ชื่อ label ไป UUID และเปลี่ยน `label` ใน request เป็นชื่อ JSON รูปแบบอื่น, nonempty flags/grouping/descriptions, embedded `imageData` และขนาดไม่ตรงภาพต้องรายงาน error ไม่ทิ้ง metadata เงียบ ๆ ภาพที่มี EXIF orientation ไม่ใช่ identity จะถูกปฏิเสธใน dry-run นี้

| รหัส / สถานะ | วิธีทดสอบ | ผลที่ควรได้ |
|---|---|---|
| P5-03 พร้อมลอง | ทำสำเนาชุด dry-run ให้มีไฟล์ถูกหนึ่งไฟล์และผิดหนึ่งไฟล์ เช่น class index ไม่อยู่ใน mapping | แสดงผลแยกรายไฟล์ exit 2 เมื่อมี per-file failures; ไฟล์ผิดไม่มี partial candidate ที่ดูเหมือนสำเร็จ |
| P5-04 งานผู้พัฒนา | ตรวจ segmentation/classification preview ด้วย fixture ที่รู้ geometry/ลำดับคลาส และอ่านกลับด้วยตัวตรวจอิสระ | YOLO geometry อยู่ใน tolerance, ไม่มีสลับคลาส, classification folder mapping ไม่ชนกัน; มีหลักฐานใน `tests/test_formats.py` แล้ว แต่ยังไม่ใช่ user acceptance ของ export จริง |
| P5-05 รอพัฒนา PR16 | จาก released version + canonical split ส่งออก detect/segment/classification แล้วย้าย folder ไป path ใหม่ อ่านด้วย training loader ที่เลือก | ข้อมูลพกพาได้, image bytes/hash ตรง release, class/geometry/empty ถูก, มี provenance/checksums; ห้ามอ้างว่า preview ผ่านแล้ว export จริงผ่าน |
| P5-06 รอพัฒนา PR17 | Import LabelMe เข้า project จริง ทดลอง existing annotation, invalid rows, interrupted import และ mapping | สร้าง revision/audit ตามจริง ไม่มี silent loss และไม่ทับ annotation เดิม |

YOLO detection import เข้า project มีแล้วใน Phase 7 ให้ใช้ชุดทดสอบด้านล่างแทนการรอ P5-06 ส่วนวงจร label → working export → train ภายนอก → infer ภายนอก → import ทำได้โดยใช้ Phase 8 ที่เพิ่มใหม่ แต่ approved release/export ยังรอพัฒนา และต้องรับรอง training environment ของผู้ใช้อีกครั้ง

## 10. Phase 6 — Backup, Installation และการใช้งานจริง

### P6-01 พร้อมลอง: backup → verify → restore

ใน DataRoot ทดสอบสร้างกรอบและ polygon ที่จำตำแหน่งได้ จดจำนวน project/ภาพ/สมาชิก/revision ปิด Client และ Server ให้หยุดก่อน:

```powershell
.\.venv\Scripts\python.exe -m visionlabel.cli backup --root D:\VisionLabel-UAT --destination D:\VisionLabel-UAT-Backup-01
.\.venv\Scripts\python.exe -m visionlabel.cli verify-backup --backup-set D:\VisionLabel-UAT-Backup-01
.\.venv\Scripts\python.exe -m visionlabel.cli restore --backup-set D:\VisionLabel-UAT-Backup-01 --destination D:\VisionLabel-UAT-Restored-01
.\.venv\Scripts\python.exe -m visionlabel.launcher --root D:\VisionLabel-UAT-Restored-01
```

**ควรได้:** Backup มี manifest สถานะ COMPLETE, verify สำเร็จ, restore ไป folder ใหม่แล้วล็อกอินใหม่ได้ project/ภาพ/กรอบ/สมาชิก/revision ตรงก่อน backup; session/lease เก่าใช้ต่อไม่ได้ Backup ไม่รวม inbox, Client cache หรือ unsaved drafts จึงไม่ควรคาดหวังให้รายการเหล่านี้ติดมาด้วย

| รหัส / สถานะ | วิธีทดสอบ | ผลที่ควรได้ |
|---|---|---|
| P6-02 พร้อมลอง | ขณะ service ทดสอบยังเปิดอยู่ สั่ง backup ไปปลายทางใหม่; หลังปิด service ลองใช้ชื่อ destination ที่มีอยู่แล้ว | ปฏิเสธทั้ง service ยังใช้งานและปลายทางที่มีอยู่ ไม่ทับชุด backup เดิม |
| P6-03 พร้อมลองบนสำเนา | Copy backup ทดสอบอีกชุด ทำให้ blob หนึ่งไฟล์ใน **สำเนา** เปลี่ยน bytes แล้ว verify/restore สำเนานั้น | แจ้ง hash/integrity failure ไม่เผยแพร่ restore สำเร็จ และ backup ต้นฉบับยังใช้ได้ |
| P6-04 รอเครื่องใหม่/บริษัท | ย้าย **completed backup** ไปดิสก์แยก verify สำเนา แล้ว restore ลงเครื่องใหม่ จับเวลาตั้งแต่เริ่มกู้จนเปิดตรวจข้อมูลได้ | ข้อมูลและ hashes ตรง, บันทึก RTO; เป้าหมายสเปก RTO ≤4 ชั่วโมง / RPO ≤24 ชั่วโมง ต้องวัดกับขนาดข้อมูลจริง ไม่อนุมานจากชุดเล็ก |

### P6-05 Offline kit — สร้างที่บ้านได้; รับรองเครื่องใหม่ภายหลัง

ต้องสร้าง kit ใหม่จาก source ที่มี Phase 7 ชุด `offline-kit-phase6` เดิมไม่รวม YOLO/BMP รุ่นล่าสุด ขั้นสร้าง kit อาจดาวน์โหลด dependency แต่ขั้น install ต้องทำ offline ได้:

```powershell
.\.venv\Scripts\python.exe scripts/build_offline_kit.py --output dist\offline-kit-uat-phase7
```

ย้ายทั้ง folder ไปเครื่อง Windows x64 ที่มี **Python 3.12.10** แล้ว เปลี่ยน path Python ให้ตรงเครื่องปลายทาง ปิด Internet สำหรับช่วงติดตั้งโดยยังคงช่องทางที่จำเป็นตามนโยบาย IT:

```powershell
& 'C:\Python312\python.exe' 'D:\Transfer\offline-kit-uat-phase7\install.py' --verify-only
& 'C:\Python312\python.exe' 'D:\Transfer\offline-kit-uat-phase7\install.py' --target 'D:\Apps\VisionLabel-UAT'
& 'D:\Apps\VisionLabel-UAT\Start-VisionLabel.ps1' -DataRoot 'D:\VisionLabel-UAT-NewPC'
```

**ควรได้:** Verify และ install จาก local wheels สำเร็จใน target ใหม่ สร้าง admin/import/วาด/save/reload และ BMP/YOLO ได้ ไม่มีการติดตั้ง package แบบ global ชุดนี้ยังต้องใช้ Python และไม่ใช่ Nuitka `.exe` การลองใน environment ใหม่บนเครื่องเดิมยังไม่แทน clean-machine acceptance

### งานที่ต้องมีผู้พัฒนา/IT และสภาพแวดล้อมเฉพาะ

| รหัส / สถานะ | วิธีทดสอบเมื่อเตรียมพร้อม | เกณฑ์/หลักฐานที่ต้องเก็บ |
|---|---|---|
| P6-06 รอ production package | ติดตั้ง/เปิด/อัปเกรด/ถอนติดตั้ง Nuitka และ service บนเครื่องสะอาดตามสิทธิ์ผู้ใช้จริง | เอกสารขั้นตอนตรง package, font/Unicode/DPI ใช้ได้, notices/SBOM ตรงสิ่งที่ bundle |
| P6-07 รอ LAN และ load harness | ใช้ baseline 4-core, RAM16GB, SSD, LAN1Gbps, 10 sessions, 50,000 ภาพ/project, JPEG/PNG1920×1080, ≤200 shapes/ภาพ จับ latency ในแต่ละงาน | p95 metadata <300ms, save <1s, cached open <300ms, uncached <2s พร้อมรายงานสเปกเครื่องและโหลด; split ต้องวัดแยกเพราะ pair-swap มีต้นทุนสูง |
| P6-08 ผู้พัฒนา/IT ใน VM หรือดิสก์ทดสอบ | ทำ disk-full, disconnect, service restart, kill ระหว่าง save/backup/restore ทีละกรณี แล้วตรวจ DB/blobs และ retry | ไม่เสีย committed data, ไม่มี partial artifact ที่อ้าง COMPLETE, ไม่มี stale overwrite; staging ที่ค้างไม่ถูกนับเป็น backup สำเร็จ ห้ามทำดิสก์งานจริงเต็มเพื่อทดสอบ |
| P6-09 รอ IT | ใช้นโยบาย block outbound ภายนอกในเครื่อง/VM ทดสอบ เปิดแอป import/save/อ่านคู่มือ และเมื่อ LAN พร้อมให้คง LAN ที่จำเป็นไว้ เก็บ firewall/connection logs | Runtime ไม่พยายามติดต่อภายนอก และฟังก์ชันที่รองรับยังทำงาน; การถอด Internet แล้วแอปเปิดได้อย่างเดียวไม่พิสูจน์ว่าไม่มี attempt |
| P6-10 รอการเชื่อมงาน Phase 2–5 | ซ้อม upgrade/migration และ backup/restore ที่มี released versions, splits, exports เปรียบเทียบ manifest hashes และ regenerate golden export | Hash/เนื้อหาตรงก่อนกู้, ไม่มี active claims เก่าคืนชีพ; ปัจจุบันยังไม่มี artifacts เหล่านี้ให้รับรอง |
| P6-11 รอพัฒนาส่วนจัดการ | ตรวจ backup schedule/retention, integrity scan, cache/draft cleanup, health/metrics และ job cancellation ตามสเปกกับผู้ดูแล | มีหลักฐานการทำงาน/แจ้ง failure และไม่ลบ unsaved draft เงียบ ๆ; คู่มือการ backup แบบ manual ไม่แทนระบบเหล่านี้ |

## 11. Phase 7 — Import YOLO Predictions และ BMP (แนะนำให้ลองก่อน)

### 11.1 เตรียมชุดเล็กที่รู้คำตอบ

ใช้ detection project ใหม่ คลาส `Spring,Defect` และ import ด้วย admin/maintainer เตรียมภาพทดสอบ 640×400 ชื่อ `spring_img.bmp` กับ `spring_img.txt` ใน **โฟลเดอร์เดียวกัน** ของ inbox ใส่ข้อความ:

```text
0 0.5 0.5 0.4 0.3
```

ถ้าขนาดภาพเป็น 640×400 จริง กรอบควรเป็น `(x1,y1)=(192,140)` ถึง `(x2,y2)=(448,260)` ถ้าใช้ภาพขนาดอื่น ให้เทียบจาก `x1=(cx-w/2)×ความกว้างภาพ`, `y1=(cy-h/2)×ความสูงภาพ` และคำนวณ x2/y2 ด้วยเครื่องหมายบวก

อย่าใช้รูป copy ที่ bytes เหมือนกันทั้งหมดเพื่อทดสอบหลายกรณีใน project เดียว เพราะระบบตรวจ duplicate ด้วย hash หากใช้ภาพเดิม ให้ใช้ project ใหม่และ inbox ที่มีเฉพาะชุดกรณีนั้น ไม่มีตัวเลือกแยก `images/` กับ `labels/` ใน desktop: ต้องวาง TXT ข้างภาพก่อน

### 11.2 รายการพร้อมลองที่บ้าน

อัปเดต 6 ต.ค. 2026: ผู้ใช้ยืนยัน import ภาพและ YOLO prediction จากงานจริงแล้วแก้กรอบได้ ยืนยันส่วน import/edit ของ P7-02 และ prediction จริงใน P7-13 เท่านั้น ยังไม่ถือว่า preview, reload, mapping ทุกแบบ หรือ negative cases ผ่านครบ

| รหัส | ขั้นตอน | ผลที่ควรได้ |
|---|---|---|
| P7-01 Preview ไม่เพิ่มภาพ | เปิด **Import YOLO labels** ตั้ง `0=Spring`, `1=Defect` แล้วกด **Preview** อ่าน Import report และตรวจรายการภาพใน project ใหม่ | รายงานกรอบ/คลาสถูก แต่ยังไม่มีภาพหรือ annotation revision ใหม่; ระบบสร้าง import job เพื่อ audit ได้ |
| P7-02 Import → แก้ → reload | เปิด dialog อีกครั้ง ตรวจ mapping เดิม กด **Import predictions** เปิดภาพ แก้กรอบ/คลาส Ctrl+S แล้วปิดเปิด | ได้กรอบจาก TXT เป็น revision1 / IN_PROGRESS; แก้แล้วเป็น revision2 และ reload ตรง ไม่อนุมัติ prediction อัตโนมัติ |
| P7-03 Mapping ไม่ตรงลำดับ project | ใช้ project ใหม่ เปลี่ยน `0=Defect` ทั้งที่ Defect เป็นคลาสที่สอง แล้ว preview/import ไฟล์ class0 | กรอบเป็น Defect จริง และ mapping ที่กลับมาใช้ import ตรงที่ตรวจใน preview ไม่เดาจากลำดับ UI |
| P7-04 หลายกรอบ / PNG/JPEG/BMP | ใช้ภาพแต่ละ format คู่ TXT หลายบรรทัดที่ valid เปิดภาพและกรอบทั้งหมด | จำนวนกรอบเท่าจำนวนแถวและตรงภาพ; ภาพไม่กลับหัว/สลับแกน BMP, ตำแหน่งไม่เลื่อนหลัง save/reload |
| P7-05 Missing กับ empty | แยก 3 project/ชุด: ไม่มี TXT; TXT ว่างโดยไม่ติ๊ก empty option; TXT ว่างโดยติ๊ก option ยืนยัน verified-empty | Missing เป็น UNLABELED เสมอ; empty ปกติยัง UNLABELED; empty ที่เลือกยืนยันจึงเป็น verified-empty ไม่ตีความว่าโมเดลไม่เจอเท่ากับภาพว่างจริงโดยอัตโนมัติ |
| P7-06 TXT ผิด | ใช้สำเนา เพิ่ม confidence เป็นคอลัมน์ที่ 6, class ที่ไม่อยู่ mapping, ค่า NaN, width0, หรือกรอบล้นภาพ ทีละกรณี และลองไฟล์ที่มีแถวดี+แถวเสีย | รายงาน error ทั้งไฟล์ ไม่มีนำเข้าเฉพาะแถวดีแล้วบอกว่าสำเร็จ; ไฟล์อื่นที่ถูกต้องยังมีรายงานของตนเอง |
| P7-07 ชื่อ/โฟลเดอร์ | ใช้ชื่อไทย, extension ตัวพิมพ์ใหญ่ และ subfolder; จากนั้นใส่ `same.bmp` กับ `same.png` ใน folder เดียวคู่ `same.txt` | Unicode/subfolder ใช้ได้; same stem หลายภาพต้องแจ้ง ambiguous; TXT ที่ไม่มีภาพคู่ไม่ได้ถูกเลือกโดย image scan |
| P7-08 ไม่ทับงานเดิม | หลัง P7-02 แก้ TXT แล้ว import ซ้ำ ตรวจภาพเดิม; ลองภาพที่เคยวาดเองด้วย | รายงาน annotation exists/conflict และ revision/กรอบที่ผู้ใช้แก้ยังอยู่ครบ แม้ annotation เดิมเป็น verified-empty ก็ไม่ทับ |
| P7-09 ภาพยังไม่มี revision / มี lease | Import inbox แบบธรรมดาให้ภาพอยู่ revision0 ปิด editor ที่ถือ lease แล้ว import prediction; อีกภาพเปิดค้างใน Client อีกบัญชีแล้วลอง import | revision0 ที่ไม่มี lease รับ prediction ได้; ภาพมี lease ไม่ถูกแย่งเขียน หาก image import สำเร็จแต่ label save ไม่ได้ รายงานอาจเป็น `image_retained=true`, `label_state=NOT_IMPORTED` |
| P7-10 Task / permission | ลองด้วย annotator/viewer และลองใน segmentation/classification | ปฏิเสธหรือไม่เปิด action ที่ไม่รองรับ ไม่สร้าง annotation ผิดประเภท; detection import ต้อง admin/maintainer |
| P7-11 Source เปลี่ยนหลัง preview | ในชุดทดสอบ Preview แล้วแก้ TXT ก่อน Import predictions | Import อ่าน source ใหม่ ไม่ถือว่า preview จอง/freeze ไฟล์ไว้ ตรวจ report กับ source ล่าสุดอีกครั้ง |

### 11.3 ยังต้องยืนยันด้วยไฟล์หน้างาน

- **P7-12 BMP จากกล้อง/เครื่องจักรจริง:** นำตัวอย่างที่ได้รับอนุญาตหลายขนาด/bit depth มา import ตรวจสี ทิศทาง ขอบภาพและพิกัดหลัง zoom/save/reload หลักฐานปัจจุบันทดสอบ 8-bit indexed, 24-bit top-down/bottom-up และ 32-bit RGB ไม่ได้แปลว่าทุก variant ของ BMP ใช้ได้โดยไม่ decode ตรวจจริง
- **P7-13 Prediction จริง:** ใช้ภาพประมาณ 5–20 ภาพที่รู้ผลจากโมเดล ตรวจ class order, หลายกรอบ, false positive/negative แล้วปรับบันทึกและเปิดใหม่ เปรียบเทียบกับภาพต้นฉบับ ไม่ต้องรอครบพันภาพก่อนเริ่มรับรอง
- **P7-14 Batch ใหญ่:** เมื่อชุดเล็กผ่านจึงลองขนาดใกล้งานจริง จดจำนวนภาพ/กรอบ เวลา import, UI responsiveness และ errors รายไฟล์ ไม่อ้างว่ารองรับทุกขนาดจากผลชุดเล็ก หากใช้ CLI dry-run ของ Phase 5 ประกอบ จะจำกัด request ที่ 1000 รายการ; ข้อนี้ไม่ใช่การระบุขีดจำกัด batch ของปุ่ม desktop ใน Phase 7
- **P7-15 ติดตั้งรุ่นล่าสุดในบริษัท:** ใช้ source/kit ที่มี Phase 7 แล้วทวน P7-01/02/04 บนเครื่องเป้าหมายก่อนใช้ dataset จริง การลองแบบ local ที่บริษัททำได้ก่อน LAN แต่ไม่ใช่การรับรอง multi-PC

ไฟล์ที่รองรับปัจจุบันคือ `.png`, `.jpg`, `.jpeg`, `.bmp` ไม่เกิน 50 MiB/40 ล้านพิกเซลต่อภาพ และต้อง decode ผ่าน ไม่ควรนับ TIFF/WebP/GIF/HEIC/RAW เป็นกรณีที่ต้องผ่านใน Phase 7 นี้ ไม่มี auto EXIF rotation

## 11A. Phase 8 — Export ไปเทรน YOLO (งานใหม่)

**พร้อมลองบนเครื่องเดียว:** เปิด launcher ตามเดิม ใช้ admin หรือ maintainer ของ project ไม่ต้องใช้ NAS หรือเชื่อมต่อ Client อีกเครื่อง ผู้ใช้ยังไม่ได้ยืนยัน Phase 8 โดยตรง

สถานะเครือข่ายล่าสุด: ผู้ใช้ลอง Laptop1/Laptop2 ผ่าน hotspot มือถือแล้ว ping หากันไม่ได้ แต่ทั้งคู่ ping Raspberry Pi ได้ และ NAS เปลี่ยน IP จึงย้ายการรับรอง LAN กลับไปบริษัท ผลนี้ไม่ใช่ข้อบกพร่องที่ยืนยันของแอป และแอปยังไม่มี LAN/HTTPS อยู่แล้ว

วิธีเริ่ม: เลือก project → Save → **Export YOLO** → ตั้ง **Validation %**, **Test %**, **Seed** → **1. Prepare export / retry** → ตรวจจำนวนจริงและภาพที่ข้าม → **Browse parent folder...** → ตั้ง **New folder name** → **2. Save dataset to folder**

Validation เป็นจำนวนเต็ม 1–99%, test 0–98%, รวมต้องน้อยกว่า 100%; train เป็นส่วนที่เหลือ เลือก test=0 ได้ แต่ validation ต้องมีเพื่อเตรียมชุด training/validation ที่ใช้งานได้ ไม่ใช้ภาพ train เป็น val แทนอัตโนมัติ

| รหัส | ขั้นตอนที่ผู้ใช้ยังต้องลอง | ผลที่ควรได้ |
|---|---|---|
| P8-01 Detection จริง | ใช้ภาพที่แก้ prediction แล้วและกด Save ทดลอง val20/test10, Prepare แล้ว Save dataset | มี images/train,val,test และ labels ที่ชื่อคู่กัน พิกัด `class cx cy w h` ตรงกรอบที่แก้ พร้อม data.local.yaml |
| P8-02 Segmentation | ใช้ segmentation project ที่มี polygon บันทึกแล้ว ส่งออกและอ่าน TXT | แถวเป็น class ตามด้วยคู่พิกัด normalized ของ vertices ไม่ใช่ bbox; รูป polygon ไม่เสียและคลาสไม่สลับ |
| P8-03 Classification | ใช้ project ที่ label หลายคลาส ส่งออกและตรวจ train/val/test | ภาพอยู่ใต้โฟลเดอร์คลาส; ไม่มี YOLO bbox TXT; class_mapping.json บอกชื่อ/UUID/schema index/consumer order ใช้เฉพาะคลาสที่มีภาพและทุกคลาสต้องมีใน train |
| P8-04 เปอร์เซ็นต์ / ข้อมูลน้อย | ลอง val20/test0 และ val20/test10; ลองรวม100 หรือ validation0; ลองชุดที่มีเพียง1ภาพ | test0 ไม่สร้างชุด test; ค่าไม่ถูกต้องถูกปฏิเสธ; ภาพ/group ไม่พอมี error ชัดเจน ไม่แอบเอาภาพเดียวกันใส่หลายชุด |
| P8-05 จำนวนจริง / คลาสหายาก | ใช้ชุดเล็กที่รู้จำนวนแต่ละคลาส ตรวจ report หลัง Prepare | จำนวนจริงแสดงครบและอาจต่างจาก % เป้าหมายเพราะ rounding/group/coverage; train มีทุก observed class หรือ export ล้มเหลวพร้อมเหตุผล |
| P8-06 Missing / verified empty | มีภาพไม่ label, ภาพที่ save แล้วแต่ไม่มี shape และไม่ verified-empty, กับภาพ verified-empty | สองแบบแรกอยู่รายการ excluded ไม่แปลงเป็น negative; verified-empty detection/segment มีภาพและ TXT ศูนย์ไบต์ |
| P8-07 Destination | หลังแก้ modal focus วันที่ 7 ต.ค. 2026 ให้ลอง Browse แล้ว Cancel จากนั้น Browse อีกครั้งเลือก path ภาษาไทย/มีช่องว่าง Save ลงชื่อ folder ใหม่ แล้วลองใช้ folder เดิม | หน้าต่างเลือก folder กดได้; เลือกหรือ Cancel แล้วกลับหน้า Export พร้อมค่าเดิมและผล Prepare; ลงในเครื่องที่เปิด Desktop จริง; folder เดิมไม่ถูกทับ ไม่แก้ source image/TXT (automated rendered callback smoke ผ่านแล้ว ยังรอยืนยันด้วยเมาส์จริง) |
| P8-08 Frozen snapshot | Prepare เสร็จ ปิด dialog แก้ annotation และ save เปิด dialog แล้วบันทึก export ที่เตรียมเดิม; จากนั้น Prepare ใหม่ | ชุดเดิมยังอ้าง revision ณ Prepare เดิม ชุดใหม่จึงเห็นการแก้; manifest ระบุ revision/hash และชื่อภาพเดิม |
| P8-09 Permissions | Login annotator/viewer แล้วลอง Export; ทดลอง admin/maintainer | สองบทบาทแรก export ไม่ได้; admin/maintainer ทำได้โดยไม่ต้องมี reviewer หรือสองเครื่อง |
| P8-10 Interrupted download / disk full | ผู้พัฒนาหรือ IT ใช้ดิสก์/VM ทดสอบ สร้าง export แล้วจำลอง download ขาดหรือ disk เต็มก่อน publish | ไม่แสดง folder ปลายทางที่ดูเหมือนสำเร็จเมื่อไฟล์ยังไม่ครบ; retry ด้วยพื้นที่เพียงพอได้ ห้ามทำดิสก์งานจริงเต็ม |
| P8-11 ย้าย dataset | Copy export ไป path ใหม่ รัน `python prepare_dataset.py` ภายในชุดใหม่ แล้วเปิด data.local.yaml | path ใหม่ถูกต้อง; detection/segment ใช้ data.local.yaml ที่สร้างใหม่; classification ใช้ dataset root ใหม่ |
| P8-12 เทรนจริง | ใน environment Ultralytics ของผู้ใช้ ใช้ local model ให้ตรง detect/segment/classify รันอย่างละ1 epochก่อน แล้วดู batch visualization และ class names | Loader รับชุดข้อมูลได้ geometry/class ตรง ไม่มี label parsing errors; จดเวอร์ชัน Ultralytics/Python/Torch, model และผล รอบนี้ยังไม่ได้ทดสอบ training runtime จริงให้ผู้ใช้ |
| P8-13 ชุดใหญ่ / ความเร็ว | หลังชุดเล็กผ่าน ทดลองข้อมูลขนาดใกล้งานจริง จดจำนวนภาพ/ขนาด/time/disk | UI ยังตอบสนอง, งานเสร็จหรือ error ชัดเจน; ต้องมีพื้นที่ทั้ง server export-cache และ client download/staging ไม่ถือว่าผ่าน 50,000 ภาพจากชุดเล็ก |
| P8-14 กลับมาหลัง restore | Restore backup ในพื้นที่ใหม่ แล้วลอง download job เดิมและ Prepare ใหม่ | Cached ZIP ไม่อยู่ใน backup จึงอาจแจ้ง unavailable สำหรับ job เดิม; Prepare ใหม่สร้าง export จากข้อมูลที่กู้ได้ |

ตัวอย่างคำสั่งใน **environment training แยกต่างหาก** เปลี่ยน path และ model ให้ตรงเครื่อง:

```powershell
# Detection: model ต้องเป็น detection model ที่มีอยู่แล้ว
 yolo detect train model="D:\Models\detect.pt" data="D:\Datasets\batch1\data.local.yaml" epochs=1 imgsz=640
# Segmentation: ใช้ segmentation model
 yolo segment train model="D:\Models\segment.pt" data="D:\Datasets\segment1\data.local.yaml" epochs=1 imgsz=640
# Classification: data เป็น folder ไม่ใช่ YAML
 yolo classify train model="D:\Models\classify.pt" data="D:\Datasets\classes1" epochs=1 imgsz=224
```

Manifest ระบุ `approved_release=false` เพราะนี่เป็น working snapshot ที่อาจมี prediction ยังไม่ตรวจทั้งหมด ไม่ถือว่าผ่าน review/release ของ Phase 2–5 การเปลี่ยน source แล้วใช้ seed เดิมไม่ได้รับประกันว่า test set จะเป็นภาพเดิม

## 12. ลำดับแนะนำสำหรับรอบทดสอบถัดไป

0. **ทดลอง export ใหม่ก่อน:** P8-01/02/03 → P8-07 → P8-11 → P8-12 บนเครื่องเดียว แนะนำใช้ชุดเล็กก่อน
1. **ทวนกรณี Phase 7 ที่ยังไม่ยืนยัน:** P7-01 → P7-02 → P7-03 → P7-05 → P7-08 โดยใช้ภาพไม่กี่ภาพก่อน ตรงกับ workflow ที่ต้องการนำ prediction มาแก้
2. **ตรวจงาน editor ที่ยังไม่ระบุ:** P1-02/03/05/09 และ P3-01 ถึง P3-05
3. **ตรวจสิทธิ์บนเครื่องเดียว:** P2-01 ถึง P2-07 ด้วยบัญชีทดสอบสองบัญชี
4. **ซ้อมกู้ข้อมูล:** P6-01/02 ก่อนเก็บ annotation ที่มีคุณค่าจำนวนมาก
5. **เมื่อสะดวกใช้ CLI:** P4-01 และ P5-01/02 เป็นการรับรอง developer preview เท่านั้น
6. **เมื่ออยู่บริษัท:** ภาพจริง/เครื่องใหม่/restore/offline kit ทำได้ตามความพร้อม ส่วน LAN/review/release/canonical split และ approved export ต้องรอ implementation ที่ระบุไว้ก่อน; working export Phase 8 ลองบนเครื่องเดียวได้แล้ว

## 13. แบบบันทึกผล

Copy ตารางนี้เพิ่มแถวตามกรณีที่ลอง ใช้ “ผ่าน / ไม่ผ่าน / ยังไม่ลอง / รอพัฒนา / N/A พร้อมเหตุผล” ไม่ต้องติ๊กว่าผ่านเพราะไม่มี error เพียงอย่างเดียว ให้ตรวจผลที่คาดหวังในกรณีนั้นด้วย

| รหัส | วันที่ / ผู้ทดสอบ | Commit / เครื่อง / Scale | ผล | สิ่งที่สังเกต / หลักฐาน |
|---|---|---|---|---|
| P8-01 | — | — | ยังไม่ลอง | — |
| P7-01 | — | — | ยังไม่ลอง | — |
| P7-02 | — | — | ยังไม่ลอง | — |
| P6-01 | — | — | ยังไม่ลอง | — |

เมื่อพบปัญหา ระบุลำดับกด, ค่าที่กรอก, ประเภทภาพ/ขนาด, revision ก่อนและหลัง, ข้อความ error แบบเต็ม และขั้นตอนที่ทำซ้ำได้ หากใช้ข้อมูลบริษัท ให้เก็บหลักฐานในพื้นที่ที่บริษัทอนุญาต

## 14. หลักฐานที่ใช้จัดทำรายงาน

จำนวน tests ด้านล่างเป็นผล **ที่บันทึกไว้ในแต่ละช่วง** ไม่ควรนำมาบวกกัน; แถว Phase 8 เป็นผลรันในงานเพิ่ม export นี้:

| ช่วง | หลักฐานฝั่งพัฒนาที่บันทึกไว้ |
|---|---|
| Phase 1 | 46 tests, rendered desktop smoke, process-crash checks, wheel smoke |
| Phase 2 | 54 tests รวม account/membership/concurrency และ GUI smoke |
| Phase 3 | 73 tests รวม polygon/QC/migration และ GUI smoke |
| Phase 4 | 104 tests รวม deterministic split/golden reports/CLI |
| Phase 5 | 141 tests รวม conversion/dry-run และ offline wheel smoke |
| Phase 6 | 160 tests รวม operations/kit, offline kit smoke |
| Phase 8 | Full suite 191 tests ผ่าน; หลังปรับเงื่อนไข verified-empty และเพิ่มตรวจ helper ย้าย path มี focused export suite 15 กรณีผ่าน รวม real HTTP/Desktop export และ offline wheel smoke ตรวจ classifier/segmentation/detection bytes แบบอิสระ ไม่ได้ติดตั้งหรือรัน Ultralytics training |
| Phase 7 | Full suite 172 tests ก่อนการปรับ UI/mapping รอบสุดท้าย; หลังปรับมี focused Phase 7 suite 16 cases และ GUI/wheel smoke ไม่อ้างว่า full suite หลังแก้รอบสุดท้ายมีผลจำนวนใหม่แล้ว |

แหล่งอ้างอิงภายใน repository:

- [Specification: แผน Phase, acceptance tests และ DoD](VisionLabel_DataTracking_Specification.md)
- [Phase 1 verification / user acceptance](docs/phase1-verification.md)
- [Phase 2](docs/phase2-plan.md), [Phase 3](docs/phase3-plan.md), [Phase 4](docs/phase4-plan.md)
- [Phase 5](docs/phase5-plan.md), [Phase 6](docs/phase6-plan.md), [Phase 7](docs/phase7-plan.md), [Phase 8](docs/phase8-plan.md)
- [Operations guide](docs/operations-guide.md), [README](README.md), [คู่มือ HTML ไทย/อังกฤษ](SoftwareExplainer.html)
- [หลักฐานภาพและรายงาน](docs/verification-artifacts/), [หลักฐาน Phase 7](docs/verification-artifacts/phase7/)

รายงานนี้เป็นรายการรับรองที่ยังเหลือ ไม่ใช่คำประกาศว่า Phase 0–8 หรือระบบ production ผ่านครบแล้ว งานที่ยังต้องพัฒนายังคงอยู่ใน Phase ต้นทางตามแผนเดิม
