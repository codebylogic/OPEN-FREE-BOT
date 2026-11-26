OpenCode Telegram Bot (free server + free models)
Telegram se OpenCode chalane wala bot. Server par opencode CLI chalta hai, bot
usko drive karta hai. Code se login, model choose, thinking level, session
manage — sab Telegram se.
code
Telegram  ──►  bot.py  ──►  opencode run --format json  ──►  Zen free models
   ▲                              │
   └────── streamed reply ────────┘
Important: OpenCode Zen ke free models sirf OpenCode client ke andar kaam
karte hain (raw API par 403 aata hai). Isi liye bot khud opencode run chalata
hai, apna HTTP client nahi banata.
1. Kya-kya milega
Command
Kaam
/start YOUR_CODE
access code se login (bina code ke kuch nahi chalega)
/free
free models ki list, button tap karke select
/model ya /modal
model change; /model provider/model se seedha bhi
/thinking
reasoning effort: default / low / medium / high
/new
naya session (purana context clear)
/exit
current chat session band
/status
model, session id, running hai ya nahi
/stop
chal raha run kill
/logout
access code dobara maango
koi bhi text
usi session me prompt ban ke jayega
Har chat ka apna session, model aur thinking level SQLite me save rehta hai.
2. Zaroorat
1.
Telegram bot token — @BotFather se (/newbot).
2.
Ek server jo 24x7 chale. Free options neeche.
3.
Node.js 18+ (opencode ke liye) aur Python 3.10+ (bot ke liye).
Free server options (2026)
Option
Free?
Bot ke liye theek?
Oracle Cloud Always Free (Ampere ARM, 2 OCPU / 12 GB)
Haan, time limit nahi
✅ Best. 24x7 chalta hai, par card verification chahiye
Northflank Sandbox ($20/month credit, always-on)
Haan
✅ Agar Linux manage nahi karna; card ke bina try karne layak
Render free (webhook mode)
Haan, no card
⚠️ 15 min idle par sleep; 512 MB RAM tight
Apna laptop / PC / Raspberry Pi
Haan
✅ Jab tak on hai
Android phone + Termux
Haan
⚠️ Chalta hai, battery/background limits
Google Cloud free e2-micro (US region)
Haan
⚠️ 1 GB RAM + 1 GB egress/month — tight
Render / Koyeb / Railway free tier
Limited
❌ Free web service sleep ho jati hai, long-polling bot ke liye theek nahi
AWS Free Tier (naya account)
Credits, 6 mahine
❌ Permanent free nahi
FPS.ms / FadeHost / VisiHost free
128-256 MB
❌ opencode ke liye RAM kam
Free tiers badalte rehte hain — signup se pehle price page check kar lo.
Card nahi hai? → [`SERVER-OPTIONS.md`](SERVER-OPTIONS.md) me sirf card-free raste hain
(apna PC, Termux, Northflank, Render webhook) — Oracle/GCP/Koyeb teeno card maangte hain.
3. Step-by-step (Oracle Cloud Always Free)
Step 1 — Bot token lo
1.
Telegram me @BotFather → /newbot → naam + username.
2.
Token milega: 123456789:AA... — isko sambhal ke rakho.
3.
@userinfobot ko message karke apna numeric user id le lo (optional, security ke liye).
Step 2 — Free VM banao
1.
cloud.oracle.com → sign up (card verification hota hai, charge nahi).
2.
Home region India (Mumbai / Hyderabad) chuno — baad me badal nahi sakte.
3.
Compute → Instances → Create instance
•
Shape: Ampere → VM.Standard.A1.Flex, 2 OCPU / 12 GB (Always Free ki
     nayi limit — June 2026 me 4/24 se aadhi hui; isse zyada mat lo, warna
     instance disable ho jayega)
