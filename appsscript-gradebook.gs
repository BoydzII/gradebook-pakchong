/**
 * ปพ.5 Online — ฐานข้อมูลบุคลากรกลาง (เฟส 1: ตัวตนและสิทธิ์)
 * ============================================================================
 * ทำให้ครูและผู้บริหารเข้าสู่ระบบจากอุปกรณ์ใดก็ได้ ด้วยบัญชี Google ของโรงเรียน
 * โดยรายชื่อ บทบาท และกลุ่มสาระ เก็บไว้ที่ Google Sheet กลางเพียงที่เดียว
 *
 * วิธีติดตั้ง (ทำครั้งเดียว ~10 นาที)
 *   1) สร้าง Google Sheet ใหม่ ตั้งชื่อว่า "ฐานข้อมูลกลาง-ปพ5"
 *   2) ส่วนขยาย → Apps Script → ลบโค้ดเดิม → วางไฟล์นี้ทั้งหมด
 *   3) เมนู "เรียกใช้" → เลือกฟังก์ชัน setupFirstTime → กดเรียกใช้ → อนุญาตสิทธิ์
 *   4) ทำให้ใช้งานได้ → การทำให้ใช้งานได้ใหม่ → ประเภท: เว็บแอป
 *        ดำเนินการในชื่อ: ฉัน        ผู้ที่มีสิทธิ์เข้าถึง: ทุกคน
 *   5) คัดลอก URL ที่ได้ ไปวางในแอป (ผู้ดูแลระบบ → ตั้งค่า → ระบบบุคลากรกลาง)
 *   6) กรอกรายชื่อบุคลากรในแผ่น staff แล้วให้ทุกคนเข้าใช้ด้วยปุ่ม
 *      "เข้าสู่ระบบด้วย Google"
 *
 * ความปลอดภัย
 *   - URL ของเว็บแอปเป็นสาธารณะเสมอ ด่านกันคือการตรวจ id_token ของ Google
 *     กับรายชื่อในแผ่น staff ใครไม่มีชื่อในชีตจะเข้าไม่ได้
 *   - ไม่มีการเก็บรหัสผ่านใด ๆ ใช้บัญชี Google ของโรงเรียนโดยตรง
 *   - ทุกคำสั่งที่แก้ข้อมูลต้องแนบ token ที่ออกให้ตอน login และตรวจสิทธิ์ทุกครั้ง
 */

var SHEET_STAFF = 'staff';
var SHEET_LOG = 'log';
var TOKEN_HOURS = 12;                 // อายุการเข้าใช้ต่อครั้ง
var STAFF_COLS = ['email', 'name', 'roles', 'learningArea', 'phone', 'homeroom', 'active', 'lastLogin'];
var STAFF_HEAD = ['อีเมล', 'ชื่อ-นามสกุล', 'บทบาท', 'กลุ่มสาระ/กลุ่มงาน', 'เบอร์โทร', 'ห้องที่ปรึกษา', 'ใช้งาน', 'เข้าใช้ล่าสุด'];
var VALID_ROLES = ['teacher', 'head', 'executive', 'admin'];

/* ---------- ตัวช่วยพื้นฐาน ---------------------------------------------- */
function props_() { return PropertiesService.getScriptProperties(); }
function book_() { return SpreadsheetApp.getActiveSpreadsheet(); }

function secret_() {
  var s = props_().getProperty('SECRET');
  if (!s) { s = Utilities.getUuid() + Utilities.getUuid(); props_().setProperty('SECRET', s); }
  return s;
}

function sheet_(name, headers) {
  var sh = book_().getSheetByName(name);
  if (!sh) {
    sh = book_().insertSheet(name);
    sh.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
    sh.setFrozenRows(1);
  }
  return sh;
}

function setupFirstTime() {
  var sh = sheet_(SHEET_STAFF, STAFF_HEAD);
  sheet_(SHEET_LOG, ['เวลา', 'อีเมล', 'คำสั่ง', 'ผลลัพธ์']);
  if (sh.getLastRow() < 2) {
    sh.appendRow(['admin@school.ac.th', 'ผู้ดูแลระบบคนแรก', 'teacher,admin', 'สำนักงาน (สนง.)', '', '', 'ใช้งาน', '']);
  }
  secret_();
  SpreadsheetApp.getUi().alert('ติดตั้งเรียบร้อย\n\nกรุณาแก้อีเมลในแถวแรกของแผ่น staff ให้เป็นอีเมลจริงของผู้ดูแลระบบ ' +
    'แล้วจึงทำให้ใช้งานได้เป็นเว็บแอป');
}

function log_(email, action, result) {
  try {
    sheet_(SHEET_LOG, ['เวลา', 'อีเมล', 'คำสั่ง', 'ผลลัพธ์'])
      .appendRow([new Date(), email || '-', action || '-', result || '-']);
  } catch (e) { /* บันทึก log ไม่สำเร็จ ไม่ให้กระทบการทำงานหลัก */ }
}

/* ---------- โทเคน ------------------------------------------------------- */
function sign_(text) {
  return Utilities.base64EncodeWebSafe(
    Utilities.computeHmacSha256Signature(text, secret_()));
}

