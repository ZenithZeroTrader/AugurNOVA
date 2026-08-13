import feedparser
import requests
import os
import json
import hashlib
import re
from datetime import datetime, timedelta, timezone

# --------------------------------------------------
# AUGURNOVA - GOLD MODE v1.2.6 (Phase 2: Sentiment)
# "นักพยากรณ์ผู้จับจังหวะก่อนทองระเบิด"
# + Flow มวลชนจากเทรดจริง PAXG (OKX) — ประตูที่กันบอทไม่ได้
# --------------------------------------------------

feedparser.USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GOLD_WORDS = ['gold', 'xau', 'bullion', 'precious', 'safe haven', 'safe-haven']

HAVEN_WORDS = ['war', 'attack', 'invasion', 'escalat', 'crisis', 'panic',
               'crash', 'emergency', 'conflict', 'missile', 'tension',
               'recession', 'fear', 'geopolitic', 'bank collapse']

DOVISH_WORDS = ['cool', 'eases', 'easing', 'soften', 'dovish', 'rate cut',
                'cuts rates', 'cut rates', 'lower rates', 'disinflation',
                'dampens', 'diminishes', 'weakens']

HAWK_WORDS = ['rate hike', 'hike', 'hawkish', 'higher rate', 'yields rise',
              'yields climb', 'dollar firm', 'dollar rise', 'strong jobs',
              'tightening', 'fed official']

RSS_FEEDS = [
    'https://www.forexlive.com/feed/',
    'https://www.fxstreet.com/rss',
    'https://www.investing.com/rss/news_25.rss',
    'https://www.kitco.com/rss',
]

CROWD_FILE = 'seen_crowd.json'
TH_TZ = timezone(timedelta(hours=7))

CROWDED = 70
EXTREME = 75


def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f)


def load_seen():
    s = load_json('seen_gold_v2.json')
    return set(s) if s else set()


def article_id(entry):
    raw = entry.get('link', '') or entry.get('title', '')
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def find_words(text, words):
    return [w for w in words if re.search(r'\b' + re.escape(w), text)]


