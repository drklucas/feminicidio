# Indicadores de Violência Contra as Mulheres — RS (2012–2026)

Projeto de estruturação e análise dos dados públicos de violência contra mulheres
no Rio Grande do Sul, disponibilizados pela Secretaria de Segurança Pública do RS.

---

## Dados

### Origem

Os arquivos foram baixados do portal de dados da SSP-RS e cobrem o período de **2012 a 2026**.
São 10 planilhas `.xlsx` em `archives/`:

| Arquivo | Período | Granularidade |
|---|---|---|
| `...2012-a-2017...xlsx` | 2012–2017 | Anual por município |
| `...2018...xlsx` | 2018 | Mensal por município |
| `...2019...xlsx` | 2019 | Mensal por município |
| `...2020...xlsx` | 2020 | Mensal por município |
| `...2021...xlsx` | 2021 | Mensal por município |
| `...2022...xlsx` | 2022 | Mensal por município |
| `...2023...xlsx` | 2023 | Mensal por município |
| `...2024...xlsx` | 2024 | Mensal por município |
| `...2025...xlsx` | 2025 | Mensal por município |
| `...2026...xlsx` | 2026 | Mensal por município |

### Estrutura de cada planilha

Cada arquivo contém **6 abas**, uma por tipo de crime:

| Aba original | Chave normalizada |
|---|---|
| Geral | `geral` |
| Feminicídio Tentado | `feminicidio_tentado` |
| Feminicídio Consumado | `feminicidio_consumado` |
| Ameaça | `ameaca` |
| Estupro | `estupro` |
| Lesão Corporal | `lesao_corporal` |

Cada aba lista os **~500 municípios do RS** nas linhas. As colunas variam conforme o período:

- **2012–2017**: colunas são os anos (2012, 2013, …, 2017)
- **2018–2026**: colunas são os meses (Jan, Fev, …, Dez)

Total estimado após carga: **~286 mil registros**.

---

## Banco de Dados (versão local)

### Tecnologia

- **PostgreSQL 16** rodando em container Docker
- Gerenciado via **Docker Compose**

### Schema

```sql
CREATE TABLE ocorrencias (
    id          SERIAL PRIMARY KEY,
    municipio   VARCHAR(150) NOT NULL,
    tipo_crime  VARCHAR(30)  NOT NULL,
    ano         SMALLINT     NOT NULL,
    mes         SMALLINT,        -- NULL para dados anuais (2012-2017)
    quantidade  INTEGER      NOT NULL DEFAULT 0,

    CONSTRAINT uq_ocorrencia UNIQUE (municipio, tipo_crime, ano, mes)
);
```

Índices criados em `municipio`, `tipo_crime`, `ano` e `(ano, mes)`.

---

## Estrutura do projeto

```
feminicidio/
├── archives/               # Planilhas .xlsx originais (SSP-RS)
├── README.md               # Este arquivo
├── generate_static.py      # Gera os arquivos estáticos para o GitHub Pages
├── docs/                   # Saída estática gerada (publicada pelo GitHub Pages)
│   ├── .nojekyll
│   ├── index.html
│   └── data/
│       ├── 0.json          # Dados do município 0 (ordem alfabética)
│       └── ...
├── .github/
│   └── workflows/
│       └── deploy.yml      # CI: gera e publica o site a cada push em main
└── artefacts/
    ├── docker-compose.yml  # Container PostgreSQL 16
    ├── schema.sql          # DDL — criado automaticamente pelo container
    ├── load_data.py        # Script ETL Python (xlsx → PostgreSQL)
    └── app/
        ├── Dockerfile
        ├── app.py          # API Flask
        ├── requirements.txt
        └── static/
            └── index.html  # Template HTML (fonte para generate_static.py)
```

---

## GitHub Pages (publicação automática)

### Como funciona

O script `generate_static.py` lê diretamente os arquivos `.xlsx` de `archives/`,
compila todos os dados em memória e gera:

- **`docs/index.html`** — mesmo painel interativo, mas com os dados estaduais
  (série anual e mensal de todo o RS) **embutidos como variáveis JavaScript**,
  eliminando a necessidade de servidor.
- **`docs/data/{id}.json`** — um arquivo por município (~500 arquivos),
  carregados sob demanda quando o usuário pesquisa uma cidade.

