self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("push", event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {}
  const title = data.title || "台積電 2330 追蹤提醒";
  const options = {
    body: data.body || "每日分析已更新",
    icon: "icon.svg",
    badge: "icon.svg",
    data: { url: data.url || "./" },
    tag: "tsmc-stock-alert",
    renotify: true
  };
  event.waitUntil(self.registration.showNotification(title, options));
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "./", self.location).href;
  event.waitUntil(clients.matchAll({type:"window",includeUncontrolled:true}).then(list=>{
    for (const client of list) {
      if (client.url.startsWith(self.registration.scope) && "focus" in client) {
        client.navigate(target); return client.focus();
      }
    }
    return clients.openWindow(target);
  }));
});
