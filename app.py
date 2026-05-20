"""
Lucas do Camarão – Sistema de Rotas de Entrega
===============================================
• Mapa interativo via Folium (Leaflet.js)
• Distâncias e traçados REAIS pelas rodovias via OSRM + OpenStreetMap
• Algoritmo de Dijkstra para menor caminho
• Heurística do Vizinho Mais Próximo para rota completa
"""

import math
from pathlib import Path

import folium
import networkx as nx
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Lucas do Camarão · Rotas",
    page_icon="🦐",
    layout="wide",
)

# ──────────────────────────────────────────────────────────────────────────────
# CARREGA CSS EXTERNO
# ──────────────────────────────────────────────────────────────────────────────
def load_css(path: str) -> None:
    """Lê o arquivo .css e injeta no Streamlit via <style>."""
    css = Path(path).read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

load_css("style.css")

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ──────────────────────────────────────────────────────────────────────────────
OSRM_BASE = "http://router.project-osrm.org"

TIPOS = {
    "galpao":  {"emoji": "🏭", "label": "Galpão",  "cor_hex": "#f59e0b", "cor_folium": "orange"},
    "loja":    {"emoji": "🏪", "label": "Loja",     "cor_hex": "#22c55e", "cor_folium": "green"},
    "cliente": {"emoji": "📦", "label": "Cliente",  "cor_hex": "#38bdf8", "cor_folium": "blue"},
}

TILE_OPTIONS = {
    "🌍 OpenStreetMap (rodovias detalhadas)": "OpenStreetMap",
}

