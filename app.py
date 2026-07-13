import streamlit as st
import pandas as pd
import math
import os
import io
from datetime import datetime
import streamlit.components.v1 as components
from streamlit_js_eval import get_geolocation
import folium
from streamlit_folium import st_folium
import qrcode


# ==================================================
# 基本設定
# ==================================================

st.set_page_config(
    page_title="レスキューライド",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="collapsed"
)

REVIEW_FILE = "reviews.csv"
LOCATION_FILE = "live_locations.csv"

# GPS未取得時の仮位置
DEFAULT_LAT = 35.6595
DEFAULT_LON = 139.7005


# ==================================================
# CSS
# ==================================================

st.markdown("""
<style>
[data-testid="stSidebar"] {
    display: none;
}

.main .block-container {
    padding-top: 1.2rem;
    padding-left: 3rem;
    padding-right: 3rem;
    max-width: 1400px;
}

body {
    background-color: #f5f7fb;
}

.hero {
    background: linear-gradient(135deg, #0f766e, #0284c7);
    padding: 34px 36px;
    border-radius: 26px;
    color: white;
    box-shadow: 0 8px 24px rgba(0,0,0,0.16);
    margin-bottom: 22px;
}

.hero-title {
    font-size: 44px;
    font-weight: 900;
    margin-bottom: 8px;
}

.hero-sub {
    font-size: 18px;
    opacity: 0.95;
    line-height: 1.7;
}

.section-title {
    font-size: 30px;
    font-weight: 900;
    color: #0f172a;
    margin: 18px 0 14px 0;
}

.mode-card {
    background: white;
    border-radius: 24px;
    padding: 26px;
    border: 2px solid #e5e7eb;
    box-shadow: 0 4px 14px rgba(15,23,42,0.08);
    text-align: center;
    min-height: 205px;
    margin-bottom: 10px;
}

.mode-card-selected {
    border: 4px solid #0284c7;
    background: #eff6ff;
}

.mode-icon {
    font-size: 48px;
    margin-bottom: 8px;
}

.mode-title {
    font-size: 28px;
    font-weight: 900;
    color: #0f172a;
    margin-bottom: 8px;
}

.mode-desc {
    font-size: 15px;
    color: #475569;
    line-height: 1.7;
}

.gps-box {
    background: white;
    border-radius: 22px;
    padding: 22px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 4px 14px rgba(15,23,42,0.08);
    margin-bottom: 18px;
}

.status-bar {
    background: white;
    border-radius: 18px;
    padding: 16px 20px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 3px 10px rgba(15,23,42,0.06);
    margin-bottom: 18px;
}

.card {
    background: white;
    border-radius: 22px;
    padding: 24px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 4px 14px rgba(15,23,42,0.08);
    margin-bottom: 18px;
}

.metric-card {
    background: white;
    border-radius: 20px;
    padding: 20px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 3px 10px rgba(15,23,42,0.06);
    text-align: center;
}

.metric-num {
    font-size: 34px;
    font-weight: 900;
    color: #0f766e;
}

.metric-label {
    color: #64748b;
    font-size: 14px;
    font-weight: 700;
}

.alert-danger {
    background: #fee2e2;
    color: #991b1b;
    border-left: 10px solid #dc2626;
    padding: 22px;
    border-radius: 18px;
    font-size: 20px;
    font-weight: 900;
    line-height: 1.7;
    margin-bottom: 16px;
}

.alert-warning {
    background: #fef3c7;
    color: #92400e;
    border-left: 10px solid #f59e0b;
    padding: 22px;
    border-radius: 18px;
    font-size: 20px;
    font-weight: 900;
    line-height: 1.7;
    margin-bottom: 16px;
}

.alert-safe {
    background: #dcfce7;
    color: #166534;
    border-left: 10px solid #16a34a;
    padding: 22px;
    border-radius: 18px;
    font-size: 20px;
    font-weight: 900;
    line-height: 1.7;
    margin-bottom: 16px;
}

.stButton > button {
    border-radius: 14px;
    min-height: 48px;
    font-weight: 800;
    border: 1px solid #cbd5e1;
}

.stButton > button:hover {
    border-color: #0284c7;
    color: #0284c7;
}

div[role="radiogroup"] {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
}

div[role="radiogroup"] label {
    background: white;
    border: 2px solid #e5e7eb;
    border-radius: 16px;
    padding: 10px 18px;
    box-shadow: 0 2px 8px rgba(15,23,42,0.05);
    min-width: 150px;
    text-align: center;
}

div[role="radiogroup"] label:hover {
    border-color: #0284c7;
}
</style>
""", unsafe_allow_html=True)


