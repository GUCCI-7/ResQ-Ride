import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim
import streamlit.components.v1 as components
import math
import os
import re
import requests
import qrcode
from io import BytesIO
from datetime import datetime
import json


# =========================
# 基本設定
# =========================
APP_NAME = "レスキューライド"
POSTS_FILE = "rescue_ride_posts.csv"

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🚲",
    layout="wide"
)

st.title(f"🚲 {APP_NAME}")
st.subheader("GPS現在地検索・全国地域検索・ルート危険度表示・自動セーフティ・オーラ・危険地点共有")


# =========================
# 距離計算
# =========================
def calc_distance_km(lat1, lon1, lat2, lon2):
    R = 6371

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.asin(math.sqrt(a))
    return R * c


# =========================
# 緯度・経度変換
# =========================
def clean_number(value):
    if pd.isna(value):
        return None

    text = str(value).strip()
    text = text.replace("　", "")
    text = text.replace(" ", "")
    text = text.replace(",", "")
    text = re.sub(r"[^0-9.]", "", text)

    if text == "":
        return None

    try:
        return float(text)
    except:
        return None


def convert_lat(value):
    num = clean_number(value)

    if num is None:
        return None

    if 20 <= num <= 50:
        return num

    try:
        s = str(int(num)).zfill(9)
        degree = int(s[0:2])
        minute = int(s[2:4])
        second = float(s[4:]) / 1000

        lat = degree + minute / 60 + second / 3600

        if 20 <= lat <= 50:
            return lat
        return None
    except:
        return None


def convert_lon(value):
    num = clean_number(value)

    if num is None:
        return None

    if 120 <= num <= 150:
        return num

    try:
        s = str(int(num)).zfill(10)
        degree = int(s[0:3])
        minute = int(s[3:5])
        second = float(s[5:]) / 1000

        lon = degree + minute / 60 + second / 3600

        if 120 <= lon <= 150:
            return lon
        return None
    except:
        return None


# =========================
# 事故データ読み込み
# =========================
@st.cache_data
def load_data():
    if os.path.exists("honhyo_2024.csv"):
        encodings = ["cp932", "utf-8-sig", "utf-8", "shift_jis"]

        for enc in encodings:
            try:
                df = pd.read_csv("honhyo_2024.csv", encoding=enc)
                return df, "honhyo_2024.csv"
            except:
                pass

        raise Exception("CSVを読み込めませんでした。文字コードが合っていない可能性があります。")

    elif os.path.exists("honhyo_2024.xlsx"):
        df = pd.read_excel("honhyo_2024.xlsx")
        return df, "honhyo_2024.xlsx"

    else:
        raise FileNotFoundError("honhyo_2024.csv または honhyo_2024.xlsx が見つかりません。")


def find_lat_lon_columns(df):
    df.columns = [str(c).strip() for c in df.columns]

    lat_col = None
    lon_col = None

    for col in df.columns:
        col_text = str(col)

        if lat_col is None and ("緯度" in col_text or "北緯" in col_text):
            lat_col = col

        if lon_col is None and ("経度" in col_text or "東経" in col_text):
            lon_col = col

    return lat_col, lon_col


@st.cache_data
def prepare_accident_data():
    df, filename = load_data()

    lat_col, lon_col = find_lat_lon_columns(df)

    if lat_col is None or lon_col is None:
        return None, filename, None, None

    df["lat"] = df[lat_col].apply(convert_lat)
    df["lon"] = df[lon_col].apply(convert_lon)

    df = df.dropna(subset=["lat", "lon"])

    df = df[
        (df["lat"] >= 24.0) &
        (df["lat"] <= 46.5) &
        (df["lon"] >= 122.0) &
        (df["lon"] <= 146.5)
    ]

    return df, filename, lat_col, lon_col


# =========================
# 地域名検索
# =========================
@st.cache_data
def geocode_place(place_name):
    try:
        geolocator = Nominatim(user_agent="rescue_ride_streamlit_app")
        location = geolocator.geocode(place_name + ", Japan", timeout=10)

        if location:
            return location.latitude, location.longitude, location.address

        return None, None, None

    except:
        return None, None, None


