"""
Gera os arquivos estáticos para o GitHub Pages.

Lê os .xlsx de archives/, compila os dados em memória e produz:
  docs/index.html            - HTML com dados estaduais embutidos como JS
  docs/data/{id}.json        - um JSON por município (carregado sob demanda)
  docs/.nojekyll             - desativa o Jekyll no GitHub Pages

Uso:
    pip install openpyxl
    python generate_static.py
"""

from __future__ import annotations
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

import openpyxl

# ── Caminhos ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
ARCHIVES_DIR = ROOT / "archives"
TEMPLATE_HTML = ROOT / "artefacts" / "app" / "static" / "index.html"
DOCS_DIR = ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"

# ── Mapeamento de abas ────────────────────────────────────────────────────────
ABA_MAP = {
    "feminicídio tentado":   "feminicidio_tentado",
    "femicídio tentado":     "feminicidio_tentado",
    "feminicídio consumado": "feminicidio_consumado",
    "femicídio consumado":   "feminicidio_consumado",
    "ameaça":                "ameaca",
    "estupro":               "estupro",
    "lesão corporal":        "lesao_corporal",
    "geral":                 "geral",
}

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4,
    "mai": 5, "jun": 6, "jul": 7, "ago": 8,
    "set": 9, "out": 10, "nov": 11, "dez": 12,
}


# ── Leitura dos xlsx (mesma lógica de load_data.py, sem PostgreSQL) ───────────

def _extrair_ano(filename: str) -> int | None:
    m = re.search(r"(20\d{2})", filename)
    return int(m.group(1)) if m else None


def _cab_mensal(headers) -> dict[int, int] | None:
    mapping = {}
    for i, h in enumerate(headers):
        if isinstance(h, str) and h.strip().lower() in MESES:
            mapping[i] = MESES[h.strip().lower()]
    return mapping or None


def _cab_anual(headers) -> dict[int, int] | None:
    mapping = {}
    for i, h in enumerate(headers):
        if isinstance(h, (int, float)) and 2000 <= int(h) <= 2030:
            mapping[i] = int(h)
    return mapping or None


def _ler_aba(ws, tipo_crime: str, ano_arquivo: int) -> list[tuple]:
    records = []
    col_mes = col_ano = municipio_col = None

    for row in ws.iter_rows(values_only=True):
        if col_mes is None and col_ano is None:
            for i, cell in enumerate(row):
                if isinstance(cell, str) and "munic" in cell.lower():
                    municipio_col = i
            if municipio_col is not None:
                col_mes = _cab_mensal(row)
                if col_mes is None:
                    col_ano = _cab_anual(row)
            continue

        if municipio_col is None:
            continue

        municipio = row[municipio_col] if municipio_col < len(row) else None
        if not municipio or not isinstance(municipio, str):
            continue
        municipio = municipio.strip().upper()
        if not municipio:
            continue
        _m = municipio.lower()
        if _m in ("município", "municipio", "total", "geral"):
            continue
        if len(municipio) > 100:
            continue
        if municipio[0].isdigit():
            continue

        if col_mes:
            for col_idx, mes in col_mes.items():
                if col_idx < len(row):
                    qtd = row[col_idx]
                    qtd = int(qtd) if isinstance(qtd, (int, float)) else 0
                    records.append((municipio, tipo_crime, ano_arquivo, mes, qtd))
        elif col_ano:
            for col_idx, ano in col_ano.items():
                if col_idx < len(row):
                    qtd = row[col_idx]
                    qtd = int(qtd) if isinstance(qtd, (int, float)) else 0
                    records.append((municipio, tipo_crime, ano, None, qtd))

    return records


def ler_todos_xlsx(archives_dir: Path) -> dict[tuple, int]:
    """
    Retorna um dict {(municipio, tipo_crime, ano, mes): quantidade}
    com deduplicação via primeira-escrita-ganha (igual ao ON CONFLICT DO NOTHING).
    """
    xlsx_files = sorted(f for f in os.listdir(archives_dir) if f.endswith(".xlsx"))
    print(f"Arquivos xlsx encontrados: {len(xlsx_files)}")

    unique: dict[tuple, int] = {}

    for filename in xlsx_files:
        filepath = archives_dir / filename
        ano_arquivo = _extrair_ano(filename)
        print(f"  -> {filename}  (ano base: {ano_arquivo})")

        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        for sheet_name in wb.sheetnames:
            tipo_crime = ABA_MAP.get(sheet_name.strip().lower())
            if tipo_crime is None:
                continue
            ws = wb[sheet_name]
            for rec in _ler_aba(ws, tipo_crime, ano_arquivo):
                key = rec[:4]  # (municipio, tipo, ano, mes)
                if key not in unique:
                    unique[key] = rec[4]
        wb.close()

    print(f"  Total de registros únicos: {len(unique):,}")
    return unique


