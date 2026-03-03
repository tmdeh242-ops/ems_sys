import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime, timedelta
import plotly.express as px
import smtplib
from email.mime.text import MIMEText
import json
import os

# 1. 페이지 설정
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")

# =========================
# 🔐 보안 및 이메일 설정
# =========================
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

ADMIN_PASSWORD = "3090"
EMAIL_SENDER = os.environ.get["EMAIL_ADDRESS"]
EMAIL_PASSWORD = os.environ.get["EMAIL_PASSWORD"]
ADMIN_RECEIVER = os.environ.get["ADMIN_NOTIFY_EMAIL"]

def send_email_notification(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = ADMIN_RECEIVER
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, ADMIN_RECEIVER, msg.as_string())
        return True
    except: return False

# =========================
# 📊 데이터 동기화
# =========================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("EMS")

@st.cache_data(show_spinner="데이터 동기화 중...", ttl=300)
def load_all_data():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    cols = ["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부"]
    df_list = []
    for s in sheets:
        try:
            ws = sheet.worksheet(s)
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=cols)
                df["단지"] = s.split("_")[0]
                df["거래유형"] = s.split("_")[1]
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame(columns=cols + ["단지", "거래유형"])

df_total = load_all_data()

# =========================
# 🏠 사이드바 메뉴
# =========================
with st.sidebar:
    st.markdown("### 🏢 EMS 관리 센터")
    choice = st.radio("메뉴 이동", ["📊 통합 대시보드", "🔍 등록 매물 조회", "🔐 관리자 모드"])
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# =========================
# 1️⃣ 📊 통합 대시보드 (그래프 축 수정 완료)
# =========================
if choice == "📊 통합 대시보드":
    st.title("📊 실시간 통합 현황")
    
    c1, c2 = st.columns(2)
    t_m = len(df_total)
    a_m = len(df_total[df_total["거래여부"] == "관람가능"])
    c1.metric("📌 전체 관리 매물", f"{t_m}개")
    c2.metric("✅ 즉시 관람 가능", f"{a_m}개")

    st.divider()
    
    # 📈 [업그레이드] 그래프 범위 및 정수화 설정
    if not df_total.empty:
        status_df = df_total.groupby(['단지', '거래여부']).size().reset_index(name='수량')
        
        fig_bar = px.bar(status_df, 
                         x='단지', y='수량', color='거래여부', 
                         barmode='group', title="단지별 보유 현황 (단위: 세대)",
                         category_orders={"단지": ["1단지", "2단지", "3단지"]}, # 단지 순서 고정
                         labels={"수량": "매물 수량(세대)", "단지": "단지명"})
        
        # 💡 축 설정 핵심: 소수점 제거 및 0 이하 제거
        fig_bar.update_yaxes(dtick=1, rangemode='tozero') 
        fig_bar.update_layout(margin=dict(l=20, r=20, t=60, b=20))
        st.plotly_chart(fig_bar, use_container_width=True)

    st.write("#### 🏠 전체 매물 간략 정보")
    st.dataframe(df_total[["단지", "동", "호수", "타입", "거래여부"]], use_container_width=True, hide_index=True)

# =========================
# 2️⃣ 🔍 등록 매물 조회 (명칭 변경)
# =========================
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    search_q = st.text_input("동 또는 호수를 입력하세요 (예: 101)", "")
    
    df_v = df_total.copy()
    if search_q:
        df_v = df_v[df_v["동"].str.contains(search_q) | df_v["호수"].str.contains(search_q)]
    
    for _, row in df_v.head(30).iterrows():
        with st.container(border=True):
            col_a, col_b = st.columns([3, 1])
            col_a.markdown(f"**{row['단지']} {row['동']}동 {row['호수']}호** ({row['타입']})")
            col_a.caption(f"구분: {row['거래유형']} | 분양: {row['분양구분']}")
            color = "green" if row['거래여부'] == "관람가능" else "red"
            col_b.markdown(f":{color}[**{row['거래여부']}**]")

