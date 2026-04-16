"""
Gera a tabela geral_por_mes_rs com série mensal estadual (RS).

Fonte de dados:
1) 2012-2017: CSV oficial agregado do estado (mensal).
2) 2018+: agregação por soma dos municípios na tabela ocorrencias.

Uso:
    py artefacts/build_geral_por_mes_rs.py
"""

from __future__ import annotations

import csv
import os
import re
import unicodedata
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


DB = dict(
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", "5432")),
    dbname=os.environ.get("DB_NAME", "feminicidio"),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", "postgres"),
)

ROOT = Path(__file__).resolve().parent.parent
ARCHIVES_DIR = ROOT / "archives"
CSV_2012_2017 = (
    ARCHIVES_DIR
    / "12160259-site-violencia-contra-as-mulheres-2012-a-2017-atualizado-em-09-janeiro-2018-publicacao - Geral.csv"
)

TIPO_MAP_CSV = {
    "femicidio tentado": "feminicidio_tentado",
    "femicidio consumado": "feminicidio_consumado",
    "ameaca": "ameaca",
    "estupro": "estupro",
    "lesao corporal": "lesao_corporal",
    "geral": "geral",
}

MESES_LONGOS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def normalizar_txt(valor: str | None) -> str:
    if not valor:
        return ""
    base = unicodedata.normalize("NFKD", valor.strip().lower())
    return "".join(ch for ch in base if not unicodedata.combining(ch))


def numero_ptbr(valor: str) -> int:
    v = valor.strip()
    if not v or v == "-":
        return 0
    v = v.replace(".", "").replace(",", ".")
    return int(float(v))


def ler_csv_2012_2017(path: Path) -> list[tuple[int, int, str, int, str]]:
    """
    Retorna linhas no formato:
    (ano, mes, tipo_crime, quantidade, fonte)
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV nao encontrado: {path}")

    rows: list[tuple[int, int, str, int, str]] = []
    ano_atual: int | None = None
    idx_mes: dict[int, int] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for raw in reader:
            row = [c.strip() for c in raw]
            joined = " ".join(row)

            m = re.search(r"Ano de\s+(20\d{2})", joined)
            if m:
                ano_atual = int(m.group(1))
                idx_mes = {}
                continue

            if ano_atual is None:
                continue

            col_nome = row[1] if len(row) > 1 else ""
            nome_norm = normalizar_txt(col_nome)

            if nome_norm == "municipio":
                for i, cell in enumerate(row):
                    mes = MESES_LONGOS.get(normalizar_txt(cell))
                    if mes:
                        idx_mes[i] = mes
                continue

            tipo = TIPO_MAP_CSV.get(nome_norm)
            if not tipo or not idx_mes:
                continue

            for col_idx, mes in idx_mes.items():
                if col_idx >= len(row):
                    continue
                qtd = numero_ptbr(row[col_idx])
                rows.append((ano_atual, mes, tipo, qtd, "csv_geral_2012_2017"))

    return rows


def construir_de_municipios(cur) -> list[tuple[int, int, str, int, str]]:
    """
    Soma 2018+ a partir dos municípios.
    Exclui linhas artificiais conhecidas que aparecem em algumas abas "Geral".
    """
    cur.execute(
        """
        SELECT
            ano,
            mes,
            tipo_crime,
            SUM(quantidade)::int AS total
        FROM ocorrencias
        WHERE mes IS NOT NULL
          AND ano >= 2018
          AND UPPER(municipio) NOT IN (
                'GERAL',
                'FEMINICIDIO TENTADO',
                'FEMINICIDIO CONSUMADO',
                'AMEACA',
                'ESTUPRO',
                'LESAO CORPORAL'
          )
        GROUP BY ano, mes, tipo_crime
        ORDER BY ano, mes, tipo_crime
        """
    )
    return [(a, m, t, q, "soma_municipios") for a, m, t, q in cur.fetchall()]


def criar_tabela(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS geral_por_mes_rs (
            ano SMALLINT NOT NULL CHECK (ano BETWEEN 2012 AND 2030),
            mes SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
            tipo_crime VARCHAR(30) NOT NULL CHECK (tipo_crime IN (
                'feminicidio_tentado',
                'feminicidio_consumado',
                'ameaca',
                'estupro',
                'lesao_corporal',
                'geral'
            )),
            quantidade INTEGER NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
            fonte VARCHAR(40) NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_geral_por_mes_rs PRIMARY KEY (ano, mes, tipo_crime)
        );
        """
    )


def upsert_rows(cur, rows: list[tuple[int, int, str, int, str]]) -> None:
    execute_values(
        cur,
        """
        INSERT INTO geral_por_mes_rs (ano, mes, tipo_crime, quantidade, fonte)
        VALUES %s
        ON CONFLICT (ano, mes, tipo_crime)
        DO UPDATE SET
            quantidade = EXCLUDED.quantidade,
            fonte = EXCLUDED.fonte,
            updated_at = NOW()
        """,
        rows,
    )


def main() -> None:
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    try:
        criar_tabela(cur)
        csv_rows = ler_csv_2012_2017(CSV_2012_2017)
        db_rows = construir_de_municipios(cur)
        all_rows = csv_rows + db_rows
        upsert_rows(cur, all_rows)
        conn.commit()

        print(f"CSV 2012-2017: {len(csv_rows)} linhas")
        print(f"Soma municipios (2018+): {len(db_rows)} linhas")
        print(f"Total upsert: {len(all_rows)} linhas")

        cur.execute(
            """
            SELECT MIN(ano), MAX(ano), COUNT(*)
            FROM geral_por_mes_rs
            """
        )
        ano_min, ano_max, total = cur.fetchone()
        print(f"Tabela geral_por_mes_rs => anos {ano_min}-{ano_max}, {total} linhas")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
