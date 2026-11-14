export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return new Response("LINE webhook worker OK");
    }
    if (request.method === "GET" && url.pathname === "/user-id") {
      if (url.searchParams.get("key") !== env.ADMIN_KEY) return new Response("Unauthorized", {status:401});
      const id = await env.LINE_USERS.get("last_user_id");
      return new Response(id || "尚未收到使用者訊息；請先將官方帳號加好友並傳送文字訊息。", {
        headers: {"content-type":"text/plain; charset=utf-8"}
      });
    }
    if (request.method !== "POST" || url.pathname !== "/callback") {
      return new Response("Not found", {status:404});
    }
    const raw = await request.text();
    const signature = request.headers.get("x-line-signature") || "";
    const key = await crypto.subtle.importKey(
      "raw", new TextEncoder().encode(env.LINE_CHANNEL_SECRET),
      {name:"HMAC",hash:"SHA-256"}, false, ["sign"]
    );
    const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(raw));
    const expected = btoa(String.fromCharCode(...new Uint8Array(mac)));
    if (signature !== expected) return new Response("Invalid signature", {status:401});
    const body = JSON.parse(raw);
    for (const event of (body.events || [])) {
      const uid = event.source?.userId;
      if (uid) await env.LINE_USERS.put("last_user_id", uid);
    }
    return new Response("OK");
  }
};