•
Image: Ubuntu 24.04 (ya 22.04)
•
SSH key upload karo, private key sambhalo
4.
Create hone ke baad public IP se SSH:
bash
ssh -i ~/Downloads/ssh-key.key ubuntu@<VM_PUBLIC_IP>
"Out of capacity" aaye to dusra availability domain ya 1 OCPU / 6 GB try karo.
Koi inbound port kholne ki zaroorat nahi — bot khud Telegram se long polling karta hai.
Oracle idle Always Free instance ko 7 din baad reclaim kar sakta hai (CPU/network/memory
teeno 20% se neeche rahein to) — .env aur data/ ka backup rakho.
Step 3 — Files server par le jao
Apne laptop se:
bash
scp -i ~/Downloads/ssh-key.key -r opencode-telegram-bot ubuntu@<VM_PUBLIC_IP>:~/
Step 4 — opencode install karo (VM par)
bash
curl -fsSL https://opencode.ai/install | bash
# shell dobara kholo ya:
export PATH="$HOME/.opencode/bin:$PATH"
opencode --version
opencode models | head        # free models dikhne chahiye
Agar installer fail ho:
bash
sudo apt-get install -y nodejs npm
npm install -g opencode-ai
Step 5 — .env banao
bash
cd ~/opencode-telegram-bot
cp .env.example .env
nano .env
Kam se kam ye do line bharo:
code
BOT_TOKEN=123456789:AA...
ACCESS_CODE=koi-lamba-random-code
OPENCODE_WORKDIR wahi folder do jisme tumhara project rakha hai, jaise
/home/ubuntu/opencode-workspace.
Step 6 — Bot start karo
A) systemd (recommended, bina Docker)
bash
cd ~/opencode-telegram-bot
chmod +x deploy/install.sh
./deploy/install.sh
Script venv banata hai, dependencies install karta hai, service enable karta hai.
Log: tail -f ~/opencode-telegram-bot/bot.log
B) Docker
bash
sudo apt-get install -y docker.io docker-compose-v2
cd ~/opencode-telegram-bot
docker compose up -d --build
docker compose logs -f
C) Seedha test (debug ke liye)
bash
cd ~/opencode-telegram-bot
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python bot.py
Step 7 — Telegram par test
1.
Bot ko kholo → /start YOUR_CODE
2.
/free → koi free model tap karo
3.
hello, tum kaun ho? bhejo → jawab aayega
4.
/status → model + session id dikhega
5.
/new → naya session, /exit → session band
4. Free models — sach kya hai
•
opencode models | grep free se live list dekho. Bot ki /free bhi yahi list
  dikhata hai (10 min cache).
•
Ye offers "limited time" hote hain: model aate-jaate rehte hain, kabhi paid
  ho jate hain. Isliye list hard-code na karo.
•
Data terms model ke hisaab se alag hain. Zero-retention wale (jaise
  glm-5.3-flash-free, deepseek-v4.1-flash-free) real code ke liye theek hain;
  stealth / trial models (jaise big-pickle, Nemotron trial endpoints) ko public
  samjho — unka data improve/train ke liye ja sakta hai.
•
Private/proprietary repo par kaam kar rahe ho to sirf zero-retention models
  chuno, ya OPENCODE_DISABLE_FREE_MODELS jaisa client-side filter use karo.
•
Free models ke rate limits published nahi hain; heavy use par 429 aa sakta hai.
5. Settings (.env)
Variable
Default
Matlab
BOT_TOKEN
—
zaroori, BotFather ka token
ACCESS_CODE
—
zaroori, /start ka secret
ALLOWED_USER_IDS
khali
sirf in Telegram ids ko allow (comma separated)
OPENCODE_WORKDIR
~/opencode-workspace
opencode isi folder me kaam karega
OPENCODE_BIN
opencode
binary ka naam ya poora path
DEFAULT_MODEL
khali
shuruaati model, jaise opencode/glm-5.3-flash-free
DEFAULT_THINKING
default
default / low / medium / high
AUTO_APPROVE
true
--auto: permission prompts auto-approve (headless ke liye chahiye)
RUN_TIMEOUT
900
ek prompt ka max seconds
OPENCODE_VARIANT_STYLE
auto
hash = model#high (v2), flag = --variant (v1)
STATE_DB
./data/state.db
session/model state
WEBHOOK_URL
khali
khali = long polling. Host ka HTTPS URL do to webhook mode (Render/Koyeb jaise PaaS ke liye)
PORT
8080
webhook server ka port (Render khud set karta hai)
WEBHOOK_SECRET
khali
webhook ko protect karne wala random string
5b. Webhook mode (free PaaS jaise Render ke liye)
Default me bot long polling karta hai (VPS/Oracle/PC ke liye best). Free PaaS
15 min idle par app ko sula deti hai, aur polling bot sone ke baad wapas nahi
uthta — isliye WEBHOOK_URL set karte hi bot webhook mode me chala jata hai:
•
POST /webhook — Telegram ka update. Bot 200 turant lauta ke update queue me
  daal deta hai (5-10 min ke agent run par Telegram dobara bhejta rehta hai,
  turant ack na ho to kaam duplicate hota hai).
