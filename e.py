import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
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
    except: return False

# =========================
# 📊 데이터 로드 및 정렬 로직
# =========================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
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
                # 숫자 정렬을 위한 전처리
                df["동_num"] = pd.to_numeric(df["동"], errors='coerce').fillna(0)
                df["호_num"] = pd.to_numeric(df["호수"], errors='coerce').fillna(0)
                df_list.append(df)
        except: continue
    
    if df_list:
        full_df = pd.concat(df_list, ignore_index=True)
        return full_df.sort_values(by=["단지", "동_num", "호_num"])
    return pd.DataFrame(columns=cols + ["단지", "거래유형"])

df_total = load_all_data()

# 강조 UI 스타일 함수
def color_status(val):
    if val == "관람가능": color = '#d4edda' # 연초록
    elif val == "거래완료": color = '#f8d7da' # 연빨강
    else: color = 'white'
    return f'background-color: {color}'

# =========================
# 🏠 사이드바 메뉴
# =========================
with st.sidebar:
    st.markdown("### 🏢 EMS 관리 센터")
    choice = st.radio("메뉴 이동", ["📊 실시간 매물 현황", "🔍 등록 매물 조회", "🔐 관리자 모드"])
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# =========================
# 1️⃣ 📊 실시간 매물 현황
# =========================
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 매물 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체 관리 매물", f"{len(df_total)}개")
    c2.metric("✅ 완료 매물", f"{len(df_total[df_total['거래여부'] == '거래완료'])}개")
    c3.metric("🏠 관람 가능 매물", f"{len(df_total[df_total['거래여부'] == '관람가능'])}개")

    st.divider()
    st.subheader("🏆 완료 세대 현황")
    df_done = df_total[df_total["거래여부"] == "거래완료"].copy()
    view_cols = ["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부"]
    st.dataframe(df_done[view_cols].style.applymap(color_status, subset=['거래여부']), use_container_width=True, hide_index=True)

# =========================
# 2️⃣ 🔍 등록 매물 조회
# =========================
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    f1, f2, f3, f4 = st.columns(4)
    s_danji = f1.multiselect("단지", df_total["단지"].unique())
    s_bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique())
    s_gubun = f3.multiselect("매물구분", df_total["매물구분"].unique())
    s_type = f4.multiselect("타입", sorted(df_total["타입"].unique()))
    search_q = st.text_input("동 또는 호수 직접 검색")
    
    df_v = df_total.copy()
    if s_danji: df_v = df_v[df_v["단지"].isin(s_danji)]
    if s_bunyang: df_v = df_v[df_v["분양구분"].isin(s_bunyang)]
    if s_gubun: df_v = df_v[df_v["매물구분"].isin(s_gubun)]
    if s_type: df_v = df_v[df_v["타입"].isin(s_type)]
    if search_q: df_v = df_v[df_v["동"].str.contains(search_q) | df_v["호수"].str.contains(search_q)]
    
    st.dataframe(df_v[["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부"]].style.applymap(color_status, subset=['거래여부']), use_container_width=True, hide_index=True)

