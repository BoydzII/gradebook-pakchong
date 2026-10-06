/**
 * KruSpace — สำรองใบลาและคำขอแลกคาบลง Google Sheet ทุกคืน
 * ============================================================================
 * ทำไมต้องมี: ตั้งแต่ v189 แอปฟังใบลาเฉพาะ 30 วันล่าสุด (และคำขอแลกคาบเฉพาะภาคที่เปิดดู)
 * เพื่อลดค่าอ่าน Firestore ข้อมูลเก่ายังอยู่ครบใน Firestore (แบบใบลาและสถิติการลาต้องใช้)
 * ชีตนี้เป็นสำเนาสำรองนอก Firebase + ให้ผู้บริหาร/ฝ่ายบุคคลกรองและสรุปเองได้
 *
 * ค่าใช้จ่าย: อ่าน Firestore คืนละครั้งเท่าจำนวนใบลา+คำขอ+บุคลากร (ราว 2,000–4,000 ครั้ง ≈ ไม่ถึง 1 บาท/เดือน)
 *            Apps Script ฟรี ไม่ต้องเปิดบริการอื่นเพิ่ม
 *
 * วิธีติดตั้ง (ครั้งเดียว ~10 นาที) — ต้องใช้บัญชี Google ที่เป็นเจ้าของ/ผู้แก้ไขโปรเจกต์ Firebase pakchongallinone
 *   1) สร้าง Google Sheet ใหม่ ตั้งชื่อเช่น "สำรองใบลา-KruSpace"
 *   2) ส่วนขยาย → Apps Script → ลบโค้ดเดิม → วางไฟล์นี้ทั้งหมด
 *   3) ⚙ การตั้งค่าโปรเจกต์ → ติ๊ก "แสดงไฟล์ Manifest 'appsscript.json' ในเครื่องมือแก้ไข"
 *      แล้วเปิดไฟล์ appsscript.json แทนที่ทั้งไฟล์ด้วย:
 *        {
 *          "timeZone": "Asia/Bangkok",
 *          "runtimeVersion": "V8",
 *          "exceptionLogging": "STACKDRIVER",
 *          "oauthScopes": [
 *            "https://www.googleapis.com/auth/spreadsheets.currentonly",
 *            "https://www.googleapis.com/auth/script.external_request",
 *            "https://www.googleapis.com/auth/script.scriptapp",
 *            "https://www.googleapis.com/auth/datastore"
 *          ]
 *        }
 *   4) เลือกฟังก์ชัน setupNightly → เรียกใช้ → อนุญาตสิทธิ์ (ครั้งแรกจะสำรองให้ทันที 1 รอบ)
 *   5) เสร็จ — ระบบสำรองเองทุกคืนราวตี 2 กดเรียก backupNow เมื่อต้องการสำรองทันที
 *
 * ความปลอดภัย
 *   - สคริปต์ใช้สิทธิ์ของบัญชีที่ติดตั้ง อ่าน Firestore อย่างเดียว ไม่เขียนและไม่ลบอะไรใน Firestore
 *   - ไม่มีรหัสผ่านหรือคีย์ลับในไฟล์นี้ แชร์ชีตให้เฉพาะคนที่ควรเห็นข้อมูลการลาเท่านั้น
 */

var PROJECT_ID = 'pakchongallinone';
var SHEET_LEAVES = 'ใบลา';
var SHEET_SWAPS = 'คำขอแลกคาบ';
var SHEET_LOG = 'บันทึกการสำรอง';
// ถ้าจำนวนที่อ่านได้ลดลงฮวบเกินนี้ อย่าเขียนทับ — Firestore ไม่ได้ลบใบลาเก่า จำนวนจึงไม่ควรลดลงมาก
// ลดลงมากแปลว่าอ่านไม่ครบหรือมีคนลบข้อมูลผิด ต้องให้คนตรวจก่อน (ใช้ backupForce ถ้าตั้งใจ)
var MAX_DROP_RATIO = 0.2;

var REASONS = { personal: 'ลากิจส่วนตัว', sick: 'ลาป่วย', sickAppt: 'ลาป่วย (พบแพทย์ตามนัด)', maternity: 'ลาคลอดบุตร',
  official: 'ไปราชการ', other: 'อื่นๆ', swap: 'แลกคาบปกติ (ไม่ใช่การลา)' };
var APPROVAL = { draft: 'ยังไม่ส่ง', submitted: 'รออนุมัติ', approved: 'อนุมัติ', rejected: 'ไม่อนุมัติ',
  none: '-', waiting: 'รอหัวหน้า', endorsed: 'หัวหน้ารับรอง' };

/* ---------- ติดตั้ง ---------------------------------------------------- */
function setupNightly() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'backupNow') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('backupNow').timeBased().everyDays(1).atHour(2).inTimezone('Asia/Bangkok').create();
  backupNow();
}

function backupNow() { return run_(false); }
function backupForce() { return run_(true); }