# ── Agregações ────────────────────────────────────────────────────────────────

def agregar_estado(data: dict[tuple, int]):
    """Agrega no nível do estado (todos os municípios)."""
    # Anual: soma por (tipo, ano)  [inclui mes=None e mes=número]
    anual: dict[tuple, int] = defaultdict(int)
    # Mensal: soma por (ano, tipo, mes) onde mes IS NOT NULL
    mensal: dict[tuple, int] = defaultdict(int)

    for (mun, tipo, ano, mes), qtd in data.items():
        anual[(tipo, ano)] += qtd
        if mes is not None:
            mensal[(ano, tipo, mes)] += qtd

    anual_lista = [
        {"tipo": tipo, "ano": ano, "total": total}
        for (tipo, ano), total in sorted(anual.items(), key=lambda x: (x[0][1], x[0][0]))
    ]

    anos_com_mensal = sorted({ano for (ano, _, _) in mensal})
    mensal_por_ano: dict[str, list] = {}
    for ano in anos_com_mensal:
        mensal_por_ano[str(ano)] = [
            {"tipo": tipo, "mes": mes, "total": total}
            for (a, tipo, mes), total in sorted(mensal.items(), key=lambda x: (x[0][2], x[0][1]))
            if a == ano
        ]

    return anual_lista, mensal_por_ano


def agregar_por_municipio(data: dict[tuple, int]) -> dict[str, dict]:
    """Retorna {municipio: {anual: [...], mensal: {ano: [...]}}}."""
    mun_anual: dict[tuple, int] = defaultdict(int)
    mun_mensal: dict[tuple, int] = defaultdict(int)

    for (mun, tipo, ano, mes), qtd in data.items():
        mun_anual[(mun, tipo, ano)] += qtd
        if mes is not None:
            mun_mensal[(mun, ano, tipo, mes)] += qtd

    # Agrupa por município
    municipios: dict[str, dict] = {}

    for (mun, tipo, ano), total in mun_anual.items():
        m = municipios.setdefault(mun, {"anual": [], "mensal": {}})
        m["anual"].append({"tipo": tipo, "ano": ano, "total": total})

    for (mun, ano, tipo, mes), total in mun_mensal.items():
        m = municipios.setdefault(mun, {"anual": [], "mensal": {}})
        ano_str = str(ano)
        m["mensal"].setdefault(ano_str, []).append(
            {"tipo": tipo, "mes": mes, "total": total}
        )

    # Ordena listas internas
    for mun_data in municipios.values():
        mun_data["anual"].sort(key=lambda r: (r["ano"], r["tipo"]))
        for lst in mun_data["mensal"].values():
            lst.sort(key=lambda r: (r["mes"], r["tipo"]))

    return municipios


# ── Modificação do HTML ───────────────────────────────────────────────────────

