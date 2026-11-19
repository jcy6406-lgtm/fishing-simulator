import os, sqlite3, secrets, random, time
from flask import Flask, request, jsonify, session, render_template_string, g
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE","1")=="1")
DB=os.environ.get("DATABASE_PATH","/tmp/fishing-players.sqlite3")
RODS=[("竹製釣竿",0,[72,23,5,0,0]),("碳纖維釣竿",350,[57,29,13,1,0]),("精工海釣竿",1200,[42,32,22,4,0]),("深藍探險竿",4000,[30,34,27,8,1]),("傳說星潮竿",15000,[18,32,32,15,3])]
RAW=[
("水中垃圾",0,"lake,sea","🗑️"),("小蝦",0,"lake,sea","🦐"),("螃蟹",0,"sea","🦀"),("蝌蚪",0,"lake","🐸"),
("小草魚",1,"lake","🐟"),("烏龜",1,"lake","🐢"),("海星",1,"sea","⭐"),("孔雀魚",1,"lake","🐠"),("小丑魚",1,"sea","🐠"),("海蛞蝓",1,"sea","🐌"),
("鰻魚",2,"lake,sea","🐟"),("海蛇",2,"sea","🐍"),("海龜",2,"sea","🐢"),("像素魚",2,"lake,sea","👾"),("食人魚",2,"lake","🐟"),("蠑螈",2,"lake","🦎"),("金魚",2,"lake","🐠"),
("鯊魚",3,"sea","🦈"),("鯨魚",3,"sea","🐋"),("美人魚",3,"sea","🧜"),("深海魷魚",3,"sea","🦑"),("鱷魚",3,"lake","🐊"),("龍鱗湖君",3,"lake","🐉"),("湖中大水母",3,"lake","🪼"),("伊西 Issie",3,"lake","🐉"),
("尼斯湖水怪",4,"lake","🦕"),("海龍",4,"sea","🐲")]
PRICES=[8,35,140,1100,15000]
FISH=[dict(name=n,level=l,places=p.split(","),emoji=e,price=PRICES[l]) for n,l,p,e in RAW]
def db():
 if "db" not in g:
  g.db=sqlite3.connect(DB,timeout=20);g.db.row_factory=sqlite3.Row;g.db.execute("PRAGMA busy_timeout=5000")
 return g.db
@app.teardown_appcontext
def close(exc):
 d=g.pop("db",None)
 if d:d.close()
def init():
 os.makedirs(os.path.dirname(os.path.abspath(DB)),exist_ok=True)
 with sqlite3.connect(DB) as d:
  d.executescript("""CREATE TABLE IF NOT EXISTS players(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,coins INTEGER DEFAULT 0,rod INTEGER DEFAULT 0,caught INTEGER DEFAULT 0,place TEXT DEFAULT 'lake',last_cast REAL DEFAULT 0);
  CREATE TABLE IF NOT EXISTS bag(id INTEGER PRIMARY KEY,pid INTEGER NOT NULL,name TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS dex(pid INTEGER NOT NULL,name TEXT NOT NULL,PRIMARY KEY(pid,name));""")
init()
@app.before_request
def guard():
 if request.path.startswith("/api/") and request.method=="POST" and request.headers.get("X-Requested-With")!="FishingSimulator":return jsonify(error="無效請求"),403
def player():
 pid=session.get("pid")
 return db().execute("SELECT * FROM players WHERE id=?",(pid,)).fetchone() if pid else None
def state(p):
 return dict(username=p["username"],coins=p["coins"],rod=p["rod"],caught=p["caught"],place=p["place"],bag=[r[0] for r in db().execute("SELECT name FROM bag WHERE pid=? ORDER BY id DESC",(p["id"],))],dex=[r[0] for r in db().execute("SELECT name FROM dex WHERE pid=?",(p["id"],))])
@app.get("/")
def home():return render_template_string(HTML)
@app.get("/api/config")
def config():return jsonify(fish=FISH,rods=[dict(name=n,cost=c,weights=w) for n,c,w in RODS])
@app.get("/api/me")
def me():
 p=player();return jsonify(state(p)) if p else (jsonify(error="尚未登入"),401)
@app.post("/api/register")
def register():
 a=request.get_json(silent=True) or {};n=str(a.get("username","")).strip();pw=str(a.get("password",""))
 if not 2<=len(n)<=24 or not 8<=len(pw)<=128:return jsonify(error="名稱需2至24字，密碼至少8字"),400
 try:
  c=db().execute("INSERT INTO players(username,password) VALUES(?,?)",(n,generate_password_hash(pw)));db().commit()
 except sqlite3.IntegrityError:return jsonify(error="名稱已被使用"),409
 session.clear();session["pid"]=c.lastrowid;return jsonify(state(player()))
