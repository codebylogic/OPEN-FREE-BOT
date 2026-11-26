# Free server options — **bina credit card** (Nov 2026)

Aapke paas card nahi hai, to ye doc sirf un options par hai jo **bina card** shuru
ho sakte hain. Sab limits provider ke apne pages se check kiye gaye hain.

---

## 0. Pehle sach: card ke bina kya band ho jata hai

| Option | Status |
| --- | --- |
| Oracle Cloud Always Free (2 OCPU / 12 GB ARM) | ❌ Card verification chahiye (charge nahi hota, par card mandatory) |
| Google Cloud e2-micro | ❌ Billing account = card |
| Koyeb free | ❌ Signup par card, $29 ka temporary hold |
| Hugging Face Spaces (Docker) | ❌ Ab Docker/Gradio Space banane ke liye **paid plan** chahiye — sirf Static Spaces free hain |
| AWS Free Tier | ❌ Card + sirf 6 mahine / $200 credit |
| Railway / Fly.io trial | ❌ Trial ke baad card |

Yani "bada cloud free tier" sab card maangta hai. Card-free me teen asli raste
bachte hain: **apna machine**, **Termux (phone)**, aur **do PaaS jo card nahi
maangte** — Northflank aur Render. Neeche teeno ka poora tareeka hai.

---

## 1. Is bot ko kitna chahiye (yaad rahe)

| Cheez | Kitna |
| --- | --- |
| RAM | Bot ~70 MB, `opencode` (Node) chalte waqt ~300-700 MB → **1 GB aaram, 512 MB tight** |
| Disk | ~2-3 GB (Node + opencode + repo) |
| CPU | Bahut kam |
| Network | Koi inbound port nahi (polling) **ya** ek HTTPS URL (webhook) |

---

## 2. Card-free options — ranked

| Option | Kya milta hai | 24x7? | Verdict |
| --- | --- | --- | --- |
| **Apna laptop / PC** | Sab kuch, apni RAM | ❌ Jab tak on hai | ✅ **Sabse pehle yahi karo** — 10 min me bot live, koi signup nahi |
| **Android + Termux** | Phone ki RAM/CPU | ✅ Charger par | ✅ Purana phone pada hai to best "free 24x7" |
| **Northflank Sandbox** | $20/month credit, 2 services, **always-on, no sleeping**, Dockerfile se build | ✅ | ✅ **Best cloud bet** — pricing page "no card needed" kehta hai (billing docs me card likha hai, signup par pata chalega) |
| **Render free** | 512 MB container, free HTTPS URL, no card (free services ke liye) | ⚠️ 15 min idle par sleep | ⚠️ **Webhook mode me** chal jayega; 512 MB me opencode tight |
| **GitHub Actions** (public repo) | Free runners, har 6 ghante me ek job (~5h 40m) | ⚠️ Har 6h me ~20 min gap | ✅ Card-free, par GitHub policy ka grey area |
| **GitHub Codespaces** | 2-core, 60 ghante/month free | ❌ | ✅ Sirf testing/experiment ke liye |
| Back4App / FPS.ms / FadeHost | 128-256 MB | ✅ | ❌ `opencode` ke liye RAM kam |
| PythonAnywhere free | 1 web app | ❌ | ❌ Subprocess/CPU limits |

---

## 3. ✅ Step 1: Apne laptop/PC par abhi chalao (0 signup)

Ye pehle karo — bot ka poora flow (code, model, session) verify ho jayega.

```bash
# Linux / macOS, ya Windows par WSL2 Ubuntu
curl -fsSL https://opencode.ai/install | bash
export PATH="$HOME/.opencode/bin:$PATH"
opencode models | head          # free models dikhne chahiye

cd opencode-telegram-bot
cp .env.example .env
nano .env                       # BOT_TOKEN aur ACCESS_CODE bharo
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python bot.py
```

Telegram me `/start YOUR_CODE` → `/free` → model tap → `hello` bhejo.
Laptop band = bot band, par config 100% same hai jo aage cloud par chalega.

---

## 4. ✅ Step 2: Northflank Sandbox (card-free always-on ka best chance)

Always-on, no sleeping — polling mode hi theek hai, `WEBHOOK_URL` khali chhodo.

1. Project ko GitHub par push karo (**private repo chalega**, `.env` push mat karo).
2. https://app.northflank.com → GitHub se signup.
   - Agar card maange to ruk jao → Render wala Step 5 try karo.
   - Pricing page "No card needed" kehta hai, isliye pehle isi ko try karna worth hai.
3. **Create project** → **Create service → Build from repo** → apna repo:
   - Build type: **Dockerfile**, path `Dockerfile`
