import feedparser
import requests
import os
import json
import hashlib
import re
from datetime import datetime, timedelta, timezone

# --------------------------------------------------
# AUGURNOVA - GOLD MODE v1.7 (3 เกียร์ เริ่มที่ 15)
# "นักพยากรณ์ผู้จับจังหวะก่อนทองระเบิด"
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
    try:
        r = requests.get('https://www.okx.com/api/v5/market/trades',
                         params={'instId': 'PAXG-USDT', 'limit': '300'},
                         headers={'User-Agent': feedparser.USER_AGENT},
                         timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if not data:
                print("Sentiment okx: ข้อมูลว่าง")
                return None
            buy = sum(float(t.get('sz', 0)) for t in data if t.get('side') == 'buy')
            sell = sum(float(t.get('sz', 0)) for t in data if t.get('side') == 'sell')
            total = buy + sell
            if total <= 0:
                return None
            lp = round(100 * buy / total)
            print("Sentiment via: okx flow ->", (lp, 100 - lp))
            return (lp, 100 - lp)
        print("Sentiment okx: HTTP", r.status_code)
    except Exception as e:
        print("Sentiment okx error:", e)
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
        return "👥 Flow : -"
    lp, sp = senti
    if state == 'CROWDED_BUY':
        return f"👥 Flow : buy แออัด {lp}%!"
    if state == 'CROWDED_SELL':
        return f"👥 Flow : sell แออัด {sp}%!"
    return f"👥 Flow : สมดุล (ซื้อ{lp}/ขาย{sp})"


def action_line(direction, state):
    v = {
        ('up', 'BALANCED'): "มอง Buy เมื่อชนโซนของคุณ",
        ('up', 'CROWDED_BUY'): "ขึ้นได้แต่ระวังเขย่าลงก่อน รอ sweep จบค่อย Buy",
        ('up', 'CROWDED_SELL'): "เชื้อ squeeze เพียบ ทางขึ้นอาจแรง มอง Buy ตอนย่อ",
        ('down', 'BALANCED'): "มอง Sell เมื่อชนโซนของคุณ",
        ('down', 'CROWDED_SELL'): "ลงได้แต่ระวังดีดขึ้นก่อน รอเขย่าจบค่อย Sell",
        ('down', 'CROWDED_BUY'): "เชื้อล้างพอร์ตเพียบ ทางลงอาจแรง มอง Sell ตอนดีด",
    }.get((direction, state), "สองแรงดึง รอแท่งยืนยัน")
    return "🧠 คำตัดสิน : " + v


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
    time_str = now_th.strftime("%d/%m/%Y %H:%M")

    # ---------- CONTRARIAN ----------
    if not alerts and senti and state in ('CROWDED_BUY', 'CROWDED_SELL') \
            and (senti[0] >= EXTREME or senti[0] <= 100 - EXTREME):
        last = load_json(CROWD_FILE)
        if last != state:
            save_json(CROWD_FILE, state)
            lp, sp = senti
            if state == 'CROWDED_BUY':
                msg = ("🧙‍♂️ AUGURNOVA 🥇 CONTRARIAN\n"
                       f"👥 Flow : buy แออัด {lp}% (ไม่มีข่าวหนุน)\n"
                       "🧠 คำตัดสิน : ระวังทุบลงกิน stop → มอง Sell ตอนดีด\n")
            else:
                msg = ("🧙‍️ AUGURNOVA  CONTRARIAN\n"
                       f"👥 Flow : sell แออัด {sp}% (ไม่มีข่าวกด)\n"
                       "🧠 คำตัดสิน : ระวังดีดขึ้นกิน stop → มอง Buy ตอนย่อ\n")
            msg += "━━━━━━\n⏰ " + time_str + " | 💡 ตั้ง SL เสมอ"
            send_telegram(msg)
            print("Contrarian alert sent!")
            return
    save_json(CROWD_FILE, state if state else 'NONE')

    # ---------- โหมดปกติ (ส่งเฉพาะ Score >= 15) ----------
    if not alerts or total_impact < 15:
        print("No strong gold news. Market calm.")
        return

    if total_impact >= 60:
        level = "🚨 CRITICAL พายุใหญ่สุดขั้ว"
    elif total_impact >= 30:
        level = "⚠️ HIGH พายุเข้า"
    else:
        level = "⚡ MEDIUM ข่าวแรง"

    if total_up - total_down >= 10:
        direction = 'up'
        dir_txt = "📈 ขึ้น : แรงซื้อปลอดภัย/dovish นำ"
    elif total_down - total_up >= 10:
        direction = 'down'
        dir_txt = "📉 ลง : แรงกดดันดอกเบี้ย/ดอลลาร์"
    else:
        direction = 'mixed'
        dir_txt = "↔️ นิ่ง : สองแรงดึง"

    msg = "🧙‍♂️ AUGURNOVA 🥇\n"
    msg += f"{level} | Score {total_impact}\n"
    msg += dir_txt + "\n"
    msg += crowd_label(state, senti) + "\n"
    msg += action_line(direction, state) + "\n"
    msg += "━━━━━━\n"
    for i, (impact, title, link, g, hav, dov, hawk) in enumerate(alerts[:3], 1):
        tags = []
        if g:
            tags.append("🥇 " + ", ".join(g))
        if hav:
            tags.append("⬆️ " + ", ".join(hav))
        if dov:
            tags.append("🕊️ " + ", ".join(dov))
        if hawk:
            tags.append("⬇️ " + ", ".join(hawk))
        msg += f"{i}. {title} {' | '.join(tags)}\n"
        msg += f"   {link}\n"
    msg += "━━━━━━\n"
    msg += "⏰ " + time_str + " | 💡 ตั้ง SL เสมอ"

    send_telegram(msg)
    print("Alert sent! Impact:", total_impact)


if __name__ == "__main__":
    scan_news()