@app.post("/api/login")
def login():
 a=request.get_json(silent=True) or {};p=db().execute("SELECT * FROM players WHERE username=?",(str(a.get("username","")).strip(),)).fetchone()
 if not p or not check_password_hash(p["password"],str(a.get("password",""))):return jsonify(error="帳號或密碼錯誤"),401
 session.clear();session["pid"]=p["id"];return jsonify(state(p))
@app.post("/api/logout")
def logout():session.clear();return jsonify(ok=True)
@app.post("/api/place")
def place():
 p=player()
 if not p:return jsonify(error="請登入"),401
 loc=(request.get_json(silent=True) or {}).get("place")
 if loc not in ("lake","sea"):return jsonify(error="釣點無效"),400
 db().execute("UPDATE players SET place=? WHERE id=?",(loc,p["id"]));db().commit();return jsonify(state(player()))
@app.post("/api/cast")
def cast():
 p=player()
 if not p:return jsonify(error="請登入"),401
 d=db();d.execute("BEGIN IMMEDIATE");p=d.execute("SELECT * FROM players WHERE id=?",(p["id"],)).fetchone();now=time.time()
 if now-p["last_cast"]<3:d.rollback();return jsonify(error="請稍候再拋竿"),429
 level=random.choices(range(5),weights=RODS[p["rod"]][2])[0];fish=random.choice([f for f in FISH if f["level"]==level and p["place"] in f["places"]])
 d.execute("UPDATE players SET caught=caught+1,last_cast=? WHERE id=?",(now,p["id"]))
 d.execute("INSERT INTO bag(pid,name) VALUES(?,?)",(p["id"],fish["name"]))
 d.execute("INSERT OR IGNORE INTO dex(pid,name) VALUES(?,?)",(p["id"],fish["name"]))
 d.commit();return jsonify(catch=fish,state=state(player()))
@app.post("/api/sell")
def sell():
 p=player()
 if not p:return jsonify(error="請登入"),401
 d=db();d.execute("BEGIN IMMEDIATE");items=d.execute("SELECT id,name FROM bag WHERE pid=?",(p["id"],)).fetchall();values={f["name"]:f["price"] for f in FISH};earned=sum(values[x["name"]] for x in items)
 d.execute("DELETE FROM bag WHERE pid=?",(p["id"],));d.execute("UPDATE players SET coins=coins+? WHERE id=?",(earned,p["id"]));d.commit();return jsonify(earned=earned,state=state(player()))
@app.post("/api/upgrade")
def upgrade():
 p=player()
 if not p:return jsonify(error="請登入"),401
 i=p["rod"]+1
 if i>=len(RODS):return jsonify(error="已是最高級釣竿"),400
 cost=RODS[i][1]
 if p["coins"]<cost:return jsonify(error="金幣不足"),400
 db().execute("UPDATE players SET coins=coins-?,rod=? WHERE id=?",(cost,i,p["id"]));db().commit();return jsonify(state(player()))