# =========================
# ルート取得
# =========================
@st.cache_data
def get_route(start_lat, start_lon, goal_lat, goal_lon):
    url_list = [
        f"https://routing.openstreetmap.de/routed-bike/route/v1/driving/{start_lon},{start_lat};{goal_lon},{goal_lat}?overview=full&geometries=geojson&steps=false",
        f"https://routing.openstreetmap.de/routed-car/route/v1/driving/{start_lon},{start_lat};{goal_lon},{goal_lat}?overview=full&geometries=geojson&steps=false",
        f"https://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{goal_lon},{goal_lat}?overview=full&geometries=geojson&steps=false"
    ]

    last_error = None

    for url in url_list:
        try:
            res = requests.get(url, timeout=15)
            data = res.json()

            if data.get("code") == "Ok":
                route = data["routes"][0]
                coords = route["geometry"]["coordinates"]

                route_points = [[lat, lon] for lon, lat in coords]
                distance_km = route["distance"] / 1000
                duration_min = route["duration"] / 60

                return route_points, distance_km, duration_min, None

            last_error = data

        except Exception as e:
            last_error = e

    return None, None, None, last_error


# =========================
# ルート危険度
# =========================
def count_accidents_near_point(accident_df, lat, lon, radius_km):
    count = 0

    for _, row in accident_df.iterrows():
        d = calc_distance_km(lat, lon, row["lat"], row["lon"])
        if d <= radius_km:
            count += 1

    return count


def get_risk_color(count, low_threshold, high_threshold):
    if count >= high_threshold:
        return "red"
    elif count >= low_threshold:
        return "orange"
    return "green"


def get_risk_label(count, low_threshold, high_threshold):
    if count >= high_threshold:
        return "危険度：高"
    elif count >= low_threshold:
        return "危険度：中"
    return "危険度：低"


def draw_colored_route(m, route_points, accident_df, density_radius_km, low_threshold, high_threshold):
    risk_summary = {
        "green": 0,
        "orange": 0,
        "red": 0
    }

    if len(route_points) < 2:
        return risk_summary

    for i in range(len(route_points) - 1):
        p1 = route_points[i]
        p2 = route_points[i + 1]

        mid_lat = (p1[0] + p2[0]) / 2
        mid_lon = (p1[1] + p2[1]) / 2

        count = count_accidents_near_point(
            accident_df,
            mid_lat,
            mid_lon,
            density_radius_km
        )

        color = get_risk_color(count, low_threshold, high_threshold)
        label = get_risk_label(count, low_threshold, high_threshold)

        risk_summary[color] += 1

        folium.PolyLine(
            locations=[p1, p2],
            color=color,
            weight=7,
            opacity=0.85,
            popup=f"{label}<br>周辺事故件数：{count}件"
        ).add_to(m)

    return risk_summary


# =========================
# セーフティ・オーラ
# =========================
def get_nearest_accident(accident_df, lat, lon):
    if accident_df is None or len(accident_df) == 0:
        return None, None, None

    temp_df = accident_df.copy()

    temp_df["distance_km"] = temp_df.apply(
        lambda row: calc_distance_km(lat, lon, row["lat"], row["lon"]),
        axis=1
    )

    nearest = temp_df.sort_values("distance_km").iloc[0]

    return nearest["distance_km"], nearest["lat"], nearest["lon"]


def play_voice_alert(message):
    safe_message = json.dumps(message)

    components.html(
        f"""
        <script>
        const message = {safe_message};

        function playBeep() {{
            try {{
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                const audioCtx = new AudioContext();
                const oscillator = audioCtx.createOscillator();
                const gainNode = audioCtx.createGain();

                oscillator.type = "sine";
                oscillator.frequency.setValueAtTime(880, audioCtx.currentTime);
                gainNode.gain.setValueAtTime(0.18, audioCtx.currentTime);

                oscillator.connect(gainNode);
                gainNode.connect(audioCtx.destination);

                oscillator.start();
                oscillator.stop(audioCtx.currentTime + 0.35);
            }} catch (e) {{}}
        }}

        function speakAlert() {{
            try {{
                const utterance = new SpeechSynthesisUtterance(message);
                utterance.lang = "ja-JP";
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                window.speechSynthesis.cancel();
                window.speechSynthesis.speak(utterance);
            }} catch (e) {{}}
        }}

        playBeep();
        speakAlert();
        </script>
        """,
        height=0
    )