O GitHub Actions (`deploy.yml`) executa esse script a cada `push` na branch `main`
e publica `docs/` automaticamente.

### Passo a passo — configurar o GitHub Pages

#### 1. Criar o repositório no GitHub

```bash
git init
git add .
git commit -m "chore: initial commit"
git branch -M main
git remote add origin https://github.com/<seu-usuario>/<nome-do-repo>.git
git push -u origin main
```

#### 2. Ativar o GitHub Pages via GitHub Actions

1. Acesse o repositório no GitHub.
2. Vá em **Settings → Pages**.
3. Em **Source**, selecione **"GitHub Actions"**.
4. Salve.

> Não é necessário selecionar branch/pasta; o workflow cuida do deploy.

#### 3. Aguardar o primeiro deploy

Após o `push`, a aba **Actions** mostrará o workflow **"Deploy GitHub Pages"** em execução.
Quando terminar (normalmente em 3–5 minutos), o site estará disponível em:

```
https://<seu-usuario>.github.io/<nome-do-repo>/
```

#### 4. Atualizar os dados

Para publicar dados novos basta:

1. Adicionar ou substituir arquivos `.xlsx` em `archives/`.
2. Fazer commit e push para `main`.
3. O workflow roda automaticamente e republica o site.

### Rodar o gerador localmente

```bash
pip install openpyxl
python generate_static.py
```

Os arquivos serão criados em `docs/`. Abra `docs/index.html` diretamente no
navegador (ou sirva com `python -m http.server` dentro de `docs/`) para testar.

```bash
cd docs
python -m http.server 8000
# acesse http://localhost:8000
```

> **Atenção:** abrir `index.html` diretamente via `file://` pode bloquear os
> `fetch()` dos arquivos de município em alguns navegadores. Use o servidor HTTP
> acima para testes locais completos.

---

## Versão local com Docker + Flask

### Pré-requisitos

- Docker Desktop rodando
- Python 3.x com os pacotes: `openpyxl`, `psycopg2-binary`

```bash
pip install openpyxl psycopg2-binary
```

### 1. Subir o banco

```bash
cd artefacts
docker compose up -d
```

O PostgreSQL ficará disponível em `localhost:5432`.  
Credenciais: usuário `postgres`, senha `postgres`, banco `feminicidio`.  
O `schema.sql` é executado automaticamente na primeira inicialização.

### 2. Carregar os dados

```bash
cd ..
py artefacts/load_data.py
```

O script lê todos os `.xlsx` de `archives/`, normaliza os dados e insere no banco
em lotes de 5000 registros com `ON CONFLICT DO NOTHING`.

### 3. Verificar a carga

```bash
docker exec -it feminicidio_db psql -U postgres -d feminicidio -c \
  "SELECT tipo_crime, ano, SUM(quantidade) AS total
   FROM ocorrencias
   GROUP BY tipo_crime, ano
   ORDER BY ano, tipo_crime;"
```

### 4. Acessar o painel

Com os containers rodando (`docker compose up -d`), acesse:

```
http://localhost:8080
```

---

## Observações técnicas

- O arquivo 2012–2017 agrega múltiplos anos em uma única planilha; o ETL extrai
  um registro por município/ano com `mes = NULL`.
- A coluna `Total` das planilhas é ignorada no ETL (calculável via `SUM`).
- A aba `Fórmulas - Demais indicadores` presente em alguns arquivos é ignorada.
- Nomes de municípios são normalizados para maiúsculas no momento da carga.
- A versão estática não possui dados mensais para 2012–2017 (o arquivo original
  não contém granularidade mensal nesses anos).

---

## Problema encontrado — Docker Desktop / WSL

Durante a configuração, o Docker Desktop não iniciava devido a uma falha no WSL.
O diagnóstico revelou:

- **Erro:** `REGDB_E_CLASSNOTREGISTERED` ao rodar `wsl --update`
- **Causa:** serviço Windows Installer (`msiserver`) parado, impedindo a atualização via MSI

**Solução:** abrir PowerShell como Administrador e executar:

```powershell
msiexec /regserver
net start msiserver
wsl --update
```

Alternativa (sem depender do MSI):

```powershell
winget install Microsoft.WSL
```
