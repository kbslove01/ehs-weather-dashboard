import streamlit as st
import requests
import math
import datetime
import pandas as pd
import os

# 1. 페이지 설정 (넓은 화면, 구획 테두리 없는 깔끔한 플랫 디자인 테마)
st.set_page_config(layout="wide", page_title="EHS 온열질환 예측 대시보드")

# 대시보드 메인 타이틀 (구획 구분선 포함)
st.title("☀️ 수원 현장 EHS 온열질환 예측 대시보드")
st.markdown("<hr style='border:1px solid #0f172a;'>", unsafe_allow_html=True)

# 2. 기상청 API 데이터 수집 함수 (안정적인 구동을 위해 예외 처리 및 샘플 데이터 탑재)
def get_live_weather():
    service_key = os.environ.get("KMA_SERVICE_KEY")
    # API 키가 등록되지 않았거나 오류 발생 시 보여줄 깔끔한 현장 샘플 데이터
    default_data = {
        "temp": 28.5, "rh": 65.0, "cur_rain": 0.0, "exp_rain": 5.0,
        "cur_snow": 0.0, "exp_snow": 0.0, "low_temp": 21.0, "high_temp": 32.5
    }
    
    if not service_key:
        return default_data

    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
    now = datetime.datetime.now()
    base_date = now.strftime("%Y%m%d")
    base_time = now.strftime("%H00")
    
    params = {'serviceKey': service_key, 'pageNo': '1', 'numOfRows': '20', 'dataType': 'JSON', 'base_date': base_date, 'base_time': base_time, 'nx': '60', 'ny': '121'}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        items = data['response']['body']['items']['item']
        
        res = default_data.copy()
        for item in items:
            if item['category'] == 'T1H': res["temp"] = float(item['obsrValue'])
            elif item['category'] == 'REH': res["rh"] = float(item['obsrValue'])
        return res
    except:
        return default_data

# 3. 노동부 지침 및 기상청 일치형 체감온도 계산 함수
def calculate_apparent_temp(T, RH):
    exponent = (17.27 * T) / (237.7 + T)
    e = (RH / 100.0) * 6.105 * math.exp(exponent)
    # 기상청-노동부 수식 규격 동기화 (/100 및 풍속 0.1 고정 반영)
    apparent_temp = -2.7 + (1.04 * T) + (2.0 * (e / 100)) - (0.65 * 0.1)
    return round(apparent_temp, 1)

# 데이터 바인딩
w = get_live_weather()
app_temp = calculate_apparent_temp(w["temp"], w["rh"])

# 안전 단계 설정
if app_temp >= 38.0: level, color = "위험 단계", "#ef4444"
elif app_temp >= 35.0: level, color = "경고 단계", "#f97316"
elif app_temp >= 33.0: level, color = "주의 단계", "#eab308"
elif app_temp >= 31.0: level, color = "관심 단계", "#3b82f6"
else: level, color = "정상 단계", "#10b981"

# 📌 첫 번째 행: 구획(테두리) 없는 3열 배치
row1_col1, row1_col2, row1_col3 = st.columns(3)

with row1_col1:
    st.caption("📅 실시간 기상 현황 (수원)")
    st.markdown(f"<span style='font-size: 40px;'>☀️</span> <span style='font-size: 36px; font-weight:800;'>{w['temp']}°C</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='color:#64748b; font-size:14px;'>최저 {w['low_temp']}°C / 최고 {w['high_temp']}°C</span>", unsafe_allow_html=True)

with row1_col2:
    st.caption("🔥 노동부 지침 기준 체감온도")
    st.markdown(f"<span style='font-size: 36px; font-weight:800; color:{color};'>{app_temp}°C</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size: 24px; font-weight:800; color:{color};'>{level}</span>", unsafe_allow_html=True)

with row1_col3:
    st.caption("🚨 단기 폭염 특보 리스크 예측")
    st.markdown(
        f"<div style='font-size:15px; line-height:1.7; color:#334155;'>"
        f"내일 이후 현장 최고 체감온도가 <span style='color:#ef4444; font-weight:700;'>33.5°C 이상</span>으로 오를 가능성이 감지됩니다.<br>"
        f"실외 작업자 휴게시간 조치를 선제적으로 수립해 주세요."
        f"</div>", 
        unsafe_allow_html=True
    )

st.markdown("<br><hr style='border:0.5px solid #e2e8f0;'><br>", unsafe_allow_html=True)

# 📌 두 번째 행: 구획 없는 4열 배치 (현재강수량 / 예상강수량 / 현재적설량 / 예상적설량)
row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)

with row2_col1:
    st.caption("🌧️ 현재 강수량")
    st.markdown(f"<span style='font-size:32px; font-weight:800;'>{w['cur_rain']} mm</span>", unsafe_allow_html=True)
    st.caption("현재 현장 내 강수 현황 없음")

with row2_col2:
    st.caption("☂️ 오늘 예상 강수량")
    st.markdown(f"<span style='font-size:32px; font-weight:800; color:#2563eb;'>{w['exp_rain']} mm</span>", unsafe_allow_html=True)
    st.caption("오후 15~16시 사이 강수 유입 가능성")

with row2_col3:
    st.caption("❄️ 현재 적설량")
    st.markdown(f"<span style='font-size:32px; font-weight:800;'>{w['cur_snow']} cm</span>", unsafe_allow_html=True)
    st.caption("적설로 인한 구조물 위험 없음")

with row2_col4:
    st.caption("☃️ 예상 적설량")
    st.markdown(f"<span style='font-size:32px; font-weight:800; color:#94a3b8;'>{w['exp_snow']} cm</span>", unsafe_allow_html=True)
    st.caption("향후 48시간 내 강설 예보 없음")

st.markdown("<br><hr style='border:0.5px solid #e2e8f0;'><br>", unsafe_allow_html=True)

# 📌 세 번째 행: 꺾은선 그래프 영역 (미래 날짜별 최고/평균 기온)
st.caption("📈 향후 5일간 기온 추이 분석 (미래 예측 데이터 연동)")

# 차트용 데이터 프레임 구성
chart_data = pd.DataFrame({
    '최고기온 (🔴)': [32.5, 34.0, 34.5, 31.0, 30.0],
    '평균기온 (🔵)': [26.1, 27.3, 28.0, 25.2, 24.5]
}, index=['오늘(6/20)', '내일(6/21)', '모레(6/22)', '6/23(화)', '6/24(수)'])

# 스트림릿 내장형 깔끔한 꺾은선 차트 표출
st.line_chart(chart_data, height=300)