# =========================
# 3️⃣ 🔐 관리자 모드 (예약 로직 전면 개편)
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
        st.subheader("📅 세대관람 예약 등록")
        res_dj = st.selectbox("예약 단지 선택", ["1단지", "2단지", "3단지"])
        f_unit = df_total[df_total["단지"] == res_dj]
        r_count = st.selectbox("관람 세대수 선택", [1, 2, 3], index=0)
        
        # 💡 [렉 해결] 동/호수 선택을 form 밖으로 꺼내어 실시간 반영 보장
        r_items = []
        for i in range(r_count):
            with st.container(border=True):
                st.markdown(f"**📍 세대 선택 {i+1}**")
                col1, col2 = st.columns(2)
                # 정렬된 동/호수 리스트 제공
                unique_dongs = sorted(f_unit["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                d_sel = col1.selectbox("동", unique_dongs, key=f"d_live_{i}")
                
                filtered_hos = f_unit[f_unit["동"]==d_sel]
                unique_hos = sorted(filtered_hos["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                h_sel = col2.selectbox("호수", unique_hos, key=f"h_live_{i}")
                
                match = f_unit[(f_unit["동"]==d_sel) & (f_unit["호수"]==h_sel)]
                if not match.empty:
                    m_row = match.iloc[0]
                    # 상태 강조 표시
                    st.markdown(f"✅ 타입: **{m_row['타입']}** | 현재상태: **{m_row['거래여부']}**")
                    r_items.append({"동":d_sel, "호수":h_sel, "타입":m_row['타입'], "상태":m_row['거래여부']})

        # 기타 정보 입력 (form)
        with st.form("other_info_form"):
            c1, c2 = st.columns(2)
            r_name = c1.text_input("예약자 성함")
            r_agency = c2.text_input("중개업소 명칭")
            r_manager = st.text_input("동행 매니저")
            t_val = st.selectbox("방문 시간", [f"{h:02d}:00" for h in range(8,21)])
            memo_input = st.text_input("상세 메모")
            
            if st.form_submit_button("📅 예약 최종 확정", use_container_width=True):
                if not r_name: st.error("예약자 성함을 입력해주세요.")
                elif any(x["상태"] == "거래완료" for x in r_items): st.error("거래완료 세대가 포함되어 있습니다.")
                else:
                    target_ws = f"{res_dj}_관람예약" if int(t_val[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target_ws)
                    # 데이터 구조 (10열): 날짜, 예약자, 업소, 세대수, 동, 호수, 타입, 시간, 매니저, 비고
                    rows = [[date.today().strftime("%Y-%m-%d"), r_name, r_agency, f"{r_count}세대", s["동"], s["호수"], s["타입"], t_val, r_manager, memo_input] for s in r_items]
                    ws.append_rows(rows)
                    
                    # 메일 알림
                    m_body = f"새로운 세대관람 예약\n- 예약자: {r_name}\n- 중개업소: {r_agency}\n- 시간: {t_val}\n- 매니저: {r_manager}\n\n[관람세대]\n"
                    for s in r_items: m_body += f"🏠 {s['동']}동 {s['호수']}호 ({s['타입']})\n"
                    m_body += f"\n- 메모: {memo_input}"
                    send_email_notification(f"📢 [{res_dj}] 예약 알림: {r_name}님", m_body)
                    
                    st.success("예약이 완료되었습니다!")
                    st.cache_data.clear()

    with tab2:
        v_dj = st.selectbox("현황 조회 단지", ["1단지", "2단지", "3단지", "야간"])
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            df_c = pd.DataFrame(v_data[1:], columns=["날짜","예약자","중개업소","세대수","동","호수","타입","시간","동행매니저","비고"])
            st.dataframe(df_c[df_c['날짜'] == date.today().strftime("%Y-%m-%d")], use_container_width=True, hide_index=True)
        except: st.info("내역이 없습니다.")

    with tab3:
        u_dj = st.selectbox("관리 단지", ["1단지", "2단지", "3단지"], key="m_dj")
        u_f = df_total[df_total["단지"]==u_dj]
        if not u_f.empty:
            c1, c2 = st.columns(2)
            # 관리 페이지용 정렬
            u_dongs = sorted(u_f["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
            ud = c1.selectbox("동", u_dongs, key="m_d")
            u_hos = sorted(u_f[u_f["동"]==ud]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
            uh = c2.selectbox("호수", u_hos, key="m_h")
            
            match_u = u_f[(u_f["동"]==ud) & (u_f["호수"]==uh)]
            if not match_u.empty:
                curr = match_u.iloc[0]
                st.info(f"현재 상태: **{curr['거래여부']}**")
                new_s = st.radio("상태 변경", ["관람가능", "거래완료"], index=0 if curr['거래여부']=="관람가능" else 1)
                if st.button("💾 업데이트 저장", use_container_width=True):
                    ws = sheet.worksheet(f"{u_dj}_{curr['거래유형']}")
                    for i, r in enumerate(ws.get_all_values()):
                        if r[2] == ud and r[3] == uh:
                            ws.update_cell(i+1, 9, new_s)
                            break
                    st.success("반영 완료!")
                    st.cache_data.clear()
                    st.rerun()