HTML=r'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>釣魚模擬器</title><style>
*{box-sizing:border-box}body{margin:0;font-family:system-ui,"Noto Sans TC",sans-serif;background:#071c2b;color:#f3f8f8}button,input,select{font:inherit}button{cursor:pointer;border:0;border-radius:10px;padding:11px 16px;background:#f4c46a;color:#1c2833;font-weight:700}button:hover{filter:brightness(1.08)}input{padding:12px;border:1px solid #7b9caa;border-radius:10px;background:#102b3d;color:white;width:100%}header{display:flex;justify-content:space-between;align-items:center;padding:15px 5%;background:#0b2537}main{max-width:1150px;margin:auto;padding:20px}.panel{background:#123145dd;border:1px solid #4d7a85;border-radius:16px;padding:20px;margin:12px 0}.auth{min-height:75vh;display:grid;place-items:center;background:linear-gradient(#06172555,#06172599),url('/static/download.png') center/cover no-repeat;background-color:#102d40}.auth .panel{width:min(420px,92vw);backdrop-filter:blur(12px)}.auth input{margin:7px 0}.auth button{margin:7px 5px 7px 0}.scene{position:relative;height:390px;overflow:hidden;border-radius:16px;background:#205d73 center/cover no-repeat;perspective:600px}.scene.lake{background-image:linear-gradient(#0001,#0001),url('/static/ChatGPT 圖像 2026年11月19日 上午09_12_49.png')}.scene.sea{background-image:linear-gradient(#0001,#0001),url('/static/ChatGPT 圖像 2026年11月19日 上午09_12_58.png')}.scene.night:before{content:'';position:absolute;inset:0;background:#04172c88;pointer-events:none}.scene.rain:after{content:"";position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(108deg,transparent 0 13px,#c6eaf955 14px 15px,transparent 16px 24px);animation:rain .4s linear infinite}.sun{position:absolute;right:13%;top:12%;font-size:54px}.shore{display:none}.boat{position:absolute;bottom:-80px;left:26%;width:48%;height:180px;background:linear-gradient(#fff,#c6d5dd);clip-path:polygon(15% 0,85% 0,100% 100%,0 100%);border-radius:30px}.rod{position:absolute;bottom:12px;left:50%;width:7px;height:280px;background:linear-gradient(90deg,#2a1b12,#d1a05e);transform-origin:bottom center;transform:rotate(27deg);border-radius:10px;transition:transform .4s}.line{position:absolute;left:52%;bottom:235px;height:90px;width:1px;background:#fff9;transform:rotate(27deg);transform-origin:bottom}.float{position:absolute;top:53%;left:60%;font-size:23px;animation:bob 1.8s ease-in-out infinite}.casting .rod{animation:cast 1.7s ease-in-out}.casting .float{animation:floatcast 1.7s ease-out}.bite .rod{animation:bite .35s infinite alternate}.bite .float{animation:bob .25s infinite alternate}.actions{display:flex;flex-wrap:wrap;gap:10px;margin:15px 0}.stats{display:flex;gap:16px;flex-wrap:wrap;color:#f7d88b}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}.fish{border:1px solid #587583;border-radius:12px;padding:12px;background:#0c2536;text-align:center}.fish .emoji{font-size:42px}.white{color:#d8dce0}.green{color:#6fe2a1}.blue{color:#75baff}.yellow{color:#f5d15e}.red{color:#ff7777}.hidden{display:none!important}#notice{min-height:25px;color:#f5d15e}.muted{color:#b0cbd2}small{color:#b0cbd2}@keyframes cast{0%{transform:rotate(27deg)}35%{transform:rotate(-30deg)}75%{transform:rotate(60deg)}100%{transform:rotate(27deg)}}@keyframes bite{to{transform:rotate(17deg)}}@keyframes bob{to{transform:translateY(7px)}}@keyframes floatcast{0%{top:15%;left:50%;opacity:0}60%{top:53%;left:60%;opacity:1}100%{top:53%;left:60%}}@keyframes rain{to{background-position:0 40px}}@media(max-width:600px){.scene{height:300px}}
</style></head><body><header><strong>🎣 釣魚模擬器</strong><span id="who">探索未知的水域</span></header><section id="auth" class="auth"><div class="panel"><h1>釣魚模擬器</h1><p>從湖岸到遠洋，收藏傳說中的神祕生物。</p><input id="name" placeholder="玩家名稱" maxlength="24"><input id="password" type="password" placeholder="密碼（至少8字）"><div><button onclick="auth('register')">註冊</button><button onclick="auth('login')">登入</button></div><p id="autherr"></p></div></section><main id="game" class="hidden"><div class="stats"><b id="coins"></b><b id="rodname"></b><b id="caught"></b></div><div class="actions"><button onclick="changePlace('lake')">🌿 霧隱湖岸</button><button onclick="changePlace('sea')">🚤 遠洋快艇</button><button onclick="showDex()">📖 生物圖鑑</button><button onclick="showBag()">🎒 背包</button><button onclick="logout()">登出</button></div><div id="scene" class="scene"><div class="sun" id="sun">☀️</div><div id="ground" class="shore"></div><div class="line"></div><div class="float">🔴</div><div class="rod"></div></div><div class="actions"><button id="castBtn" onclick="cast()">🎣 拋竿釣魚</button><button onclick="sell()">💰 賣出背包全部漁獲</button><button onclick="upgrade()">⬆️ 升級釣竿</button></div><div id="notice"></div><div class="panel"><h2 id="paneltitle">航海生物圖鑑</h2><div id="collection" class="grid"></div></div><p class="muted">天氣以裝置定位的即時天氣資料呈現；未授權定位時使用台北。測試版資料可能在伺服器重新部署後遺失。</p></main><script>
let cfg=null,s=null,busy=false,weather={};const $=id=>document.getElementById(id),classes=['white','green','blue','yellow','red'],labels=['白','綠','藍','黃','紅'];const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,data){let opts=data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'FishingSimulator'},body:JSON.stringify(data)};let r=await fetch('/api/'+path,opts),j=await r.json();if(!r.ok)throw Error(j.error||'操作失敗');return j}
function msg(t){$('notice').textContent=t}
async function auth(mode){try{s=await api(mode,{username:$('name').value,password:$('password').value});start()}catch(e){$('autherr').textContent=e.message}}
async function start(){cfg=cfg||await api('config');$('auth').classList.add('hidden');$('game').classList.remove('hidden');update();showDex();getWeather()}
function update(){$('scene').classList.toggle('lake',s.place==='lake');$('scene').classList.toggle('sea',s.place==='sea');$('who').textContent=s.username;$('coins').textContent='🪙 '+s.coins;$('rodname').textContent='🎣 '+cfg.rods[s.rod].name;$('caught').textContent='累計 '+s.caught+' 次';$('ground').className=s.place==='sea'?'boat':'shore';$('scene').style.backgroundPosition='center'}
async function changePlace(place){try{s=await api('place',{place});update();msg(place==='lake'?'已抵達霧隱湖岸':'已登上白色快艇');showDex()}catch(e){msg(e.message)}}
async function cast(){if(busy)return;busy=true;$('castBtn').disabled=true;try{$('scene').classList.add('casting');msg('正在拋竿……');await sleep(1800);$('scene').classList.remove('casting');msg('浮標落水，等待魚兒上鉤……');await sleep(1000);let r=await api('cast',{});$('scene').classList.add('bite');msg('有魚上鉤！收線中……');await sleep(950);$('scene').classList.remove('bite');s=r.state;update();msg('🎉 釣到了 '+r.catch.emoji+' '+r.catch.name+'（'+labels[r.catch.level]+'色品質）');showBag()}catch(e){msg(e.message)}finally{$('scene').classList.remove('casting','bite');busy=false;$('castBtn').disabled=false}}
async function sell(){try{let r=await api('sell',{});s=r.state;update();msg('出售成功！獲得 '+r.earned+' 金幣');showBag()}catch(e){msg(e.message)}}
async function upgrade(){try{let r=await api('upgrade',{});s=r.state;update();msg('升級成功！ '+cfg.rods[s.rod].name)}catch(e){msg(e.message)}}
function showDex(){$('paneltitle').textContent='📖 航海生物圖鑑（已解鎖 '+s.dex.length+'/'+cfg.fish.length+'）';$('collection').replaceChildren();for(let f of cfg.fish){let found=s.dex.includes(f.name),el=document.createElement('div');el.className='fish '+classes[f.level];let ico=document.createElement('div');ico.className='emoji';ico.textContent=found?f.emoji:'❔';let title=document.createElement('strong');title.textContent=found?f.name:'未知生物';let info=document.createElement('p');info.textContent=labels[f.level]+'色 · '+f.places.map(p=>p==='lake'?'湖泊':'海洋').join(' / ');el.append(ico,title,info);$('collection').append(el)}}
function showBag(){$('paneltitle').textContent='🎒 背包（'+s.bag.length+' 件）';$('collection').replaceChildren();for(let n of s.bag){let f=cfg.fish.find(x=>x.name===n),el=document.createElement('div');el.className='fish '+classes[f.level];el.textContent=f.emoji+' '+n+' · '+f.price+' 金幣';$('collection').append(el)}}
async function logout(){await api('logout',{});location.reload()}
async function getWeather(lat=25.033,long=121.565){try{let d=await (await fetch('https://api.open-meteo.com/v1/forecast?latitude='+lat+'&longitude='+long+'&current=weather_code,is_day&timezone=auto')).json(),w=d.current;if(!w)return;$('scene').classList.toggle('night',w.is_day===0);$('scene').classList.toggle('rain',w.weather_code>=51&&w.weather_code<=82);$('sun').textContent=w.is_day===0?'🌙':w.weather_code>=51&&w.weather_code<=82?'🌧️':'☀️'}catch(e){}}
if(navigator.geolocation)navigator.geolocation.getCurrentPosition(p=>{weather={lat:p.coords.latitude,long:p.coords.longitude}},()=>{}, {timeout:4000});
setInterval(()=>getWeather(weather.lat,weather.long),900000);
api('config').then(c=>cfg=c).then(()=>api('me')).then(p=>{s=p;start()}).catch(()=>{});
</script></body></html>'''
if __name__=="__main__":app.run(port=int(os.environ.get("PORT",5000)))
