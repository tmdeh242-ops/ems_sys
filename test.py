import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date
from st_aggrid import AgGrid, GridOptionsBuilder
import smtplib
from email.mime.text import MIMEText
import json
import os

st.set_page_config(page_title="EMS 관람예약 시스템", layout="wide")

# =========================
# 🔐 관리자 세션
# =========================
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

ADMIN_PASSWORD = "3090"

# ------------------------------
# 구글 시트 인증
# ------------------------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# 환경변수 로드 (기존 방식 유지)
creds_dict = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("EMS")

# =========================
# CSS (기존 디자인 유지)
# =========================
st.markdown("""
<style>
.main {background-color: #f4f7fa;}
.sidebar .sidebar-content {background-color: #002b45;color: white;}
div.stButton > button {
    background-color: #004c7a;
    color: white;
    border-radius: 8px;
    height: 3em;
}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align:center;color:#002b45;'>🏢 EMS 매물등록관리시스템</h1>", unsafe_allow_html=True)

# =========================
# 📩 이메일 알림
# =========================
def send_email_notification(content):
    try:
        sender = os.environ["EMAIL_ADDRESS"]
        password = os.environ["EMAIL_PASSWORD"]
        receiver = os.environ["ADMIN_NOTIFY_EMAIL"]

        msg = MIMEText(content)
        msg["Subject"] = "📢 새로운 관람 예약 등록"
        msg["From"] = sender
        msg["To"] = receiver

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
    except:
        pass

# ------------------------------
# 데이터 로드 캐싱 (TTL 추가로 성능 개선)
# ------------------------------
@st.cache_data(show_spinner="데이터를 불러오는 중...", ttl=600)
def load_sheet_data(sheets_to_load, columns):
    df_list = []
    for s in sheets_to_load:
        try:
            ws = sheet.worksheet(s)
            data = ws.get_all_values()
            df = pd.DataFrame(data[1:], columns=columns) if len(data) > 1 else pd.DataFrame(columns=columns)
            df["단지"] = s.split("_")[0]
            df["거래유형"] = s.split("_")[1]
            df_list.append(df)
        except:
            continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame(columns=columns + ["단지", "거래유형"])

sheets_to_load = [
    "1단지_매매","1단지_임대",
    "2단지_매매","2단지_임대",
    "3단지_매매","3단지_임대"
]

columns = ["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부"]
df_total = load_sheet_data(sheets_to_load, columns)

# ------------------------------
# 메뉴
# ------------------------------
menu = ["통합 대시보드", "매물 조회", "관리자 페이지"]
choice = st.sidebar.selectbox("메뉴 선택", menu)

# =========================
# 1️⃣ 통합 대시보드
# =========================
if choice == "통합 대시보드":
    # 1. 상단 요약 지표
    total_count = len(df_total)
    available_count = len(df_total[df_total["거래여부"] == "관람가능"])
    
    m1, m2, m3 = st.columns(3)
    with m1:
        st.container(border=True).metric("🏠 전체 관리 매물", f"{total_count}세대")
    with m2:
        st.container(border=True).metric("✅ 관람 가능 매물", f"{available_count}세대")
    with m3:
        st.container(border=True).metric("📅 오늘 예약", "5건") # 실제 데이터 카운트로 변경 가능

    # 2. 버튼형 필터 (st.pills는 최신버전 기능)
    st.write("### 🔍 빠른 필터")
    selected_danji = st.pills("단지 선택", ["1단지", "2단지", "3단지"], selection_mode="multi", default=["1단지"])

    # 3. 데이터 그리드 (기존 AgGrid 유지 또는 st.dataframe 업그레이드)
    st.dataframe(
        df_filtered,
        use_container_width=True,
        column_config={
            "거래여부": st.column_config.SelectboxColumn(
                "상태",
                options=["관람가능", "거래완료"],
                required=True,
            ),
            "매매가": st.column_config.NumberColumn("금액(만원)", format="%d"),
        },
        hide_index=True,
    )
# =========================
# 2️⃣ 매물 조회
# =========================
elif choice == "매물 조회":
    c1, c2 = st.columns(2)
    단지 = c1.selectbox("단지 선택", ["1단지","2단지","3단지"])
    거래유형 = c2.selectbox("매매/임대 선택", ["매매","임대"])

    df_view = df_total[(df_total["단지"] == 단지) & (df_total["거래유형"] == 거래유형)]
    AgGrid(df_view, height=500)

# =========================
# 3️⃣ 관리자 페이지
# =========================
elif choice == "관리자 페이지":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 비밀번호", type="password")
        if pwd:
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_auth = True
                st.rerun()
            else:
                st.error("❌ 비밀번호 오류")
        st.stop()

    st.success("🔓 관리자 모드 접속 성공")
    tab1, tab2, tab3 = st.tabs(["📅 세대관람 예약", "📊 세대관람 현황표", "⚙ 데이터 관리"])

    # --- 📅 세대관람 예약 (자동 선택박스 적용) ---
    with tab1:
        단지_res = st.selectbox("예약 단지 선택", ["1단지","2단지","3단지"], key="res_danji")
        filtered_unit = df_total[df_total["단지"] == 단지_res]
        
        ws_day = sheet.worksheet(f"{단지_res}_관람예약")
        ws_night = sheet.worksheet("야간_관람예약")
    
        with st.form("reservation_form"):
            r_col1, r_col2 = st.columns(2)
            예약자 = r_col1.text_input("예약자 성함/업체")
            연락처 = r_col2.text_input("연락처")
            
            관람세대수 = st.selectbox("관람 세대 수", [1,2,3])
            
            세대목록 = []
            오류여부 = False
    
            for i in range(관람세대수):
                cols = st.columns([2, 2, 3])
                # 동 선택 (실제 데이터 기반)
                동_list = sorted(filtered_unit["동"].unique())
                동 = cols[0].selectbox(f"{i+1}번째 동", 동_list, key=f"d{i}")
                
                # 호수 선택 (선택된 동의 호수만 필터링)
                호수_list = sorted(filtered_unit[filtered_unit["동"] == 동]["호수"].unique())
                호수 = cols[1].selectbox(f"{i+1}번째 호수", 호수_list, key=f"h{i}")
    
                match = filtered_unit[(filtered_unit["동"]==동) & (filtered_unit["호수"]==호수)]
                타입 = match.iloc[0]["타입"]
                상태 = match.iloc[0]["거래여부"]
    
                if 상태 == "거래완료":
                    cols[2].error(f"❌ 거래완료 세대")
                    오류여부 = True
                else:
                    cols[2].success(f"타입: {타입} (관람가능)")
                
                세대목록.append({"동":동, "호수":호수, "타입":타입})
    
            중개업소 = st.text_input("중개업소명")
            동행매니저 = st.text_input("동행매니저")
            비고 = st.text_input("특이사항/비고")
            예약시간 = st.selectbox("예약시간", [f"{h:02d}:00~{h+1:02d}:00" for h in range(8,21)])
    
            submit = st.form_submit_button("📅 예약 확정 및 저장")
    
            if submit:
                if 오류여부:
                    st.error("❌ 예약이 불가능한 세대가 포함되어 있습니다.")
                else:
                    with st.status("데이터를 저장하는 중...") as status:
                        target_ws = ws_day if int(예약시간[:2]) < 16 else ws_night
                        기존데이터 = target_ws.get_all_values()
                        
                        rows_to_add = []
                        for 세대 in 세대목록:
                            # 중복 체크
                            중복 = any(row[0] == date.today().strftime("%Y-%m-%d") and row[4] == 세대["동"] and row[5] == 세대["호수"] and row[7] == 예약시간 for row in 기존데이터)
                            
                            if 중복:
                                st.warning(f"⚠️ {세대['동']}동 {세대['호수']}호는 이미 해당 시간에 예약이 있습니다.")
                                continue
                                
                            rows_to_add.append([
                                date.today().strftime("%Y-%m-%d"), 예약자, 중개업소, f"{관람세대수}세대",
                                세대["동"], 세대["호수"], 세대["타입"], 예약시간, 동행매니저, 비고
                            ])
    
                        if rows_to_add:
                            target_ws.append_rows(rows_to_add) # 배치 업데이트로 속도 향상
                            status.update(label="✅ 예약이 성공적으로 등록되었습니다!", state="complete")
                            st.cache_data.clear() # 캐시 갱신
                        else:
                            status.update(label="❌ 등록할 데이터가 없습니다.", state="error")

    # --- 📊 세대관람 현황표 (카드형 UI 적용) ---
    with tab2:
        c1, c2 = st.columns(2)
        선택단지 = c1.selectbox("단지 필터", ["1단지","2단지","3단지","야간"])
        선택날짜 = c2.date_input("조회 날짜", date.today())
        
        target_sheet_name = f"{선택단지}_관람예약" if 선택단지 != "야간" else "야간_관람예약"
        ws = sheet.worksheet(target_sheet_name)
        data = ws.get_all_values()
        
        columns_res = ["예약날짜","예약자","중개업소","관람세대수","동","호수","타입","예약시간","동행매니저","비고"]
        df_res = pd.DataFrame(data[1:], columns=columns_res) if len(data) > 1 else pd.DataFrame(columns=columns_res)
        df_filtered = df_res[df_res["예약날짜"] == 선택날짜.strftime("%Y-%m-%d")]

        if not df_filtered.empty:
            for _, row in df_filtered.iterrows():
                with st.container(border=True):
                    col_a, col_b = st.columns([3, 1])
                    col_a.markdown(f"**🏠 {row['동']}동 {row['호수']}호** ({row['타입']})")
                    col_b.info(row['예약시간'])
                    st.write(f"👤 예약: {row['예약자']} ({row['중개업소']}) | 🧑‍💼 매니저: {row['동행매니저']}")
                    if row['비고']: st.caption(f"📝 비고: {row['비고']}")
        else:
            st.info("📅 해당 날짜에 예약 내역이 없습니다.")

    # --- ⚙ 데이터 관리 (상태 변경 최적화) ---
    with tab3:
        if st.button("🔄 전체 데이터 새로고침"):
            st.cache_data.clear()
            st.rerun()

        st.divider()
        st.subheader("🛠 매물 상태 관리 (관람가능/거래완료)")
        
        m_col1, m_col2, m_col3 = st.columns(3)
        단지_sel = m_col1.selectbox("단지", ["1단지","2단지","3단지"], key="admin_edit_danji")
        
        # 실제 데이터 기반 동/호수 선택박스 적용
        f_unit = df_total[df_total["단지"] == 단지_sel]
        동_sel = m_col2.selectbox("동 선택", sorted(f_unit["동"].unique()), key="admin_edit_dong")
        호수_sel = m_col3.selectbox("호수 선택", sorted(f_unit[f_unit["동"] == 동_sel]["호수"].unique()), key="admin_edit_ho")

        match = f_unit[(f_unit["동"]==동_sel) & (f_unit["호수"]==호수_sel)]
        
        if not match.empty:
            row = match.iloc[0]
            st.info(f"현재 상태: **{row['거래여부']}** (유형: {row['거래유형']})")
            
            new_status = st.segmented_control("상태 변경", ["관람가능", "거래완료"], default=row['거래여부'])
            
            if st.button("💾 변경사항 저장"):
                with st.spinner("구글 시트 업데이트 중..."):
                    ws = sheet.worksheet(f"{단지_sel}_{row['거래유형']}")
                    data = ws.get_all_values()
                    
                    # 해당 행 찾아서 업데이트
                    for idx, r in enumerate(data):
                        if r[2] == 동_sel and r[3] == 호수_sel:
                            ws.update_cell(idx+1, 9, new_status)
                            break
                    
                    st.success("✅ 상태가 성공적으로 변경되었습니다.")
                    st.cache_data.clear()
                    st.rerun()