def show_safety_aura(nearest_distance_km, aura_radius_km):
    st.header("🛡️ 自動セーフティ・オーラ")

    if nearest_distance_km is None:
        st.info("事故データが読み込めていないため、セーフティ・オーラは判定できません。")
        return "unknown"

    nearest_m = nearest_distance_km * 1000

    if nearest_distance_km <= aura_radius_km:
        st.error(f"⚠️ 危険地点が近くにあります。最寄り事故地点まで約 {nearest_m:.0f}m です。")

        st.markdown(
            """
            <style>
            .aura-danger {
                animation: pulseDanger 1.1s infinite;
                border-radius: 18px;
                padding: 22px;
                text-align: center;
                font-size: 26px;
                font-weight: bold;
                color: white;
                background: radial-gradient(circle, #ff3b30, #b00020);
                box-shadow: 0 0 25px rgba(255, 0, 0, 0.9);
                margin-bottom: 20px;
            }

            @keyframes pulseDanger {
                0% { box-shadow: 0 0 10px rgba(255,0,0,0.4); transform: scale(1); }
                50% { box-shadow: 0 0 35px rgba(255,0,0,1); transform: scale(1.02); }
                100% { box-shadow: 0 0 10px rgba(255,0,0,0.4); transform: scale(1); }
            }
            </style>

            <div class="aura-danger">
                ⚠️ SAFETY AURA 発動中<br>
                周囲に事故多発・危険地点があります
            </div>
            """,
            unsafe_allow_html=True
        )

        return "danger"

    elif nearest_distance_km <= aura_radius_km * 2:
        st.warning(f"🟠 注意エリアです。最寄り事故地点まで約 {nearest_m:.0f}m です。")

        st.markdown(
            """
            <style>
            .aura-warning {
                border-radius: 18px;
                padding: 20px;
                text-align: center;
                font-size: 24px;
                font-weight: bold;
                color: #3b2500;
                background: #ffd166;
                box-shadow: 0 0 18px rgba(255, 193, 7, 0.8);
                margin-bottom: 20px;
            }
            </style>

            <div class="aura-warning">
                🟠 SAFETY AURA 注意<br>
                周辺に事故地点があります
            </div>
            """,
            unsafe_allow_html=True
        )

        return "warning"

    else:
        st.success(f"🟢 現在の周辺は比較的安全です。最寄り事故地点まで約 {nearest_m:.0f}m です。")

        st.markdown(
            """
            <style>
            .aura-safe {
                border-radius: 18px;
                padding: 20px;
                text-align: center;
                font-size: 24px;
                font-weight: bold;
                color: white;
                background: #2ecc71;
                box-shadow: 0 0 18px rgba(46, 204, 113, 0.8);
                margin-bottom: 20px;
            }
            </style>

            <div class="aura-safe">
                🟢 SAFETY AURA 正常<br>
                周辺の危険度は低めです
            </div>
            """,
            unsafe_allow_html=True
        )

        return "safe"


