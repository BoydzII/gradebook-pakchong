/* Service Worker ของ ปพ.5 Online
   หน้าที่หลักคือทำให้เปิดแอปได้แม้เน็ตหลุด และติดตั้งลงมือถือ/ไอแพดเป็นไอคอนแอปได้
   ข้อมูลคะแนนและตารางสอนยังอยู่ใน localStorage ของเครื่องเหมือนเดิม ไฟล์นี้ไม่ยุ่งกับข้อมูล

   วิธีอัปเดตแอปหลังแก้โค้ด: เปลี่ยนเลขเวอร์ชันที่ CACHE_VERSION แล้วอัปโหลดใหม่
   ผู้ใช้จะเห็นแถบแจ้ง "มีเวอร์ชันใหม่" ให้กดอัปเดต */

const CACHE_VERSION = 'v43';
const CACHE_NAME = 'gradebook-' + CACHE_VERSION;

/* ไฟล์แกนของแอป โหลดไว้ล่วงหน้าให้เปิดออฟไลน์ได้ */
const APP_SHELL = [
  './',
  './index.html',
  './config.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-512.png',
  './icons/apple-touch-icon.png',
  './icons/school-logo.png',
  './vendor/firebase-app-compat.js',
  './vendor/firebase-auth-compat.js',
  './vendor/firebase-firestore-compat.js'
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    // ใส่ทีละไฟล์ เพื่อให้ไฟล์เดียวพลาดแล้วไม่ทำให้การติดตั้งล้มทั้งชุด
    await Promise.all(APP_SHELL.map(url => cache.add(url).catch(() => {})));
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k.startsWith('gradebook-') && k !== CACHE_NAME).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

/* ให้หน้าเว็บสั่งข้ามคิวรอได้ เมื่อผู้ใช้กดปุ่มอัปเดต */
self.addEventListener('message', event => {
  if (event.data === 'skip-waiting') self.skipWaiting();
  // ให้หน้าเว็บถามเลขเวอร์ชันได้ ใช้ตอนติดตั้งเป็นแอปแล้วอยากรู้ว่าตอนนี้ใช้เวอร์ชันอะไร
  if (event.data === 'get-version' && event.source) event.source.postMessage({ type: 'version', version: CACHE_VERSION });
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // ข้ามคำขอข้ามโดเมนทั้งหมด (Google Sign-In, Sheets API, Drive) ให้วิ่งตรงตามปกติ
  if (url.origin !== self.location.origin) return;

  // การเปิดหน้าเว็บ: เอาของใหม่จากเน็ตก่อน ถ้าเน็ตล่มค่อยใช้ของในเครื่อง
  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        const cache = await caches.open(CACHE_NAME);
        cache.put('./', fresh.clone());
        return fresh;
      } catch (e) {
        const cached = await caches.match('./', { ignoreSearch: true }) ||
          await caches.match('./index.html', { ignoreSearch: true });
        return cached || new Response('<h1>ออฟไลน์</h1><p>ยังไม่เคยเปิดแอปบนเครื่องนี้ขณะออนไลน์</p>',
          { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
      }
    })());
    return;
  }

  // ไฟล์อื่นในโดเมนเดียวกัน: ใช้ของในเครื่องก่อนให้เปิดไว แล้วอัปเดตเบื้องหลัง
  event.respondWith((async () => {
    const cached = await caches.match(req);
    const network = fetch(req).then(res => {
      if (res && res.ok) caches.open(CACHE_NAME).then(c => c.put(req, res.clone()));
      return res;
    }).catch(() => null);
    return cached || (await network) || new Response('', { status: 504 });
  })());
});