function makeToken_(email) {
  var body = Utilities.base64EncodeWebSafe(JSON.stringify({
    email: String(email).toLowerCase(),
    exp: Date.now() + TOKEN_HOURS * 3600 * 1000
  }));
  return body + '.' + sign_(body);
}

function readToken_(token) {
  if (!token) return null;
  var parts = String(token).split('.');
  if (parts.length !== 2 || sign_(parts[0]) !== parts[1]) return null;
  var data;
  try { data = JSON.parse(Utilities.newBlob(Utilities.base64DecodeWebSafe(parts[0])).getDataAsString()); }
  catch (e) { return null; }
  if (!data || !data.exp || data.exp < Date.now()) return null;
  return data;
}

/* ---------- แผ่นบุคลากร -------------------------------------------------- */
function staffRows_() {
  var sh = sheet_(SHEET_STAFF, STAFF_HEAD);
  var last = sh.getLastRow();
  if (last < 2) return [];
  var values = sh.getRange(2, 1, last - 1, STAFF_COLS.length).getValues();
  return values.map(function (row, i) {
    var obj = { rowIndex: i + 2 };
    STAFF_COLS.forEach(function (key, c) { obj[key] = row[c]; });
    obj.email = String(obj.email || '').trim().toLowerCase();
    obj.name = String(obj.name || '').trim();
    obj.roles = String(obj.roles || 'teacher').split(/[,\s]+/)
      .map(function (r) { return String(r).trim(); })
      .filter(function (r) { return VALID_ROLES.indexOf(r) >= 0; });
    if (!obj.roles.length) obj.roles = ['teacher'];
    obj.learningArea = String(obj.learningArea || '').trim();
    obj.phone = String(obj.phone || '').trim();
    obj.homeroom = String(obj.homeroom || '').trim();
    obj.active = String(obj.active === '' || obj.active == null ? 'ใช้งาน' : obj.active).trim() !== 'ไม่ใช้งาน';
    return obj;
  }).filter(function (x) { return x.email; });
}

function findStaff_(email) {
  var key = String(email || '').trim().toLowerCase();
  var found = staffRows_().filter(function (s) { return s.email === key; });
  return found.length ? found[0] : null;
}

function publicStaff_(s) {
  return { email: s.email, name: s.name, roles: s.roles, learningArea: s.learningArea,
    phone: s.phone, homeroom: s.homeroom };
}

/* ---------- ตรวจตัวตนจาก Google ----------------------------------------- */
/** ยืนยันตัวตนกับ Google แล้วคืนอีเมลที่ยืนยันแล้ว
    รับได้ทั้ง access token (ที่แอปได้จากปุ่มลงชื่อเข้าใช้) และ id_token */
function verifyGoogleUser_(req) {
  var allowed = props_().getProperty('CLIENT_ID');
  if (req.accessToken) {
    var r1 = UrlFetchApp.fetch('https://www.googleapis.com/oauth2/v3/userinfo',
      { headers: { Authorization: 'Bearer ' + req.accessToken }, muteHttpExceptions: true });
    if (r1.getResponseCode() !== 200) throw new Error('ยืนยันบัญชี Google ไม่สำเร็จ');
    var u = JSON.parse(r1.getContentText());
    if (!u.email) throw new Error('บัญชี Google นี้ไม่มีอีเมล');
    return String(u.email).toLowerCase();
  }
  if (!req.idToken) throw new Error('ไม่พบข้อมูลยืนยันตัวตนจาก Google');
  var r2 = UrlFetchApp.fetch('https://oauth2.googleapis.com/tokeninfo?id_token=' +
    encodeURIComponent(req.idToken), { muteHttpExceptions: true });
  if (r2.getResponseCode() !== 200) throw new Error('ยืนยันบัญชี Google ไม่สำเร็จ');
  var info = JSON.parse(r2.getContentText());
  if (!info.email) throw new Error('บัญชี Google นี้ไม่มีอีเมล');
  if (String(info.email_verified) !== 'true') throw new Error('อีเมลนี้ยังไม่ได้ยืนยันกับ Google');
  if (allowed && info.aud !== allowed) throw new Error('แอปนี้ไม่ได้รับอนุญาตให้เข้าใช้');
  return String(info.email).toLowerCase();
}

/* ---------- คำสั่งของ API ------------------------------------------------ */
function apiLogin_(req) {
  var email = verifyGoogleUser_(req);
  var staff = findStaff_(email);
  if (!staff) { log_(email, 'login', 'ไม่พบชื่อในระบบ'); throw new Error('อีเมลนี้ยังไม่มีในฐานข้อมูลบุคลากร กรุณาติดต่อผู้ดูแลระบบ'); }
  if (!staff.active) { log_(email, 'login', 'ถูกปิดการใช้งาน'); throw new Error('บัญชีนี้ถูกปิดการใช้งาน'); }
  sheet_(SHEET_STAFF, STAFF_HEAD).getRange(staff.rowIndex, STAFF_COLS.indexOf('lastLogin') + 1).setValue(new Date());
  log_(email, 'login', 'สำเร็จ');
  return { token: makeToken_(email), expiresInHours: TOKEN_HOURS, staff: publicStaff_(staff) };
}

