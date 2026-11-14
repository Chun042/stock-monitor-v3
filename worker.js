const cors = (env) => ({
  "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN,
  "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type,Authorization",
  "Vary": "Origin"
});
const json = (data, status=200, env=null) => new Response(JSON.stringify(data), {
  status, headers: {"content-type":"application/json; charset=utf-8", ...(env ? cors(env) : {})}
});
const defaults = {daily:false, technical:true, revenue:true, risk:true};
function validPrefs(p) {
  const out = {...defaults};
  for (const k of Object.keys(defaults)) if (typeof p?.[k] === "boolean") out[k]=p[k];
  return out;
}
async function sha256(s) {
  const b=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,"0")).join("");
}
export default {
  async fetch(req, env) {
    const u=new URL(req.url);
    if(req.method==="OPTIONS") return new Response(null,{status:204,headers:cors(env)});
    if(u.pathname==="/health") return json({ok:true,service:"tsmc-multiuser-push"});
    if(u.pathname==="/api/register" && req.method==="POST") {
      if(req.headers.get("Origin")!==env.ALLOWED_ORIGIN) return json({error:"origin denied"},403,env);
      const body=await req.json();
      if(!body.inviteCode || body.inviteCode!==env.INVITE_CODE) return json({error:"邀請碼錯誤"},403,env);
      if(!body.displayName || typeof body.displayName!=="string" || body.displayName.length>24) return json({error:"請填寫暱稱（最多24字）"},400,env);
      if(!body.subscription?.endpoint || !body.subscription?.keys?.p256dh || !body.subscription?.keys?.auth) return json({error:"推播訂閱資料不完整"},400,env);
      const deviceId=await sha256(body.subscription.endpoint);
      const now=new Date().toISOString();
      await env.DB.prepare(`INSERT INTO devices(device_id,display_name,subscription_json,preferences_json,created_at,updated_at,last_seen_at)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET display_name=excluded.display_name,
        subscription_json=excluded.subscription_json,preferences_json=excluded.preferences_json,updated_at=excluded.updated_at,last_seen_at=excluded.last_seen_at`)
        .bind(deviceId,body.displayName,JSON.stringify(body.subscription),JSON.stringify(validPrefs(body.preferences)),now,now,now).run();
      return json({ok:true,deviceId},200,env);
    }
    if(u.pathname==="/api/preferences" && req.method==="POST") {
      if(req.headers.get("Origin")!==env.ALLOWED_ORIGIN) return json({error:"origin denied"},403,env);
      const body=await req.json();
      if(!body.inviteCode || body.inviteCode!==env.INVITE_CODE) return json({error:"邀請碼錯誤"},403,env);
      const id=await sha256(body.subscription?.endpoint||"");
      if(!id) return json({error:"缺少訂閱"},400,env);
      const now=new Date().toISOString();
      const result=await env.DB.prepare("UPDATE devices SET preferences_json=?,updated_at=?,last_seen_at=? WHERE device_id=?")
        .bind(JSON.stringify(validPrefs(body.preferences)),now,now,id).run();
      if(!result.meta.changes) return json({error:"找不到此裝置，請重新註冊"},404,env);
      return json({ok:true},200,env);
    }
    if(u.pathname==="/api/unsubscribe" && req.method==="POST") {
      if(req.headers.get("Origin")!==env.ALLOWED_ORIGIN) return json({error:"origin denied"},403,env);
      const body=await req.json();
      if(body.inviteCode!==env.INVITE_CODE) return json({error:"邀請碼錯誤"},403,env);
      const id=await sha256(body.subscription?.endpoint||"");
      await env.DB.prepare("DELETE FROM devices WHERE device_id=?").bind(id).run();
      return json({ok:true},200,env);
    }

    // Per-browser profile watchlists. The shared invite code is household access,
    // not a full account-authentication system; ownerId is a client-generated profile key.
    if(u.pathname==="/api/watchlist" && req.method==="GET") {
      const ownerId=u.searchParams.get("ownerId")||"";
      const inviteCode=u.searchParams.get("inviteCode")||"";
      if(inviteCode!==env.INVITE_CODE || !/^[a-zA-Z0-9_-]{12,80}$/.test(ownerId)) return json({error:"unauthorized"},403,env);
      const {results=[]}=await env.DB.prepare("SELECT symbol,market,display_name,created_at FROM watchlists WHERE owner_id=? ORDER BY created_at DESC").bind(ownerId).all();
      return json({items:results},200,env);
    }
    if(u.pathname==="/api/watchlist/add" && req.method==="POST") {
      if(req.headers.get("Origin")!==env.ALLOWED_ORIGIN) return json({error:"origin denied"},403,env);
      const b=await req.json();
      if(b.inviteCode!==env.INVITE_CODE || !/^[a-zA-Z0-9_-]{12,80}$/.test(b.ownerId||"")) return json({error:"unauthorized"},403,env);
      const market=b.market==="US"?"US":"TW", symbol=String(b.symbol||"").trim().toUpperCase();
      if(!/^[A-Z0-9.^_-]{1,15}$/.test(symbol)) return json({error:"股票代號格式不正確"},400,env);
      if(!b.displayName || String(b.displayName).length>40) return json({error:"請提供股票名稱"},400,env);
      const count=await env.DB.prepare("SELECT COUNT(*) AS n FROM watchlists WHERE owner_id=?").bind(b.ownerId).first();
      if((count?.n||0)>=30) return json({error:"每個自選清單最多追蹤 30 檔"},400,env);
      await env.DB.prepare("INSERT INTO watchlists(owner_id,symbol,market,display_name,created_at) VALUES(?,?,?,?,?) ON CONFLICT(owner_id,symbol,market) DO UPDATE SET display_name=excluded.display_name")
        .bind(b.ownerId,symbol,market,String(b.displayName),new Date().toISOString()).run();
      return json({ok:true},200,env);
    }
    if(u.pathname==="/api/watchlist/remove" && req.method==="POST") {
      if(req.headers.get("Origin")!==env.ALLOWED_ORIGIN) return json({error:"origin denied"},403,env);
      const b=await req.json();
      if(b.inviteCode!==env.INVITE_CODE || !/^[a-zA-Z0-9_-]{12,80}$/.test(b.ownerId||"")) return json({error:"unauthorized"},403,env);
      await env.DB.prepare("DELETE FROM watchlists WHERE owner_id=? AND symbol=? AND market=?")
        .bind(b.ownerId,String(b.symbol||"").toUpperCase(),b.market==="US"?"US":"TW").run();
      return json({ok:true},200,env);
    }
    if(u.pathname==="/api/holdings" && req.method==="GET") {
      const ownerId=u.searchParams.get("ownerId")||"", inviteCode=u.searchParams.get("inviteCode")||"";
      if(inviteCode!==env.INVITE_CODE || !/^[a-zA-Z0-9_-]{12,80}$/.test(ownerId)) return json({error:"unauthorized"},403,env);
      const {results=[]}=await env.DB.prepare("SELECT symbol,market,quantity,average_cost,currency,updated_at FROM holdings WHERE owner_id=? ORDER BY updated_at DESC").bind(ownerId).all();
      return json({items:results},200,env);
    }
    if(u.pathname==="/api/holdings/save" && req.method==="POST") {
      if(req.headers.get("Origin")!==env.ALLOWED_ORIGIN) return json({error:"origin denied"},403,env);
      const b=await req.json();
      if(b.inviteCode!==env.INVITE_CODE || !/^[a-zA-Z0-9_-]{12,80}$/.test(b.ownerId||"")) return json({error:"unauthorized"},403,env);
      const symbol=String(b.symbol||"").toUpperCase(), market=b.market==="US"?"US":"TW";
      const quantity=Number(b.quantity), cost=Number(b.averageCost);
      if(!/^[A-Z0-9.^_-]{1,15}$/.test(symbol) || !(quantity>0) || !(cost>=0) || !Number.isFinite(quantity+cost)) return json({error:"持股數量或成本不正確"},400,env);
      const inList=await env.DB.prepare("SELECT 1 FROM watchlists WHERE owner_id=? AND symbol=? AND market=?").bind(b.ownerId,symbol,market).first();
      if(!inList){
        const count=await env.DB.prepare("SELECT COUNT(*) AS n FROM watchlists WHERE owner_id=?").bind(b.ownerId).first();
        if((count?.n||0)>=30) return json({error:"自選股已達 30 檔上限，請先移除一檔再登記持股"},400,env);
        await env.DB.prepare("INSERT INTO watchlists(owner_id,symbol,market,display_name,created_at) VALUES(?,?,?,?,?)")
          .bind(b.ownerId,symbol,market,symbol,new Date().toISOString()).run();
      }
      await env.DB.prepare(`INSERT INTO holdings(owner_id,symbol,market,quantity,average_cost,currency,updated_at)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner_id,symbol,market) DO UPDATE SET quantity=excluded.quantity,average_cost=excluded.average_cost,currency=excluded.currency,updated_at=excluded.updated_at`)
        .bind(b.ownerId,symbol,market,quantity,cost,market==="US"?"USD":"TWD",new Date().toISOString()).run();
      return json({ok:true},200,env);
    }
    if(u.pathname==="/api/holdings/delete" && req.method==="POST") {
      if(req.headers.get("Origin")!==env.ALLOWED_ORIGIN) return json({error:"origin denied"},403,env);
      const b=await req.json();
      if(b.inviteCode!==env.INVITE_CODE || !/^[a-zA-Z0-9_-]{12,80}$/.test(b.ownerId||"")) return json({error:"unauthorized"},403,env);
      await env.DB.prepare("DELETE FROM holdings WHERE owner_id=? AND symbol=? AND market=?")
        .bind(b.ownerId,String(b.symbol||"").toUpperCase(),b.market==="US"?"US":"TW").run();
      return json({ok:true},200,env);
    }
    if(u.pathname==="/admin/watchlists" && req.method==="GET") {
      if(req.headers.get("Authorization")!==`Bearer ${env.ADMIN_TOKEN}`) return json({error:"unauthorized"},401);
      const {results=[]}=await env.DB.prepare("SELECT owner_id,symbol,market,display_name FROM watchlists ORDER BY owner_id,symbol").all();
      return json({items:results},200);
    }

    if(u.pathname==="/admin/devices" && req.method==="GET") {
      if(req.headers.get("Authorization")!==`Bearer ${env.ADMIN_TOKEN}`) return json({error:"unauthorized"},401);
      const {results=[]}=await env.DB.prepare("SELECT device_id,display_name,subscription_json,preferences_json FROM devices").all();
      return json({devices:results});
    }
    return json({error:"not found"},404,env);
  }
};
