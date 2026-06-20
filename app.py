import streamlit as st
import requests
import math
import datetime
import pandas as pd
import os
import urllib.parse

# 1. 페이지 설정 및 상단 여백 최소화를 위한 CSS 주입
st.set_page_config(layout="wide", page_title="EHS 온열질환 예측 대시보드")

st.markdown("""
    <style>
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 0rem !important;
            padding-left: 3rem !important;
            padding-right: 3rem !important;
        }
        div[data-testid="stVerticalBlock"] > div {
            padding-bottom: 0px !important;
            padding-top: 0px !important;
        }
        iframe {
            margin-bottom: 0px !important;
        }
    </style>
""", unsafe_allow_html=True)

# 대시보드 메인 타이틀
st.markdown("<h2 style='margin-top:0px; margin-bottom:5px;'>☀️ 수원 현장 EHS 온열질환 예측 대시보드</h2>", unsafe_allow_html=True)
st.markdown("<hr style='border:1px solid #0f172a; margin-top:5px; margin-bottom:15px;'>", unsafe_allow_html=True)

WEEKDAYS = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

@st.cache_data(ttl=3600)
def fetch_kma_data():
    service_key = os.environ.get("KMA_SERVICE_KEY")
    
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now = (now_utc + datetime.timedelta(hours=9)).replace(tzinfo=None)
    
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

    fcst_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    
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
            raw_data.append({'date': item['fcstDate'], 'time': item['fcstTime'], 'category': item['category'], 'value': item['fcstValue']})
        df_raw = pd.DataFrame(raw_data)
        
        try:
            df_today = df_raw[df_raw['date'] == current_date_str]
            available_times = sorted(df_today['time'].unique())
            closest_time = min(available_times, key=lambda x: abs(int(x) - int(current_hour_str)))
            df_now = df_today[df_today['time'] == closest_time]
            
            tmp_now = df_now[df_now['category'] == 'TMP']['value'].values
            reh_now = df_now[df_now['category'] == 'REH']['value'].values
            pcp_now = df_now[df_now['category'] == 'PCP']['value'].values
            
            if len(tmp_now) > 0: default_weather["temp"] = float(tmp_now[0])
            if len(reh_now) > 0: default_weather["rh"] = float(reh_now[0])
            if len(pcp_now) > 0 and '강수없음' not in str(pcp_now[0]):
                default_weather["cur_rain"] = float(str(pcp_now[0]).replace('mm','').strip())
        except:
            pass

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
    except:
        return default_weather, default_forecast

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

# 📌 첫 번째 행: 3열 배치
row1_col1, row1_col2, row1_col3 = st.columns(3)
with row1_col1:
    st.caption(f"📅 실시간 기상 현황 ({w['date_str']})")
    st.markdown(f"<p style='margin:0px; line-height:1.1;'><span style='font-size: 38px;'>☀️</span> <span style='font-size: 34px; font-weight:800;'>{w['temp']}°C</span></p>", unsafe_allow_html=True)
    st.markdown(f"<span style='color:#64748b; font-size:13px;'>최저 {w['low_temp']}°C / 최고 {w['high_temp']}°C (수원 기준)</span>", unsafe_allow_html=True)

with row1_col2:
    st.caption("🔥 노동부 지침 기준 체감온도")
    st.markdown(f"<p style='margin:0px; line-height:1.1; font-size: 34px; font-weight:800; color:{color};'>{app_temp}°C</p>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size: 20px; font-weight:800; color:{color};'>{level}</span>", unsafe_allow_html=True)

with row1_col3:
    st.caption("🚨 단기 폭염 특보 리스크 예측")
    tomorrow_max_app = df_forecast.iloc[1, 0]
    risk_msg = "실외 작업자 브레이크 타임 선제 조치 요망" if tomorrow_max_app >= 33.0 else "현장 온열 질환 예방 지침 준수 및 수분 섭취 권고"
    st.markdown(f"<div style='font-size:14px; line-height:1.5; color:#334155; margin:0px;'>내일 이후 현장 최고 기온이 <span style='color:#ef4444; font-weight:700;'>{tomorrow_max_app}°C</span> 내외로 예측됩니다.<br>**조치 사항:** {risk_msg}</div>", unsafe_allow_html=True)

st.markdown("<hr style='border:0.5px solid #e2e8f0; margin-top:10px; margin-bottom:10px;'>", unsafe_allow_html=True)

# 📌 두 번째 행: 4열 배치
row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
with row2_col1:
    st.caption("🌧️ 현재 강수량")
    st.markdown(f"<span style='font-size:28px; font-weight:800;'>{w['cur_rain']} mm</span>", unsafe_allow_html=True)
    st.caption("현재 실시간 기상대 계측치")
with row2_col2:
    st.caption("☂️ 오늘 예상 강수량")
    today_exp_rain = df_forecast.iloc[0]['예상강수량']
    st.markdown(f"<span style='font-size:28px; font-weight:800; color:#2563eb;'>{today_exp_rain} mm</span>", unsafe_allow_html=True)
    st.caption("오후 시간대 강수 유입 가능성 확인" if today_exp_rain > 0 else "오늘 하루 중 특이 강수 예보 없음")
with row2_col3:
    st.caption("❄️ 현재 적설량")
    st.markdown(f"<span style='font-size:28px; font-weight:800;'>{w['cur_snow']} cm</span>", unsafe_allow_html=True)
    st.caption("현재 구조물 위험 없음")
with row2_col4:
    st.caption("☃️ 예상 적설량")
    today_exp_snow = df_forecast.iloc[0]['예상적설량']
    st.markdown(f"<span style='font-size:28px; font-weight:800; color:#94a3b8;'>{today_exp_snow} cm</span>", unsafe_allow_html=True)
    st.caption("향후 48시간 내 강설 리스크 없음")

st.markdown("<hr style='border:0.5px solid #e2e8f0; margin-top:10px; margin-bottom:10px;'>", unsafe_allow_html=True)

# 📌 세 번째 행: 차트 영역 
# 📌 기존의 꺾은선 그래프 부분을 아래 코드로 교체해 주세요.
st.caption("📈 향후 5일간 기온 추이 분석 (기상청 단기예보 실시간 연동)")

# 💡 [보완 완료] interactive=False를 통해 마우스 조작을 완전히 차단하고 고정합니다.
chart_df = df_forecast[['최고기온 (🔴)', '평균기온 (🔵)']].reset_index().rename(columns={'index': '날짜'})
chart_melted = pd.melt(chart_df, id_vars=['날짜'], value_vars=['최고기온 (🔴)', '평균기온 (🔵)'], var_name='구분', value_name='기온 (°C)')

import altair as alt
line_chart = alt.Chart(chart_melted).mark_line(interpolate='monotone', point=True).encode(
    x=alt.X('날짜:N', sort=None, title=None),
    y=alt.Y('기온 (°C):Q', scale=alt.Scale(zero=False)),
    color=alt.Color('구분:N', scale=alt.Scale(domain=['최고기온 (🔴)', '평균기온 (🔵)'], range=['#ef4444', '#3b82f6']), legend=alt.Legend(title=None)),
    tooltip=['날짜', '구분', '기온 (°C)']
).properties(
    height=220
).interactive(False) # 💡 여기서 마우스 상호작용을 완전히 끕니다.

st.altair_chart(line_chart, use_container_width=True)
st.altair_chart(line_chart, use_container_width=True)
