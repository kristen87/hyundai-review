#!/usr/bin/env python3
"""
현대카드 앱 리뷰 수집 및 분석 스크립트
- 매주 월요일 실행, 지난 주 데이터 수집
- 수집 소스: 앱스토어, 플레이스토어, 네이버 블로그, 네이버 카페(전체), Brunch,
             디씨인사이드, 뽐뿌, 클리앙, X(트위터), 유튜브
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import sys
from datetime import datetime, timedelta, date
import time
import hashlib
import re
from urllib.parse import quote

# ============================================================
# 설정
# ============================================================

# 워크스페이스 경로를 동적으로 탐색
def find_workspace():
    """현대카드 리뷰 분석 디렉토리 경로 반환"""
    # GitHub Actions 등 CI 환경에서는 현재 디렉토리 사용
    if os.environ.get("CI"):
        return os.path.abspath(".")
    # 로컬 Mac에서는 Documents 폴더 사용
    return os.path.expanduser("~/Documents/현대카드_리뷰분석")

BASE_DIR = find_workspace()
DATA_DIR = os.path.join(BASE_DIR, "data")

# ============================================================
# API 키 설정
# GitHub Actions: 환경변수(Secrets)에서 자동으로 읽어옴
# 로컬 Mac: 아래 값을 직접 입력하세요 (이 파일은 GitHub에 올리지 마세요)
# ============================================================
NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID",     "x6w93pwB4hZcOnLmeEi3")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "btnmtiUL7B")
YOUTUBE_API_KEY     = os.environ.get("YOUTUBE_API_KEY",     "")
NETLIFY_SITE        = os.environ.get("NETLIFY_SITE",        "1486c4a4-e066-49e5-8424-a4b966790288")
NETLIFY_AUTH_TOKEN  = os.environ.get("NETLIFY_AUTH_TOKEN",  "")  # 토큰은 환경변수로만 사용
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
SEEN_IDS_FILE = os.path.join(DATA_DIR, "seen_ids.json")

# 검색 키워드
KEYWORDS = [
    "현대카드 앱",
    "현대카드 후기",
    "현대카드 불만",
    "현대카드 앱 후기",
    "현대카드 앱 추천",
    "현대카드 앱 리뷰",
]

# 현대카드 앱 패키지명 (플레이스토어)
PLAYSTORE_APP_IDS = [
    "com.hyundaicard.appcard",
    "kr.co.hyundaicard.applemembers",
    "com.hyundaicard",
]

# 감성 분석 키워드
POSITIVE_KEYWORDS = [
    # 전반적 긍정
    "좋아", "좋음", "좋다", "좋네", "좋은", "좋고", "괜찮", "나쁘지 않",
    # 편의성
    "편리", "편하", "편함", "편해", "편리하", "간편", "쉽게", "쉽다", "쉬워", "쉬운",
    "직관", "심플", "깔끔", "간결", "빠르", "빠른", "빠름", "신속",
    # 추천/만족
    "추천", "강추", "만족", "만족스", "마음에 들", "마음에드", "흡족", "기대 이상",
    "기대이상", "후회 없", "후회없",
    # 품질/성능
    "훌륭", "최고", "완벽", "완전 좋", "완전좋", "짱", "대박", "굿", "굳",
    "잘 됩", "잘됩", "잘 돼", "잘돼", "잘 되", "잘되", "잘 작동", "정상적",
    "안정적", "안정", "유용", "유용하", "도움",
    # 개선 인식
    "개선됐", "개선되었", "좋아졌", "나아졌", "향상", "업데이트 후 좋",
    "업뎃 후 좋", "이전보다 좋",
    # 혜택/기능
    "혜택", "포인트 좋", "캐시백", "이벤트 좋", "기능이 좋",
    "디자인 좋", "ui 좋", "ux 좋", "인터페이스 좋",
    # 감사/애용
    "감사", "고마", "잘 쓰", "잘쓰", "애용", "즐겨 쓰", "즐겨쓰",
    "계속 쓸", "계속쓸", "오래 쓸", "오래쓸",
    # 슬랭/구어체 긍정
    "개꿀", "꿀이다", "꿀앱", "갓앱", "레전드", "킹받", "존잘",
    # UX/디자인 칭찬
    "잘하는", "잘 하는", "가장 잘", "최고로", "으뜸",
]

NEGATIVE_KEYWORDS = [
    # 오류/버그
    "오류", "에러", "버그", "충돌", "튕", "먹통", "다운", "강제 종료", "강제종료",
    "앱 죽", "앱죽", "앱 꺼", "앱꺼", "앱이 꺼", "재시작", "재부팅",
    "로그인 안", "로그인이 안", "접속 안", "접속이 안", "접속 불가",
    # 성능
    "느리", "느림", "느려", "느린", "버벅", "버벅임", "렉", "랙", "로딩",
    "무거", "배터리 많이",
    # 불편/불만
    "불편", "불편하", "불만", "불만족", "짜증", "짜증나", "화나", "화남",
    "답답", "답답하", "열받", "아쉽", "아쉬운", "아쉬워",
    # 품질 평가
    "최악", "별로", "별루", "최하", "형편없", "한심", "쓰레기", "개악",
    "실망", "실망스", "기대 이하", "기대이하", "못 쓰", "못쓰",
    "쓸모없", "쓸모 없", "필요없", "필요 없",
    # 작동 문제
    "문제", "안 됩", "안됩", "안 돼", "안돼", "안되", "작동 안", "작동안",
    "되질 않", "되지 않", "고장", "불량",
    # 의문/비판
    "왜 이", "왜이", "이게 뭐", "이게뭐", "도대체", "대체 왜", "대체왜",
    "진짜 별로", "진짜별로", "너무 불", "너무불",
    # 혜택/개편 불만
    "혜택 줄", "혜택이 줄", "혜택 없어", "개편 후", "개편후",
    "업데이트 후 나", "업뎃 후 나", "이전이 더",
    # 고객센터
    "연결 안", "연결이 안", "상담 안", "응답 없", "무응답", "처리 안",
    "연결 힘들", "연결이 힘들", "상담 힘들",
    # 어려움/불가능
    "힘들어", "힘들다", "어렵다", "어려워", "불가능", "안 됨", "안됨",
    # 슬랭/구어체 부정
    "그지같", "구리다", "구려", "최구림", "별점 1", "별 1개",
    # 광고/팝업
    "광고 많", "광고가 많", "팝업 많", "팝업이 많",
    # 로그인 유지 문제
    "로그인 풀", "자동 로그인 풀", "로그인이 풀", "계속 풀려", "풀려요", "풀림",
    # 광고/팝업 과다
    "너무 많아", "광고 너무", "너무 많은 광고",
]


# ============================================================
# 유틸리티 함수
# ============================================================

def get_week_range():
    """지난 주 월요일~일요일 날짜 반환"""
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)
    return last_monday, last_sunday

def make_id(source, text, date_str=""):
    content = f"{source}_{text[:60]}_{date_str}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()

def load_seen_ids():
    if os.path.exists(SEEN_IDS_FILE):
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen_ids(seen_ids):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f, ensure_ascii=False)

def analyze_sentiment(text):
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    if pos == 0 and neg == 0:
        # 키워드 미검출 → 진짜 중립
        return "중립"
    if pos > neg:
        return "긍정"
    elif neg > pos:
        return "부정"
    else:
        # 동점(1:1, 2:2 등) → 부정 우선 (불만 표현이 더 명시적인 경향)
        return "부정"

def parse_relative_date(date_str, start_date, end_date):
    """'N일 전', 'YYYY.MM.DD' 등 다양한 날짜 파싱"""
    today = date.today()
    date_str = date_str.strip()
    try:
        if "일 전" in date_str:
            m = re.search(r"(\d+)일 전", date_str)
            if m:
                d = today - timedelta(days=int(m.group(1)))
                return d if start_date <= d <= end_date else None
        elif "시간 전" in date_str or "분 전" in date_str:
            return today if start_date <= today <= end_date else None
        elif "어제" in date_str:
            d = today - timedelta(days=1)
            return d if start_date <= d <= end_date else None
        else:
            for fmt in ["%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"]:
                try:
                    d = datetime.strptime(date_str[:10], fmt).date()
                    return d if start_date <= d <= end_date else None
                except:
                    continue
    except:
        pass
    return None


# ============================================================
# 앱스토어 수집 (iTunes RSS API)
# ============================================================

def collect_appstore_reviews(start_date, end_date, seen_ids):
    collected = []
    print("  앱스토어 앱 ID 탐색 중...")
    try:
        search_url = "https://itunes.apple.com/search?term=현대카드&country=kr&entity=software&limit=20"
        resp = requests.get(search_url, timeout=15)
        data = resp.json()
        app_id = None
        for r in data.get("results", []):
            name = r.get("trackName", "")
            if "현대카드" in name and "DIVE" not in name:
                app_id = r["trackId"]
                print(f"  앱 발견: {name} (ID: {app_id})")
                break

        if not app_id:
            print("  현대카드 앱 ID를 찾지 못했습니다.")
            return collected

        for page in range(1, 11):
            rss_url = f"https://itunes.apple.com/kr/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
            resp = requests.get(rss_url, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            entries = data.get("feed", {}).get("entry", [])
            if not entries or len(entries) <= 1:
                break

            items = entries[1:] if page == 1 else entries
            for entry in items:
                try:
                    content = entry.get("content", {}).get("label", "")
                    title = entry.get("title", {}).get("label", "")
                    rating = entry.get("im:rating", {}).get("label", "")
                    updated = entry.get("updated", {}).get("label", "")[:10]

                    rid = make_id("appstore", content, updated)
                    if rid in seen_ids:
                        continue

                    d = parse_relative_date(updated, start_date, end_date)
                    if d is None:
                        continue

                    collected.append({
                        "id": rid, "source": "앱스토어",
                        "title": title, "content": content,
                        "rating": rating, "date": str(d),
                        "sentiment": analyze_sentiment(content + title),
                        "url": ""
                    })
                    seen_ids.add(rid)
                except:
                    continue
            time.sleep(0.5)

    except Exception as e:
        print(f"  앱스토어 오류: {e}")
    return collected


# ============================================================
# 플레이스토어 수집 (google-play-scraper)
# ============================================================

def collect_playstore_reviews(start_date, end_date, seen_ids):
    collected = []
    try:
        from google_play_scraper import reviews as gp_reviews, Sort

        app_id_used = None
        for pkg in PLAYSTORE_APP_IDS:
            try:
                result, _ = gp_reviews(
                    pkg, lang="ko", country="kr",
                    sort=Sort.NEWEST, count=300
                )
                if result:
                    app_id_used = pkg
                    print(f"  플레이스토어 앱 발견: {pkg}")
                    break
            except:
                continue

        if not app_id_used:
            print("  플레이스토어 앱을 찾지 못했습니다.")
            return collected

        for r in result:
            try:
                review_date = r.get("at")
                if not review_date:
                    continue
                d = review_date.date() if hasattr(review_date, "date") else date.fromisoformat(str(review_date)[:10])
                if not (start_date <= d <= end_date):
                    continue

                text = r.get("content", "")
                date_str = str(d)
                rid = make_id("playstore", text, date_str)
                if rid in seen_ids:
                    continue

                collected.append({
                    "id": rid, "source": "플레이스토어",
                    "title": "", "content": text,
                    "rating": str(r.get("score", "")), "date": date_str,
                    "sentiment": analyze_sentiment(text),
                    "url": ""
                })
                seen_ids.add(rid)
            except:
                continue

    except ImportError:
        print("  google-play-scraper 미설치 — 건너뜀")
    except Exception as e:
        print(f"  플레이스토어 오류: {e}")
    return collected


# ============================================================
# 네이버 블로그 수집 (웹 스크래핑)
# ============================================================

def naver_search(where, keyword, headers):
    """네이버 모바일 검색 결과 파싱"""
    url = (
        f"https://m.search.naver.com/search.naver"
        f"?where={where}&query={quote(keyword)}&start=1&display=30&sort=date"
    )
    resp = requests.get(url, headers=headers, timeout=15)
    return BeautifulSoup(resp.text, "html.parser")

def extract_posts(soup):
    """다양한 셀렉터로 포스트 목록 추출"""
    selectors = [
        ".lst_type li", ".list_item", ".blog_item",
        "li.type01", ".cafe_item", "li[class]",
        ".api_item", ".bx", ".sh_blog_l",
    ]
    for sel in selectors:
        posts = soup.select(sel)
        if posts:
            return posts
    return []

def parse_post(post, source_label, keyword, start_date, end_date, seen_ids):
    """포스트 하나를 파싱해서 dict 반환"""
    try:
        title_el = (post.select_one(".tit_item, .sh_blog_title, .title, [class*='title'], a.result_title")
                    or post.select_one("a"))
        content_el = post.select_one(".dsc_item, .sh_blog_passage, .desc, [class*='dsc'], [class*='desc'], p")
        date_el = post.select_one(".sub_time, .sh_blog_time, .date, [class*='date'], time")
        link_el = post.select_one("a[href]")

        title = title_el.get_text(strip=True) if title_el else ""
        content = content_el.get_text(strip=True) if content_el else ""
        date_str = date_el.get_text(strip=True) if date_el else ""
        url_val = link_el.get("href", "") if link_el else ""

        if not title or len(title) < 3:
            return None

        d = parse_relative_date(date_str, start_date, end_date)
        if d is None:
            return None

        full_text = f"{title} {content}"
        rid = make_id(source_label, full_text, str(d))
        if rid in seen_ids:
            return None

        seen_ids.add(rid)
        return {
            "id": rid, "source": source_label,
            "title": title, "content": content,
            "rating": "", "date": str(d),
            "sentiment": analyze_sentiment(full_text),
            "url": url_val, "keyword": keyword
        }
    except:
        return None

def collect_naver_blog(start_date, end_date, seen_ids):
    """네이버 블로그 검색 API v1 사용"""
    import html as _html
    _headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    collected = []
    for keyword in KEYWORDS:
        try:
            params = {"query": keyword, "display": 100, "sort": "date"}
            resp = requests.get(
                "https://openapi.naver.com/v1/search/blog.json",
                headers=_headers, params=params, timeout=15
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            for it in items:
                try:
                    from email.utils import parsedate_to_datetime
                    pub = parsedate_to_datetime(it.get("pubDate", "")).date()
                except Exception:
                    pub = None
                if pub and not (start_date.date() <= pub <= end_date.date()):
                    continue
                def _clean(s):
                    return _html.unescape(re.sub(r"<[^>]+>", "", s or ""))
                title        = _clean(it.get("title", ""))
                body         = _clean(it.get("description", ""))
                link         = it.get("link") or it.get("bloggerlink", "")
                uid          = link or title
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                collected.append({
                    "id": uid, "source": "네이버 블로그",
                    "title": title, "content": body,
                    "url": link, "date": pub.isoformat() if pub else "",
                    "keyword": keyword,
                    "sentiment": analyze_sentiment(title + " " + body),
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"  네이버 블로그 API 오류 ({keyword}): {e}")
    print(f"  네이버 블로그: {len(collected)}건")
    return collected

def collect_naver_cafe(start_date, end_date, seen_ids):
    """네이버 카페글 검색 API v1 사용"""
    import html as _html
    _headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    collected = []
    for keyword in KEYWORDS:
        try:
            params = {"query": keyword, "display": 100, "sort": "date"}
            resp = requests.get(
                "https://openapi.naver.com/v1/search/cafearticle.json",
                headers=_headers, params=params, timeout=15
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            for it in items:
                try:
                    from email.utils import parsedate_to_datetime
                    pub = parsedate_to_datetime(it.get("pubDate", "")).date()
                except Exception:
                    pub = None
                if pub and not (start_date.date() <= pub <= end_date.date()):
                    continue
                def _clean(s):
                    return _html.unescape(re.sub(r"<[^>]+>", "", s or ""))
                title     = _clean(it.get("title", ""))
                body      = _clean(it.get("description", ""))
                link      = it.get("link", "")
                cafe_name = _clean(it.get("cafename", ""))
                label     = f"네이버 카페 ({cafe_name})" if cafe_name else "네이버 카페"
                uid       = link or title
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                collected.append({
                    "id": uid, "source": label,
                    "title": title, "content": body,
                    "url": link, "date": pub.isoformat() if pub else "",
                    "keyword": keyword,
                    "sentiment": analyze_sentiment(title + " " + body),
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"  네이버 카페 API 오류 ({keyword}): {e}")
    print(f"  네이버 카페: {len(collected)}건")
    return collected

def collect_dcinside(start_date, end_date, seen_ids):
    """디씨인사이드 금융/카드 갤러리 검색"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://www.dcinside.com/",
    }
    collected = []
    # 검색 대상 갤러리: 신용카드 갤러리
    search_urls = [
        f"https://search.dcinside.com/post/p/1/sort/latest/q/{quote(kw)}"
        for kw in ["현대카드 앱", "현대카드 후기", "현대카드 불만"]
    ]
    for url in search_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            posts = soup.select(".sch_result_list li") or soup.select(".gall_list tr.us-post") or soup.select("li.result-item")
            for post in posts:
                try:
                    title_el = post.select_one(".tit, .subject, a.sch_tit, .result-tit, a")
                    content_el = post.select_one(".sch_cont, .cont, .result-cont, p")
                    date_el = post.select_one(".date, .gall_date, .result-date, time")
                    link_el = post.select_one("a[href]")

                    title = title_el.get_text(strip=True) if title_el else ""
                    content = content_el.get_text(strip=True) if content_el else ""
                    date_str = date_el.get_text(strip=True) if date_el else ""
                    url_val = link_el.get("href", "") if link_el else ""

                    if not title or len(title) < 3:
                        continue
                    if not any(kw in title + content for kw in ["현대카드", "hyundai card"]):
                        continue

                    d = parse_relative_date(date_str, start_date, end_date)
                    if d is None:
                        continue

                    full_text = f"{title} {content}"
                    rid = make_id("dcinside", full_text, str(d))
                    if rid in seen_ids:
                        continue

                    if url_val and not url_val.startswith("http"):
                        url_val = "https://www.dcinside.com" + url_val

                    seen_ids.add(rid)
                    collected.append({
                        "id": rid, "source": "디씨인사이드",
                        "title": title, "content": content,
                        "rating": "", "date": str(d),
                        "sentiment": analyze_sentiment(full_text),
                        "url": url_val, "keyword": "현대카드"
                    })
                except:
                    continue
            time.sleep(1.2)
        except Exception as e:
            print(f"  디씨인사이드 오류: {e}")
    return collected