# ==================================================
# 基本関数
# ==================================================

def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def speak(text):
    text = text.replace("'", "").replace('"', "")
    components.html(
        f"""
        <script>
        const msg = new SpeechSynthesisUtterance('{text}');
        msg.lang = 'ja-JP';
        msg.rate = 1.0;
        msg.pitch = 1.0;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(msg);
        </script>
        """,
        height=0
    )


def make_qr_image(url):
    qr = qrcode.QRCode(
        version=1,
        box_size=8,
        border=3
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer


# ==================================================
# GPS関数
# ==================================================

def get_gps():
    """
    スマホブラウザのGPSを取得。
    1回目は許可確認だけでNoneになることがある。
    その場合はもう一度押す。
    """
    try:
        location = get_geolocation()

        if location is None:
            return None

        if isinstance(location, dict) and "coords" in location:
            coords = location["coords"]

            return {
                "latitude": coords.get("latitude"),
                "longitude": coords.get("longitude"),
                "accuracy": coords.get("accuracy"),
                "speed": coords.get("speed"),
                "heading": coords.get("heading")
            }

        if isinstance(location, dict) and "latitude" in location and "longitude" in location:
            return {
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "accuracy": location.get("accuracy"),
                "speed": location.get("speed"),
                "heading": location.get("heading")
            }

        return {"error": "GPSの返り値を読み取れませんでした。もう一度押してください。"}

    except Exception as e:
        return {"error": f"GPS取得中にエラーが発生しました：{e}"}


def show_gps_result(gps, user_id, mode):
    if gps is None:
        st.warning("GPS取得中です。位置情報を許可したあと、もう一度GPSボタンを押してください。")
        return

    if isinstance(gps, dict) and "error" in gps:
        st.error(f"GPSを取得できませんでした：{gps['error']}")
        return

    if isinstance(gps, dict) and gps.get("latitude") is not None and gps.get("longitude") is not None:
        accuracy = gps.get("accuracy", None)

        st.session_state.lat = float(gps["latitude"])
        st.session_state.lon = float(gps["longitude"])
        st.session_state.accuracy = accuracy
        st.session_state.speed = gps.get("speed", None)
        st.session_state.heading = gps.get("heading", None)
        st.session_state.gps_fixed = True

        update_location(
            user_id,
            mode,
            st.session_state.lat,
            st.session_state.lon
        )

        if accuracy is not None:
            if accuracy <= 20:
                st.success(f"高精度で現在地を取得しました。GPS精度：約{round(accuracy)}m")
            elif accuracy <= 50:
                st.warning(f"現在地を取得しました。GPS精度：約{round(accuracy)}m")
            else:
                st.warning(
                    f"現在地を取得しましたが、誤差が大きいです。GPS精度：約{round(accuracy)}m。"
                    "屋外や窓際で再取得してください。"
                )
        else:
            st.success("現在地を取得しました。")

        st.rerun()

    else:
        st.warning("GPSの取得結果がまだ返っていません。もう一度GPSボタンを押してください。")


def gps_status_text():
    if st.session_state.accuracy is None:
        return "未取得"

    accuracy = st.session_state.accuracy

    if accuracy <= 20:
        return f"高精度：約{round(accuracy)}m"
    elif accuracy <= 50:
        return f"使用可能：約{round(accuracy)}m"
    else:
        return f"誤差大：約{round(accuracy)}m"


def is_gps_good_enough():
    if st.session_state.accuracy is None:
        return False

    return st.session_state.accuracy <= 50


# ==================================================
# データ保存
# ==================================================

def load_reviews():
    if os.path.exists(REVIEW_FILE):
        try:
            return pd.read_csv(REVIEW_FILE)
        except Exception:
            pass

    df = pd.DataFrame(columns=[
        "datetime", "mode", "place_name", "lat", "lon",
        "danger_level", "category", "comment"
    ])
    df.to_csv(REVIEW_FILE, index=False)
    return df


def save_review(mode, place_name, lat, lon, danger_level, category, comment):
    df = load_reviews()

    new = pd.DataFrame([{
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "place_name": place_name,
        "lat": lat,
        "lon": lon,
        "danger_level": danger_level,
        "category": category,
        "comment": comment
    }])

    df = pd.concat([df, new], ignore_index=True)
    df.to_csv(REVIEW_FILE, index=False)


def load_locations():
    if os.path.exists(LOCATION_FILE):
        try:
            return pd.read_csv(LOCATION_FILE)
        except Exception:
            pass

    df = pd.DataFrame(columns=[
        "user_id", "mode", "lat", "lon", "updated_at"
    ])
    df.to_csv(LOCATION_FILE, index=False)
    return df


def update_location(user_id, mode, lat, lon):
    df = load_locations()
    df = df[df["user_id"] != user_id]

    new = pd.DataFrame([{
        "user_id": user_id,
        "mode": mode,
        "lat": lat,
        "lon": lon,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])

    df = pd.concat([df, new], ignore_index=True)
    df.to_csv(LOCATION_FILE, index=False)


# ==================================================
# 危険地点データ
# ==================================================

def sample_danger_points():
    return pd.DataFrame([
        {
            "place_name": "見通しの悪い交差点",
            "lat": 35.6595,
            "lon": 139.7005,
            "danger_level": 5,
            "category": "飛び出し注意",
            "comment": "歩道から車道へ自転車が出てきやすい地点"
        },
        {
            "place_name": "通学路付近",
            "lat": 35.6610,
            "lon": 139.7020,
            "danger_level": 4,
            "category": "自転車多い",
            "comment": "学生の自転車が多く、朝夕は特に注意"
        },
        {
            "place_name": "路上駐車が多い道路",
            "lat": 35.6578,
            "lon": 139.6992,
            "danger_level": 3,
            "category": "死角あり",
            "comment": "車の陰から自転車が出てくる可能性あり"
        }
    ])


def danger_points():
    base = sample_danger_points()
    reviews = load_reviews()

    if len(reviews) > 0:
        add = reviews[[
            "place_name", "lat", "lon",
            "danger_level", "category", "comment"
        ]].copy()
        df = pd.concat([base, add], ignore_index=True)
    else:
        df = base

    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["danger_level"] = pd.to_numeric(df["danger_level"], errors="coerce").fillna(3)
    df = df.dropna(subset=["lat", "lon"])
    return df


def nearby_dangers(lat, lon, df, radius):
    items = []

    for _, row in df.iterrows():
        d = haversine_m(lat, lon, row["lat"], row["lon"])
        if d <= radius:
            item = row.to_dict()
            item["distance_m"] = round(d, 1)
            items.append(item)

    return sorted(items, key=lambda x: x["distance_m"])


def nearby_users(lat, lon, mode, radius, user_id):
    df = load_locations()

    if len(df) == 0:
        return []

    target = "車モード" if mode == "自転車モード" else "自転車モード"
    df = df[(df["mode"] == target) & (df["user_id"] != user_id)]

    items = []

    for _, row in df.iterrows():
        try:
            d = haversine_m(lat, lon, float(row["lat"]), float(row["lon"]))
            if d <= radius:
                item = row.to_dict()
                item["distance_m"] = round(d, 1)
                items.append(item)
        except Exception:
            pass

    return sorted(items, key=lambda x: x["distance_m"])


# ==================================================
# 地図
# ==================================================

def create_map(lat, lon, mode, danger_df, location_df):
    m = folium.Map(location=[lat, lon], zoom_start=16, tiles="OpenStreetMap")

    if mode == "自転車モード":
        icon_color = "blue"
        icon_name = "bicycle"
    else:
        icon_color = "green"
        icon_name = "car"

    folium.Marker(
        [lat, lon],
        tooltip="現在地",
        popup=f"現在地：{mode}",
        icon=folium.Icon(color=icon_color, icon=icon_name, prefix="fa")
    ).add_to(m)

    folium.Circle(
        location=[lat, lon],
        radius=50,
        color="#0284c7",
        fill=True,
        fill_opacity=0.08,
        tooltip="現在地50m圏内"
    ).add_to(m)

    for _, row in danger_df.iterrows():
        level = int(row["danger_level"])

        if level >= 5:
            color = "red"
        elif level >= 3:
            color = "orange"
        else:
            color = "green"

        popup = f"""
        <b>{row['place_name']}</b><br>
        危険度：{level}<br>
        種類：{row['category']}<br>
        内容：{row['comment']}
        """

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=8 + level,
            color=color,
            fill=True,
            fill_opacity=0.75,
            popup=popup,
            tooltip=f"{row['place_name']} 危険度{level}"
        ).add_to(m)

    if len(location_df) > 0:
        for _, row in location_df.iterrows():
            try:
                other_mode = row["mode"]
                other_lat = float(row["lat"])
                other_lon = float(row["lon"])

                if other_mode == "自転車モード":
                    c = "blue"
                    i = "bicycle"
                else:
                    c = "green"
                    i = "car"

                folium.Marker(
                    [other_lat, other_lon],
                    tooltip=other_mode,
                    popup=f"{other_mode}<br>更新：{row['updated_at']}",
                    icon=folium.Icon(color=c, icon=i, prefix="fa")
                ).add_to(m)

            except Exception:
                pass

    return m


# ==================================================
# セッション
# ==================================================

if "mode" not in st.session_state:
    st.session_state.mode = None

if "lat" not in st.session_state:
    st.session_state.lat = DEFAULT_LAT

if "lon" not in st.session_state:
    st.session_state.lon = DEFAULT_LON

if "accuracy" not in st.session_state:
    st.session_state.accuracy = None

if "speed" not in st.session_state:
    st.session_state.speed = None

if "heading" not in st.session_state:
    st.session_state.heading = None

if "user_id" not in st.session_state:
    st.session_state.user_id = "user_001"

if "gps_fixed" not in st.session_state:
    st.session_state.gps_fixed = False


# ==================================================
# ヘッダー
# ==================================================

st.markdown("""
<div class="hero">
    <div class="hero-title">🚲 レスキューライド</div>
    <div class="hero-sub">
        自転車と車の接近リスク、危険地点、ヒヤリハットを事前に知らせる安全支援アプリ
    </div>
</div>
""", unsafe_allow_html=True)


# ==================================================
# モード選択
# ==================================================

st.markdown('<div class="section-title">① 利用モードを選択</div>', unsafe_allow_html=True)

mode_col1, mode_col2 = st.columns(2)

with mode_col1:
    selected = st.session_state.mode == "自転車モード"

    st.markdown(f"""
    <div class="mode-card {'mode-card-selected' if selected else ''}">
        <div class="mode-icon">🚲</div>
        <div class="mode-title">自転車モード</div>
        <div class="mode-desc">
            危険地点に近づいたら画面と音声で警告。<br>
            車ユーザーが近くにいる場合も接近アラート。<br>
            自転車目線の危険口コミを投稿できます。
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🚲 自転車モードを選択", use_container_width=True):
        st.session_state.mode = "自転車モード"
        st.rerun()

with mode_col2:
    selected = st.session_state.mode == "車モード"

    st.markdown(f"""
    <div class="mode-card {'mode-card-selected' if selected else ''}">
        <div class="mode-icon">🚗</div>
        <div class="mode-title">車モード</div>
        <div class="mode-desc">
            危険地点に近づいたら画面と音声で警告。<br>
            自転車ユーザーが近くにいる場合も接近アラート。<br>
            車目線のヒヤリハット口コミを投稿できます。
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🚗 車モードを選択", use_container_width=True):
        st.session_state.mode = "車モード"
        st.rerun()


# ==================================================
# GPS取得
# ==================================================

st.markdown('<div class="section-title">② 現在地を取得</div>', unsafe_allow_html=True)

st.markdown('<div class="gps-box">', unsafe_allow_html=True)

gps_top1, gps_top2, gps_top3 = st.columns([1.2, 1.2, 2])

with gps_top1:
    st.session_state.user_id = st.text_input(
        "ユーザー名",
        value=st.session_state.user_id,
        help="複数人で試す場合は、それぞれ違う名前にしてください。"
    )

with gps_top2:
    if st.button("📍 GPSで現在地を取得", use_container_width=True):
        if st.session_state.mode is None:
            st.warning("先に自転車モードか車モードを選択してください。")
        else:
            gps = get_gps()
            show_gps_result(gps, st.session_state.user_id, st.session_state.mode)

with gps_top3:
    st.info(
        f"緯度：{st.session_state.lat:.6f} ／ "
        f"経度：{st.session_state.lon:.6f} ／ "
        f"GPS精度：{gps_status_text()}"
    )

st.caption("実証実験ではスマホのSafari/Chromeで開いてください。位置情報を許可したあと、GPSボタンをもう一度押すと反映されやすいです。")

st.markdown('</div>', unsafe_allow_html=True)


if st.session_state.mode is None:
    st.info("まずは上の2つから利用モードを選択してください。")
    st.stop()


mode = st.session_state.mode
user_id = st.session_state.user_id


# ==================================================
# QRコード
# ==================================================

st.markdown('<div class="section-title">③ スマホ展開用QRコード</div>', unsafe_allow_html=True)

qr_col1, qr_col2 = st.columns([2, 1])

with qr_col1:
    app_url = st.text_input(
        "Streamlit Cloudの公開URLを貼ってください",
        placeholder="例：https://rescue-ride.streamlit.app/"
    )

    st.caption("このURLからQRコードを作成します。スマホで読み取ると、そのまま実証実験用アプリを開けます。")

with qr_col2:
    if app_url.strip() != "":
        qr_img = make_qr_image(app_url.strip())
        st.image(qr_img, caption="スマホ実証実験用QRコード", width=220)
    else:
        st.info("公開URLを入力するとQRコードが表示されます。")


# ==================================================
# 項目メニュー
# ==================================================

st.markdown('<div class="section-title">④ 項目メニュー</div>', unsafe_allow_html=True)

page = st.radio(
    "項目メニュー",
    ["安全マップ", "アラート", "口コミ投稿", "口コミ一覧", "実証実験チェック", "テスト"],
    horizontal=True,
    label_visibility="collapsed"
)


# ==================================================
# 基本設定
# ==================================================

st.markdown('<div class="status-bar">', unsafe_allow_html=True)

set_col1, set_col2, set_col3, set_col4 = st.columns([1, 1, 1, 1.4])

with set_col1:
    alert_radius = st.selectbox(
        "危険地点アラート距離",
        [30, 50, 100, 150, 200, 300],
        index=2
    )

with set_col2:
    user_radius = st.selectbox(
        "接近検知距離",
        [20, 30, 50, 100, 150, 200],
        index=2
    )

with set_col3:
    voice_on = st.toggle("音声警告", value=True)

with set_col4:
    if st.button("🔄 現在地を再取得・更新", use_container_width=True):
        gps = get_gps()
        show_gps_result(gps, user_id, mode)

st.markdown('</div>', unsafe_allow_html=True)


with st.expander("GPSが使えない場合の手動入力"):
    manual1, manual2, manual3 = st.columns([1, 1, 1])

    with manual1:
        manual_lat = st.number_input(
            "緯度",
            value=float(st.session_state.lat),
            format="%.6f"
        )

    with manual2:
        manual_lon = st.number_input(
            "経度",
            value=float(st.session_state.lon),
            format="%.6f"
        )

    with manual3:
        st.write("")
        st.write("")
        if st.button("手動位置を反映", use_container_width=True):
            st.session_state.lat = manual_lat
            st.session_state.lon = manual_lon
            st.session_state.accuracy = None
            st.session_state.gps_fixed = True
            update_location(user_id, mode, manual_lat, manual_lon)
            st.success("位置を反映しました。")
            st.rerun()


lat = st.session_state.lat
lon = st.session_state.lon

danger_df = danger_points()
location_df = load_locations()

near_danger = nearby_dangers(lat, lon, danger_df, alert_radius)
near_user = nearby_users(lat, lon, mode, user_radius, user_id)


# ==================================================
# メトリクス
# ==================================================

m1, m2, m3, m4 = st.columns(4)

with m1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{mode.replace('モード', '')}</div>
        <div class="metric-label">現在のモード</div>
    </div>
    """, unsafe_allow_html=True)

with m2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{len(danger_df)}</div>
        <div class="metric-label">登録危険地点</div>
    </div>
    """, unsafe_allow_html=True)

with m3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{len(near_danger)}</div>
        <div class="metric-label">近くの危険地点</div>
    </div>
    """, unsafe_allow_html=True)

with m4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{len(near_user)}</div>
        <div class="metric-label">接近中の相手</div>
    </div>
    """, unsafe_allow_html=True)


