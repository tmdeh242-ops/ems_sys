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
# 🔐 보안 및 이메일 설정 (Secrets 반영)
# =========================
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

ADMIN_PASSWORD = "3090"

# Streamlit Secrets에서 설정값 불러오기
try:
    EMAIL_SENDER = st.secrets["EMAIL_ADDRESS"]
    EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
    ADMIN_RECEIVER = st.secrets["ADMIN_NOTIFY_EMAIL"]
except KeyError as e:
    st.error(f"Secrets 설정 오류: {e} 항목을 찾을 수 없습니다.")
    st.stop()

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
    except Exception as e:
        st.sidebar.error(f"메일 발송 에러: {e}")
        return False

# =========================
# 📊 데이터 동기화 로직
# =========================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# 서비스 계정 정보도 Secrets에서 관리하는 것을 권장합니다.
creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
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
    st.markdown("### 🏢 EMS 매물등록 관리시스템")
    choice = st.radio("메뉴 이동", ["📊 통합 대시보드", "🔍 등록 매물 조회", "🔐 관리자 모드"])
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# =========================
# 1️⃣ 📊 통합 대시보드
# =========================
if choice == "📊 통합 대시보드":
    st.title("📊 실시간 통합 현황")
    if df_total.empty:
        st.warning("표시할 데이터가 없습니다.")
    else:
        c1, c2 = st.columns(2)
        c1.metric("📌 전체 관리 매물", f"{len(df_total)}개")
        c2.metric("✅ 즉시 관람 가능", f"{len(df_total[df_total['거래여부'] == '관람가능'])}개")

        status_df = df_total.groupby(['단지', '거래여부']).size().reset_index(name='수량')
        fig_bar = px.bar(status_df, x='단지', y='수량', color='거래여부', barmode='group', title="단지별 보유 현황",
                         category_orders={"단지": ["1단지", "2단지", "3단지"]})
        fig_bar.update_yaxes(dtick=1, rangemode='tozero')
        st.plotly_chart(fig_bar, use_container_width=True)

# =========================
# 2️⃣ 🔍 등록 매물 조회
# =========================
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    search_q = st.text_input("동 또는 호수 입력 (예: 101)", "")
    df_v = df_total.copy()
    if search_q:
        df_v = df_v[df_v["동"].astype(str).str.contains(search_q) | df_v["호수"].astype(str).str.contains(search_q)]
    st.dataframe(df_v[["단지", "동", "호수", "타입", "거래여부"]], use_container_width=True, hide_index=True)

# =========================
# 3️⃣ 🔐 관리자 모드
# =========================
elif choice == "🔐 관리자 모드":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 인증", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📅 세대관람 예약", "📊 세대관람 현황", "⚙️ 관람 가능여부 관리"])

    with tab1:
        res_dj = st.selectbox("예약 단지", ["1단지", "2단지", "3단지"])
        f_unit = df_total[df_total["단지"] == res_dj]
        
        if f_unit.empty:
            st.error("데이터가 없습니다.")
        else:
            with st.form("res_form_v4"):
                r_name = st.text_input("예약자(중개업소) 명칭")
                r_count = st.selectbox("관람 세대수", [1, 2, 3])
                
                r_items = []
                for i in range(r_count):
                    st.write(f"**세대 {i+1}**")
                    col_d, col_h = st.columns(2)
                    d_sel = col_d.selectbox("동 선택", sorted(f_unit["동"].unique()), key=f"d_v4_{i}")
                    h_sel = col_h.selectbox("호수 선택", sorted(f_unit[f_unit["동"]==d_sel]["호수"].unique()), key=f"h_v4_{i}")
                    
                    # 💡 IndexError 방지: empty 체크 후 iloc[0] 사용
                    match = f_unit[(f_unit["동"]==d_sel) & (f_unit["호수"]==h_sel)]
                    if not match.empty:
                        m_row = match.iloc[0]
                        st.caption(f"타입: {m_row['타입']} | 상태: {m_row['거래여부']}")
                        r_items.append({"동":d_sel, "호수":h_sel, "타입":m_row['타입'], "상태":m_row['거래여부']})
                    else:
                        st.caption("⚠️ 선택한 세대를 찾을 수 없습니다.")
                
                t_val = st.selectbox("방문 시간", [f"{h:02d}:00" for h in range(8,21)])
                memo = st.text_input("상세 메모")
                
                # 폼 제출 버튼
                if st.form_submit_button("📅 예약 확정 및 메일 발송", use_container_width=True):
                    if not r_name:
                        st.error("예약자명을 입력해주세요.")
                    elif any(x["상태"] == "거래완료" for x in r_items):
                        st.error("거래완료 세대가 포함되어 있습니다.")
                    else:
                        target_ws = f"{res_dj}_관람예약" if int(t_val[:2]) < 16 else "야간_관람예약"
                        ws = sheet.worksheet(target_ws)
                        rows = [[date.today().strftime("%Y-%m-%d"), r_name, "", f"{r_count}세대", s["동"], s["호수"], s["타입"], t_val, "", memo] for s in r_items]
                        ws.append_rows(rows)
                        
                        # 메일 알림 발송
                        detail_msg = "\n".join([f"- {s['동']}동 {s['호수']}호" for s in r_items])
                        body = f"새 예약 알림\n예약자: {r_name}\n시간: {t_val}\n세대:\n{detail_msg}\n메모: {memo}"
                        send_email_notification(f"📢 [{res_dj}] 예약 알림", body)
                        
                        st.success("예약이 저장되었습니다.")
                        st.cache_data.clear()

    with tab2:
        v_dj = st.selectbox("현황 조회 단지", ["1단지", "2단지", "3단지", "야간"])
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            df_c = pd.DataFrame(v_data[1:], columns=["날짜","예약자","중개업소","세대수","동","호수","타입","시간","매니저","비고"])
            st.dataframe(df_c[df_c['날짜'] == date.today().strftime("%Y-%m-%d")], use_container_width=True, hide_index=True)
        except: st.info("관람 내역이 없습니다.")

    with tab3:
        u_dj = st.selectbox("관리 단지", ["1단지", "2단지", "3단지"], key="final_u_dj")
        u_f = df_total[df_total["단지"]==u_dj]
        if not u_f.empty:
            ud = st.selectbox("동", sorted(u_f["동"].unique()), key="final_u_d")
            uh = st.selectbox("호수", sorted(u_f[u_f["동"]==ud]["호수"].unique()), key="final_u_h")
            match_u = u_f[(u_f["동"]==ud) & (u_f["호수"]==uh)]
            if not match_u.empty:
                curr_s = match_u.iloc[0]
                new_s = st.radio("상태 변경", ["관람가능", "거래완료"], index=0 if curr_s["거래여부"]=="관람가능" else 1)
                if st.button("💾 변경 저장", use_container_width=True):
                    ws = sheet.worksheet(f"{u_dj}_{curr_s['거래유형']}")
                    for i, r in enumerate(ws.get_all_values()):
                        if r[2] == ud and r[3] == uh:
                            ws.update_cell(i+1, 9, new_s)
                            break
                    st.success("업데이트 완료!")
                    st.cache_data.clear()
                    st.rerun()
