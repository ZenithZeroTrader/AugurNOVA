import feedparser
import requests
import os
import json
import hashlib
import re
from datetime import datetime, timedelta, timezone

# --------------------------------------------------
# AUGURNOVA - GOLD MODE v1.7 (ข่าวเท่านั้น)
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
    'https://www.investing.com/rss/news_25.rss',
]

SEEN_FILE = 'seen_gold_v2.json'
TH_TZ = timezone(timedelta(hours=7))


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
    s = load_json(SEEN_FILE)
    return set(s) if s else set()


def article_id(entry):
    raw = entry.get('link', '') or entry.get('title', '')
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def find_words(text, words):
    return [w for w in words if re.search(r'\b' + re.escape(w), text)]


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

    save_json(SEEN_FILE, list(seen)[-500:])

    now_th = datetime.now(TH_TZ)
    time_str = now_th.strftime("%d/%m/%Y %H:%M")

    if not alerts or total_impact < 15:
        print("No strong gold news. Market calm.")
        return

    if total_impact >= 60:
        level = "🚨 CRITICAL พายุใหญ่สุดขั้ว"
    elif total_impact >= 30:
        level = "️ HIGH พายุเข้า"
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

    action = {
        ('up', 'BALANCED'): "มอง Buy เมื่อชนโซนของคุณ",
        ('up', 'CROWDED_BUY'): "ขึ้นได้แต่ระวังเขย่าลงก่อน รอ sweep จบค่อย Buy",
        ('up', 'CROWDED_SELL'): "เชื้อ squeeze เพียบ ทางขึ้นอาจแรง มอง Buy ตอนย่อ",
        ('down', 'BALANCED'): "มอง Sell เมื่อชนโซนของคุณ",
        ('down', 'CROWDED_SELL'): "ลงได้แต่ระวังดีดขึ้นก่อน รอเขย่าจบค่อย Sell",
        ('down', 'CROWDED_BUY'): "เชื้อล้างพอร์ตเพียบ ทางลงอาจแรง มอง Sell ตอนดีด",
    }.get((direction, 'BALANCED'), "สองแรงดึง รอแท่งยืนยัน")

    msg = f"‍♂️ AUGURNOVA \n{level} | Score {total_impact}\n{dir_txt}\n🧠 คำตัดสิน : {action}\n━━━━━━\n"
    
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
        msg += f"{i}. {title} {' | '.join(tags)}\n   {link}\n"
    
    msg += f"━━━━━━\n⏰ {time_str} | 💡 ตั้ง SL เสมอ"

    send_telegram(msg)
    print("Alert sent! Impact:", total_impact)


if __name__ == "__main__":
    scan_news()