# =========================
# QRコード
# =========================
def make_qr_code(url):
    qr = qrcode.QRCode(
        version=1,
        box_size=8,
        border=3
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer


# =========================
# 投稿データ保存・読み込み
# =========================
def load_posts_from_csv():
    if os.path.exists(POSTS_FILE):
        try:
            df = pd.read_csv(POSTS_FILE, encoding="utf-8-sig")
            return df.to_dict("records")
        except:
            return []
    return []


def save_posts_to_csv(posts):
    if len(posts) == 0:
        return

    df = pd.DataFrame(posts)
    df.to_csv(POSTS_FILE, index=False, encoding="utf-8-sig")


def posts_to_csv_bytes(posts):
    if len(posts) == 0:
        df = pd.DataFrame(columns=[
            "投稿日時",
            "カテゴリー",
            "危険度",
            "場所名",
            "緯度",
            "経度",
            "状況チェック",
            "コメント",
            "登録方法"
        ])
    else:
        df = pd.DataFrame(posts)

    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


# =========================
# 初期設定
# =========================
if "center_lat" not in st.session_state:
    st.session_state.center_lat = 35.681236
    st.session_state.center_lon = 139.767125
    st.session_state.place_label = "東京駅"
    st.session_state.address_label = "東京駅"
    st.session_state.mode_label = "地域名検索"

if "posts" not in st.session_state:
    st.session_state.posts = load_posts_from_csv()

if "route_points" not in st.session_state:
    st.session_state.route_points = None
    st.session_state.route_distance_km = None
    st.session_state.route_duration_min = None
    st.session_state.start_label = None
    st.session_state.goal_label = None
    st.session_state.start_lat = None
    st.session_state.start_lon = None
    st.session_state.goal_lat = None
    st.session_state.goal_lon = None

if "last_alert_status" not in st.session_state:
    st.session_state.last_alert_status = None


# =========================
# GPS取得
# =========================
gps = get_geolocation()


# =========================
# サイドバー
# =========================
st.sidebar.header("🔍 検索設定")

search_mode = st.sidebar.radio(
    "地図の中心検索方法",
    ["地域名で検索", "GPS現在地で検索"]
)

search_radius = st.sidebar.slider(
    "事故地点の表示範囲",
    min_value=1,
    max_value=100,
    value=10,
    step=1
)

max_points = st.sidebar.slider(
    "事故地点の最大表示数",
    min_value=100,
    max_value=10000,
    value=2000,
    step=100
)

show_debug = st.sidebar.checkbox("データ確認を表示", value=True)

st.sidebar.write("---")


# =========================
# セーフティ・オーラ設定
# =========================
st.sidebar.header("🛡️ セーフティ・オーラ設定")

use_safety_aura = st.sidebar.checkbox(
    "自動セーフティ・オーラをONにする",
    value=True
)

use_voice_alert = st.sidebar.checkbox(
    "音声アラートをONにする",
    value=True
)

aura_radius_m = st.sidebar.slider(
    "危険接近判定距離",
    min_value=50,
    max_value=1000,
    value=300,
    step=50
)

aura_radius_km = aura_radius_m / 1000


# =========================
# 地域名検索
# =========================
if search_mode == "地域名で検索":
    place_name = st.sidebar.text_input(
        "地域名・駅名・市区町村名",
        value="八王子"
    )

    if st.sidebar.button("地図の中心を検索"):
        lat, lon, address = geocode_place(place_name)

        if lat is not None and lon is not None:
            st.session_state.center_lat = lat
            st.session_state.center_lon = lon
            st.session_state.place_label = place_name
            st.session_state.address_label = address
            st.session_state.mode_label = "地域名検索"
            st.sidebar.success("検索できました。")
        else:
            st.sidebar.error("地域が見つかりませんでした。例：大阪駅、名古屋市、福岡市")


# =========================
# GPS検索
# =========================
else:
    st.sidebar.info("ブラウザで位置情報を許可してください。")

    if gps is not None:
        try:
            gps_lat = gps["coords"]["latitude"]
            gps_lon = gps["coords"]["longitude"]

            st.sidebar.success("GPSを取得しました。")

            if st.sidebar.button("GPS現在地を中心にする"):
                st.session_state.center_lat = gps_lat
                st.session_state.center_lon = gps_lon
                st.session_state.place_label = "GPS現在地"
                st.session_state.address_label = "ブラウザで取得した現在地"
                st.session_state.mode_label = "GPS現在地検索"

        except:
            st.sidebar.error("GPS情報の読み取りに失敗しました。")
    else:
        st.sidebar.warning("GPSがまだ取得できていません。位置情報を許可して、F5で更新してください。")


# =========================
# ルート検索設定
# =========================
st.sidebar.write("---")
st.sidebar.header("🚲 ルート検索")

route_display_mode = st.sidebar.radio(
    "ルート表示方法",
    [
        "表示しない",
        "通常ルートを表示",
        "事故密集度で色分け表示"
    ],
    index=2
)

route_start = st.sidebar.text_input(
    "出発地",
    value="八王子駅"
)

route_goal = st.sidebar.text_input(
    "目的地",
    value="創価大学"
)

use_current_as_start = st.sidebar.checkbox(
    "現在の地図中心を出発地にする",
    value=False
)

density_radius_km = st.sidebar.slider(
    "ルート危険度の判定範囲",
    min_value=0.05,
    max_value=1.0,
    value=0.25,
    step=0.05,
    help="ルート上の各地点から何km以内の事故を数えるか"
)

low_threshold = st.sidebar.slider(
    "黄色にする事故件数",
    min_value=1,
    max_value=10,
    value=2,
    step=1
)

high_threshold = st.sidebar.slider(
    "赤にする事故件数",
    min_value=2,
    max_value=20,
    value=5,
    step=1
)

route_button = st.sidebar.button("ルート検索する")


# =========================
# QRコード設定
# =========================
st.sidebar.write("---")
st.sidebar.header("🔗 QRコード")

app_url = st.sidebar.text_input(
    "共有したいURL",
    value="http://localhost:8501"
)

show_qr = st.sidebar.checkbox(
    "QRコードを表示",
    value=True
)


# =========================
# 投稿フィルター設定
# =========================
st.sidebar.write("---")
st.sidebar.header("📝 投稿フィルター")

post_filter_category = st.sidebar.selectbox(
    "表示する投稿カテゴリー",
    ["すべて", "交差点", "道路・車道", "歩道・路肩", "夜間・暗い道", "駐輪場周辺", "その他"]
)


# =========================
# 事故データ準備
# =========================
accident_df = None
filename = None
lat_col = None
lon_col = None

try:
    accident_df, filename, lat_col, lon_col = prepare_accident_data()
except:
    accident_df = None


# =========================
# ルート検索ボタン処理
# =========================
if route_button:
    if use_current_as_start:
        start_lat = st.session_state.center_lat
        start_lon = st.session_state.center_lon
        start_address = st.session_state.place_label
    else:
        start_lat, start_lon, start_address = geocode_place(route_start)

    goal_lat, goal_lon, goal_address = geocode_place(route_goal)

    if start_lat is None or start_lon is None:
        st.sidebar.error("出発地が見つかりませんでした。")
    elif goal_lat is None or goal_lon is None:
        st.sidebar.error("目的地が見つかりませんでした。")
    else:
        route_points, distance_km, duration_min, error = get_route(
            start_lat,
            start_lon,
            goal_lat,
            goal_lon
        )

        if route_points is None:
            st.sidebar.error("ルートを取得できませんでした。")
            st.sidebar.write(error)
        else:
            st.session_state.route_points = route_points
            st.session_state.route_distance_km = distance_km
            st.session_state.route_duration_min = duration_min
            st.session_state.start_label = start_address
            st.session_state.goal_label = goal_address
            st.session_state.start_lat = start_lat
            st.session_state.start_lon = start_lon
            st.session_state.goal_lat = goal_lat
            st.session_state.goal_lon = goal_lon

            mid_index = len(route_points) // 2
            st.session_state.center_lat = route_points[mid_index][0]
            st.session_state.center_lon = route_points[mid_index][1]
            st.session_state.place_label = "検索ルート周辺"
            st.session_state.address_label = f"{route_start} → {route_goal}"
            st.session_state.mode_label = "ルート検索"

            st.sidebar.success("ルートを取得しました。")


# =========================
# 危険地点投稿
# =========================
st.header("📍 危険地点を投稿")

post_category = st.selectbox(
    "投稿カテゴリー",
    ["交差点", "道路・車道", "歩道・路肩", "夜間・暗い道", "駐輪場周辺", "その他"]
)

danger = st.slider("危険度を選択", 1, 5, 3)

st.write("### 危険地点の設定方法")

post_location_mode = st.radio(
    "危険地点をどこに設定しますか？",
    [
        "現在地GPSで登録",
        "地名・住所で登録",
        "緯度経度を直接入力",
        "現在の地図中心で登録"
    ]
)

post_place = ""
post_lat = None
post_lon = None
post_address = ""
post_location_method = post_location_mode

if post_location_mode == "現在地GPSで登録":
    post_place = st.text_input("場所名", value="GPS現在地")

    if gps is not None:
        try:
            post_lat = gps["coords"]["latitude"]
            post_lon = gps["coords"]["longitude"]
            post_address = "ブラウザで取得した現在地"
            st.success(f"GPS取得済み：緯度 {post_lat:.6f} / 経度 {post_lon:.6f}")
        except:
            st.warning("GPS情報の読み取りに失敗しました。")
    else:
        st.warning("GPSが取得できていません。ブラウザで位置情報を許可してください。")

elif post_location_mode == "地名・住所で登録":
    post_place = st.text_input("危険地点の地名・住所", value="八王子駅前")

    if st.button("投稿地点の住所を確認"):
        lat, lon, address = geocode_place(post_place)

        if lat is not None and lon is not None:
            st.session_state.post_search_lat = lat
            st.session_state.post_search_lon = lon
            st.session_state.post_search_address = address
            st.success("投稿地点を取得しました。")
        else:
            st.error("投稿地点が見つかりませんでした。")

    if "post_search_lat" in st.session_state:
        post_lat = st.session_state.post_search_lat
        post_lon = st.session_state.post_search_lon
        post_address = st.session_state.post_search_address
        st.info(f"登録予定地点：{post_address}")

elif post_location_mode == "緯度経度を直接入力":
    post_place = st.text_input("場所名", value="手入力地点")

    col_lat, col_lon = st.columns(2)

    with col_lat:
        post_lat = st.number_input("緯度", value=35.681236, format="%.6f")

    with col_lon:
        post_lon = st.number_input("経度", value=139.767125, format="%.6f")

    post_address = "緯度経度を直接入力"

else:
    post_place = st.text_input("場所名", value=st.session_state.place_label)
    post_lat = st.session_state.center_lat
    post_lon = st.session_state.center_lon
    post_address = st.session_state.address_label
    st.info(f"現在の地図中心を登録します：緯度 {post_lat:.6f} / 経度 {post_lon:.6f}")


st.write("### 危険地点の状況チェック")

situation_options = [
    "見通しが悪い",
    "車通りが多い",
    "道が狭い・路肩がない",
    "夜間に暗い・ライトが少ない"
]

selected_situations = []

for option in situation_options:
    checked = st.checkbox(option)
    if checked:
        selected_situations.append(option)

comment = st.text_area("補足コメント", placeholder="例：朝の通学時間に車が多く、右折車との接触が怖い。")

if st.button("危険地点を投稿"):
    if post_lat is None or post_lon is None:
        st.error("投稿地点の緯度・経度が取得できていません。")
    elif str(post_place).strip() == "":
        st.error("場所名を入力してください。")
    elif len(selected_situations) == 0:
        st.error("状況チェックを1つ以上選んでください。")
    else:
        new_post = {
            "投稿日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "カテゴリー": post_category,
            "危険度": danger,
            "場所名": post_place,
            "緯度": post_lat,
            "経度": post_lon,
            "住所情報": post_address,
            "状況チェック": " / ".join(selected_situations),
            "コメント": comment,
            "登録方法": post_location_method
        }

        st.session_state.posts.append(new_post)
        save_posts_to_csv(st.session_state.posts)

        st.success("危険地点を投稿しました。")


# =========================
# 地図表示
# =========================
st.header("🗺️ 安全マップ")

center_lat = st.session_state.center_lat
center_lon = st.session_state.center_lon

st.write(f"検索方法：**{st.session_state.mode_label}**")
st.write(f"検索地点：**{st.session_state.place_label}**")
st.write(f"住所情報：**{st.session_state.address_label}**")
st.write(f"事故地点の表示範囲：**{search_radius}km以内**")

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=13
)