# ============================================================
# 뽐뿌 수집
# ============================================================

def collect_ppomppu(start_date, end_date, seen_ids):
    """뽐뿌 자유게시판/재테크포럼 검색"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://www.ppomppu.co.kr/",
    }
    collected = []
    boards = [
        ("freeboard", "자유게시판"),
        ("money", "재테크포럼"),
    ]
    for board_id, board_name in boards:
        try:
            url = f"https://www.ppomppu.co.kr/zboard/zboard.php?id={board_id}&keyword=현대카드+앱&search=sub_memo"
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            rows = soup.select("tr.list1, tr.list0, tr.common") or soup.select("table.list_form_board tr")
            for row in rows:
                try:
                    title_el = row.select_one(".title a, td.title a, a.list_subject")
                    date_el = row.select_one("td.time, td:nth-child(6), .date")
                    link_el = row.select_one("a[href]")

                    title = title_el.get_text(strip=True) if title_el else ""
                    date_str = date_el.get_text(strip=True) if date_el else ""
                    url_val = link_el.get("href", "") if link_el else ""

                    if not title or len(title) < 3:
                        continue

                    d = parse_relative_date(date_str, start_date, end_date)
                    if d is None:
                        continue

                    if url_val and not url_val.startswith("http"):
                        url_val = "https://www.ppomppu.co.kr/zboard/" + url_val.lstrip("/")

                    rid = make_id("ppomppu", title, str(d))
                    if rid in seen_ids:
                        continue

                    seen_ids.add(rid)
                    collected.append({
                        "id": rid, "source": f"뽐뿌 ({board_name})",
                        "title": title, "content": "",
                        "rating": "", "date": str(d),
                        "sentiment": analyze_sentiment(title),
                        "url": url_val, "keyword": "현대카드 앱"
                    })
                except:
                    continue
            time.sleep(1.2)
        except Exception as e:
            print(f"  뽐뿌 오류 ({board_name}): {e}")
    return collected


# ============================================================
# 클리앙 수집
# ============================================================

def collect_clien(start_date, end_date, seen_ids):
    """클리앙 커뮤니티 검색"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://www.clien.net/",
    }
    collected = []
    for keyword in ["현대카드 앱", "현대카드 불만", "현대카드 후기"]:
        try:
            url = f"https://www.clien.net/service/search?q={quote(keyword)}&sort=recency&boardCd=&isRestrict=false"
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            posts = soup.select(".list_item.symph_row") or soup.select(".contents_listview .list_item") or soup.select("div.list_item")
            for post in posts:
                try:
                    title_el = post.select_one(".list_subject span, .subject_fixed, a.list_subject")
                    date_el = post.select_one(".list_time span.timestamp, time, .symph_date")
                    link_el = post.select_one("a.list_subject, a[href*='/service/']")

                    title = title_el.get_text(strip=True) if title_el else ""
                    date_str = date_el.get("datetime", date_el.get_text(strip=True)) if date_el else ""
                    url_val = link_el.get("href", "") if link_el else ""

                    if not title or len(title) < 3:
                        continue

                    d = parse_relative_date(date_str[:10], start_date, end_date)
                    if d is None:
                        continue

                    if url_val and not url_val.startswith("http"):
                        url_val = "https://www.clien.net" + url_val

                    rid = make_id("clien", title, str(d))
                    if rid in seen_ids:
                        continue

                    seen_ids.add(rid)
                    collected.append({
                        "id": rid, "source": "클리앙",
                        "title": title, "content": "",
                        "rating": "", "date": str(d),
                        "sentiment": analyze_sentiment(title),
                        "url": url_val, "keyword": keyword
                    })
                except:
                    continue
            time.sleep(1.2)
        except Exception as e:
            print(f"  클리앙 오류 ({keyword}): {e}")
    return collected