function needStaff_(req) {
  var data = readToken_(req.token);
  if (!data) throw new Error('หมดเวลาการเข้าใช้ กรุณาเข้าสู่ระบบใหม่');
  var staff = findStaff_(data.email);
  if (!staff || !staff.active) throw new Error('บัญชีนี้ใช้งานไม่ได้แล้ว');
  return staff;
}

function needRole_(req, role) {
  var staff = needStaff_(req);
  if (staff.roles.indexOf(role) < 0) throw new Error('บัญชีนี้ไม่มีสิทธิ์ทำรายการนี้');
  return staff;
}

function apiMe_(req) { return { staff: publicStaff_(needStaff_(req)) }; }

/** รายชื่อบุคลากรทั้งหมด สำหรับให้แอปซิงก์ลงเครื่อง */
function apiStaffList_(req) {
  needStaff_(req);
  return { staff: staffRows_().filter(function (s) { return s.active; }).map(publicStaff_) };
}

/** ผู้ดูแลระบบส่งรายชื่อขึ้นไปเก็บที่ส่วนกลาง (เขียนทับทั้งแผ่น) */
function apiStaffSave_(req) {
  needRole_(req, 'admin');
  var list = req.staff || [];
  if (!list.length) throw new Error('ไม่มีรายชื่อที่จะบันทึก');
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) throw new Error('ระบบกำลังถูกใช้งานอยู่ กรุณาลองใหม่');
  try {
    var sh = sheet_(SHEET_STAFF, STAFF_HEAD);
    var prev = {}, added = 0, updated = 0;
    staffRows_().forEach(function (s) { prev[s.email] = s; });
    var rows = list.map(function (t) {
      var email = String(t.email || '').trim().toLowerCase();
      if (!email) return null;
      if (prev[email]) { updated++; } else { added++; }
      return [email, String(t.name || '').trim(),
        (t.roles || ['teacher']).join(','), String(t.learningArea || '').trim(),
        String(t.phone || '').trim(), String(t.homeroom || '').trim(),
        t.active === false ? 'ไม่ใช้งาน' : 'ใช้งาน',
        prev[email] ? prev[email].lastLogin : ''];
    }).filter(function (r) { return r; });
    if (sh.getLastRow() > 1) sh.getRange(2, 1, sh.getLastRow() - 1, STAFF_COLS.length).clearContent();
    if (rows.length) sh.getRange(2, 1, rows.length, STAFF_COLS.length).setValues(rows);
    log_('', 'staffSave', 'เพิ่ม ' + added + ' อัปเดต ' + updated);
    return { saved: rows.length, added: added, updated: updated };
  } finally { lock.releaseLock(); }
}

/** ตรวจว่าเชื่อมต่อได้จริง ใช้ตอนกรอก URL ในแอป (ไม่ต้องมี token) */
function apiPing_() {
  return { ok: true, sheet: book_().getName(), staffCount: staffRows_().length,
    version: 'gradebook-staff-1.0', serverTime: new Date().toISOString() };
}

var ROUTES = {
  ping: apiPing_, login: apiLogin_, me: apiMe_,
  staffList: apiStaffList_, staffSave: apiStaffSave_
};

/* ---------- จุดรับคำขอ --------------------------------------------------- */
function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function handle_(req) {
  try {
    var fn = ROUTES[req && req.action];
    if (!fn) throw new Error('ไม่รู้จักคำสั่ง: ' + (req && req.action));
    var data = fn(req) || {};
    data.ok = true;
    return json_(data);
  } catch (err) {
    return json_({ ok: false, error: String(err && err.message ? err.message : err) });
  }
}

function doPost(e) {
  var req = {};
  try { req = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (x) { }
  return handle_(req);
}

/** รองรับ GET เฉพาะคำสั่ง ping เพื่อให้ทดสอบจากเบราว์เซอร์ได้ */
function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) || 'ping';
  if (action !== 'ping') return json_({ ok: false, error: 'ใช้ POST สำหรับคำสั่งนี้' });
  return handle_({ action: 'ping' });
}

/** ล็อกให้เฉพาะแอปของโรงเรียนเรียกได้ (ไม่บังคับ) — ใส่ OAuth Client ID แล้วเรียกครั้งเดียว */
function setAllowedClientId() {
  var ui = SpreadsheetApp.getUi();
  var res = ui.prompt('จำกัดให้เฉพาะแอปของโรงเรียน', 'วาง OAuth Client ID (ลงท้าย .apps.googleusercontent.com)', ui.ButtonSet.OK_CANCEL);
  if (res.getSelectedButton() !== ui.Button.OK) return;
  var id = res.getResponseText().trim();
  if (id) { props_().setProperty('CLIENT_ID', id); ui.alert('บันทึกแล้ว'); }
  else { props_().deleteProperty('CLIENT_ID'); ui.alert('ยกเลิกการจำกัดแล้ว'); }
}