# =========================
# セーフティ・オーラ判定
# =========================
nearest_distance_km = None
nearest_lat = None
nearest_lon = None
aura_status = "unknown"

if use_safety_aura and accident_df is not None and len(accident_df) > 0:
    nearest_distance_km, nearest_lat, nearest_lon = get_nearest_accident(
        accident_df,
        center_lat,
        center_lon
    )

    aura_status = show_safety_aura(nearest_distance_km, aura_radius_km)

    if use_voice_alert:
        if aura_status == "danger" and st.session_state.last_alert_status != "danger":
            play_voice_alert("危険地点が近くにあります。注意してください。")
        elif aura_status == "warning" and st.session_state.last_alert_status != "warning":
            play_voice_alert("周辺に事故地点があります。注意してください。")

    st.session_state.last_alert_status = aura_status

    if nearest_lat is not None and nearest_lon is not None:
        aura_color = "red"

        if aura_status == "warning":
            aura_color = "orange"
        elif aura_status == "safe":
            aura_color = "green"

        folium.Circle(
            location=[center_lat, center_lon],
            radius=aura_radius_m,
            color=aura_color,
            fill=True,
            fill_opacity=0.12,
            popup="セーフティ・オーラ判定範囲"
        ).add_to(m)

        folium.Marker(
            location=[nearest_lat, nearest_lon],
            popup=f"最寄り事故地点<br>距離：約{nearest_distance_km * 1000:.0f}m",
            tooltip="最寄り事故地点",
            icon=folium.Icon(color="red", icon="warning-sign")
        ).add_to(m)


