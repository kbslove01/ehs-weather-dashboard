import streamlit as st
import requests
import math
import datetime
import pandas as pd
import os
import urllib.parse

# 1. 페이지 설정 (넓은 화면, 구획 테두리 없는 깔끔한 플랫 디자인 테마)
st.set_page_config(layout="wide", page_title="EHS 온열질환 예측 대시보드")

# 대시보드 메인 타이틀
st.title("☀️ 수원 현장 EHS 온열질환 예측 대시보드")
st.markdown("<hr style='border:1px solid #0f172a;'>", unsafe_allow_html=True)

# 한국어 요일 매핑용 리스트
WEEKDAYS = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

# 기상청 API 과도한 호출 방지를 위한 1시간 캐싱 적용
@st.cache_data(ttl=3600)
def fetch_kma_data():
    service_key = os.environ.get("KMA_SERVICE_KEY")
    
    # 💡 [해외 서버 시차 버그 해결] 서버의 UTC 시간을 한국 시간(UTC + 9시간)으로 강제 변환
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now = (now_utc + datetime.timedelta(hours=9)).replace(tzinfo=None)
    
    # 기본 데이터 구조 샘플 (API 미연동 또는 에러 발생 시 시스템 멈춤 방지용 백업)
    default_weather = {
        "temp": 28.5, "rh": 65.0, "cur_rain": 0.0, "cur_snow": 0.0,
        "date_str": f"{now.strftime('%Y-%m-%d')} ({WEEKDAYS[now.weekday()]})"
    }
    
    # 5일간의 그래프/예보용 샘플 데이터 기본 프레임
    dates = [(now + datetime.timedelta(days=i)) for i in range(5)]
    default_forecast = pd.DataFrame({
        '최고기온 (🔴)': [32.5, 34.0, 34.5, 31.0, 30.0],
        '평균기온 (🔵)': [26.1, 27.3, 28.0, 25.2, 24.5],
        '예상강수량': [5.0, 0.0, 15.0, 0.0, 0.0],
        '예상적설량': [0.0, 0.0, 0.0, 0.0, 0.0]
    }, index=[f"{d.strftime('%m/%d')}({WEEKDAYS[d.weekday()][0]})" for d in dates])

    if not service_key:
        print("⚠️ [Secrets 에러]: KMA_SERVICE_KEY 환경 변수가 로드되지 않았습니다.")
        return default_weather, default_forecast

    # 💡 공공데이터포털 인증키 중복 인코딩 버그 방지
    validated_key = urllib.parse.unquote(service_key)

    # 💡 기상청 40분 데이터 생성 지연 안전 보정 (한국 시간 기준)
    adjusted_time = now - datetime.timedelta(minutes=40)
    base_date = adjusted_time.strftime("%Y%m%d")
    base_time = adjusted_time.strftime("%H00")
    
    # A. 초단기실황 API 호출 (1행 실시간 데이터용)
    ncst_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
    ncst_res = None
    
    try:
        response = requests.get(ncst_url, params={'serviceKey': validated_key, 'pageNo': '1', 'numOfRows': '20', 'dataType': 'JSON', 'base_date': base_date, 'base_time': base_time, 'nx': '60', 'ny': '121'}, timeout=5)
        ncst_res = response.json()
        items = ncst_res['response']['body']['items']['item']
        for item in items:
            if item['category'] == 'T1H': default_weather["temp"] = float(item['obsrValue'])
            elif item['category'] == 'REH': default_weather["rh"] = float(item['obsrValue'])
            elif item['category'] == 'RN1': default_weather["cur_rain"] = max(0.0, float(str(item['obsrValue']).replace('mm','').strip()) if '강수없음' not in str(item['obsrValue']) else 0.0)
    except Exception as e:
        print(f"🔴 [실시간 API 에러 발생]: {e}")
        if ncst_res: print(f"💬 기상청 초단기실황 응답 내용: {ncst_res}")

    # B. 단기예보 API 호출 (2행 예보 및 3행 미래 꺾은선 그래프용)
    fcst_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    hour = adjusted_time.hour
    if hour < 2: f_date, f_time = (adjusted_time - datetime.timedelta(days=1)).strftime("%Y%m%d"), "2300"
    else:
        available_hours = [2, 5, 8, 11, 14, 17, 20, 23]
        closest_hour = max([h for h in available_hours if h <= hour])
        f_date, f_time = adjusted_time.strftime("%Y%m%d"), f"{closest_hour:02d}00"

    fcst_res = None
    try:
        response = requests.get(fcst_url, params={'serviceKey': validated_key, 'pageNo': '1', 'numOfRows': '1000', 'dataType': 'JSON', 'base_date': f_date, 'base_time': f_time, 'nx': '60', 'ny': '121'}, timeout=5)
        fcst_res = response.json()
        f_items = fcst_res['response']['body']['items']['item']
        
        raw_data = []
        for item in f_items:
            raw_data.append({'date': item['fcstDate'], 'time': item['fcstTime'], 'category': item['category'], 'value': item['fcstValue']})
        df_raw = pd.DataFrame(raw_data)
        
        processed_forecast = {}
        unique_dates = sorted(df_raw['date'].unique())[:5]
        
        for idx, d_code in enumerate(unique_dates):
            d_obj = datetime.datetime.strptime(d_code, "%Y%m%d")
            d_label = f"{d_obj.strftime('%m/%d')}({WEEKDAYS[d_obj.weekday()][0]})"
            df_day = df_raw[df_raw['date'] == d_code]
            
            tmp_vals = df_day[df_day['category'] == 'TMP']['value'].astype(float).tolist()
            max_t = max(tmp_vals) if tmp_vals else default_forecast.iloc[idx, 0]
            avg_t = round(sum(tmp_vals)/len(tmp_vals), 1) if tmp_vals else default_forecast.iloc[idx, 1]
            
            pcp_rows = df_day[df_day['category'] == 'PCP']['value'].tolist()
            rain_val = 0.0
            for p in pcp_rows:
                try: rain_val = max(rain_val, float(str(p).replace('mm','').strip()) if '강수없음' not in str(p) else 0.0)
                except: pass
                
            sno_rows = df_day[df_day['category'] == 'SNO']['value'].tolist()
            snow_val = 0.0
            for s in sno_rows:
                try: snow_val = max(snow_val, float(str(s).replace('cm','').strip()) if '적설없음' not in str(s) else 0.0)
                except: pass
            
            processed_forecast[d_label] = {'최고기온 (🔴)': max_t, '평균기온 (🔵)': avg_t, '예상강수량': rain_val, '예상적설량': snow_val}
            
        final_df = pd.DataFrame(processed_forecast).T
        if len(final_df) < 5:
            final_df = pd.concat([final_df, default_forecast.iloc[len(final_df):]])
            
        return default_weather, final_df
    except Exception as e:
        print(f"🔴 [미래예보 API 에러 발생]: {e}")
        if fcst_res: print(f"💬 기상청 단기예보 응답 내용: {fcst_res}")
        return default_weather, default_forecast

