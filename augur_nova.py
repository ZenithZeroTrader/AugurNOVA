import feedparser
import requests
import os
import json
import hashlib
from datetime import datetime, timedelta, timezone

# --------------------------------------------------
# AUGURNOVA Phase 1 : News Panic Detection
# "นักพยากรณ์ผู้จับจังหวะก่อนตลาดระเบิด"
# --------------------------------------------------

feedparser.USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ---------- คลังคำศัพท์ความกลัว (ปรับแต่งได้) ----------
CRITICAL_WORDS = ['war', 'crash', 'emergency', 'default', 'collapse',
                  'bankruptcy', 'attack', 'invasion']
HIGH_WORDS = ['recession', 'hike', 'sanction', 'crisis', 'panic',
              'inflation', 'tariff', 'sell-off']
MEDIUM_WORDS = ['slowdown', 'warning', 'uncertainty', 'fear', 'concern']

# ---------- แหล่งข่าว (RSS ฟรี) ----------
RSS_FEEDS = [
    'https://www.forexlive.com/feed/',
    'https://www.fxstreet.com/rss',
    'https://www.investing.com/rss/news_25.rss',
]

SEEN_FILE = 'seen_news.json'
TH_TZ = timezone(timedelta(hours=7))  # เวลาไทย


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


def calculate_score(text):
    score = 0
    found = []
    t = text.lower()
    for w in CRITICAL_WORDS:
        if w in t:
            score += 10
            found.append('🔴 ' + w)
    for w in HIGH_WORDS:
        if w in t:
            score += 5
            found.append('🟠 ' + w)
    for w in MEDIUM_WORDS:
        if w in t:
            score += 2
            found.append('🟡 ' + w)
    return score, found


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
    total_score = 0

    for feed_url in RSS_FEEDS:
        try:
            print("Scanning:", feed_url)
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:15]:
                aid = article_id(entry)
                if aid in seen:
                    continue  # ข้ามข่าวที่เคยแจ้งแล้ว (กันแจ้งเตือนซ้ำ)
                seen.add(aid)

                title = entry.get('title', '')
                link = entry.get('link', '')
                score, found = calculate_score(title)
                if score > 0:
                    total_score += score
                    alerts.append((score, title, link, found))
        except Exception as e:
            print("Feed error:", feed_url, e)

    save_seen(seen)

    if not alerts or total_score < 5:
        print("No new panic news. Market calm.")
        return

    if total_score >= 25:
        level = "🚨 CRITICAL - ตลาดแพนิกหนักมาก! ระวังกราฟกระชากแรง"
    elif total_score >= 10:
        level = "⚠️ HIGH - ข่าวร้ายถี่ผิดปกติ เตรียมตัวให้พร้อม"
    else:
        level = "⚡ MEDIUM - เริ่มมีข่าวร้าย เฝ้าระวังใกล้ชิด"

    now_th = datetime.now(TH_TZ)
    msg = "🧙‍️ AUGURNOVA ALERT\n"
    msg += level + "\n"
    msg += f"Fear Score: {total_score}\n"
    msg += "━━━━━━━━━━━━━━━\n"
    for i, (score, title, link, found) in enumerate(alerts[:5], 1):
        msg += f"{i}. {title}\n"
        msg += f"   คำที่เจอ: {', '.join(found)} (score {score})\n"
        msg += f"   {link}\n"
    msg += "━━━━━━━━━━━━━━━\n"
    msg += "⏰ " + now_th.strftime("%d/%m/%Y %H:%M") + " (เวลาไทย)"

    send_telegram(msg)
    print("Alert sent! Score:", total_score)


if __name__ == "__main__":
    scan_news()
