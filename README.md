# 🚚 Sistema de Rotas de Entrega

Mini-sistema em Python + Streamlit para visualização de grafo de clientes
e cálculo da menor rota de entrega.

## Funcionalidades

- **Mapa do Grafo** — visualiza todos os clientes como nós e as conexões como arestas ponderadas pela distância real (Haversine)
- **Menor Caminho (Dijkstra)** — encontra o caminho de menor distância entre dois pontos quaisquer
- **Rota Completa (Vizinho Mais Próximo)** — percorre todos os clientes partindo do depósito com heurística TSP

## Como rodar

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Rodar o app
streamlit run app.py
```

## Como usar

1. O app abre com 5 clientes de exemplo em Fortaleza-CE
2. **Sidebar esquerda**: adicione/remova clientes informando nome, latitude e longitude
3. **Aba "Mapa do Grafo"**: veja todos os pontos e conexões no mapa
4. **Aba "Menor Caminho"**: selecione origem e destino → clique em "Calcular" para ver a rota Dijkstra destacada
5. **Aba "Rota Completa"**: clique em "Calcular rota completa" para gerar a sequência otimizada de entregas

## Algoritmos

| Algoritmo | Uso | Complexidade |
|---|---|---|
| **Haversine** | Distância real entre coordenadas GPS | O(1) por par |
| **Dijkstra** | Menor caminho entre 2 pontos | O((V+E) log V) |
| **Vizinho Mais Próximo** | Rota completa (TSP heurístico) | O(V²) |

## Tecnologias

- `streamlit` — interface web
- `networkx` — estrutura de grafo e Dijkstra
- `plotly` — mapa interativo (Mapbox)
- `pandas` — tabelas de resultados
