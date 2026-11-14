// 公開設定：只放 VAPID 公鑰與 Worker 網址，不可放任何私鑰或邀請碼。
window.APP_CONFIG = {
  VAPID_PUBLIC_KEY: "PASTE_VAPID_PUBLIC_KEY_HERE",
  PUSH_API_BASE: "https://stock-monitor-api.dasps9103.workers.dev"
};