/* ---------- สำรอง ------------------------------------------------------ */
function run_(force) {
  var started = new Date();
  try {
    var names = staffNames_();
    var leaves = listAll_('leaves');
    var swaps = listAll_('swaps');
    var nL = writeSheet_(SHEET_LEAVES, leafHead_(), leaves.map(function (x) { return leafRow_(x, names); }), force);
    var nS = writeSheet_(SHEET_SWAPS, swapHead_(), swaps.map(function (x) { return swapRow_(x, names); }), force);
    log_(started, 'สำเร็จ', 'ใบลา ' + nL + ' • คำขอแลกคาบ ' + nS + noPeriodWarn_(leaves, swaps));
  } catch (e) {
    log_(started, 'ผิดพลาด', String(e && e.message || e));
    throw e;
  }
}

/** อ่านทั้งคอลเลกชันผ่าน Firestore REST ทีละหน้า (สิทธิ์ของบัญชีที่ติดตั้งสคริปต์) */
function listAll_(collection) {
  var out = [], token = '';
  var base = 'https://firestore.googleapis.com/v1/projects/' + PROJECT_ID + '/databases/(default)/documents/' + collection;
  do {
    var url = base + '?pageSize=300' + (token ? '&pageToken=' + encodeURIComponent(token) : '');
    var res = UrlFetchApp.fetch(url, { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() }, muteHttpExceptions: true });
    if (res.getResponseCode() !== 200) throw new Error('อ่าน ' + collection + ' ไม่ได้ (' + res.getResponseCode() + '): ' + res.getContentText().slice(0, 300));
    var body = JSON.parse(res.getContentText() || '{}');
    (body.documents || []).forEach(function (d) {
      var o = fields_(d.fields || {});
      // เก็บรหัสเอกสารแยกไว้ที่ _doc — บุคลากรแบบ noemail_xxx มี id จริง (รหัสครูในใบลา) อยู่ในข้อมูล
      // ถ้าเขียนทับด้วยรหัสเอกสาร ชื่อครูเหล่านั้นจะหาไม่เจอ ส่วนใบลา/คำขอ รหัสต้องเป็นรหัสเอกสารเสมอ
      o._doc = d.name.split('/').pop();
      if (collection !== 'staff' || !o.id) o.id = o._doc;
      out.push(o);
    });
    token = body.nextPageToken || '';
  } while (token);
  return out;
}

/** แปลงค่าแบบ Firestore REST เป็นค่าธรรมดา — KruSpace เก็บอาร์เรย์ซ้อนไว้ใต้ __arr (fbEncodeNested) */
function value_(v) {
  if (!v) return '';
  if ('stringValue' in v) return v.stringValue;
  if ('integerValue' in v) return Number(v.integerValue);
  if ('doubleValue' in v) return v.doubleValue;
  if ('booleanValue' in v) return v.booleanValue;
  if ('timestampValue' in v) return v.timestampValue;
  if ('nullValue' in v) return '';
  if ('arrayValue' in v) return (v.arrayValue.values || []).map(value_);
  if ('mapValue' in v) {
    var o = fields_(v.mapValue.fields || {});
    return Array.isArray(o.__arr) ? o.__arr : o;
  }
  return '';
}
function fields_(f) { var o = {}; Object.keys(f).forEach(function (k) { o[k] = value_(f[k]); }); return o; }

/** รหัสครูในใบลาคือ 't_' + รหัสเอกสารบุคลากร หรือ id ในข้อมูล (ครูไม่มีอีเมล) หรือรหัสเก่าใน legacyIds */
function staffNames_() {
  var map = {};
  listAll_('staff').forEach(function (s) {
    var name = s.name || s.email || s.id;
    map['t_' + s._doc] = name;
    if (s.id) map[s.id] = name;
    (s.legacyIds || []).forEach(function (old) { map[old] = name; });
  });
  return map;
}

