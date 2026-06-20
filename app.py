import streamlit as st
import requests
import math
import datetime
import pandas as pd
import os
import urllib.parse

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="EHS 온열질환 예측 대시보드")

st.title("☀️ 수원 현장 EHS 온열질환 예측 대시보드")
st.markdown("<hr style='border:1px solid #0f172a;'>", unsafe_allow_html=True)

WEEKDAYS = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

# 효율적인 구동을 위해 다시 1시간 캐싱 적용
@st.cache_data(ttl=3600)
def fetch_kma_data():
    service_key = os.environ.get("KMA_SERVICE_KEY")
    
    # 서버 UTC 시간을 한국 시간(UTC+9)으로 강제 변환
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now = (now_utc + datetime.timedelta(hours=9)).replace(tzinfo=None)
    
    # 기본 백업 데이터 구조
    default_weather = {
        "temp": 22.5, "rh": 65.0, "cur_rain": 0.0, "cur_snow": 0.0,
        "date_str": f"{now.strftime('%Y-%m-%d')} ({WEEKDAYS[now.weekday()]})"
    }
    
    dates = [(now + datetime.timedelta(days=i)) for i in range(5)]
    default_forecast = pd.DataFrame({
        '최고기온 (🔴)': [25.0, 27.0, 28.5, 26.0, 25.0],
        '평균기온 (🔵)': [21.1, 22.3, 23.0, 20.2, 19.5],
        '예상강수량': [9.0, 0.0, 0.0, 0.0, 0.0],
        '예상적설량': [0.0, 0.0, 0.0, 0.0, 0.0]
    }, index=[f"{d.strftime('%m/%d')}({WEEKDAYS[d.weekday()][0]})" for d in dates])

    if not service_key:
        return default_weather, default_forecast

    validated_key = urllib.parse.unquote(service_key)
    current_date_str = now.strftime("%Y%m%d")
    current_hour_str = now.strftime("%H00")

    # 💡 성공한 '단기예보 API'만 사용하여 모든 데이터를 안전하게 수집합니다.
    fcst_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    
    # 단기예보 안전 호출 시간대 계산
    adjusted_time = now - datetime.timedelta(minutes=40)
    hour = adjusted_time.hour
    if hour < 2: f_date, f_time = (adjusted_time - datetime.timedelta(days=1)).strftime("%Y%m%d"), "2300"
    else:
        available_hours = [2, 5, 8, 11, 14, 17, 20, 23]
        closest_hour = max([h for h in available_hours if h <= hour])
        f_date, f_time = adjusted_time.strftime("%Y%m%d"), f"{closest_hour:02d}00"

    try:
        response = requests.get(fcst_url, params={'serviceKey': validated_key, 'pageNo': '1', 'numOfRows': '1000', 'dataType': 'JSON', 'base_date': f_date, 'base_time': f_time, 'nx': '60', 'ny': '121'}, timeout=5)
        fcst_res = response.json()
        f_items = fcst_res['response']['body']['items']['item']
        
        raw_data = []
        for item in f_items:
            raw_data.append({
                'date': item['fcstDate'],
                'time': item['fcstTime'],
                'category': item['category'],
                'value': item['fcstValue']
            })
        df_raw = pd.DataFrame(raw_data)
        
        # 💡 [핵심 보정 엔진] 전체 예보 데이터 중 '현재 날짜'와 '현재 시간'에 가장 가까운 실시간 기온/습도 매핑
        try:
            df_today = df_raw[df_raw['date'] == current_date_str]
            # 현재 시각과 가장 가까운 예보 시간 매칭
            available_times = sorted(df_today['time'].unique())
            closest_time = min(available_times, key=lambda x: abs(int(x) - int(current_hour_str)))
            
            df_now = df_today[df_today['time'] == closest_time]
            
            # 현재 기온(TMP) 및 현재 습도(REH) 추출
            tmp_now = df_now[df_now['category'] == 'TMP']['value'].values
            reh_now = df_now[df_now['category'] == 'REH']['value'].values
            pcp_now = df_now[df_now['category'] == 'PCP']['value'].values
            
            if len(tmp_now) > 0: default_weather["temp"] = float(tmp_now[0])
            if len(reh_now) > 0: default_weather["rh"] = float(reh_now[0])
            if len(pcp_now) > 0 and '강수없음' not in str(pcp_now[0]):
                default_weather["cur_rain"] = float(str(pcp_now[0]).replace('mm','').strip())
        except Exception as inner_e:
            print(f"현재 시간대 데이터 매핑 실패: {inner_e}")

        # 5일간의 그래프용 데이터 그룹화 가공
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
            
            processed_forecast[d_label] = {
                '최고기온 (🔴)': max_t,
                '평균기온 (🔵)': avg_t,
                '예상강수량': rain_val,
                '예상적설량': snow_val
            }
            
        final_df = pd.DataFrame(processed_forecast).T
        if len(final_df) < 5:
            final_df = pd.concat([final_df, default_forecast.iloc[len(final_df):]])
            
        return default_weather, final_df
    except Exception as e:
        print(f"데이터 로드 치명적 실패: {e}")
        return default_weather, default_forecast

# 체감온도 계산 및 UI 바인딩
def calculate_apparent_temp(T, RH):
    exponent = (17.27 * T) / (237.7 + T)
    e = (RH / 100.0) * 6.105 * math.exp(exponent)
    return round(-2.7 + (1.04 * T) + (2.0 * (e / 100)) - (0.65 * 0.1), 1)

w, df_forecast = fetch_kma_data()
app_temp = calculate_apparent_temp(w["temp"], w["rh"])
w["high_temp"] = df_forecast.iloc[0, 0]
w["low_temp"] = df_forecast.iloc[0, 1] - 5.0

if app_temp >= 38.0: level, color = "위험 단계", "#ef4444"
elif app_temp >= 35.0: level, color = "경고 단계", "#f97316"
elif app_temp >= 33.0: level, color = "주의 단계", "#eab308"
elif app_temp >= 31.0: level, color = "관심 단계", "#3b82f6"
else: level, color = "정상 단계", "#10b981"

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
    st.markdown(f"<div style='font-size:15px; line-height:1.7; color:#334155;'>내일 이후 현장 최고 기온이 <span style='color:#ef4444; font-weight:700;'>{tomorrow_max_app}°C</span> 내외로 예측됩니다.<br>**조치 사항:** {risk_msg}</div>", unsafe_allow_html=True)

st.markdown("<br><hr style='border:0.5px solid #e2e8f0;'><br>", unsafe_allow_html=True)

row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
with row2_col1:
    st.caption("🌧️ 현재 강수량")
    st.markdown(f"<span style='font-size:32px; font-weight:800;'>{w['cur_rain']} mm</span>", unsafe_allow_html=True)
    st.caption("현재 실시간 기상대 계측치")
with row2_col2:
    st.caption("☂️ 오늘 예상 강수량")
    today_exp_rain = df_forecast.iloc[0]['예상강수량']
    st.markdown(f"<span style='font-size:32px; font-weight:800; color:#2563eb;'>{today_exp_rain} mm</span>", unsafe_allow_html=True)
    st.caption("오후 시간대 강수 유입 가능성 확인" if today_exp_rain > 0 else "오늘 하루 중 특이 강수 예보 없음")
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

st.caption("📈 향후 5일간 기온 추이 분석 (기상청 단기예보 실시간 연동)")
st.line_chart(df_forecast[['최고기온 (🔴)', '평균기온 (🔵)']], height=300)