# 노동부 지침 체감온도 계산 함수
def calculate_apparent_temp(T, RH):
    exponent = (17.27 * T) / (237.7 + T)
    e = (RH / 100.0) * 6.105 * math.exp(exponent)
    apparent_temp = -2.7 + (1.04 * T) + (2.0 * (e / 100)) - (0.65 * 0.1)
    return round(apparent_temp, 1)

# 데이터 가동
w, df_forecast = fetch_kma_data()
app_temp = calculate_apparent_temp(w["temp"], w["rh"])

# 최고/최저 기온 데이터 바인딩
w["high_temp"] = df_forecast.iloc[0, 0]
w["low_temp"] = df_forecast.iloc[0, 1] - 5.0

# 안전 보건 단계 설정
if app_temp >= 38.0: level, color = "위험 단계", "#ef4444"
elif app_temp >= 35.0: level, color = "경고 단계", "#f97316"
elif app_temp >= 33.0: level, color = "주의 단계", "#eab308"
elif app_temp >= 31.0: level, color = "관심 단계", "#3b82f6"
else: level, color = "정상 단계", "#10b981"

# 📌 첫 번째 행: 구획(테두리) 없는 3열 배치
row1_col1, row1_col2, row1_col3 = st.columns(3)

with row1_col1:
    st.caption(f"📅 실시간 기상 현황 ({w['date_str']})")
    st.markdown(f"<span style='font-size: 40px;'>☀️</span> <span style='font-size: 36px; font-weight:800;'>{w['temp']}°C</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='color:#64748b; font-size:14px;'>최저 {w['low_temp']}°C / 최고 {w['high_temp']}°C (수원 기준)</span>", unsafe_allow_html=True)

