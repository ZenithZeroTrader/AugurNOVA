import feedparser
import requests
import os
import json
import hashlib
import re
from datetime import datetime, timedelta, timezone

# --------------------------------------------------
# AUGURNOVA - GOLD MODE v1.2.5 (Phase 2: Sentiment)
# "นักพยากรณ์ผู้จับจังหวะก่อนทองระเบิด"
# + วัดความแออัดด้วย Funding Rate (fapi/OKX) สดจริง
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

CROWDED = 0.03    # funding % ที่ถือว่าแออัด
EXTREME = 0.06    # funding % ที่ถือว่าสุดขั้ว


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


def fetch_funding():
    """ดึง Funding Rate ของ PAXG (ทองโทเคน) = ตัววัดความแออัดของมวลชน"""
    # ประตู 1: Binance fapi (เกิดมาเพื่อบอท ไม่คืน 202)
    try:
        r = requests.get('https://futures.binance.com/fapi/v1/premiumIndex',
                         params={'symbol': 'PAXGUSDT'},
                         headers={'User-Agent': feedparser.USER_AGENT},
                         timeout=15)
        if r.status_code == 200:
            rate = float(r.json().get('lastFundingRate', 0)) * 100
            print("Sentiment via: binance funding ->", round(rate, 4), "%")
            return rate
        print("Sentiment binance funding: HTTP", r.status_code)
    except Exception as e:
        print("Sentiment binance funding error:", e)

    # ประตู 2: OKX
    try:
        r = requests.get('https://www.okx.com/api/v5/public/funding-rate',
                         params={'instId': 'PAXG-USDT-SWAP'},
                         headers={'User-Agent': feedparser.USER_AGENT},
                         timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                rate = float(data[0].get('fundingRate', 0)) * 100
                print("Sentiment via: okx funding ->", round(rate, 4), "%")
                return rate
        print("Sentiment okx funding: HTTP", r.status_code)
    except Exception as e:
        print("Sentiment okx funding error:", e)

    print("Sentiment: ทุกประตูปิดสนิท")
    return None


def crowd_state(rate):
    if rate is None:
        return None
    if rate >= CROWDED:
        return 'CROWDED_BUY'
    if rate <= -CROWDED:
        return 'CROWDED_SELL'
    return 'BALANCED'


def crowd_label(state, rate):
    if rate is None:
        return "👥 มวลชน: (ดึงข้อมูลไม่ได้)"
    if state == 'CROWDED_BUY':
        return f"👥 Funding PAXG: +{rate:.4f}% → มวลชนแออัด Long (ยอมจ่ายแพงเพื่อถือซื้อ!)"
    if state == 'CROWDED_SELL':
        return f"👥 Funding PAXG: {rate:.4f}% → มวลชนแออัด Short (ยอมจ่ายแพงเพื่อถือขาย!)"
    return f"👥 Funding PAXG: {rate:+.4f}% → สมดุล (ปกติ ~0.01%)"


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
    rate = fetch_funding()
    state = crowd_state(rate)

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
    if not alerts and rate is not None and abs(rate) >= EXTREME \
            and state in ('CROWDED_BUY', 'CROWDED_SELL'):
        last = load_json(CROWD_FILE)
        if last != state:
            save_json(CROWD_FILE, state)
            if state == 'CROWDED_BUY':
                msg = ("🧙‍️ AUGURNOVA  CONTRARIAN MODE\n"
                       f"Funding พุ่ง +{rate:.4f}% = มวลชนแออัด Long สุดขั้วโดยไม่มีข่าวหนุน\n"
                       "⚠️ Smart Money อาจทุบลงกินสภาพคล่องก่อน\n"
                       "💡 มองหา Sell ตอนดีด / อย่าไล่ Buy\n")
            else:
                msg = ("🧙‍♂️ AUGURNOVA 🥇 CONTRARIAN MODE\n"
                       f"Funding ดิ่ง {rate:.4f}% = มวลชนแออัด Short สุดขั้วโดยไม่มีข่าวกด\n"
                       "⚠️ Smart Money อาจดีดขึ้นกินสภาพคล่องก่อน\n"
                       "💡 มองหา Buy ตอนย่อ / อย่าไล่ Sell\n")
            msg += crowd_label(state, rate) + "\n"
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

    msg = "🧙‍♂️ AUGURNOVA 🥇 GOLD MODE v1.2.5\n"
    msg += level + "\n"
    msg += f"Gold Impact Score: {total_impact}\n"
    msg += dir_txt + "\n"
    msg += crowd_label(state, rate) + "\n"
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