# ============================================================
# 브런치 수집
# ============================================================

def collect_brunch(start_date, end_date, seen_ids):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    collected = []
    for keyword in KEYWORDS[:3]:  # 브런치는 주요 키워드만
        try:
            url = f"https://brunch.co.kr/search/{quote(keyword)}"
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            posts = (
                soup.select(".search_article_wrap li")
                or soup.select(".article_item")
                or soup.select("[class*='article']")
            )

            for post in posts:
                try:
                    title_el = post.select_one(".tit_article, .title, a")
                    content_el = post.select_one(".txt_article, .desc, p")
                    date_el = post.select_one(".date_article, .date, [class*='date']")
                    link_el = post.select_one("a[href]")

                    title = title_el.get_text(strip=True) if title_el else ""
                    content = content_el.get_text(strip=True) if content_el else ""
                    date_str = date_el.get_text(strip=True) if date_el else ""
                    url_val = link_el.get("href", "") if link_el else ""

                    if not title or len(title) < 3:
                        continue

                    full_text = f"{title} {content}"
                    rid = make_id("brunch", full_text, date_str)
                    if rid in seen_ids:
                        continue

                    d = parse_relative_date(date_str, start_date, end_date) or start_date

                    full_url = f"https://brunch.co.kr{url_val}" if url_val.startswith("/") else url_val

                    seen_ids.add(rid)
                    collected.append({
                        "id": rid, "source": "Brunch",
                        "title": title, "content": content,
                        "rating": "", "date": str(d),
                        "sentiment": analyze_sentiment(full_text),
                        "url": full_url, "keyword": keyword
                    })
                except:
                    continue
            time.sleep(1.2)
        except Exception as e:
            print(f"  브런치 오류 ({keyword}): {e}")
    return collected