st.markdown("<br>", unsafe_allow_html=True)


# ==================================================
# 安全マップ
# ==================================================

if page == "安全マップ":
    st.markdown('<div class="section-title">🗺️ 安全マップ</div>', unsafe_allow_html=True)

    info1, info2 = st.columns([2, 1])

    with info1:
        m = create_map(lat, lon, mode, danger_df, location_df)
        st_folium(m, width=None, height=570)

    with info2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("現在の状態")

        speed = st.session_state.speed
        heading = st.session_state.heading

        speed_text = "不明" if speed is None else f"{round(speed * 3.6, 1)}km/h"
        heading_text = "不明" if heading is None else f"{round(heading)}度"

        st.write(f"**ユーザー名：** {user_id}")
        st.write(f"**モード：** {mode}")
        st.write(f"**緯度：** {lat:.6f}")
        st.write(f"**経度：** {lon:.6f}")
        st.write(f"**GPS精度：** {gps_status_text()}")
        st.write(f"**速度：** {speed_text}")
        st.write(f"**進行方向：** {heading_text}")
        st.write(f"**危険地点警告距離：** {alert_radius}m")
        st.write(f"**接近検知距離：** {user_radius}m")

        if is_gps_good_enough():
            st.success("実証実験に使えるGPS精度です。")
        else:
            st.warning("GPS精度が不足しています。スマホで屋外・窓際で再取得してください。")

        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("地図の見方")
        st.write("🔵 自転車ユーザー")
        st.write("🟢 車ユーザー")
        st.write("🔴 危険度が高い地点")
        st.write("🟠 注意が必要な地点")
        st.write("青い円：現在地50m圏内")
        st.markdown('</div>', unsafe_allow_html=True)