# =========================
# 3️⃣ 🔐 관리자 모드 (탭 명칭 변경 및 기능)
# =========================
elif choice == "🔐 관리자 모드":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 인증", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        st.stop()

    # 💡 요청하신 명칭으로 탭 변경
    tab1, tab2, tab3 = st.tabs(["📅 세대관람 예약", "📊 세대관람 현황", "⚙️ 관람 가능여부 관리"])

    # --- 📅 세대관람 예약 ---
    with tab1:
        res_dj = st.selectbox("예약 단지", ["1단지", "2단지", "3단지"])
        f_unit = df_total[df_total["단지"] == res_dj]
        
        with st.form("res_form_final"):
            r_name = st.text_input("예약자(중개업소) 성함/명칭")
            r_count = st.select_slider("관람 세대수 선택", options=[1, 2, 3])
            
            r_items = []
            for i in range(r_count):
                st.markdown(f"**[{i+1}번 세대 선택]**")
                c1, c2 = st.columns(2)
                d = c1.selectbox(f"동 선택", sorted(f_unit["동"].unique()), key=f"d_final_{i}")
                h = c2.selectbox(f"호수 선택", sorted(f_unit[f_unit["동"]==d]["호수"].unique()), key=f"h_final_{i}")
                m_m = f_unit[(f_unit["동"]==d) & (f_unit["호수"]==h)].iloc[0]
                st.caption(f"→ 현재 상태: {m_m['거래여부']}")
                r_items.append({"동":d, "호수":h, "타입":m_m['타입'], "상태":m_m['거래여부']})
            
            t_v = st.selectbox("방문 예정 시간", [f"{h:02d}:00" for h in range(8,21)])
            memo = st.text_input("상세 메모")
            
            if st.form_submit_button("📅 예약 확정 (메일 발송)", use_container_width=True):
                if any(x["상태"] == "거래완료" for x in r_items):
                    st.error("이미 거래가 완료된 세대가 포함되어 있습니다.")
                elif not r_name:
                    st.warning("예약자 명칭을 입력해주세요.")
                else:
                    target_s = f"{res_dj}_관람예약" if int(t_v[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target_s)
                    rows = [[date.today().strftime("%Y-%m-%d"), r_name, "", f"{r_count}세대", s["동"], s["호수"], s["타입"], t_v, "", memo] for s in r_items]
                    ws.append_rows(rows)
                    
                    # 메일 알림
                    body = f"새로운 세대관람 예약\n- 단지: {res_dj}\n- 예약자: {r_name}\n- 시간: {t_v}\n- 메모: {memo}"
                    send_email_notification(f"📢 [{res_dj}] 신규 세대관람 예약 알림", body)
                    
                    st.success("✅ 예약이 정상적으로 등록되었습니다.")
                    st.cache_data.clear()

    # --- 📊 세대관람 현황 (카드형) ---
    with tab2:
        v_dj = st.selectbox("현황 조회 단지", ["1단지", "2단지", "3단지", "야간"])
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            df_c = pd.DataFrame(v_data[1:], columns=["날짜","예약자","중개업소","세대수","동","호수","타입","시간","매니저","비고"])
            df_c['날짜'] = pd.to_datetime(df_c['날짜'])
            df_view = df_c[df_c['날짜'].dt.date >= date.today()].sort_values(by=['날짜', '시간'])
            
            for _, r in df_view.iterrows():
                with st.container(border=True):
                    st.markdown(f"**📅 {r['날짜'].strftime('%m/%d')} {r['시간']}**")
                    st.write(f"🏠 {r['동']}동 {r['호수']}호 | {r['예약자']}")
                    if r['비고']: st.caption(f"📝 메모: {r['비고']}")
        except: st.info("등록된 관람 현황이 없습니다.")

    # --- ⚙️ 관람 가능여부 관리 ---
    with tab3:
        st.subheader("매물 상태 수동 변경")
        u_dj = st.selectbox("단지 선택", ["1단지", "2단지", "3단지"], key="m_u")
        u_f = df_total[df_total["단지"]==u_dj]
        if not u_f.empty:
            c1, c2 = st.columns(2)
            ud = c1.selectbox("동", sorted(u_f["동"].unique()), key="m_ud")
            uh = c2.selectbox("호수", sorted(u_f[u_f["동"]==ud]["호수"].unique()), key="m_uh")
            curr = u_f[(u_f["동"]==ud) & (u_f["호수"]==uh)].iloc[0]
            st.info(f"현재 상태: **{curr['거래여부']}**")
            new_s = st.radio("변경할 상태 선택", ["관람가능", "거래완료"], horizontal=True)
            if st.button("💾 상태 업데이트 반영", use_container_width=True):
                ws = sheet.worksheet(f"{u_dj}_{curr['거래유형']}")
                for i, r in enumerate(ws.get_all_values()):
                    if r[2] == ud and r[3] == uh:
                        ws.update_cell(i+1, 9, new_s)
                        break
                st.success("상태가 성공적으로 변경되었습니다.")
                st.cache_data.clear()
                st.rerun()