4. **Compute plan:** 0.5 vCPU / 1 GB (nf-compute-50, ~$12/month — $20 credit me fit).
5. **Environment variables** (secret group):
   ```
   BOT_TOKEN=...
   ACCESS_CODE=...
   DEFAULT_MODEL=opencode/glm-5.3-flash-free
   OPENCODE_WORKDIR=/workspace
   STATE_DB=/app/data/state.db
   AUTO_APPROVE=true
   ```
   `WEBHOOK_URL` **mat** daalo (khali = polling mode).
6. **Volumes:** `/app/data` (1 GB) aur `/workspace` (5 GB) — warna restart par
   session/model state udd jayega.
7. Deploy → Logs me `ready v1.1.0 | workdir=/workspace ...` → Telegram test.

---

## 5. ⚠️ Step 3: Render free (no card) — webhook mode

Render free service 15 min bina traffic ke baad sleep ho jati hai. Polling bot
sone ke baad wapas nahi uthta, isliye bot me **webhook mode** add kiya gaya hai:
Telegram message ko HTTPS par bhejta hai, Render jagta hai, kaam chalta hai.

**Bot ke andar kya hota hai:** webhook par 200 turant lauta diya jata hai aur
update queue me chala jata hai — warna 5-10 min chalne wale agent run par
Telegram dobara bhejta rehta hai aur kaam duplicate hota hai.

1. Repo GitHub par push karo (project me `render.yaml` already hai).
2. https://render.com → signup (GitHub se, free plan, no card).
3. **New → Blueprint** → apna repo chuno → `render.yaml` auto-detect.
4. Pehla deploy ke baad Render ek URL dega, jaise `https://opencode-bot-xxxx.onrender.com`.
5. **Environment** me `WEBHOOK_URL` = wahi URL (bina trailing slash) daalo, aur
   `WEBHOOK_SECRET` = koi lamba random string. Phir **Manual Deploy → Restart**.
6. Health check `/health` hai — Render dashboard me green dikhna chahiye.
7. Telegram me `/start YOUR_CODE`.

**Honest caveats:**
- **512 MB RAM** — `opencode` chalte waqt OOM ho sakta hai. Logs me `Killed` dikhe
  to Render free is bot ke liye kaafi nahi; Northflank ya apna PC use karo.
- **Cold start:** 15 min idle ke baad pehla message ~30-60 s lag sakta hai.
- **Disk ephemeral:** restart par `data/state.db` chala jayega → `/start` dobara
  karna padega (model/session reset). Normal hai.
- **Build time:** Dockerfile opencode install karta hai, to build 3-6 min le sakta hai.

Polling mode chahiye (VPS/Oracle/PC) to `.env` me `WEBHOOK_URL` khali chhod do —
bot khud `getUpdates` par chala jayega.

---

## 5b. ✅ Step 3b: GitHub Actions (public repo, card-free)

Project me `.github/workflows/bot.yml` already hai: har 6 ghante me job chalti hai,
bot ~5h 40m chal ke gracefully band hota hai, aur state `actions/cache` me save
hota hai. Tests ke liye `ci.yml`.

1. Repo **public** karo (private me 2,000 min/month free hain, bot ~43,000 min maangta hai).
2. Settings → Secrets and variables → Actions: `BOT_TOKEN`, `ACCESS_CODE`.
3. Actions → **bot** → **Run workflow**.

**Sach:** har 6 ghante me ~20 min downtime, har run me 1-2 min install, aur GitHub
ki policy Actions ko "project ke build/test/deploy" tak seemit rakhti hai — personal
bot us grey area me aata hai. Account risk nahi lena to laptop/Termux better hai.

---

## 6. ✅ Step 4: Android + Termux (bina card, sach me 24x7)

Purana phone charger par laga do — free mini-server.

```bash
# F-Droid se Termux install karo (Play Store wala purana hai)
pkg update && pkg install python nodejs git openssh -y
curl -fsSL https://opencode.ai/install | bash   # ya: npm i -g opencode-ai
export PATH="$HOME/.opencode/bin:$PATH"
opencode --version

# project copy karo (git clone ya scp), phir:
cd opencode-telegram-bot
cp .env.example .env && nano .env
pip install -r requirements.txt
termux-wake-lock          # background me chalta rahe
python bot.py
```

Settings me battery optimisation off karo, phone charging par rakho.

---

## 7. Kya chunna hai — seedha jawab

1. **Aaj:** laptop/PC par chalao, bot verify karo (Step 3).
2. **24x7 free chahiye:** Northflank try karo (Step 4). Card maange to Render
   webhook mode (Step 5) — 512 MB me OOM ho to Termux (Step 6).
3. **Baad me card mila:** Oracle Cloud Always Free (2 OCPU / 12 GB) sabse best
   hai — `README.md` ka Step 2 wahi hai, config badalne ki zaroorat nahi.

Kisi bhi host par `.env` aur `data/` ka backup rakho — free tiers kabhi bhi
badal sakte hain.