def fetch_sentiment():
    """วัดแรงบุกของมวลชน: สัดส่วน Taker Buy/Sell จากเทรดล่าสุดของ PAXG (OKX)"""
    try:
        r = requests.get('https://www.okx.com/api/v5/market/trades',
                         params={'instId': 'PAXG-USDT', 'limit': '300'},
                         headers={'User-Agent': feedparser.USER_AGENT},
                         timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if not data:
                print("Sentiment okx: ข้อมูลว่าง (อาจไม่มีคู่ PAXG-USDT)")
                return None
            buy = sum(float(t.get('sz', 0)) for t in data if t.get('side') == 'buy')
            sell = sum(float(t.get('sz', 0)) for t in data if t.get('side') == 'sell')
            total = buy + sell
            if total <= 0:
                print("Sentiment okx: ปริมาณเทรดเป็น 0")
                return None
            lp = round(100 * buy / total)
            sp = 100 - lp
            print("Sentiment via: okx flow ->", (lp, sp))
            return (lp, sp)
        print("Sentiment okx: HTTP", r.status_code)
    except Exception as e:
        print("Sentiment okx error:", e)
    print("Sentiment: ทุกประตูปิดสนิท")
    return None


def crowd_state(long_pct):
    if long_pct is None:
        return None
    if long_pct >= CROWDED:
        return 'CROWDED_BUY'
    if long_pct <= 100 - CROWDED:
        return 'CROWDED_SELL'
    return 'BALANCED'


def crowd_label(state, senti):
    if senti is None:
        return "👥 มวลชน: (ดึงข้อมูลไม่ได้)"
    lp, sp = senti
    name = {'BALANCED': 'สมดุล', 'CROWDED_BUY': 'ฝั่งซื้อบุกหนัก!',
            'CROWDED_SELL': 'ฝั่งขายบุกหนัก!'}.get(state, '-')
    return f"👥 Flow มวลชนทอง (OKX): ซื้อ {lp}% / ขาย {sp}% → {name}"


def combined_verdict(direction, state):
    if state is None:
        return "🧠 คำตัดสิน: ใช้ไบแอสข่าวประกอบโซนของคุณเช่นเดิม (มวลชนไม่พร้อม)"
    v = {
        ('up', 'BALANCED'): "🧠 คำตัดสิน: ทางขึ้นสะอาด มอง Buy ตามเซ็ตอัพของคุณ",
        ('up', 'CROWDED_BUY'): "🧠 คำตัดสิน: ไบแอสขึ้นแต่รถแน่นฝั่ง Buy → ระวังเขย่าลงกิน stop ก่อน ค่อย Buy หลัง sweep จบ หรือลดไซส์",
        ('up', 'CROWDED_SELL'): "🧠 คำตัดสิน: มวลชนถือ Short สวนข่าวขึ้น = เชื้อเพลิง squeeze → ทางขึ้นอาจรุนแรง Buy ตอนย่อ",
        ('down', 'BALANCED'): "🧠 คำตัดสิน: ทางลงสะอาด มอง Sell ตามเซ็ตอัพของคุณ",
        ('down', 'CROWDED_SELL'): "🧠 คำตัดสิน: ไบแอสลงแต่รถแน่นฝั่ง Sell → ระวังดีดขึ้นกิน stop ก่อน ค่อย Sell หลังเขย่าจบ หรือลดไซส์",
        ('down', 'CROWDED_BUY'): "🧠 คำตัดสิน: มวลชนถือ Long สวนข่าวลง = เชื้อเพลิงล้างพอร์ต → ทางลงอาจรุนแรง Sell ตอนดีด",
    }.get((direction, state))
    if v:
        return v
    return "🧠 คำตัดสิน: ข่าวสองแรงดึง รอแท่งยืนยัน โดยดูว่าฝั่งไหนแออัด (ฝั่งนั้นโดนเขย่าก่อน)"


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    try:
        r = requests.post(url, data=payload, timeout=15)
        print("Telegram status:", r.status_code)
    except Exception as e:
        print("Send error:", e)


def scan_news():
    seen = load_seen()
    senti = fetch_sentiment()
    state = crowd_state(senti[0] if senti else None)

    alerts = []
    total_impact = 0
    total_up = 0
    total_down = 0

    for feed_url in RSS_FEEDS:
        try:
            print("Scanning:", feed_url)
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:15]:
                aid = article_id(entry)
                if aid in seen:
                    continue
                seen.add(aid)

                t = entry.get('title', '').lower()
                title = entry.get('title', '')
                link = entry.get('link', '')

                gold_hit = find_words(t, GOLD_WORDS)
                haven_hit = find_words(t, HAVEN_WORDS)
                dovish_hit = find_words(t, DOVISH_WORDS)
                hawk_hit = find_words(t, HAWK_WORDS)

                if dovish_hit:
                    hawk_hit = [w for w in hawk_hit
                                if w not in ('hike', 'rate hike', 'higher rate')]

                up_score = (len(haven_hit) + len(dovish_hit)) * 10
                down_score = len(hawk_hit) * 10
                bonus = 5 if gold_hit else 0

                impact = up_score + down_score + bonus
                if impact >= 10:
                    total_impact += impact
                    total_up += up_score
                    total_down += down_score
                    alerts.append((impact, title, link, gold_hit,
                                   haven_hit, dovish_hit, hawk_hit))
        except Exception as e:
            print("Feed error:", feed_url, e)

    save_json('seen_gold_v2.json', list(seen)[-500:])

    now_th = datetime.now(TH_TZ)
    time_str = now_th.strftime("%d/%m/%Y %H:%M") + " (เวลาไทย)"

    # ---------- โหมด CONTRARIAN ----------
    if not alerts and senti and state in ('CROWDED_BUY', 'CROWDED_SELL') \
            and (senti[0] >= EXTREME or senti[0] <= 100 - EXTREME):
        last = load_json(CROWD_FILE)
        if last != state:
            save_json(CROWD_FILE, state)
            lp, sp = senti
            if state == 'CROWDED_BUY':
                msg = ("🧙‍♂️ AUGURNOVA 🥇 CONTRARIAN MODE\n"
                       f"ฝั่งซื้อบุกหนักสุดขั้ว {lp}% โดยไม่มีข่าวแรงหนุน\n"
                       "⚠️ Smart Money อาจทุบลงกินสภาพคล่องก่อน\n"
                       "💡 มองหา Sell ตอนดีด / อย่าไล่ Buy\n")
            else:
                msg = ("🧙‍️ AUGURNOVA  CONTRARIAN MODE\n"
                       f"ฝั่งขายบุกหนักสุดขั้ว {sp}% โดยไม่มีข่าวแรงกด\n"
                       "⚠️ Smart Money อาจดีดขึ้นกินสภาพคล่องก่อน\n"
                       "💡 มองหา Buy ตอนย่อ / อย่าไล่ Sell\n")
            msg += crowd_label(state, senti) + "\n"
            msg += "━━━━━━━━━━━━━━━\n⏰ " + time_str + "\n"
            msg += "💡 นี่คือการแจ้งเตือนข้อมูล ไม่ใช่คำสั่งซื้อขาย ตั้ง SL เสมอ"
            send_telegram(msg)
            print("Contrarian alert sent!")
            return
    save_json(CROWD_FILE, state if state else 'NONE')

    # ---------- โหมดปกติ ----------
    if not alerts or total_impact < 5:
        print("No gold-related panic news. Market calm.")
        return

    if total_impact >= 30:
        level = "🚨 CRITICAL - ข่าวกระทบทองแรงมาก! ระวังกราฟกระชาก"
    elif total_impact >= 15:
        level = "⚠️ HIGH - ข่าวกระทบทองถี่ผิดปกติ เตรียมตัว"
    else:
        level = "⚡ MEDIUM - เริ่มมีข่าวกระทบทอง เฝ้าจอไว้"

    if total_up - total_down >= 10:
        direction = 'up'
        dir_txt = "📈 เอียง 'ขึ้น' : แรงซื้อสินทรัพย์ปลอดภัย/ dovish นำ"
    elif total_down - total_up >= 10:
        direction = 'down'
        dir_txt = "📉 เอียง 'ลง' : แรงกดดันดอกเบี้ย/ดอลลาร์นำ"
    else:
        direction = 'mixed'
        dir_txt = "↔️ 'สองแรงดึง' : ข่าวสวนทางกัน กราฟอาจสวิงแรง"

    msg = "🧙‍♂️ AUGURNOVA 🥇 GOLD MODE v1.2.6\n"
    msg += level + "\n"
    msg += f"Gold Impact Score: {total_impact}\n"
    msg += dir_txt + "\n"
    msg += crowd_label(state, senti) + "\n"
    msg += combined_verdict(direction, state) + "\n"
    msg += "━━━━━━━━━━━━━━━\n"
    for i, (impact, title, link, g, hav, dov, hawk) in enumerate(alerts[:5], 1):
        msg += f"{i}. {title}\n"
        tags = []
        if g:
            tags.append("🥇 " + ", ".join(g))
        if hav:
            tags.append("⬆️ " + ", ".join(hav))
        if dov:
            tags.append("🕊️ " + ", ".join(dov))
        if hawk:
            tags.append("⬇️ " + ", ".join(hawk))
        msg += "   " + " | ".join(tags) + f" (impact {impact})\n"
        msg += f"   {link}\n"
    msg += "━━━━━━━━━━━━━━━\n"
    msg += "⏰ " + time_str + "\n"
    msg += "💡 นี่คือการแจ้งเตือนข้อมูล ไม่ใช่คำสั่งซื้อขาย ตั้ง SL เสมอ"

    send_telegram(msg)
    print("Alert sent! Impact:", total_impact)


if __name__ == "__main__":
    scan_news()
