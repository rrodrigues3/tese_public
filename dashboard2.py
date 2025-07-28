import streamlit as st
import pandas as pd
import os
import altair as alt
import pathlib
import locale
from datetime import timedelta
import ast

# Setup da página
st.set_page_config(page_title="Dashboard Mosca da Azeitona", layout="wide")
st.title("🪰 Dashboard - Capturas da Mosca da Azeitona")

# Diretório base
BASE_DIR = pathlib.Path(__file__).parent.resolve()

# Definir locale para português
try:
    locale.setlocale(locale.LC_TIME, 'pt_PT.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except:
        pass  # fallback

# Funções auxiliares
def parse_coords(coord_str):
    try:
        return ast.literal_eval(coord_str)
    except:
        return []

def contar_deteccoes_novas(coord_str_atual, coords_anteriores, max_dist=30):
    novas = 0
    coords_atuais = parse_coords(coord_str_atual)

    for cx1, cy1, cx2, cy2 in coords_atuais:
        cx = (cx1 + cx2) / 2
        cy = (cy1 + cy2) / 2
        repetida = False

        for coords_ant in coords_anteriores:
            for ax1, ay1, ax2, ay2 in parse_coords(coords_ant):
                acx = (ax1 + ax2) / 2
                acy = (ay1 + ay2) / 2
                dist = ((cx - acx)**2 + (cy - acy)**2)**0.5
                if dist < max_dist:
                    repetida = True
                    break
            if repetida:
                break
        if not repetida:
            novas += 1
    return novas

# Carregar dados
@st.cache_data(ttl=60)
def carregar_dados():
    df = pd.read_csv(BASE_DIR / "results.csv", dtype=str)

    for col in ["Nº femea", "Nº macho", "Nº mosca"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["Data imagem"] = pd.to_datetime(df["Data imagem"], errors="coerce")
    df["Localização"] = df["Localização"].fillna("Desconhecida")
    df = df.sort_values("Data imagem", ascending=True)

    # Inicializar colunas de contagem real
    df["Nº femea real"] = 0
    df["Nº macho real"] = 0
    df["Nº mosca real"] = 0

    for i in range(len(df)):
        row = df.iloc[i]
        data = row["Data imagem"]
        placa = row["Placa ID"]

        anteriores = df[
            (df["Data imagem"] < data) &
            (df["Placa ID"] == placa) &
            (df["Data imagem"] >= data - pd.Timedelta(days=2))
        ]

        df.loc[df.index[i], "Nº femea real"] = contar_deteccoes_novas(
            row.get("Coord. femea", "[]"),
            anteriores["Coord. femea"].tolist()
        )
        df.loc[df.index[i], "Nº macho real"] = contar_deteccoes_novas(
            row.get("Coord. macho", "[]"),
            anteriores["Coord. macho"].tolist()
        )
        df.loc[df.index[i], "Nº mosca real"] = contar_deteccoes_novas(
            row.get("Coord. mosca", "[]"),
            anteriores["Coord. mosca"].tolist()
        )

    df = df.sort_values("Data imagem", ascending=False)
    return df

df = carregar_dados()

# Filtros
with st.sidebar:
    st.header("🔍 Filtros")
    
    localizacoes = st.multiselect("Filtrar por localização", df["Localização"].unique())
    if localizacoes:
        df = df[df["Localização"].isin(localizacoes)]

    data_range = st.date_input("Filtrar por intervalo de datas", [])
    if len(data_range) == 2:
        inicio, fim = data_range
        df = df[(df["Data imagem"].dt.date >= inicio) & (df["Data imagem"].dt.date <= fim)]

# 📈 Curva de voo + Alerta de risco elevado
st.subheader("📈 Curva de Voo (Capturas por Dia)")

# Agrupamento correto e cálculos diários
df_agg = df.groupby("Data imagem")[["Nº femea real", "Nº macho real", "Nº mosca real"]].sum().sort_index()
df_agg["Acumulado Total"] = df_agg["Nº mosca real"].cumsum()
df_agg["Nº mosca dia"] = df_agg["Acumulado Total"].diff().fillna(df_agg["Acumulado Total"]).clip(lower=0).astype(int)
df_agg["Nº femea dia"] = df_agg["Nº femea real"].diff().fillna(df_agg["Nº femea real"]).clip(lower=0).astype(int)
df_agg["Nº macho dia"] = df_agg["Nº macho real"].diff().fillna(df_agg["Nº macho real"]).clip(lower=0).astype(int)

df_daily = df_agg[["Nº femea dia", "Nº macho dia", "Nº mosca dia", "Acumulado Total"]].copy()
df_daily.index = df_daily.index.date
df_daily = df_daily.reset_index().rename(columns={"index": "Data"})

# Alerta de risco elevado
moscas_altas = df_daily[df_daily["Nº mosca dia"] > 5]
n_alertas = len(moscas_altas)

if "n_alertas_vistos" not in st.session_state:
    st.session_state.n_alertas_vistos = 0
if "alerta_silenciado" not in st.session_state:
    st.session_state.alerta_silenciado = False

if n_alertas > st.session_state.n_alertas_vistos or not st.session_state.alerta_silenciado:
    with st.container():
        st.error(f"🚨 Alerta: Foram detetadas {n_alertas} dias com mais de 5 moscas. Risco elevado!")
        if st.button("🔕 Silenciar alerta"):
            st.session_state.alerta_silenciado = True
            st.session_state.n_alertas_vistos = n_alertas

# Gráfico da curva de voo com tickCount corrigido
max_y = df_daily["Nº mosca dia"].max()

st.altair_chart(
    alt.Chart(df_daily).mark_line(point=True).encode(
        x=alt.X('Data:T', title='Data', axis=alt.Axis(format='%d %b')),
        y=alt.Y(
            'Nº mosca dia:Q',
            title='Nº moscas',
            scale=alt.Scale(domain=[0, max_y + 1]),
            axis=alt.Axis(tickCount=max_y + 1)
        )
    ).properties(width=700, height=300),
    use_container_width=True
)

# 📋 Deteções Diárias
st.subheader("📋 Deteções Diárias")
df_daily_sorted = df_daily.sort_values("Data", ascending=False)
st.dataframe(df_daily_sorted.rename(columns={
    "Nº femea dia": "Nº femea",
    "Nº macho dia": "Nº macho",
    "Nº mosca dia": "Nº mosca"
}), use_container_width=True)

# 📊 Capturas por Classe
st.subheader("📊 Capturas por Classe")
capturas_classes = df[["Nº femea real", "Nº macho real", "Nº mosca real"]].sum().reset_index()
capturas_classes.columns = ["Classe", "Total"]
st.bar_chart(capturas_classes.set_index("Classe"))

# 📅 Capturas Semanais por Classe
df["Semana"] = df["Data imagem"].dt.isocalendar().week
st.subheader("📅 Capturas Semanais por Classe")
st.dataframe(df.groupby("Semana")[["Nº femea real", "Nº macho real", "Nº mosca real"]].sum(), use_container_width=True)

# 📆 Capturas Mensais por Classe
df["Mês"] = df["Data imagem"].dt.month
st.subheader("📆 Capturas Mensais por Classe")
st.dataframe(df.groupby("Mês")[["Nº femea real", "Nº macho real", "Nº mosca real"]].sum(), use_container_width=True)

# 🪧 Capturas por Placa
st.subheader("🪧 Capturas por Placa")
st.dataframe(df.groupby("Placa ID")[["Nº femea real", "Nº macho real", "Nº mosca real"]].sum(), use_container_width=True)

# 🗺️ Mapa de Localizações
st.subheader("🗺️ Mapa de Localizações")
df_mapa = df[["Latitude", "Longitude"]].dropna()
df_mapa["Latitude"] = pd.to_numeric(df_mapa["Latitude"], errors="coerce")
df_mapa["Longitude"] = pd.to_numeric(df_mapa["Longitude"], errors="coerce")
df_mapa = df_mapa.dropna()

if not df_mapa.empty:
    st.map(df_mapa.rename(columns={"Latitude": "latitude", "Longitude": "longitude"}))
else:
    st.info("Sem coordenadas disponíveis para o mapa.")

# 📁 Ver imagens com deteções detalhadas
with st.expander("📁 Ver imagens com deteções detalhadas"):
    for idx, row in df.iterrows():
        st.markdown(f"### 🖼️ {row['Nome da imagem']} - {row['Data imagem'].date()}")

        cols = st.columns(3)
        for i, classe in enumerate(["femea", "macho", "mosca"]):
            img_path = BASE_DIR / "detections_output" / f"{row['Nome da imagem']}_det_{classe}.jpg"
            if img_path.exists():
                cols[i].image(str(img_path), caption=classe.capitalize(), use_container_width=True)
            else:
                cols[i].write(f"🔍 Sem imagem de {classe}")

        st.markdown(f"**📍 Localização:** {row['Localização']}")
        st.markdown(f"**🔢 Nº Deteções (reais):** F: {row['Nº femea real']} | M: {row['Nº macho real']} | Mo: {row['Nº mosca real']}")
        st.markdown("---")

# Rodapé
st.caption("Atualizado automaticamente a cada 12 horas · Desenvolvido por Rafael Rodrigues")
#t