# ============================================================
# X (트위터) 수집
# ─ 공식 API 없이 Nitter 퍼블릭 인스턴스 또는 검색 스크래핑 시도.
#   X가 로그인 없이 검색 결과를 차단할 경우 수집 0건으로 처리.
# ============================================================

def collect_twitter(start_date, end_date, seen_ids):
    """X(트위터) 현대카드 앱 언급 수집 — Nitter 인스턴스 이용"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    collected = []
    # Nitter는 X 콘텐츠를 로그인 없이 볼 수 있는 오픈소스 프론트엔드
    nitter_instances = [
        "https://nitter.net",
        "https://nitter.privacydev.net",
        "https://nitter.poast.org",
    ]
    queries = ["현대카드 앱", "현대카드 불만", "현대카드 오류"]

    for query in queries:
        collected_this = False
        for base in nitter_instances:
            if collected_this:
                break
            try:
                url = f"{base}/search?q={quote(query)}&f=tweets&since={start_date}&until={end_date}"
                resp = requests.get(url, headers=headers, timeout=12)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                tweets = soup.select(".timeline-item") or soup.select(".tweet-body")
                for tw in tweets:
                    try:
                        content_el = tw.select_one(".tweet-content, .content")
                        date_el = tw.select_one(".tweet-date a, time")
                        link_el = tw.select_one(".tweet-link, a.tweet-date")

                        content = content_el.get_text(strip=True) if content_el else ""
                        date_str = (date_el.get("title") or date_el.get("datetime") or
                                    date_el.get_text(strip=True)) if date_el else ""
                        url_val = link_el.get("href", "") if link_el else ""

                        if not content or len(content) < 5:
                            continue
                        if not any(kw in content for kw in ["현대카드", "hyundaicard"]):
                            continue

                        d = parse_relative_date(date_str[:10], start_date, end_date)
                        if d is None:
                            continue

                        if url_val and not url_val.startswith("http"):
                            url_val = f"https://x.com{url_val}"

                        rid = make_id("twitter", content, str(d))
                        if rid in seen_ids:
                            continue

                        seen_ids.add(rid)
                        collected.append({
                            "id": rid, "source": "X(트위터)",
                            "title": "", "content": content,
                            "rating": "", "date": str(d),
                            "sentiment": analyze_sentiment(content),
                            "url": url_val, "keyword": query
                        })
                        collected_this = True
                    except:
                        continue
                time.sleep(1.0)
            except Exception as e:
                print(f"  X 수집 오류 ({base}): {e}")
                continue
    return collected


# ============================================================
# 유튜브 댓글 수집
# ─ YouTube Data API v3 키 없이 검색 페이지 스크래핑.
#   JS 렌더링 없이 접근 가능한 경우에만 수집.
# ============================================================

def collect_youtube(start_date, end_date, seen_ids):
    """유튜브 '현대카드 앱' 관련 영상 댓글 수집"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    collected = []
    queries = ["현대카드 앱 리뷰", "현대카드 앱 사용법", "현대카드 앱 불편"]

    for query in queries:
        try:
            # 유튜브 검색 결과 페이지 (SP=EgIYAQ%3D%3D = 최근 1주일 필터)
            url = (
                f"https://www.youtube.com/results"
                f"?search_query={quote(query)}&sp=EgIYAQ%3D%3D"
            )
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            # ytInitialData JSON 파싱 시도
            import re as _re
            m = _re.search(r'var ytInitialData = ({.*?});</script>', resp.text, _re.DOTALL)
            if not m:
                continue
            yt_data = json.loads(m.group(1))

            # 영상 목록에서 제목·URL·날짜 추출
            contents = (
                yt_data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            videos = []
            for section in contents:
                items = section.get("itemSectionRenderer", {}).get("contents", [])
                for item in items:
                    vr = item.get("videoRenderer", {})
                    if not vr:
                        continue
                    vid_title = "".join(
                        r.get("text", "") for r in
                        vr.get("title", {}).get("runs", [])
                    )
                    vid_id = vr.get("videoId", "")
                    pub_time = vr.get("publishedTimeText", {}).get("simpleText", "")
                    desc_runs = vr.get("descriptionSnippet", {}).get("runs", [])
                    desc = "".join(r.get("text", "") for r in desc_runs)

                    if not vid_title or not vid_id:
                        continue
                    if not any(kw in vid_title + desc for kw in ["현대카드", "hyundai"]):
                        continue

                    videos.append({
                        "title": vid_title,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "pub_time": pub_time,
                        "desc": desc,
                    })

            # 각 영상을 수집 항목으로 추가 (댓글 수집은 API 필요 — 영상 자체 정보만)
            for v in videos[:5]:
                d = parse_relative_date(v["pub_time"], start_date, end_date)
                if d is None:
                    continue
                full_text = v["title"] + " " + v["desc"]
                rid = make_id("youtube", full_text, str(d))
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                collected.append({
                    "id": rid, "source": "유튜브",
                    "title": v["title"], "content": v["desc"],
                    "rating": "", "date": str(d),
                    "sentiment": analyze_sentiment(full_text),
                    "url": v["url"], "keyword": query
                })
            time.sleep(1.2)
        except Exception as e:
            print(f"  유튜브 수집 오류 ({query}): {e}")
    return collected


# ============================================================
# HTML 리포트 생성
# ============================================================

# ============================================================
# 주제 클러스터 정의 (동적 분류용)
# ============================================================
TOPIC_CLUSTERS = {
    "긍정": [
        {"id":"pos_design",   "keywords":["디자인","ui","ux","깔끔","직관","인터페이스","세련","미니멀","예쁘","심플"],
         "summary":"깔끔하고 직관적인 앱 디자인에 대한 만족도가 높아요"},
        {"id":"pos_payment",  "keywords":["결제","앱카드","애플페이","페이","간편결제","실물카드","nfc"],
         "summary":"간편결제와 앱카드 기능의 편의성에 만족하는 사용자가 많아요"},
        {"id":"pos_feature",  "keywords":["혜택","소비잔소리","소비케어","추천","ai","잠금","lock","기능"],
         "summary":"다양한 혜택과 소비 관리 기능이 유용하다는 평가예요"},
        {"id":"pos_stable",   "keywords":["빠르","안정","원활","잘됩","잘 됩","잘돼","문제없","불편없"],
         "summary":"앱이 빠르고 안정적으로 작동한다는 긍정적인 반응이에요"},
        {"id":"pos_easy",     "keywords":["편리","편하","간편","쉽게","쉬운","사용하기","쓰기"],
         "summary":"전반적인 사용 편의성이 타 카드사 앱보다 뛰어나다는 의견이에요"},
        {"id":"pos_satisfy",  "keywords":["만족","추천","최고","훌륭","완벽","강추","좋아"],
         "summary":"전반적인 앱 사용 경험에 높은 만족감을 표현하는 의견이에요"},
    ],
    "부정": [
        {"id":"neg_crash",    "keywords":["먹통","오류","에러","버그","안됩","안되","실행 안","안 됩","튕","충돌","다운","작동"],
         "summary":"앱이 실행되지 않거나 먹통이 되는 오류 문제가 반복되고 있어요"},
        {"id":"neg_login",    "keywords":["로그인","인증","생체","지문","비밀번호"],
         "summary":"로그인 및 생체인증 오류로 불편을 겪는 사용자가 많아요"},
        {"id":"neg_server",   "keywords":["서버","대기","느리","느림","로딩","먹힘"],
         "phrases":["서버 접속","서버 연결","접속 불가","대기 중","페이지 로딩","앱 로딩"],
         "excludes":["고객센터","상담","콜센터"],
         "summary":"서버 접속 지연과 로딩 문제가 자주 발생하고 있어요"},
        {"id":"neg_ui",       "keywords":["불편","광고","스크롤","개악","기능 없","인터페이스"],
         "summary":"앱의 UI와 특정 기능에 대한 불편함이 지적되고 있어요"},
        {"id":"neg_cs",       "keywords":["고객센터","상담","콜센터","전화","문의","고객지원"],
         "phrases":["고객센터 연결","상담 연결","전화 연결","연락이 안","연결이 안","고객 서비스","고객센터 전화"],
         "summary":"고객센터 연결 및 고객 서비스 대응에 대한 불만이 있어요"},
        {"id":"neg_notif",    "keywords":["알림","문자","푸시","알림 안","알림이"],
         "summary":"결제 알림과 푸시 알림이 제때 오지 않는 문제가 있어요"},
    ],
    "중립": [
        {"id":"neu_inquiry",  "keywords":["방법","어떻게","문의","질문","궁금","알려"],
         "summary":"앱 사용 방법이나 기능에 대한 문의성 의견이에요"},
        {"id":"neu_compare",  "keywords":["비교","타사","다른","카드사","대비","반면"],
         "summary":"타 카드사 앱과 비교하거나 분석한 의견이에요"},
        {"id":"neu_update",   "keywords":["업데이트","버전","개선","변경","바뀌","추가됐"],
         "summary":"앱 업데이트나 기능 변경에 대한 의견이에요"},
    ],
}

def make_cluster_html(reviews, sentiment, badge_type, review_card_fn):
    """리뷰를 주제별로 클러스터링해 아코디언 HTML 생성"""
    if not reviews:
        return '<p class="empty">리뷰 없음</p>'

    clusters_def = TOPIC_CLUSTERS.get(sentiment, [])
    assignments = {c["id"]: [] for c in clusters_def}
    unassigned = []

    for review in reviews:
        text = (review.get("title", "") + " " + review.get("content", "")).lower()
        best_id, best_score = None, 0
        for c in clusters_def:
            score = sum(1 for kw in c["keywords"] if kw in text)
            score += sum(3 for ph in c.get("phrases", []) if ph in text)
            score -= sum(2 for ex in c.get("excludes", []) if ex in text)
            if score > best_score:
                best_score, best_id = score, c["id"]
        if best_score > 0:
            assignments[best_id].append(review)
        else:
            unassigned.append(review)

    # 3건 이상인 클러스터만, 많은 순으로 최대 4개
    valid = sorted(
        [(cid, revs) for cid, revs in assignments.items() if len(revs) >= 3],
        key=lambda x: -len(x[1])
    )[:4]
    top_ids = {c[0] for c in valid}

    # 미달 클러스터 → 기타로 이동
    for cid, revs in assignments.items():
        if cid not in top_ids:
            unassigned.extend(revs)

    parts = []
    for i, (cid, revs) in enumerate(valid, 1):
        cdef = next(c for c in clusters_def if c["id"] == cid)
        summary = cdef["summary"]
        cards = "".join(review_card_fn(r, badge_type, sentiment) for r in revs)
        parts.append(f'''<div class="cluster">
  <div class="cluster-hdr">
    <span class="cluster-num">{i}</span>
    <span class="cluster-txt">{summary} <span class="cluster-cnt">({len(revs)}건)</span></span>
  </div>
  <details class="cluster-detail">
    <summary class="cluster-toggle">자세히 보기</summary>
    <div class="rv-grid cluster-cards">{cards}</div>
  </details>
</div>''')

    if unassigned:
        cards = "".join(review_card_fn(r, badge_type, sentiment) for r in unassigned)
        parts.append(f'''<div class="cluster cluster-etc">
  <div class="cluster-hdr">
    <span class="cluster-num cluster-num-etc">기타</span>
    <span class="cluster-txt">기타 의견이에요 <span class="cluster-cnt">({len(unassigned)}건)</span></span>
  </div>
  <details class="cluster-detail">
    <summary class="cluster-toggle">자세히 보기</summary>
    <div class="rv-grid cluster-cards">{cards}</div>
  </details>
</div>''')

    return "\n".join(parts)


def generate_html_report(all_reviews, start_date, end_date):
    total = len(all_reviews)
    positive = [r for r in all_reviews if r["sentiment"] == "긍정"]
    negative = [r for r in all_reviews if r["sentiment"] == "부정"]
    neutral = [r for r in all_reviews if r["sentiment"] == "중립"]

    # 소스별 통계
    source_stats = {}
    for r in all_reviews:
        src = r["source"].split(" (")[0]
        source_stats[src] = source_stats.get(src, 0) + 1

    # 주요 부정 이슈 분류
    issue_map = {
        "앱 오류 / 버그": ["오류", "버그", "에러", "튕", "충돌", "먹통", "다운", "강제 종료"],
        "로그인 / 인증 문제": ["로그인", "인증", "비밀번호", "인증서", "아이디"],
        "속도 / 로딩 문제": ["느리", "로딩", "오래 걸", "시간이 걸", "버벅"],
        "UI / UX 불편": ["불편", "복잡", "어렵", "찾기 힘", "인터페이스", "화면"],
        "혜택 / 포인트 불만": ["포인트", "혜택", "캐시백", "할인", "적립"],
        "고객센터 / 응대": ["고객센터", "상담", "문의", "응답", "답변"],
        "앱 업데이트 후 문제": ["업데이트", "업데이트 후", "최신 버전"],
    }

    issues_found = {}
    for label, kws in issue_map.items():
        cnt = sum(
            1 for r in negative
            for kw in kws
            if kw in (r.get("content", "") + r.get("title", ""))
        )
        if cnt:
            issues_found[label] = cnt
    issues_sorted = sorted(issues_found.items(), key=lambda x: x[1], reverse=True)

    # 긍정 주제
    pos_map = {
        "편리한 사용성": ["편리", "편하", "간편", "쉽"],
        "빠른 속도": ["빠르", "속도"],
        "다양한 혜택": ["혜택", "할인", "캐시백", "포인트", "적립"],
        "깔끔한 디자인": ["디자인", "깔끔", "예쁘", "직관"],
        "간편결제 / 보안": ["간편결제", "보안", "안전", "페이"],
    }
    pos_topics = {}
    for label, kws in pos_map.items():
        cnt = sum(
            1 for r in positive
            for kw in kws
            if kw in (r.get("content", "") + r.get("title", ""))
        )
        if cnt:
            pos_topics[label] = cnt
    pos_sorted = sorted(pos_topics.items(), key=lambda x: x[1], reverse=True)

    def pct(n):
        return round(n / total * 100) if total else 0

    def star_html(rating_str):
        if not rating_str or not rating_str.isdigit():
            return ""
        n = int(rating_str)
        return f'<span class="stars">{"★" * n}{"☆" * (5 - n)}</span>'

    def resolve_url(r):
        """소스별로 실제 연결 가능한 URL과 링크 텍스트 반환.
        (url, link_label) 튜플. url이 None이면 링크 미표시."""
        src = r.get("source", "")
        url = r.get("url", "")

        # ── 앱스토어: 개별 리뷰 링크 없음 → 리뷰 탭으로 ──────────────────
        if src == "앱스토어":
            return ("https://apps.apple.com/kr/app/id702653088?see-all=reviews",
                    "앱스토어 리뷰 전체 보기 →")

        # ── 플레이스토어: 개별 리뷰 링크 없음 → 리뷰 탭으로 ──────────────
        if src == "플레이스토어":
            return ("https://play.google.com/store/apps/details"
                    "?id=com.hyundaicard.appcard&hl=ko&showAllReviews=true",
                    "플레이스토어 리뷰 전체 보기 →")

        if not url or not url.startswith("http"):
            return (None, "")

        # ── 네이버 블로그: 포스트 ID 있는지 확인 ─────────────────────────
        if "blog.naver.com" in url:
            parts = [p for p in url.rstrip("/").split("/") if p]
            # 형식: blog.naver.com / userid / postno
            if len(parts) >= 3 and parts[-1].isdigit():
                return (url, "원문 보기 →")
            return (None, "")   # 블로그 홈만 있는 경우 링크 숨김

        # ── 네이버 카페: articleid 파라미터 확인 ─────────────────────────
        if "cafe.naver.com" in url:
            if "articleid=" in url or "/articles/" in url:
                return (url, "원문 보기 →")
            return (None, "")   # 카페 홈만 있는 경우 링크 숨김

        # ── 디씨인사이드: no= 파라미터 확인 ─────────────────────────────
        if "dcinside.com" in url:
            if "no=" in url:
                return (url, "원문 보기 →")
            return (None, "")   # 게시판 URL만 있는 경우 링크 숨김

        # ── X(트위터): /status/ 포함 & 트윗 ID가 실제 숫자(10자리 이상) 확인 ──
        if "x.com" in url or "twitter.com" in url:
            if "/status/" in url:
                status_id = url.split("/status/")[-1].split("?")[0].split("/")[0]
                if status_id.isdigit() and len(status_id) >= 10:
                    # nitter URL을 x.com 으로 변환
                    clean = url.replace("nitter.net", "x.com") \
                                .replace("nitter.privacydev.net", "x.com") \
                                .replace("nitter.poast.org", "x.com")
                    return (clean, "X에서 보기 →")
            return (None, "")

        # ── 유튜브: watch?v= 확인 ─────────────────────────────────────────
        if "youtube.com" in url:
            if "watch?v=" in url:
                vid_id = url.split("watch?v=")[-1].split("&")[0]
                # 최소 8자 이상의 실제 video ID 여부 확인
                if len(vid_id) >= 8:
                    return (url, "유튜브에서 보기 →")
            return (None, "")

        # ── 기타(Brunch, 뽐뿌, 클리앙 등): URL이 충분히 구체적이면 표시 ──
        if len(url) > 30:
            return (url, "원문 보기 →")
        return (None, "")

    def review_card(r, badge_class, badge_label):
        title_html = f'<div class="rv-title">{r["title"][:100]}</div>' if r.get("title") else ""
        content_text = r.get("content", "")
        truncated = content_text[:250] + ("…" if len(content_text) > 250 else "")
        resolved_url, link_label = resolve_url(r)
        link_html = (f'<a href="{resolved_url}" target="_blank" class="rv-link">{link_label}</a>'
                     if resolved_url else "")
        return f"""
        <div class="rv-card">
          <div class="rv-head">
            <div class="rv-meta">
              <span class="badge {badge_class}">{badge_label}</span>
              <span class="src-badge">{r["source"]}</span>
              {star_html(r.get("rating", ""))}
            </div>
            <span class="rv-date">{r.get("date", "")}</span>
          </div>
          {title_html}
          <div class="rv-body">{truncated}</div>
          {link_html}
        </div>"""

    # 이슈 태그 HTML
    issue_tags = "".join(
        f'<div class="tag neg">{iss} <span class="tag-cnt">{cnt}</span></div>'
        for iss, cnt in issues_sorted[:8]
    ) or '<p class="empty">이번 주 집계된 주요 이슈가 없습니다.</p>'

    pos_tags = "".join(
        f'<div class="tag pos">{tp} <span class="tag-cnt">{cnt}</span></div>'
        for tp, cnt in pos_sorted[:5]
    ) if pos_sorted else ""

    # 소스 바
    max_cnt = max(source_stats.values()) if source_stats else 1
    source_bars = "".join(
        f"""<div class="bar-row">
          <div class="bar-name">{src}</div>
          <div class="bar-track"><div class="bar-fill" style="width:{round(cnt/max_cnt*100)}%"></div></div>
          <div class="bar-val">{cnt}건</div>
        </div>"""
        for src, cnt in sorted(source_stats.items(), key=lambda x: x[1], reverse=True)
    )

    neg_cluster_html = make_cluster_html(negative, "부정", "neg", review_card)
    pos_cluster_html = make_cluster_html(positive, "긍정", "pos", review_card)
    neu_cluster_html = make_cluster_html(neutral,  "중립", "neu", review_card)

    week_label = f"{start_date.strftime('%Y.%m.%d')} ~ {end_date.strftime('%m.%d')} 주간 리포트"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>현대카드 앱 리뷰 분석 | {week_label}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:#f0f0f5;color:#1d1d1f;font-size:15px}}
a{{color:inherit;text-decoration:none}}

/* 헤더 */
.hdr{{background:linear-gradient(135deg,#1c1c1e 0%,#2c2c2e 100%);color:#fff;padding:36px 40px 24px}}
.hdr h1{{font-size:26px;font-weight:700;letter-spacing:-0.5px;margin-bottom:6px;display:flex;align-items:center;gap:12px}}
.hdr-icon{{width:44px;height:44px;border-radius:10px;object-fit:cover;flex-shrink:0}}
.hdr .sub{{font-size:13px;opacity:.6}}
/* 리포트 선택 드롭다운 */
.report-nav{{background:rgba(255,255,255,.07);border-top:1px solid rgba(255,255,255,.1);padding:14px 40px;display:flex;align-items:center;gap:12px}}
.report-nav-label{{font-size:13px;color:rgba(255,255,255,.6);white-space:nowrap}}
.report-selector{{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);color:#fff;padding:7px 14px;border-radius:8px;font-size:14px;cursor:pointer;flex:1;max-width:320px}}
.report-selector option{{background:#2c2c2e;color:#fff}}
.wrap{{max-width:1140px;margin:0 auto;padding:28px 20px}}

/* 요약 카드 */
.sum-total{{font-size:15px;font-weight:400;color:#1d1d1f;margin-bottom:12px}}
.sum-total strong{{font-size:15px;font-weight:700}}
.sum-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px}}
.sum-card{{background:#fff;border-radius:14px;padding:22px 18px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.06);cursor:pointer;transition:box-shadow .15s,transform .15s;text-decoration:none;color:inherit;display:block}}
.sum-card:hover{{box-shadow:0 6px 18px rgba(0,0,0,.12);transform:translateY(-2px)}}
.sum-num{{font-size:36px;font-weight:700;margin-bottom:4px;line-height:1}}
.sum-lbl{{font-size:12px;color:#8e8e93}}
.c-blue{{color:#0a84ff}}.c-green{{color:#30d158}}.c-red{{color:#ff453a}}.c-gray{{color:#636366}}

/* 감성 바 */
.sent-bar{{height:10px;border-radius:5px;overflow:hidden;display:flex;margin:14px 0 6px}}
.sent-bar .s-pos{{background:#30d158}}.sent-bar .s-neg{{background:#ff453a}}.sent-bar .s-neu{{background:#c7c7cc}}
.sent-lbl{{display:flex;justify-content:space-between;font-size:12px;color:#8e8e93}}

/* 섹션 */
.sec{{background:#fff;border-radius:14px;padding:26px;margin-bottom:18px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.sec h2{{font-size:18px;font-weight:700;margin-bottom:18px;display:flex;align-items:center;gap:8px}}
.sec-toggle{{width:100%;display:flex;align-items:center;justify-content:space-between;cursor:pointer;list-style:none;gap:8px}}
.sec-toggle::-webkit-details-marker{{display:none}}
.sec-toggle h2{{margin-bottom:0;flex:1}}
.sec-arrow{{font-size:13px;color:#8e8e93;transition:transform .25s;flex-shrink:0}}
details.sec-collapsible[open] .sec-arrow{{transform:rotate(180deg)}}
details.sec-collapsible .sec-body{{margin-top:18px}}
.sec h2 .bar{{width:4px;height:20px;border-radius:2px;display:inline-block}}
.bar-red{{background:#ff453a}}.bar-green{{background:#30d158}}.bar-blue{{background:#0a84ff}}.bar-gray{{background:#636366}}

/* 태그 */
.tags{{display:flex;flex-wrap:wrap;gap:8px}}
.tag{{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:100px;font-size:13px;font-weight:600}}
.tag.neg{{background:#fff2f0;color:#ff453a}}.tag.pos{{background:#f0fff4;color:#30d158}}
.tag-cnt{{background:rgba(0,0,0,.08);padding:1px 7px;border-radius:100px;font-size:11px;font-weight:400}}

/* 소스 바 차트 */
.bar-row{{display:flex;align-items:center;gap:12px;margin-bottom:10px}}
.bar-name{{min-width:130px;font-size:13px;color:#3a3a3c}}
.bar-track{{flex:1;height:8px;background:#f2f2f7;border-radius:4px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:4px;background:linear-gradient(90deg,#0a84ff,#5ac8fa)}}
.bar-val{{min-width:36px;text-align:right;font-size:12px;color:#8e8e93}}

/* 리뷰 카드 */
.rv-grid{{display:grid;gap:10px}}
.rv-card{{border:1px solid #e5e5ea;border-radius:12px;padding:16px;transition:box-shadow .15s}}
.rv-card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
.rv-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;flex-wrap:wrap;gap:6px}}
.rv-meta{{display:flex;gap:6px;align-items:center;flex-wrap:wrap}}
.badge{{padding:3px 10px;border-radius:100px;font-size:12px;font-weight:700}}
.badge.neg{{background:#fff2f0;color:#ff453a}}.badge.pos{{background:#f0fff4;color:#30d158}}.badge.neu{{background:#f2f2f7;color:#636366}}
.src-badge{{padding:3px 10px;border-radius:100px;font-size:11px;background:#f2f2f7;color:#3a3a3c}}
.stars{{color:#ffd60a;font-size:13px}}
.rv-date{{font-size:12px;color:#8e8e93;white-space:nowrap}}
.rv-title{{font-size:14px;font-weight:700;margin-bottom:5px;color:#1d1d1f}}
.rv-body{{font-size:13px;color:#3a3a3c;line-height:1.65}}
.rv-link{{font-size:12px;color:#0a84ff;margin-top:8px;display:inline-block}}
.rv-link:hover{{text-decoration:underline}}

.empty{{font-size:14px;color:#8e8e93;padding:8px 0}}

/* 클러스터 */
.cluster{{border:1px solid #e5e5ea;border-radius:12px;overflow:hidden;margin-bottom:12px}}
.cluster-hdr{{display:flex;align-items:center;gap:12px;padding:14px 18px;background:#f9f9fb}}
.cluster-num{{width:26px;height:26px;border-radius:50%;background:#1c1c1e;color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.cluster-num-etc{{background:#8e8e93;border-radius:6px;font-size:11px;width:30px;height:26px}}
.cluster-txt{{font-size:14px;font-weight:600;color:#1d1d1f;line-height:1.5}}
.cluster-cnt{{font-weight:400;color:#8e8e93;font-size:13px}}
.cluster-detail{{border-top:1px solid #e5e5ea}}
.cluster-toggle{{list-style:none;display:block;padding:9px 18px;font-size:13px;color:#0a84ff;cursor:pointer;font-weight:600;background:#fff;user-select:none}}
.cluster-toggle::-webkit-details-marker{{display:none}}
.cluster-toggle::after{{content:" ▾";font-size:10px}}
details[open]>.cluster-toggle::after{{content:" ▴"}}
.cluster-cards{{padding:12px;background:#fff}}
.footer{{text-align:center;padding:28px;color:#8e8e93;font-size:12px}}
</style>
</head>
<body>

<div class="hdr">
  <div style="max-width:1140px;margin:0 auto">
    <h1><img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAeAAAAHgCAIAAADytinCAAAOFklEQVR42u3dS4hW9f8H8HN5rqOWpkSmJuUVCUysrAiEFl2wFv9+htEiqFUFgbVIoXCn0cadO4OCLiQU5aZooAuESWFGlmVpXhrL1Lw7z/2c/+LU09M4js9o5aiv10JmhjOP8J3PeZ/P+Z7vOScIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADgPxeGoUFA2XP+cobg31MqlWq1WpqmAyo4TdOxY8dee+2148aNq9Vq5XJ51KhRpVLJiDES9Pf31+v1arVar9ePHj168uTJ48ePV6vVzghO0zSO4yRJ2uV9bkl9+q/zt8E0BP+N2bNnz5o1a8qUKXEcT5s27aqrrpo0adL48eMnTpyYz+dLpVI+nzdKjASNRqO/v//EiROnTp3as2fP77//vm/fvsOHD584cWLfvn3bt2/v6+s7efJkFEVpmqZpmiVymqY9PT2VSmVY/5eAFtAX7HQvn8/ffPPNt91228SJE2fMmDFr1qzrrrsuiqLOZrlWq0VRFMexM0RGgjRNW61WFEZxLm7/sNVsJWlSq9V++eWX77//vq+v79ChQ99+++2mTZt+/fXXrI/O5XL1el0HLaBHVhAPqLCenp7+/v4bbrhh0aJFM2bMuOWWW+bOnVsul9sbJEnSaDTCMMzlclEUtctUpTKCYjpJkzTJuuM4jtuF2hmsP/7443fffbd79+6tW7e+9NJLQRBkPbUOWkCPIPl8vtlstuts7ty5S5YsufHGG2+77bbx48efXtmKlZF/8jcsu3bt2rx585YtW9avX79jx47Ro0efPHmyy49S8wL6XxfHcRAEkydPfvrppxcuXDhr1qxisVgoFNqnh2EUdpPUipWLMaAzBw4c+Prrrzdv3vzKK6989913XX6amhfQ/+7MRrFYrNfry5cvv/vuu2+66aaxY8cGQVCtVrPgbk8u6ya4JAM6TdOklYRRWK1WS6XS/v379+7d29vbu2rVqmwJ09AfqOYF9L+iXC5XKpVisThnzpxVq1bNnDlz8uTJcRTHubjVbEVxlFVtuzoFNJd2B50kSTYHHYbhsWPHtm3btnTp0i+++KIzo0/PazUvoP9Fjz322AsvvDBu3Lhyudy5NuM8F4fCxWXQTnnnzp1vvvnm888/H0VRkiRxHLdarTAMO09ABbSA/ofl8/lGo1Eul1euXPnII49cffXVAxbw/7ONCVwUAT1ozZ88eXL79u233357o9EI/pwb7GZ/QUCfYzr39PQcO3ast7d34cKFnXeXDF1qAprLLaDr9XqxWAyCYM+ePffff/8333wTBEF2/6GA7lJsCM4+RnHcLqMkSWq12pYtW+64445oKhI7VYBcuNQtAX" style="width:44px;height:44px;border-radius:10px;flex-shrink:0" alt="현대카드 앱"> 현대카드 앱 리뷰 분석</h1>
    <div class="sub">{week_label} &nbsp;|&nbsp; 생성: {generated}</div>
  </div>
  <div class="report-nav">
    <span class="report-nav-label">📅 리포트 선택</span>
    <select id="report-selector" class="report-selector">
      <option>로딩 중...</option>
    </select>
  </div>
</div>

<div class="wrap">

<!-- 요약 카드 -->
<div class="sum-total">총 <strong>{total}</strong>건 수집</div>
<div class="sum-grid">
  <a class="sum-card" href="#sec-pos"><div class="sum-num c-green">{len(positive)}</div><div class="sum-lbl">😊 긍정 ({pct(len(positive))}%)</div></a>
  <a class="sum-card" href="#sec-neg"><div class="sum-num c-red">{len(negative)}</div><div class="sum-lbl">😤 부정 ({pct(len(negative))}%)</div></a>
  <a class="sum-card" href="#sec-neu"><div class="sum-num c-gray">{len(neutral)}</div><div class="sum-lbl">😐 중립 ({pct(len(neutral))}%)</div></a>
</div>

<!-- 감성 분포 -->
<div class="sec">
  <h2><span class="bar bar-gray"></span>감성 분포</h2>
  <div class="sent-bar">
    <div class="s-pos" style="width:{pct(len(positive))}%"></div>
    <div class="s-neg" style="width:{pct(len(negative))}%"></div>
    <div class="s-neu" style="width:{pct(len(neutral))}%"></div>
  </div>
  <div class="sent-lbl">
    <span>🟢 긍정 {pct(len(positive))}%</span>
    <span>🔴 부정 {pct(len(negative))}%</span>
    <span>⚪ 중립 {pct(len(neutral))}%</span>
  </div>
</div>

<!-- 주요 이슈 -->
<div class="sec">
  <h2><span class="bar bar-red"></span>🚨 이번 주 주요 이슈</h2>
  <div class="tags">{issue_tags}</div>
  {f'<div style="margin-top:20px"><p style="font-size:14px;font-weight:600;color:#30d158;margin-bottom:10px">✅ 주요 긍정 반응</p><div class="tags">{pos_tags}</div></div>' if pos_tags else ""}
</div>

<!-- 소스별 현황 -->
<div class="sec">
  <details class="sec-collapsible">
    <summary class="sec-toggle">
      <h2><span class="bar bar-blue"></span>📊 소스별 수집 현황</h2>
      <span class="sec-arrow">▼</span>
    </summary>
    <div class="sec-body">{source_bars if source_bars else '<p class="empty">수집된 데이터 없음</p>'}</div>
  </details>
</div>

<!-- 부정 리뷰 -->
<div class="sec" id="sec-neg">
  <h2><span class="bar bar-red"></span>😤 부정 리뷰 ({len(negative)}건)</h2>
  {neg_cluster_html}
</div>

<!-- 긍정 리뷰 -->
<div class="sec" id="sec-pos">
  <h2><span class="bar bar-green"></span>😊 긍정 리뷰 ({len(positive)}건)</h2>
  {pos_cluster_html}
</div>

<!-- 중립 리뷰 -->
<div class="sec" id="sec-neu">
  <h2><span class="bar bar-gray"></span>😐 중립 리뷰 ({len(neutral)}건)</h2>
  {neu_cluster_html}
</div>

</div>
<div class="footer">
  현대카드 앱 리뷰 자동 분석 | 수집 소스: 앱스토어 · 플레이스토어 · 네이버 블로그 · 네이버 카페(전체) · Brunch · 디씨인사이드 · 뽐뿌 · 클리앙 · X(트위터) · 유튜브
</div>
<script>
(function(){{
  var sel = document.getElementById('report-selector');
  fetch('/manifest.json')
    .then(function(r){{ return r.json(); }})
    .then(function(list){{
      sel.innerHTML = '';
      var cur = window.location.pathname.split('/').pop();
      if(!cur || cur === 'index.html') cur = list[0] && list[0].file;
      list.forEach(function(r){{
        var opt = document.createElement('option');
        opt.value = r.file === list[0].file ? '/' : '/' + r.file;
        opt.textContent = r.label;
        if(r.file === cur) opt.selected = true;
        sel.appendChild(opt);
      }});
      sel.addEventListener('change', function(e){{ window.location.href = e.target.value; }});
    }})
    .catch(function(){{ sel.innerHTML = '<option>{week_label}</option>'; }});
}})();
</script>
</body>
</html>"""


# ============================================================
# 메인
# ============================================================

def main():
    print("=" * 50)
    print("현대카드 앱 리뷰 수집 및 분석 시작")
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    start_date, end_date = get_week_range()
    print(f"수집 기간: {start_date} ~ {end_date}\n")

    seen_ids = load_seen_ids()
    print(f"기존 수집 ID: {len(seen_ids)}건")

    all_reviews = []

    print("\n[1/5] 앱스토어 수집...")
    r = collect_appstore_reviews(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print("[2/5] 플레이스토어 수집...")
    r = collect_playstore_reviews(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print("[3/5] 네이버 블로그 수집...")
    r = collect_naver_blog(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print("[4/5] 네이버 카페 수집...")
    r = collect_naver_cafe(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print("[5/5] 브런치 수집...")
    r = collect_brunch(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print("[6/8] 디씨인사이드 수집...")
    r = collect_dcinside(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print("[7/8] 뽐뿌 수집...")
    r = collect_ppomppu(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print("[8/10] 클리앙 수집...")
    r = collect_clien(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print("[9/10] X(트위터) 수집...")
    r = collect_twitter(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print("[10/10] 유튜브 수집...")
    r = collect_youtube(start_date, end_date, seen_ids)
    print(f"  결과: {len(r)}건")
    all_reviews.extend(r)

    print(f"\n총 신규 수집: {len(all_reviews)}건")

    # seen_ids 저장 (중복 방지)
    save_seen_ids(seen_ids)

    # 원본 데이터 JSON 저장
    raw_path = os.path.join(DATA_DIR, f"reviews_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(all_reviews, f, ensure_ascii=False, indent=2, default=str)
    print(f"원본 데이터: {raw_path}")

    # HTML 리포트 생성
    print("\nHTML 리포트 생성 중...")
    html = generate_html_report(all_reviews, start_date, end_date)
    report_name = f"report_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.html"
    report_path = os.path.join(REPORTS_DIR, report_name)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    # manifest.json 업데이트 (리포트 목록)
    update_manifest(report_name, start_date, end_date)

    pos_cnt = sum(1 for r in all_reviews if r["sentiment"] == "긍정")
    neg_cnt = sum(1 for r in all_reviews if r["sentiment"] == "부정")
    neu_cnt = sum(1 for r in all_reviews if r["sentiment"] == "중립")

    print(f"\n{'='*50}")
    print(f"분석 완료 — 긍정:{pos_cnt} / 부정:{neg_cnt} / 중립:{neu_cnt}")
    print(f"리포트 저장: {report_path}")
    print(f"{'='*50}")

    # Netlify 배포 (CI 환경에서는 GitHub Actions에서 별도 처리)
    if not os.environ.get("CI"):
        deploy_to_netlify(report_path)

    return report_path


def update_manifest(report_name, start_date, end_date):
    """reports/manifest.json에 새 리포트 항목 추가"""
    manifest_path = os.path.join(REPORTS_DIR, "manifest.json")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        manifest = []

    label = f"{start_date.strftime('%Y.%m.%d')} ~ {end_date.strftime('%m.%d')}"
    entry = {"file": report_name, "label": label}
    manifest = [e for e in manifest if e.get("file") != report_name]
    manifest.insert(0, entry)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"manifest.json 업데이트: {len(manifest)}개 리포트")


def deploy_to_netlify(report_path):
    """최신 리포트를 Netlify API로 배포 (CLI 불필요)"""
    import io, zipfile
    if not NETLIFY_AUTH_TOKEN or not NETLIFY_SITE:
        print("Netlify 설정이 없어 배포를 건너뜁니다.")
        return

    try:
        print("\nNetlify 배포 중...")

        # index.html 하나만 담은 zip 생성 (메모리 내)
        with open(report_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("index.html", html_content)
        zip_buffer.seek(0)

        # Netlify Deploy API 호출
        resp = requests.post(
            f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE}/deploys",
            headers={
                "Authorization": f"Bearer {NETLIFY_AUTH_TOKEN}",
                "Content-Type": "application/zip",
            },
            data=zip_buffer.getvalue(),
            timeout=60,
        )

        if resp.status_code in (200, 201):
            print("배포 완료! 👉 https://hyundai-review.netlify.app")
        else:
            print(f"배포 실패 (HTTP {resp.status_code}): {resp.text[:200]}")

    except Exception as e:
        print(f"배포 중 오류: {e}")


if __name__ == "__main__":
    main()