# =========================
# 検索地点ピン
# =========================
if st.session_state.mode_label == "GPS現在地検索":
    marker_color = "green"
    marker_name = "現在地"
else:
    marker_color = "blue"
    marker_name = st.session_state.place_label

folium.Marker(
    location=[center_lat, center_lon],
    popup=marker_name,
    tooltip=marker_name,
    icon=folium.Icon(color=marker_color, icon="info-sign")
).add_to(m)

folium.Circle(
    location=[center_lat, center_lon],
    radius=search_radius * 1000,
    color="blue",
    fill=True,
    fill_opacity=0.05,
    popup=f"{search_radius}km以内"
).add_to(m)


# =========================
# ルート表示
# =========================
if st.session_state.route_points is not None and route_display_mode != "表示しない":
    route_points = st.session_state.route_points

    st.header("🚲 ルート検索結果")

    st.write(f"出発地：**{st.session_state.start_label}**")
    st.write(f"目的地：**{st.session_state.goal_label}**")
    st.write(f"距離：約 **{st.session_state.route_distance_km:.2f} km**")
    st.write(f"所要時間：約 **{st.session_state.route_duration_min:.0f} 分**")
    st.write(f"ルート表示方法：**{route_display_mode}**")

    folium.Marker(
        location=[st.session_state.start_lat, st.session_state.start_lon],
        popup="出発地",
        tooltip="出発地",
        icon=folium.Icon(color="green", icon="play")
    ).add_to(m)

    folium.Marker(
        location=[st.session_state.goal_lat, st.session_state.goal_lon],
        popup="目的地",
        tooltip="目的地",
        icon=folium.Icon(color="red", icon="flag")
    ).add_to(m)

    if route_display_mode == "通常ルートを表示":
        folium.PolyLine(
            route_points,
            color="blue",
            weight=7,
            opacity=0.8,
            popup="通常ルート"
        ).add_to(m)

    elif route_display_mode == "事故密集度で色分け表示":
        if accident_df is not None and len(accident_df) > 0:
            risk_summary = draw_colored_route(
                m,
                route_points,
                accident_df,
                density_radius_km,
                low_threshold,
                high_threshold
            )

            total_segments = risk_summary["green"] + risk_summary["orange"] + risk_summary["red"]

            st.write("### ルート危険度")
            st.write(f"緑：事故密集度低い区間　**{risk_summary['green']}区間**")
            st.write(f"黄：事故密集度中程度の区間　**{risk_summary['orange']}区間**")
            st.write(f"赤：事故密集度高い区間　**{risk_summary['red']}区間**")

            if total_segments > 0:
                red_ratio = risk_summary["red"] / total_segments * 100
                orange_ratio = risk_summary["orange"] / total_segments * 100

                if red_ratio >= 20:
                    st.error("このルートは事故密集度が高い区間が多めです。注意して走行してください。")
                elif orange_ratio + red_ratio >= 30:
                    st.warning("このルートには注意が必要な区間があります。")
                else:
                    st.success("このルートは比較的事故密集度が低い区間が多いです。")
        else:
            folium.PolyLine(
                route_points,
                color="blue",
                weight=7,
                opacity=0.8,
                popup="ルート"
            ).add_to(m)
            st.warning("事故データが読み込めていないため、危険度色分けはできません。")