# ==================================================
# アラート
# ==================================================

elif page == "アラート":
    st.markdown('<div class="section-title">🚨 アラート</div>', unsafe_allow_html=True)

    messages = []

    if not is_gps_good_enough():
        st.warning("GPS精度が低い状態です。実証実験ではGPS精度50m以内を目安にしてください。")

    if len(near_danger) > 0:
        first = near_danger[0]

        msg = (
            f"危険地点が近くにあります。"
            f"{first['place_name']}まで約{first['distance_m']}メートルです。"
            f"注意してください。"
        )
        messages.append(msg)

        st.markdown(f"""
        <div class="alert-danger">
            ⚠️ 危険地点接近アラート<br>
            {first['place_name']} まで約 {first['distance_m']} m<br>
            種類：{first['category']} ／ 危険度：{int(first['danger_level'])}<br>
            内容：{first['comment']}
        </div>
        """, unsafe_allow_html=True)

    else:
        st.markdown("""
        <div class="alert-safe">
            ✅ 現在、設定範囲内に危険地点はありません。
        </div>
        """, unsafe_allow_html=True)

    if len(near_user) > 0:
        first_user = near_user[0]

        if mode == "自転車モード":
            title = "🚗 車接近アラート"
            target = "車"
            msg = (
                f"近くに車が接近しています。"
                f"距離は約{first_user['distance_m']}メートルです。"
                f"注意してください。"
            )
        else:
            title = "🚲 自転車接近アラート"
            target = "自転車"
            msg = (
                f"近くに自転車が接近しています。"
                f"距離は約{first_user['distance_m']}メートルです。"
                f"注意してください。"
            )

        messages.append(msg)

        st.markdown(f"""
        <div class="alert-warning">
            {title}<br>
            近くに{target}ユーザーがいます。距離：約 {first_user['distance_m']} m
        </div>
        """, unsafe_allow_html=True)

    else:
        if mode == "自転車モード":
            st.info("現在、近くに車ユーザーはいません。")
        else:
            st.info("現在、近くに自転車ユーザーはいません。")

    if voice_on and len(messages) > 0:
        if st.button("🔊 音声警告を再生", use_container_width=True):
            speak(" ".join(messages))

    st.markdown("### 近くの危険地点一覧")

    if len(near_danger) > 0:
        df = pd.DataFrame(near_danger)

        st.dataframe(
            df[["place_name", "distance_m", "danger_level", "category", "comment"]].rename(columns={
                "place_name": "場所",
                "distance_m": "距離m",
                "danger_level": "危険度",
                "category": "種類",
                "comment": "内容"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("近くの危険地点はありません。")


# ==================================================
# 口コミ投稿
# ==================================================

elif page == "口コミ投稿":
    st.markdown('<div class="section-title">💬 口コミ投稿</div>', unsafe_allow_html=True)

    if not is_gps_good_enough():
        st.warning("GPS精度が低いです。口コミ地点を正確に残すには、GPSを再取得してください。")

    if mode == "自転車モード":
        st.info("自転車ユーザーとして、危ないと感じた地点を投稿できます。")
        categories = [
            "車の接近が怖い",
            "見通しが悪い",
            "歩道が狭い",
            "路上駐車が多い",
            "交差点が危ない",
            "その他"
        ]
    else:
        st.info("車ユーザーとして、自転車の飛び出しやヒヤリハット地点を投稿できます。")
        categories = [
            "自転車の飛び出し",
            "歩道から車道へのカットイン",
            "見通しが悪い",
            "通学路で自転車が多い",
            "急ブレーキが必要だった",
            "その他"
        ]

    with st.form("review_form"):
        c1, c2 = st.columns(2)

        with c1:
            place_name = st.text_input("場所名", placeholder="例：〇〇交差点、〇〇通り")
            danger_level = st.slider("危険度", 1, 5, 3)
            category = st.selectbox("危険の種類", categories)

        with c2:
            comment = st.text_area(
                "コメント",
                placeholder="例：歩道から自転車が急に出てきやすい。夕方は特に注意が必要。"
            )
            use_current = st.checkbox("現在地を投稿地点にする", value=True)

        if use_current:
            post_lat = lat
            post_lon = lon
        else:
            lc1, lc2 = st.columns(2)

            with lc1:
                post_lat = st.number_input("投稿地点の緯度", value=float(lat), format="%.6f")

            with lc2:
                post_lon = st.number_input("投稿地点の経度", value=float(lon), format="%.6f")

        submitted = st.form_submit_button("口コミを投稿する")

        if submitted:
            if place_name.strip() == "":
                st.error("場所名を入力してください。")
            elif comment.strip() == "":
                st.error("コメントを入力してください。")
            else:
                save_review(
                    mode,
                    place_name,
                    post_lat,
                    post_lon,
                    danger_level,
                    category,
                    comment
                )
                st.success("口コミを投稿しました。")
                st.rerun()


# ==================================================
# 口コミ一覧
# ==================================================

elif page == "口コミ一覧":
    st.markdown('<div class="section-title">📝 口コミ一覧</div>', unsafe_allow_html=True)

    reviews = load_reviews()

    if len(reviews) == 0:
        st.info("口コミはまだありません。")

    else:
        f1, f2 = st.columns([1, 3])

        with f1:
            view = st.selectbox("表示", ["すべて", "自転車モード", "車モード"])

        if view == "すべて":
            show = reviews
        else:
            show = reviews[reviews["mode"] == view]

        if len(show) == 0:
            st.info("このモードの口コミはまだありません。")
        else:
            st.dataframe(
                show.sort_values("datetime", ascending=False).rename(columns={
                    "datetime": "投稿日時",
                    "mode": "モード",
                    "place_name": "場所",
                    "lat": "緯度",
                    "lon": "経度",
                    "danger_level": "危険度",
                    "category": "種類",
                    "comment": "コメント"
                }),
                use_container_width=True,
                hide_index=True
            )


# ==================================================
# 実証実験チェック
# ==================================================

elif page == "実証実験チェック":
    st.markdown('<div class="section-title">✅ 実証実験チェック</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("実証実験前チェック")

    if app_url.strip() == "":
        st.warning("QRコード用の公開URLが未入力です。")
    else:
        st.success("QRコード用URLは入力済みです。")

    if st.session_state.mode is None:
        st.warning("モードが未選択です。")
    else:
        st.success(f"モード選択済み：{mode}")

    if st.session_state.accuracy is None:
        st.warning("GPSが未取得です。")
    elif st.session_state.accuracy <= 50:
        st.success(f"GPS精度は実証実験に使用可能です：約{round(st.session_state.accuracy)}m")
    else:
        st.warning(f"GPS誤差が大きいです：約{round(st.session_state.accuracy)}m。再取得してください。")

    st.write(f"現在地：{lat:.6f}, {lon:.6f}")
    st.write(f"危険地点アラート距離：{alert_radius}m")
    st.write(f"接近検知距離：{user_radius}m")

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""
    ### 実証実験のやり方

    1. Streamlit Cloudでアプリを公開する  
    2. 公開URLをQRコード欄に貼る  
    3. 表示されたQRコードをスマホで読み取る  
    4. 自転車モード・車モードを選ぶ  
    5. 位置情報を許可する  
    6. GPSを取得する  
    7. 危険地点に近づいた時のアラート、口コミ投稿、接近アラートを確認する  

    ※ 車・自転車の接近アラートは、相手側もアプリを開いてGPS共有している場合に反応します。
    """)


# ==================================================
# テスト
# ==================================================

elif page == "テスト":
    st.markdown('<div class="section-title">⚙️ テスト設定</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="card">
    1人で発表・テストするときに、近くに車や自転車がいる状態を作れます。<br>
    自転車モードなら近くに車を追加、車モードなら近くに自転車を追加します。
    </div>
    """, unsafe_allow_html=True)

    if mode == "自転車モード":
        demo_mode = "車モード"
        demo_id = "demo_car"
    else:
        demo_mode = "自転車モード"
        demo_id = "demo_bicycle"

    t1, t2, t3 = st.columns(3)

    with t1:
        if st.button(f"近くに{demo_mode}を追加", use_container_width=True):
            update_location(
                demo_id,
                demo_mode,
                lat + 0.00030,
                lon + 0.00030
            )
            st.success(f"近くに{demo_mode}を追加しました。")
            st.rerun()

    with t2:
        if st.button("接近ユーザーをリセット", use_container_width=True):
            if os.path.exists(LOCATION_FILE):
                os.remove(LOCATION_FILE)
            st.success("接近ユーザーをリセットしました。")
            st.rerun()

    with t3:
        if st.button("口コミをリセット", use_container_width=True):
            if os.path.exists(REVIEW_FILE):
                os.remove(REVIEW_FILE)
            st.success("口コミをリセットしました。")
            st.rerun()

    st.markdown("### 位置情報データ")

    loc = load_locations()

    if len(loc) == 0:
        st.info("位置情報データはありません。")
    else:
        st.dataframe(loc, use_container_width=True, hide_index=True)


# ==================================================
# フッター
# ==================================================

st.markdown("---")
st.caption(
    "※ GPS精度はスマホ・屋外・HTTPS環境で向上します。"
    "※ 車・自転車の接近検知は、相手もアプリを開いてGPS共有している場合に反応します。"
    "本格運用ではFirebaseやSupabaseなどのリアルタイムデータベースが必要です。"
)