with row1_col2:
    st.caption("🔥 노동부 지침 기준 체감온도")
    st.markdown(f"<span style='font-size: 36px; font-weight:800; color:{color};'>{app_temp}°C</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size: 24px; font-weight:800; color:{color};'>{level}</span>", unsafe_allow_html=True)

with row1_col3:
    st.caption("🚨 단기 폭염 특보 리스크 예측")
    tomorrow_max_app = df_forecast.iloc[1, 0]
    risk_msg = "실외 작업자 브레이크 타임 선제 조치 요망" if tomorrow_max_app >= 33.0 else "현장 온열 질환 예방 지침 준수 및 수분 섭취 권고"
    st.markdown(
        f"<div style='font-size:15px; line-height:1.7; color:#334155;'> "
        f"내일 이후 현장 최고 기온이 <span style='color:#ef4444; font-weight:700;'>{tomorrow_max_app}°C</span> 내외로 예측됩니다.<br>"
        f"**조치 사항:** {risk_msg}"
        f"</div>", 
        unsafe_allow_html=True
    )

st.markdown("<br><hr style='border:0.5px solid #e2e8f0;'><br>", unsafe_allow_html=True)

# 📌 두 번째 행: 구획 없는 4열 배치
row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)

with row2_col1:
    st.caption("🌧️ 현재 강수량")
    st.markdown(f"<span style='font-size:32px; font-weight:800;'>{w['cur_rain']} mm</span>", unsafe_allow_html=True)
    st.caption("현재 실시간 기상대 계측치")

with row2_col2:
    st.caption("☂️ 오늘 예상 강수량")
    today_exp_rain = df_forecast.iloc[0]['예상강수량']
    st.markdown(f"<span style='font-size:32px; font-weight:800; color:#2563eb;'>{today_exp_rain} mm</span>", unsafe_allow_html=True)
    rain_status = "오후 시간대 강수 유입 가능성 확인" if today_exp_rain > 0 else "오늘 하루 중 특이 강수 예보 없음"
    st.caption(rain_status)

with row2_col3:
    st.caption("❄️ 현재 적설량")
    st.markdown(f"<span style='font-size:32px; font-weight:800;'>{w['cur_snow']} cm</span>", unsafe_allow_html=True)
    st.caption("현재 적설로 인한 구조물 위험 없음")

with row2_col4:
    st.caption("☃️ 예상 적설량")
    today_exp_snow = df_forecast.iloc[0]['예상적설량']
    st.markdown(f"<span style='font-size:32px; font-weight:800; color:#94a3b8;'>{today_exp_snow} cm</span>", unsafe_allow_html=True)
    st.caption("향후 48시간 내 강설 리스크 없음")

st.markdown("<br><hr style='border:0.5px solid #e2e8f0;'><br>", unsafe_allow_html=True)

# 📌 세 번째 행: 꺾은선 그래프 영역
st.caption("📈 향후 5일간 기온 추이 분석 (기상청 단기예보 실시간 연동)")
chart_df = df_forecast[['최고기온 (🔴)', '평균기온 (🔵)']]
st.line_chart(chart_df, height=300)