# =========================
# 事故地点表示
# =========================
try:
    if accident_df is None:
        st.error("緯度・経度の列が見つかりません。")
        raw_df, raw_filename = load_data()
        st.write("読み込んだ列名：")
        st.write(list(raw_df.columns))

    else:
        st.success(f"事故データを読み込みました：{filename}")

        if show_debug:
            st.write("### データ確認")
            st.write(f"使用した緯度列：**{lat_col}**")
            st.write(f"使用した経度列：**{lon_col}**")
            st.write(f"地図に使える事故データ数：**{len(accident_df)}件**")
            st.dataframe(accident_df[["lat", "lon"]].head(10))

        display_df = accident_df.copy()

        display_df["distance_km"] = display_df.apply(
            lambda row: calc_distance_km(
                center_lat,
                center_lon,
                row["lat"],
                row["lon"]
            ),
            axis=1
        )

        area_df = display_df[display_df["distance_km"] <= search_radius]
        area_df = area_df.sort_values("distance_km")

        st.write(f"### 検索範囲内の事故地点：**{len(area_df)}件**")

        if len(area_df) == 0:
            st.warning("この範囲内に事故地点がありません。検索範囲を広げてください。")

            nearest_df = display_df.sort_values("distance_km").head(10)
            st.write("近い事故地点10件：")
            st.dataframe(nearest_df[["lat", "lon", "distance_km"]])

        else:
            for _, row in area_df.head(max_points).iterrows():
                folium.CircleMarker(
                    location=[row["lat"], row["lon"]],
                    radius=4,
                    color="red",
                    fill=True,
                    fill_color="red",
                    fill_opacity=0.7,
                    popup=f"交通事故地点<br>距離：約{row['distance_km']:.2f}km"
                ).add_to(m)

            st.write("表示中の事故地点データ：")
            st.dataframe(
                area_df[["lat", "lon", "distance_km"]].head(50),
                use_container_width=True
            )

except FileNotFoundError:
    st.error("事故データファイルが見つかりません。")
    st.write("`app.py` と同じフォルダに `honhyo_2024.csv` または `honhyo_2024.xlsx` を置いてください。")

except Exception as e:
    st.error("事故データの処理中にエラーが出ました。")
    st.write(e)