/* ---------- แปลงเป็นแถว ------------------------------------------------- */
function leafHead_() {
  return ['รหัสใบลา', 'ชื่อครู', 'ประเภท', 'เหตุผลอื่น', 'ตั้งแต่', 'ถึง', 'จำนวนวัน (จ.–ศ.)', 'หมายเหตุ',
    'หัวหน้ากลุ่มสาระ', 'ผู้บริหาร', 'อนุมัติโดย', 'อนุมัติเมื่อ', 'การจัดคนสอนแทน', 'สถานะ', 'ปี/ภาค', 'ยื่นเมื่อ', 'รหัสครู'];
}
function leafRow_(x, names) {
  var ap = x.approval || {}, hd = x.headApproval || {};
  return [x.id, names[x.teacherId] || '(ไม่พบชื่อ)', REASONS[x.reason] || x.reason || '', x.reasonOther || '',
    x.fromDate || '', x.toDate || x.fromDate || '', weekdays_(x.fromDate, x.toDate || x.fromDate), x.note || '',
    APPROVAL[hd.status] || hd.status || '', APPROVAL[ap.status] || ap.status || '', ap.by || '', ap.at || '',
    x.coverageStatus || '', x.status === 'deleted' ? 'ลบแล้ว' + (x.deleteReason ? ' — ' + x.deleteReason : '') : (x.status || ''),
    x.periodId || '', x.createdAt || '', x.teacherId || ''];
}
function swapHead_() {
  return ['รหัสคำขอ', 'ผู้ขอ', 'ครูที่รับ', 'แบบ', 'วันที่สอน', 'วันที่สลับไป', 'จำนวนคาบ', 'เหตุผล', 'สถานะ',
    'จากใบลา', 'ปี/ภาค', 'สร้างเมื่อ'];
}
function swapRow_(x, names) {
  var type = { exchange: 'แลกคาบ', substitute: 'สอนแทน' }[x.type] || x.type || '';
  return [x.id, names[x.requesterTeacherId] || '', names[x.targetTeacherId] || (x.targetTeacherId ? '(ไม่พบชื่อ)' : '-'), type,
    x.sourceDate || x.date || '', x.targetDate || '', x.slotCount || '', REASONS[x.reason] || x.reason || '',
    x.status === 'deleted' ? 'ลบแล้ว' : (x.status || ''), x.leaveRequestId || '', x.periodId || '', x.createdAt || ''];
}
function weekdays_(from, to) {
  if (!from) return '';
  var d = new Date(from + 'T00:00:00'), end = new Date((to || from) + 'T00:00:00'), n = 0, guard = 0;
  while (d <= end && guard++ < 400) { var w = d.getDay(); if (w >= 1 && w <= 5) n++; d.setDate(d.getDate() + 1); }
  return n;
}

/* ---------- เขียนชีต ---------------------------------------------------- */
function writeSheet_(name, head, rows, force) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name) || ss.insertSheet(name);
  var before = Math.max(0, sh.getLastRow() - 1);
  if (!force && before > 20 && rows.length < before * (1 - MAX_DROP_RATIO)) {
    throw new Error(name + ': อ่านได้ ' + rows.length + ' แถว แต่ในชีตมี ' + before + ' แถว — ไม่เขียนทับ ' +
      'ตรวจ Firestore ก่อน ถ้าตั้งใจให้ลดลงจริงให้เรียก backupForce');
  }
  rows.sort(function (a, b) { return String(b[4]).localeCompare(String(a[4])); });   // ล่าสุดอยู่บน
  rows = rows.map(function (r) { return r.map(cell_); });
  // เขียนลงชีตชั่วคราวให้เสร็จก่อนแล้วค่อยสลับ — ถ้า setValues ล้มกลางทาง (เกินเวลา/โควตา) ชีตเดิมยังอยู่ครบ
  // ไม่ใช่ clearContents ไปแล้วเหลือชีตว่าง ซึ่งรอบหน้ากฎกันจำนวนลดจะไม่มีฐานให้เทียบอีก
  var tmpName = name + ' (กำลังเขียน)', old = ss.getSheetByName(tmpName);
  if (old) ss.deleteSheet(old);   // ค้างจากรอบที่ล้ม
  var tmp = ss.insertSheet(tmpName, sh.getIndex());
  tmp.getRange(1, 1, 1, head.length).setValues([head]).setFontWeight('bold');
  if (rows.length) tmp.getRange(2, 1, rows.length, head.length).setValues(rows);
  tmp.setFrozenRows(1);
  SpreadsheetApp.flush();
  ss.deleteSheet(sh);
  tmp.setName(name);
  return rows.length;
}

/** ข้อความที่ขึ้นต้นด้วย = + - @ ชีตจะตีความเป็นสูตร (เหตุผล/หมายเหตุที่ครูพิมพ์เอง) เติม ' นำหน้าให้เป็นข้อความ
    ไม่ตั้งทั้งคอลัมน์เป็นข้อความ (@) เพราะวันที่จะกลายเป็นข้อความ กรอง/เรียงตามวันในชีตไม่ได้ */
function cell_(v) {
  return typeof v === 'string' && /^[=+\-@]/.test(v) ? "'" + v : v;
}

/** คำขอ/ใบลาที่ไม่มีปี/ภาค — แอปฟังคำขอแลกคาบตาม periodId เครื่องที่เปิดใหม่จะไม่เห็นรายการเหล่านี้ บันทึกเตือนให้ตามแก้ */
function noPeriodWarn_(leaves, swaps) {
  var live = function (x) { return x.status !== 'deleted' && !x.periodId; };
  var nL = leaves.filter(live).length, nS = swaps.filter(live).length;
  return nL || nS ? ' • ⚠ ไม่มีปี/ภาค: คำขอแลกคาบ ' + nS + ' • ใบลา ' + nL + ' (เครื่องที่เปิดใหม่อาจไม่เห็น ตรวจในชีตคอลัมน์ ปี/ภาค ที่ว่าง)' : '';
}

function log_(started, status, detail) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_LOG) || ss.insertSheet(SHEET_LOG);
  if (sh.getLastRow() === 0) sh.appendRow(['เวลา', 'ผล', 'รายละเอียด', 'ใช้เวลา (วินาที)']);
  sh.appendRow([started, status, detail, Math.round((new Date() - started) / 1000)]);
}