•
GET /health — {"status":"ok","version":"1.2.0"}. Render ka health check isi par.
•
WEBHOOK_SECRET set ho to galat secret par 403.
Render par steps SERVER-OPTIONS.md ke Step 5 me hain; render.yaml project me hai.
5c. GitHub Actions par free (card ke bina)
Project me do workflow hain:
File
Kaam
.github/workflows/ci.yml
har push/PR par chaaron test suites + YAML check (Python 3.10 aur 3.12)
.github/workflows/bot.yml
bot ko GitHub ke runner par chalata hai — har 6 ghante me ek job, ~5h 40m tak
Setup:
1.
Repo public banao (private me mahine ke 2,000 Actions minutes hain; ye bot ~43,000 min maangta hai — public repo ke minutes free hain).
2.
Settings → Secrets and variables → Actions → BOT_TOKEN, ACCESS_CODE (aur chaho to ALLOWED_USER_IDS).
3.
Actions tab → bot workflow → Run workflow (pehla run manual, phir cron khud chalayega).
Kaise chalta hai: timeout --signal=INT 20400 python bot.py — 5h 40m baad bot gracefully band hota hai, data/state.db cache me save hota hai, aur agla cron use restore karke wahi session continue karta hai.
opencode kis repo par kaam karega
Actions ka runner har run par naya hota hai, isliye project repo har run clone hota hai:
Secret / variable
Kaam
PROJECT_REPO
user/repo — opencode isi repo me kaam karega (workspace/). Khali = koi project nahi
PROJECT_TOKEN
PAT (repo scope) — sirf private ya dusre account ke repo ke liye; public/same repo ke liye khali
AUTO_PUSH (Repository variable, secret nahi)
true = changes wapas us repo me commit + push ho jayein
AUTO_PUSH set na ho to kuch bhi push nahi hota — bot jo bhi badla wo bot-changes.patch artifact me milta hai (Actions run → Artifacts). Pehle patch dekh lo, phir AUTO_PUSH=true karo.
code
PROJECT_REPO = shivam/my-project      (secret)
AUTO_PUSH    = false                  (variable, shuru me aisa hi rakho)
Honest limits (pehle padh lo):
•
Har 6 ghante me ~15-20 min ka gap — us dauran bot offline rehta hai.
•
Har run me npm install -g opencode-ai hota hai, to start hone me ~1-2 min lagte hain.
•
GitHub 60 din tak repo me koi activity na ho to scheduled workflow disable kar deta hai — mahine me ek commit ya manual run kar dena.
•
GitHub ki Actions policy kehti hai ki Actions sirf project ke build/test/deploy ke liye use karo, kisi bhi unrelated 24x7 kaam ke liye nahi — personal bot isi grey area me aata hai. Account par bharosa hai to hi ye rasta chuno; warna Termux/laptop safe hai.
•
Secrets safe rehte hain (log me mask hote hain), par repo public hoga — code sab dekh sakte hain, .env kabhi commit mat karo.
•
AUTO_PUSH=true ka matlab hai bot bina poochhe tumhare repo me commit kar sakta hai — main par sidha push karne ke bajaye alag branch use karo, ya patch review karo.
•
Runner par opencode ek normal process hai — wo workspace/ ke bahar bhi padh sakta hai, aur job ke env vars (jaise BOT_TOKEN) bhi usi process ko dikhte hain. --auto ka matlab bina permission shell commands. Isliye bot ko aise machine par na chalao jahan bank/keys ho; dedicated runner, container ya phone rakho.
6. Troubleshooting
Problem
Kya karo
Bot reply nahi karta
tail -f bot.log. Conflict: terminated by other getUpdates = ek hi token par do bot chal rahe hain, dusra band karo
❌ BOT_TOKEN galat ya revoke ho chuka hai
@BotFather → /mybots → API Token → naya token; .env/secret/env update karke restart
❌ Telegram ka jawab samajh nahi aaya
Beech me proxy/firewall/captive portal. Server par curl -I https://api.telegram.org chalao
opencode: command not found
export PATH="$HOME/.opencode/bin:$PATH" aur systemd file me Environment=PATH=... check karo
❌ OpenCode se jawab nahi aaya
Message me error hi likha hota hai. Auth/quota issue ho to opencode run "hi" manually VM par chala ke dekho
Model list khali
opencode models manually chalao; network/DNS ya install ka issue
Har message par model galat
/model se set karo, ya .env me DEFAULT_MODEL
Thinking ka asar nahi
Sirf reasoning-capable models par lagta hai; baaki chup-chaap ignore karte hain
403 FreeTierError
Free models sirf OpenCode client ke andar chalta hai — bot ko opencode run hi chalana hoga (yahi karta hai). Raw API/curl se free model nahi chalega
Reply 2-3 message me toota
Normal: Telegram limit 4096 chars, bot tod ke bhejta hai
Timeout
RUN_TIMEOUT badhao, ya chhota prompt
Log dekho:
bash
sudo systemctl status opencode-bot
tail -n 100 ~/opencode-telegram-bot/bot.log
7. Security (padhna zaroori)
•
AUTO_APPROVE=true ka matlab hai OpenCode bina poochhe files edit kar sakta hai
  aur shell commands chala sakta hai, OPENCODE_WORKDIR ke andar. Isliye:
•
ACCESS_CODE lamba rakho, kisi ko na do.
•
ALLOWED_USER_IDS set karo taaki sirf tumhara Telegram account chale.
•
Bot ko dedicated folder/container me chalao, poore home directory par nahi.
•
Bahut zyada risk lene ki zaroorat nahi ho to AUTO_APPROVE=false — par phir
    headless run permission par atak sakta hai.
•
Bot token aur .env kabhi git me commit na karo (.gitignore me .env,
  data/, bot.log, .venv/ already hai).
•
Code leak/rotate: @BotFather → /revoke se token badal do.
8. Update karna
bash
cd ~/opencode-telegram-bot
git pull                # ya nayi zip extract karo
./.venv/bin/pip install -r requirements.txt
sudo systemctl restart opencode-bot
9. Tests
Asli opencode, API key ya Telegram token ke bina chalte hain:
bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python tests/test_helpers.py    # parsing, chunking, args building
./.venv/bin/python tests/test_stream.py     # fake opencode binary se real subprocess run
./.venv/bin/python tests/test_commands.py   # /start gate, auth guard, model/thinking
./.venv/bin/python tests/test_webhook.py    # webhook: 200/403/400, /health, handler tak update
10. Files
code
bot.py                     poora bot (single file)
requirements.txt
.env.example               settings ka template
SERVER-OPTIONS.md          free server comparison + setup (Oracle / Northflank / GCP / Termux)
Dockerfile                 opencode + node + bot
docker-compose.yml
render.yaml                Render free (webhook mode) blueprint
.github/workflows/ci.yml   push/PR par tests
.github/workflows/bot.yml  bot ko GitHub Actions par chalane wali schedule workflow
deploy/install.sh          Ubuntu par one-shot setup
deploy/opencode-bot.service systemd unit
tests/                     offline tests
.gitignore