# =========================
# 投稿地点を地図に表示
# =========================
post_marker_color = {
    "交差点": "purple",
    "道路・車道": "orange",
    "歩道・路肩": "cadetblue",
    "夜間・暗い道": "darkblue",
    "駐輪場周辺": "darkgreen",
    "その他": "gray"
}

filtered_posts_for_map = st.session_state.posts

if post_filter_category != "すべて":
    filtered_posts_for_map = [
        p for p in st.session_state.posts
        if p.get("カテゴリー") == post_filter_category
    ]

for post in filtered_posts_for_map:
    try:
        p_lat = float(post.get("緯度"))
        p_lon = float(post.get("経度"))
        p_category = post.get("カテゴリー", "その他")
        p_color = post_marker_color.get(p_category, "gray")

        folium.Marker(
            location=[p_lat, p_lon],
            popup=(
                f"ユーザー投稿<br>"
                f"カテゴリー：{p_category}<br>"
                f"危険度：{post.get('危険度')}<br>"
                f"場所：{post.get('場所名')}<br>"
                f"状況：{post.get('状況チェック')}"
            ),
            tooltip=f"投稿：{p_category}",
            icon=folium.Icon(color=p_color, icon="exclamation-sign")
        ).add_to(m)

    except:
        pass


# =========================
# 地図を表示
# =========================
st_folium(m, width=1100, height=650)


# =========================
# QRコード表示
# =========================
if show_qr:
    st.header("🔗 レスキューライド共有QRコード")

    if app_url.strip() == "":
        st.warning("QRコードを作るURLを入力してください。")
    else:
        qr_buffer = make_qr_code(app_url)

        st.image(
            qr_buffer,
            caption="このQRコードからレスキューライドにアクセス",
            width=220
        )

        st.write(f"共有URL：{app_url}")


# =========================
# 凡例
# =========================
st.header("🟢🟠🔴 ルートの色の意味")

st.write("""
- 🟢 **緑の道**：周辺の事故発生地点が少ない区間
- 🟠 **黄色の道**：周辺に事故発生地点がやや多い区間
- 🔴 **赤の道**：周辺に事故発生地点が多い区間
""")


# =========================
# 投稿一覧・カテゴリー別表示
# =========================
st.header("📝 みんなの危険地点投稿")

post_df = pd.DataFrame(st.session_state.posts)

if len(st.session_state.posts) == 0:
    st.info("まだ投稿はありません。")
else:
    st.write("### 投稿データのダウンロード")

    st.download_button(
        label="投稿データをCSVでダウンロード",
        data=posts_to_csv_bytes(st.session_state.posts),
        file_name="rescue_ride_posts.csv",
        mime="text/csv"
    )

    st.write("### カテゴリー別に見る")

    view_category = st.selectbox(
        "表示するカテゴリー",
        ["すべて", "交差点", "道路・車道", "歩道・路肩", "夜間・暗い道", "駐輪場周辺", "その他"],
        key="view_category_select"
    )

    if view_category == "すべて":
        view_df = post_df
    else:
        view_df = post_df[post_df["カテゴリー"] == view_category]

    st.write(f"表示中の投稿数：**{len(view_df)}件**")

    if len(view_df) == 0:
        st.info("このカテゴリーの投稿はまだありません。")
    else:
        st.dataframe(view_df, use_container_width=True)

        for _, post in view_df.iterrows():
            st.write("---")
            st.write(f"📅 投稿日時：{post.get('投稿日時')}")
            st.write(f"🏷️ カテゴリー：{post.get('カテゴリー')}")
            st.write(f"📍 場所：{post.get('場所名')}")
            st.write(f"⚠️ 危険度：{post.get('危険度')}")
            st.write(f"✅ 状況：{post.get('状況チェック')}")
            st.write(f"📝 コメント：{post.get('コメント')}")
            st.write(f"📌 登録方法：{post.get('登録方法')}")


# =========================
# セーフティ・オーラ説明
# =========================
st.header("🛡️ 自動セーフティ・オーラとは")

st.write("""
自動セーフティ・オーラは、GPS現在地や検索地点の周辺に事故発生地点が近づいたとき、
画面上で自動的に警告を出すパッシブ警告機能です。

音声アラートをONにすると、危険地点が近い場合に警告音と音声読み上げで注意を促します。
ただし、ブラウザの仕様によっては、最初に画面をクリックしないと音が鳴らない場合があります。
""")


# =========================
# 危険度の目安
# =========================
st.header("⚠️ 危険度の目安")

if danger <= 2:
    st.success("比較的安全")
elif danger <= 4:
    st.warning("注意して通行")
else:
    st.error("非常に危険")