PONTOS_PADRAO = {
    "Galpão Cruz": {
        "lat": -2.912391, "lon": -40.176130,
        "tipo": "galpao",
        "endereco": "Rua Cel. Teixeira Pinto, Cruz - CE",
    },
    "Loja Cruz": {
        "lat": -2.911212, "lon": -40.175789,
        "tipo": "loja",
        "endereco": "Av. Maria do Carmo CE-085, 1581, Cruz - CE",
    },
    "Loja Jericoacoara": {
        "lat": -2.798090, "lon": -40.510672,
        "tipo": "loja",
        "endereco": "R. Iracema, Jijoca de Jericoacoara - CE",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# ESTADO DA SESSÃO
# ──────────────────────────────────────────────────────────────────────────────
if "pontos"  not in st.session_state: st.session_state.pontos  = dict(PONTOS_PADRAO)
if "tile"    not in st.session_state: st.session_state.tile    = "OpenStreetMap"
if "osrm_ok" not in st.session_state: st.session_state.osrm_ok = None

# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES — OSRM
# ──────────────────────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em linha reta (km) entre dois pontos GPS."""
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return round(2 * R * math.asin(math.sqrt(a)), 4)


def _osrm_get(url: str, timeout: int = 20) -> dict:
    """GET no OSRM com tratamento de erros legível."""
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok":
            raise ValueError(f"OSRM code={data.get('code')}: {data.get('message','')}")
        return data
    except requests.exceptions.ConnectionError:
        raise ConnectionError("Sem conexão com o servidor OSRM.")
    except requests.exceptions.Timeout:
        raise TimeoutError("OSRM não respondeu a tempo.")


@st.cache_data(show_spinner=False, ttl=7200)
def osrm_table(coords_str: str) -> list[list[float]]:
    """
    Matriz NxN de distâncias reais (km).
    coords_str  →  "lon1,lat1;lon2,lat2;..."  (OSRM exige lon antes de lat)
    """
    url  = f"{OSRM_BASE}/table/v1/driving/{coords_str}?annotations=distance"
    data = _osrm_get(url)
    return [
        [v / 1000.0 if v is not None else 9999.0 for v in row]
        for row in data["distances"]
    ]


@st.cache_data(show_spinner=False, ttl=7200)
def osrm_route(coord_str: str) -> tuple[float, float, list]:
    """
    Rota real entre dois pontos.
    coord_str  →  "lon1,lat1;lon2,lat2"
    Retorna    →  (dist_km, dur_min, [[lat, lon], ...])  — formato Folium
    """
    url  = (f"{OSRM_BASE}/route/v1/driving/{coord_str}"
            f"?overview=full&geometries=geojson&steps=false")
    data = _osrm_get(url)

    leg     = data["routes"][0]
    dist_km = round(leg["distance"] / 1000.0, 3)
    dur_min = round(leg["duration"] / 60.0,   1)

    # OSRM entrega [lon, lat] → invertemos para [lat, lon] (padrão Folium)
    latlon  = [[c[1], c[0]] for c in leg["geometry"]["coordinates"]]
    return dist_km, dur_min, latlon


def check_osrm() -> bool:
    """Verifica se o OSRM está acessível. Resultado cacheado na sessão."""
    if st.session_state.osrm_ok is not None:
        return st.session_state.osrm_ok
    try:
        lj = PONTOS_PADRAO["Loja Cruz"]
        lk = PONTOS_PADRAO["Loja Jericoacoara"]
        osrm_route(f"{lj['lon']},{lj['lat']};{lk['lon']},{lk['lat']}")
        st.session_state.osrm_ok = True
    except Exception:
        st.session_state.osrm_ok = False
    return st.session_state.osrm_ok


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES — GRAFO
# ──────────────────────────────────────────────────────────────────────────────

def build_graph(pontos: dict) -> nx.Graph:
    """Grafo completo com pesos = distância por rodovia (fallback: Haversine)."""
    nomes = list(pontos.keys())
    G     = nx.Graph()

    for n in nomes:
        G.add_node(n, tipo=pontos[n]["tipo"])

    use_osrm = check_osrm()
    matrix   = None

    if use_osrm:
        coords_str = ";".join(f"{pontos[n]['lon']},{pontos[n]['lat']}" for n in nomes)
        try:
            matrix = osrm_table(coords_str)
        except Exception:
            use_osrm = False

    for i in range(len(nomes)):
        for j in range(i + 1, len(nomes)):
            a, b = nomes[i], nomes[j]
            d = (
                round((matrix[i][j] + matrix[j][i]) / 2.0, 3)
                if use_osrm and matrix
                else haversine(pontos[a]["lat"], pontos[a]["lon"],
                               pontos[b]["lat"], pontos[b]["lon"])
            )
            G.add_edge(a, b, weight=d)

    return G


def nearest_neighbor_tsp(G: nx.Graph, start: str, nodes: list) -> tuple[list, float]:
    """
    Heurística do Vizinho Mais Próximo restrita a um subconjunto de nós.
    Retorna rota que parte e volta para `start`, visitando todos em `nodes`.
    """
    visitar = set(nodes) - {start}
    route, total, cur = [start], 0.0, start

    while visitar:
        nxt    = min(visitar, key=lambda n: G[cur][n]["weight"])
        total += G[cur][nxt]["weight"]
        route.append(nxt)
        visitar.remove(nxt)
        cur    = nxt

    total += G[cur][start]["weight"]
    route.append(start)
    return route, round(total, 3)


def two_opt(route: list, G: nx.Graph) -> tuple[list, float]:
    """
    Melhoria 2-opt: tenta inverter sub-rotas para reduzir a distância total.
    Funciona sobre a lista completa incluindo retorno ao início (route[0]).
    """
    def route_cost(r: list) -> float:
        return sum(G[r[i]][r[i + 1]]["weight"] for i in range(len(r) - 1))

    best      = route[:]
    best_cost = route_cost(best)
    improved  = True

    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                nova  = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                custo = route_cost(nova)
                if custo < best_cost - 1e-6:
                    best      = nova
                    best_cost = custo
                    improved  = True

    return best, round(best_cost, 3)


def melhor_rota(G: nx.Graph, start: str, nodes: list) -> tuple[list, float]:
    """Vizinho Mais Próximo + 2-opt = melhor rota sem custo excessivo."""
    rota_nn, _      = nearest_neighbor_tsp(G, start, nodes)
    rota_final, dist = two_opt(rota_nn, G)
    return rota_final, dist


def fetch_route_segments(
    pontos: dict, edge_list: list[tuple]
) -> tuple[list, float, float]:
    """Busca a geometria OSRM de cada trecho e acumula distância/tempo."""
    segments   = []
    dist_total = 0.0
    dur_total  = 0.0

    for u, v in edge_list:
        coord_str = (
            f"{pontos[u]['lon']},{pontos[u]['lat']}"
            f";{pontos[v]['lon']},{pontos[v]['lat']}"
        )
        d, dur, latlons = osrm_route(coord_str)
        segments.append(latlons)
        dist_total += d   or 0.0
        dur_total  += dur or 0.0

    return segments, round(dist_total, 2), round(dur_total, 1)


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES — MAPA FOLIUM
# ──────────────────────────────────────────────────────────────────────────────

def _zoom_for_spread(lats: list, lons: list) -> int:
    spread = max(max(lats) - min(lats), max(lons) - min(lons))
    if spread < 0.01: return 15
    if spread < 0.05: return 13
    if spread < 0.20: return 11
    if spread < 0.50: return 9
    if spread < 1.50: return 8
    return 7


def build_folium_map(
    pontos: dict,
    G: nx.Graph,
    tile: str,
    route_segments: list | None = None,
    highlight_nodes: set  | None = None,
    show_all_edges: bool  = True,
) -> folium.Map:
    """
    Mapa Folium com três camadas independentes:
      1. Conexões do grafo  (linhas retas, referência visual)
      2. Rota pelas estradas (geometria real OSRM, destacada)
      3. Marcadores por tipo (galpão / loja / cliente)
    """
    lats   = [p["lat"] for p in pontos.values()]
    lons   = [p["lon"] for p in pontos.values()]
    center = [sum(lats) / len(lats), sum(lons) / len(lons)]

    m = folium.Map(
        location=center,
        zoom_start=_zoom_for_spread(lats, lons),
        tiles=tile,
        control_scale=True,
    )

    # ── Camada 1: arestas do grafo ────────────────────────────────────────────
    if show_all_edges:
        grp_edges = folium.FeatureGroup(name="🔗 Conexões do grafo", show=True)
        for u, v, d in G.edges(data=True):
            pu, pv = pontos[u], pontos[v]
            folium.PolyLine(
                locations=[[pu["lat"], pu["lon"]], [pv["lat"], pv["lon"]]],
                color="#22c55e", weight=1.5, opacity=0.18,
                tooltip=f"{u} ↔ {v}: {d['weight']:.2f} km",
            ).add_to(grp_edges)
        grp_edges.add_to(m)

    # ── Camada 2: rota pelas estradas reais ───────────────────────────────────
    if route_segments:
        grp_route = folium.FeatureGroup(name="🛣️ Melhor rota (rodovias)", show=True)
        for seg in route_segments:
            if len(seg) < 2:
                continue
            folium.PolyLine(seg, color="#bbf7d0", weight=11, opacity=0.22).add_to(grp_route)  # halo
            folium.PolyLine(seg, color="#16a34a", weight=5,  opacity=0.55).add_to(grp_route)  # rodovia
            folium.PolyLine(seg, color="#4ade80", weight=3,  opacity=0.95).add_to(grp_route)  # destaque
            mid = len(seg) // 2
            if mid:
                folium.Marker(
                    location=seg[mid],
                    icon=folium.DivIcon(
                        html='<div style="color:#4ade80;font-size:18px;text-shadow:0 0 4px #000">➤</div>',
                        icon_size=(20, 20), icon_anchor=(10, 10),
                    ),
                ).add_to(grp_route)
        grp_route.add_to(m)

    # ── Camada 3: marcadores ──────────────────────────────────────────────────
    for tipo_key, tipo_info in TIPOS.items():
        nomes_tipo = [n for n, p in pontos.items() if p["tipo"] == tipo_key]
        if not nomes_tipo:
            continue

        grp = folium.FeatureGroup(name=f"{tipo_info['emoji']} {tipo_info['label']}", show=True)

        for nome in nomes_tipo:
            p  = pontos[nome]
            hl = bool(highlight_nodes and nome in highlight_nodes)

            viz_html = ""
            if G.has_node(nome):
                vizinhos = sorted(G.neighbors(nome), key=lambda v: G[nome][v]["weight"])
                viz_html = "".join(
                    f"<div>→ {v}: <b>{G[nome][v]['weight']:.2f} km</b></div>"
                    for v in vizinhos[:8]
                )

            popup_html = f"""
            <div style="font-family:'DM Sans',sans-serif;min-width:210px;padding:4px">
              <div style="font-size:14px;font-weight:700;margin-bottom:4px">
                {tipo_info['emoji']} {nome}
              </div>
              <div style="color:#555;font-size:11px;margin-bottom:6px">
                {p.get('endereco', '')}
              </div>
              <div style="font-size:11px;color:#333">
                📍 {p['lat']:.6f}, {p['lon']:.6f}
              </div>
              {"<hr style='margin:7px 0'><div style='font-size:11px;font-weight:600'>🛣️ Dist. por rodovia:</div>" + viz_html if viz_html else ""}
            </div>"""

            folium.Marker(
                location=[p["lat"], p["lon"]],
                tooltip=folium.Tooltip(f"{tipo_info['emoji']} <b>{nome}</b>", sticky=True),
                popup=folium.Popup(popup_html, max_width=260),
                icon=folium.Icon(
                    color="white" if hl else tipo_info["cor_folium"],
                    icon=("home" if tipo_key == "galpao"
                          else "shopping-cart" if tipo_key == "loja"
                          else "cube"),
                    prefix="fa",
                ),
            ).add_to(grp)

        grp.add_to(m)

    folium.LayerControl(collapsed=False, position="topright").add_to(m)
    return m


# ──────────────────────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="header">
  <div style="font-size:2.2rem">🦐</div>
  <div>
    <h1>Lucas do Camarão · Rotas de Entrega</h1>
    <p>Melhor caminho pelas estradas reais · OSRM + OpenStreetMap · Dijkstra · Folium</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🗺️ Estilo do Mapa")
    tile_label = st.radio("Camada", list(TILE_OPTIONS.keys()))
    st.session_state.tile = TILE_OPTIONS[tile_label]

    st.divider()
    st.markdown("### ➕ Adicionar Ponto")
    novo_nome = st.text_input("Nome", placeholder="Ex: Cliente João")
    novo_tipo = st.selectbox(
        "Tipo", ["cliente", "loja", "galpao"],
        format_func=lambda x: TIPOS[x]["emoji"] + " " + TIPOS[x]["label"],
    )
    novo_end = st.text_input("Endereço (opcional)")
    c1s, c2s = st.columns(2)
    with c1s: nova_lat = st.number_input("Latitude",  value=-2.9112, format="%.6f", step=0.001)
    with c2s: nova_lon = st.number_input("Longitude", value=-40.1757, format="%.6f", step=0.001)

    if st.button("✅ Adicionar", use_container_width=True):
        if not novo_nome:
            st.warning("Informe um nome.")
        elif novo_nome in st.session_state.pontos:
            st.warning("Nome já existe.")
        else:
            st.session_state.pontos[novo_nome] = {
                "lat": nova_lat, "lon": nova_lon,
                "tipo": novo_tipo, "endereco": novo_end,
            }
            st.cache_data.clear()
            st.success(f"'{novo_nome}' adicionado!")
            st.rerun()

    st.divider()
    st.markdown("### 🗑️ Remover Ponto")
    removiveis = [n for n in st.session_state.pontos if n not in PONTOS_PADRAO]
    if removiveis:
        rem = st.selectbox("Selecione", removiveis)
        if st.button("Remover", use_container_width=True):
            del st.session_state.pontos[rem]
            st.cache_data.clear()
            st.rerun()
    else:
        st.caption("Adicione clientes para removê-los.")

    st.divider()
    st.markdown("### ⚙️ Opções")
    show_edges = st.toggle("Mostrar conexões do grafo", value=True)

    if st.button("🔄 Restaurar padrão", use_container_width=True):
        st.session_state.pontos  = dict(PONTOS_PADRAO)
        st.session_state.osrm_ok = None
        st.cache_data.clear()
        st.rerun()

    st.divider()
    with st.spinner("Verificando OSRM..."):
        osrm_online = check_osrm()

    if osrm_online:
        st.markdown('<div class="ok">🟢 OSRM online — rotas pelas estradas ativas</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="warn">🟡 OSRM offline — usando distância em linha reta</div>',
                    unsafe_allow_html=True)

    st.markdown("""
    <div class="legenda">
        <b>Legenda</b><br><br>
        <span style="color:#f59e0b">●</span> Galpão &nbsp;
        <span style="color:#22c55e">●</span> Loja &nbsp;
        <span style="color:#38bdf8">●</span> Cliente<br><br>
        <span style="color:#4ade80">━━</span> Rota pelas estradas<br>
        <span style="color:rgba(34,197,94,.3)">─ ─</span> Conexões do grafo
    </div>
    """, unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# DADOS GLOBAIS
# ──────────────────────────────────────────────────────────────────────────────
pontos = st.session_state.pontos
tile   = st.session_state.tile
nomes  = list(pontos.keys())

with st.spinner("🛣️ Calculando distâncias por rodovia..."):
    G = build_graph(pontos)

# ──────────────────────────────────────────────────────────────────────────────
# ABAS
# ──────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "🗺️  Mapa do Grafo",
    "📍 Menor Caminho (Dijkstra)",
    "🚛 Rota Completa de Entrega",
])

# ═══ TAB 1 ═══════════════════════════════════════════════════════════════════
with tab1:
    col_map, col_info = st.columns([3, 1])

    with col_map:
        st.markdown("""<div class="info">
            🛣️ Passe o mouse sobre os marcadores para ver as distâncias por rodovia.
            Use o controle de camadas (canto superior direito) para ligar/desligar grupos.
        </div>""", unsafe_allow_html=True)
        m = build_folium_map(pontos, G, tile, show_all_edges=show_edges)
        st_folium(m, width="100%", height=580, returned_objects=[])

    with col_info:
        st.markdown("**Pontos cadastrados**")
        for nome, info in pontos.items():
            t = TIPOS[info["tipo"]]
            st.markdown(f"""
            <div class="ntag">
              <div class="dot" style="background:{t['cor_hex']}"></div>
              {t['emoji']} {nome}
            </div>""", unsafe_allow_html=True)

        st.divider()
        for lbl, val in [
            ("🏭 Galpões",  sum(1 for p in pontos.values() if p["tipo"] == "galpao")),
            ("🏪 Lojas",    sum(1 for p in pontos.values() if p["tipo"] == "loja")),
            ("📦 Clientes", sum(1 for p in pontos.values() if p["tipo"] == "cliente")),
            ("🔗 Conexões", G.number_of_edges()),
        ]:
            st.markdown(f"""
            <div class="card">
              <div class="lbl">{lbl}</div>
              <div class="val">{val}</div>
            </div>""", unsafe_allow_html=True)

        pesos = [d["weight"] for _, _, d in G.edges(data=True)]
        if pesos:
            st.markdown(f"""
            <div class="card">
              <div class="lbl">🛣️ Dist. Média</div>
              <div class="val">{sum(pesos)/len(pesos):.1f}
                <span style="font-size:.8rem;color:#4ade80"> km</span>
              </div>
            </div>""", unsafe_allow_html=True)

# ═══ TAB 2 ═══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("#### Menor caminho entre dois pontos — Dijkstra")
    st.markdown("""<div class="info">
        O Dijkstra usa as <b>distâncias por rodovia</b> como peso de cada aresta.
        O traçado no mapa segue o caminho real pelas estradas (geometria OSRM).
    </div>""", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1: origem  = st.selectbox("📍 Origem",  nomes, index=0)
    with c2: destino = st.selectbox("🏁 Destino", [n for n in nomes if n != origem])

    if st.button("🔍 Calcular menor caminho", use_container_width=True):
        try:
            caminho  = nx.dijkstra_path(G, origem, destino, weight="weight")
            edges_hl = [(caminho[i], caminho[i + 1]) for i in range(len(caminho) - 1)]

            with st.spinner("🛣️ Buscando traçado das rodovias..."):
                segments, dist_real, dur_real = fetch_route_segments(pontos, edges_hl)

            m2 = build_folium_map(pontos, G, tile,
                                  route_segments=segments,
                                  highlight_nodes=set(caminho),
                                  show_all_edges=show_edges)
            st_folium(m2, width="100%", height=540, returned_objects=[])

            seta = " → "
            st.markdown(f"""
            <div class="route-box">
              <div class="rl">🛣️ Menor caminho por rodovia (Dijkstra)</div>
              <div class="rp">{seta.join(caminho)}</div>
              <div class="rd">📏 {dist_real:.2f} km &nbsp;·&nbsp; ⏱️ ~{dur_real:.0f} min</div>
            </div>""", unsafe_allow_html=True)

            rows, acc = [], 0.0
            for u, v in edges_hl:
                coord_str = f"{pontos[u]['lon']},{pontos[u]['lat']};{pontos[v]['lon']},{pontos[v]['lat']}"
                d, dur, _ = osrm_route(coord_str)
                acc += d or 0.0
                rows.append({
                    "Trecho": f"{u} → {v}",
                    "Rodovia (km)": f"{d:.3f}" if d else "—",
                    "Tempo (~min)": f"{dur:.1f}" if dur else "—",
                    "Acumulado (km)": f"{acc:.3f}",
                })
            st.markdown("**Detalhamento:**")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        except nx.NetworkXNoPath:
            st.error("Não há caminho entre os pontos selecionados.")
        except Exception as e:
            st.error(f"Erro: {e}")

# ═══ TAB 3 ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("#### 🚛 Melhor Rota para Múltiplos Clientes")
    st.markdown("""<div class="info">
        Selecione o <b>ponto de partida</b> e os <b>destinos</b> que deseja visitar.
        O algoritmo <b>Vizinho Mais Próximo + 2-opt</b> calcula a sequência de menor
        distância total pelas rodovias reais e retorna ao ponto de partida.
    </div>""", unsafe_allow_html=True)

    # ── Configuração da rota ──────────────────────────────────────────────────
    galp    = next((n for n, p in pontos.items() if p["tipo"] == "galpao"), nomes[0])
    partida = st.selectbox("🏭 Ponto de partida (origem e retorno)", nomes,
                           index=nomes.index(galp))

    # Todos os pontos podem ser destino (partida já é início+fim automaticamente)
    destinos_possiveis = nomes

    st.markdown("**📦 Selecione os destinos a visitar:**")
    st.caption("O ponto de partida já é incluído como início e retorno da rota.")
    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        destinos_sel = st.multiselect(
            "Destinos",
            options=destinos_possiveis,
            default=[n for n in destinos_possiveis if n != partida],
            format_func=lambda n: f"{TIPOS[pontos[n]['tipo']]['emoji']} {n}",
            label_visibility="collapsed",
        )
    with col_btn:
        todos = st.button("✅ Todos", use_container_width=True)
        if todos:
            st.session_state["_dest_todos"] = True
            st.rerun()
        if st.session_state.get("_dest_todos"):
            destinos_sel = destinos_possiveis
            st.session_state["_dest_todos"] = False

    # ── Resumo da seleção ─────────────────────────────────────────────────────
    if destinos_sel:
        nos_rota = [partida] + destinos_sel
        c1r, c2r, c3r = st.columns(3)
        c1r.metric("Pontos na rota", len(nos_rota))
        c2r.metric("Paradas",        len(destinos_sel))
        c3r.metric("Combinações possíveis",
                   f"{max(1, __import__('math').factorial(len(destinos_sel))):,}".replace(",", "."))

    calcular = st.button("🔍 Calcular melhor rota", use_container_width=True,
                         disabled=len(destinos_sel) == 0)

    if calcular and destinos_sel:
        nos_rota = [partida] + destinos_sel

        # Sub-grafo apenas com os nós selecionados
        G_sub = G.subgraph(nos_rota).copy()

        with st.spinner("🧠 Otimizando rota (Vizinho Mais Próximo + 2-opt)..."):
            rota, dist_grafo = melhor_rota(G_sub, partida, nos_rota)

        # Compara com rota sem otimização para mostrar ganho
        rota_nn, dist_nn = nearest_neighbor_tsp(G_sub, partida, nos_rota)
        ganho = round(dist_nn - dist_grafo, 3)

        edges_rota = [(rota[i], rota[i + 1]) for i in range(len(rota) - 1)]

        with st.spinner("🛣️ Buscando traçado das rodovias..."):
            segments, dist_real, dur_real = fetch_route_segments(pontos, edges_rota)

        # ── Mapa ─────────────────────────────────────────────────────────────
        # Filtra o mapa para mostrar só os pontos da rota
        pontos_rota = {n: pontos[n] for n in rota}
        m3 = build_folium_map(pontos_rota, G_sub, tile,
                              route_segments=segments,
                              highlight_nodes=set(rota),
                              show_all_edges=show_edges)
        st_folium(m3, width="100%", height=560, returned_objects=[])

        # ── Resultado ─────────────────────────────────────────────────────────
        seta = " → "
        st.markdown(f"""
        <div class="route-box">
          <div class="rl">🏆 Melhor rota encontrada (Vizinho Mais Próximo + 2-opt)</div>
          <div class="rp">{seta.join(rota)}</div>
          <div class="rd">📏 {dist_real:.2f} km &nbsp;·&nbsp; ⏱️ ~{dur_real:.0f} min</div>
        </div>""", unsafe_allow_html=True)

        # Ganho do 2-opt
        if ganho > 0:
            st.success(f"✅ O 2-opt economizou **{ganho:.2f} km** em relação à rota inicial do Vizinho Mais Próximo ({dist_nn:.2f} km → {dist_grafo:.2f} km)")

        # ── Tabela de paradas ─────────────────────────────────────────────────
        st.markdown("**Ordem de paradas:**")
        rows, acc = [], 0.0
        for i, parada in enumerate(rota):
            emoji = TIPOS[pontos[parada]["tipo"]]["emoji"]
            end   = pontos[parada].get("endereco", "")
            if i == 0:
                rows.append({"#": "🏁", "Parada": f"{emoji} {parada}",
                             "Endereço": end,
                             "Rodovia (km)": "—", "Tempo (~min)": "—",
                             "Acumulado (km)": "0.000"})
            else:
                u, v = rota[i - 1], rota[i]
                coord_str = (f"{pontos[u]['lon']},{pontos[u]['lat']}"
                             f";{pontos[v]['lon']},{pontos[v]['lat']}")
                d, dur, _ = osrm_route(coord_str)
                acc += d or 0.0
                label = "🔄 Retorno" if i == len(rota) - 1 else str(i)
                rows.append({
                    "#": label,
                    "Parada": f"{emoji} {parada}",
                    "Endereço": end,
                    "Rodovia (km)": f"{d:.3f}" if d else "—",
                    "Tempo (~min)": f"{dur:.1f}" if dur else "—",
                    "Acumulado (km)": f"{acc:.3f}",
                })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        c1m, c2m, c3m, c4m = st.columns(4)
        c1m.metric("Distância total",  f"{dist_real:.1f} km")
        c2m.metric("Tempo estimado",   f"{dur_real:.0f} min")
        c3m.metric("Paradas",          len(rota) - 2)
        c4m.metric("Economia (2-opt)", f"{ganho:.2f} km" if ganho > 0 else "—")

    elif calcular and not destinos_sel:
        st.warning("Selecione ao menos um destino.")

# ──────────────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "🦐 Lucas do Camarão · Rotas reais pelas estradas · "
    "OSRM + OpenStreetMap · Dijkstra · NetworkX · Folium · Streamlit"
)