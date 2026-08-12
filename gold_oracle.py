import feedparser
import requests
import os
import json
import hashlib
from datetime import datetime, timedelta, timezone

# --------------------------------------------------
# AUGURNOVA - GOLD MODE (XAUUSD ONLY)
# "นักพยากรณ์ผู้จับจังหวะก่อนทองระเบิด"
# --------------------------------------------------

feedparser.USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ---------- คำที่บอกว่าข่าวนี้เกี่ยวกับทอง ----------
GOLD_WORDS = ['gold', 'xau', 'bullion', 'precious', 'safe haven', 'safe-haven']

# ---------- คำที่ดันทอง "ขึ้น" (ความกลัว / ความเสี่ยง) ----------
HAVEN_WORDS = ['war', 'attack', 'invasion', 'escalat', 'crisis', 'panic',
               'crash', 'emergency', 'conflict', 'missile', 'tension',
               'recession', 'fear', 'geopolitic', 'bank collapse']

# ---------- คำที่กดทอง "ลง" (ดอกเบี้ยขาขึ้น / ดอลลาร์แข็ง) ----------
HAWK_WORDS = ['rate hike', 'hike', 'hawkish', 'higher rate', 'yields rise',
              'yields climb', 'dollar firm', 'dollar rise', 'strong jobs',
              'tightening', 'fed official', 'rate-cut bets fade']

# ---------- แหล่งข่าว ----------
RSS_FEEDS = [
    'https://www.forexlive.com/feed/',
    'https://www.fxstreet.com/rss',
    'https://www.investing.com/rss/news_25.rss',
    'https://www.kitco.com/rss',
]

SEEN_FILE = 'seen_gold.json'
TH_TZ = timezone(timedelta(hours=7))


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    with open(SEEN_FILE, 'w') as f:
        json.dump(list(seen)[-500:], f)


def article_id(entry):
    raw = entry.get('link', '') or entry.get('title', '')
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def find_words(text, words):
    return [w for w in words if w in text]


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
    total_haven = 0
    total_hawk = 0

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
                hawk_hit = find_words(t, HAWK_WORDS)

                haven_score = len(haven_hit) * 10
                hawk_score = len(hawk_hit) * 10
                bonus = 5 if gold_hit else 0

                impact = haven_score + hawk_score + bonus
                if impact >= 10:
                    total_impact += impact
                    total_haven += haven_score
                    total_hawk += hawk_score
                    alerts.append((impact, title, link, gold_hit, haven_hit, hawk_hit))
        except Exception as e:
            print("Feed error:", feed_url, e)

    save_seen(seen)

    if not alerts:
        print("No gold-related panic news. Market calm.")
        return

    if total_impact >= 30:
        level = "🚨 CRITICAL - ข่าวกระทบทองแรงมาก! ระวังกราฟกระชาก"
    elif total_impact >= 15:
        level = "⚠️ HIGH - ข่าวกระทบทองถี่ผิดปกติ เตรียมตัว"
    else:
        level = "⚡ MEDIUM - เริ่มมีข่าวกระทบทอง เฝ้าจอไว้"

    if total_haven - total_hawk >= 10:
        direction = "📈 เอียง 'ขึ้น' : แรงซื้อสินทรัพย์ปลอดภัยนำ"
    elif total_hawk - total_haven >= 10:
        direction = "📉 เอียง 'ลง' : แรงกดดันดอกเบี้ย/ดอลลาร์นำ"
    else:
        direction = "↔️ 'สองแรงดึง' : ข่าวสวนทางกัน กราฟอาจสวิงแรง"

    now_th = datetime.now(TH_TZ)
    msg = "🧙‍️ AUGURNOVA  GOLD MODE\n"
    msg += level + "\n"
    msg += f"Gold Impact Score: {total_impact}\n"
    msg += direction + "\n"
    msg += "━━━━━━━━━━━━━━━\n"
    for i, (impact, title, link, g, up, dn) in enumerate(alerts[:5], 1):
        msg += f"{i}. {title}\n"
        tags = []
        if g:
            tags.append("🥇 " + ", ".join(g))
        if up:
            tags.append("⬆️ " + ", ".join(up))
        if dn:
            tags.append("⬇️ " + ", ".join(dn))
        msg += "   " + " | ".join(tags) + f" (impact {impact})\n"
        msg += f"   {link}\n"
    msg += "━━━━━━━━━━━━━━━\n"
    msg += "⏰ " + now_th.strftime("%d/%m/%Y %H:%M") + " (เวลาไทย)\n"
    msg += "💡 นี่คือการแจ้งเตือนข้อมูล ไม่ใช่คำสั่งซื้อขาย ตั้ง SL เสมอ"

    send_telegram(msg)
    print("Alert sent! Impact:", total_impact)


if __name__ == "__main__":
    scan_news()