def _injetar_dados(
    html: str,
    anual_lista: list,
    mensal_por_ano: dict,
    anos: list,
    municipios_sorted: list,
    mun_idx: dict,
) -> str:
    """Substitui chamadas de API por dados embutidos e referências a arquivos estáticos."""

    # 1. Bloco de dados embutidos — inserido ANTES do <script> principal
    #    para que as variáveis estejam definidas quando init() for chamado.
    data_block = (
        "<script>\n"
        f"window.__ANUAL__     = {json.dumps(anual_lista, ensure_ascii=False)};\n"
        f"window.__ANOS__      = {json.dumps(anos, ensure_ascii=False)};\n"
        f"window.__MUNICIPIOS__= {json.dumps(municipios_sorted, ensure_ascii=False)};\n"
        f"window.__MENSAL__    = {json.dumps(mensal_por_ano, ensure_ascii=False)};\n"
        f"window.__MUN_IDX__   = {json.dumps(mun_idx, ensure_ascii=False)};\n"
        "</script>\n"
    )
    # Ancora no primeiro caractere único do script principal
    SCRIPT_ANCHOR = "<script>\n// ── Config"
    html = html.replace(SCRIPT_ANCHOR, data_block + SCRIPT_ANCHOR, 1)

    # 2. init(): substitui Promise.all com os três fetch de estado
    html = html.replace(
        "const [ad, anos, municipios] = await Promise.all([\n"
        "    fetch('/api/anual').then(r => r.json()),\n"
        "    fetch('/api/anos').then(r => r.json()),\n"
        "    fetch('/api/municipios').then(r => r.json()),\n"
        "  ]);",
        "const [ad, anos, municipios] = await Promise.all([\n"
        "    Promise.resolve(window.__ANUAL__),\n"
        "    Promise.resolve(window.__ANOS__),\n"
        "    Promise.resolve(window.__MUNICIPIOS__),\n"
        "  ]);",
    )

    # 3. init(): fetch mensal do ano mais recente
    html = html.replace(
        "mensalData = await fetch(`/api/mensal?ano=${latestAno}`).then(r => r.json());",
        "mensalData = window.__MENSAL__[String(latestAno)] || [];",
    )

    # 4. selAno listener (gráfico mensal estado)
    html = html.replace(
        "    mensalData = await fetch(`/api/mensal?ano=${e.target.value}`).then(r => r.json());\n"
        "    renderChartMensal();",
        "    mensalData = window.__MENSAL__[e.target.value] || [];\n"
        "    renderChartMensal();",
    )

    # 5. selAnoTab listener (tabela mensal estado)
    html = html.replace(
        "    mensalData = await fetch(`/api/mensal?ano=${e.target.value}`).then(r => r.json());\n"
        "    renderTabelaMensal();",
        "    mensalData = window.__MENSAL__[e.target.value] || [];\n"
        "    renderTabelaMensal();",
    )

    # 6. buscarCidade(): substitui os dois fetch (anual e mensal por município)
    html = html.replace(
        "  anualCidadeData = await fetch(`/api/anual?municipio=${encodeURIComponent(nome)}`).then(r => r.json());",
        "  const __munIdx = window.__MUN_IDX__[nome];\n"
        "  const __munJson = __munIdx !== undefined\n"
        "    ? await fetch(`./data/${__munIdx}.json`).then(r => r.json())\n"
        "    : {anual: [], mensal: {}};\n"
        "  anualCidadeData = __munJson.anual;",
    )
    html = html.replace(
        "  mensalCidadeData = await fetch(`/api/mensal?ano=${latestAno}&municipio=${encodeURIComponent(nome)}`).then(r => r.json());",
        "  mensalCidadeData = __munJson.mensal[String(latestAno)] || [];",
    )

    # 7. selAnoCidade listener
    html = html.replace(
        "  mensalCidadeData = await fetch(\n"
        "    `/api/mensal?ano=${e.target.value}&municipio=${encodeURIComponent(cidadeSelecionada)}`\n"
        "  ).then(r => r.json());",
        "  const __idx = window.__MUN_IDX__[cidadeSelecionada];\n"
        "  if (__idx !== undefined) {\n"
        "    const __d = await fetch(`./data/${__idx}.json`).then(r => r.json());\n"
        "    mensalCidadeData = __d.mensal[e.target.value] || [];\n"
        "  } else {\n"
        "    mensalCidadeData = [];\n"
        "  }",
    )

    return html


# ── Principal ─────────────────────────────────────────────────────────────────

def main():
    print("=== Gerando site estático para GitHub Pages ===\n")

    # Limpa e recria docs/
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DATA_DIR.mkdir(parents=True)

    # 1. Lê os xlsx
    data = ler_todos_xlsx(ARCHIVES_DIR)

    # 2. Agrega
    print("\nAgregando dados do estado…")
    anual_lista, mensal_por_ano = agregar_estado(data)

    print("Agregando dados por município…")
    municipios_data = agregar_por_municipio(data)

    municipios_sorted = sorted(municipios_data.keys())
    mun_idx = {m: i for i, m in enumerate(municipios_sorted)}
    anos = sorted({r["ano"] for r in anual_lista})

    print(f"  {len(municipios_sorted)} municípios  |  {len(anos)} anos  |  {len(anual_lista)} registros anuais")

    # 3. Escreve JSON por município
    print(f"\nEscrevendo {len(municipios_sorted)} arquivos de município em docs/data/…")
    for nome, idx in mun_idx.items():
        path = DATA_DIR / f"{idx}.json"
        path.write_text(
            json.dumps(municipios_data[nome], ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    # 4. Gera index.html
    print("Gerando docs/index.html…")
    template = TEMPLATE_HTML.read_text(encoding="utf-8")
    html = _injetar_dados(template, anual_lista, mensal_por_ano, anos, municipios_sorted, mun_idx)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")

    # 5. .nojekyll (desativa Jekyll no GitHub Pages)
    (DOCS_DIR / ".nojekyll").touch()

    print("\nConcluido. Arquivos gerados em docs/")
    print(f"  docs/index.html")
    print(f"  docs/data/0.json … docs/data/{len(municipios_sorted)-1}.json")


if __name__ == "__main__":
    main()
