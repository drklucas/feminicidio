import os
import psycopg2
from flask import Flask, jsonify, request

app = Flask(__name__, static_folder='static', static_url_path='')

DB_CONFIG = dict(
    host=os.environ.get('DB_HOST', 'localhost'),
    port=int(os.environ.get('DB_PORT', '5432')),
    dbname=os.environ.get('DB_NAME', 'feminicidio'),
    user=os.environ.get('DB_USER', 'postgres'),
    password=os.environ.get('DB_PASSWORD', 'postgres'),
)


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/api/anos')
def anos():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT ano FROM ocorrencias WHERE mes IS NOT NULL ORDER BY ano"
    )
    result = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify(result)


@app.route('/api/municipios')
def municipios():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT municipio FROM ocorrencias ORDER BY municipio"
    )
    result = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify(result)


@app.route('/api/anual')
def anual():
    municipio = request.args.get('municipio', '').strip().upper() or None
    conn = get_conn()
    cur = conn.cursor()
    if municipio:
        cur.execute("""
            SELECT tipo_crime, ano, SUM(quantidade)::int
            FROM ocorrencias
            WHERE municipio = %s
            GROUP BY tipo_crime, ano
            ORDER BY ano, tipo_crime
        """, (municipio,))
    else:
        cur.execute("""
            SELECT tipo_crime, ano, SUM(quantidade)::int
            FROM ocorrencias
            GROUP BY tipo_crime, ano
            ORDER BY ano, tipo_crime
        """)
    result = [{'tipo': r[0], 'ano': r[1], 'total': r[2]} for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify(result)


@app.route('/api/mensal')
def mensal():
    ano = request.args.get('ano', type=int)
    if not ano:
        return jsonify({'erro': 'Parâmetro ano é obrigatório'}), 400
    municipio = request.args.get('municipio', '').strip().upper() or None
    conn = get_conn()
    cur = conn.cursor()
    if municipio:
        cur.execute("""
            SELECT tipo_crime, mes, SUM(quantidade)::int
            FROM ocorrencias
            WHERE ano = %s AND mes IS NOT NULL AND municipio = %s
            GROUP BY tipo_crime, mes
            ORDER BY mes, tipo_crime
        """, (ano, municipio))
    else:
        cur.execute("""
            SELECT tipo_crime, mes, SUM(quantidade)::int
            FROM ocorrencias
            WHERE ano = %s AND mes IS NOT NULL
            GROUP BY tipo_crime, mes
            ORDER BY mes, tipo_crime
        """, (ano,))
    result = [{'tipo': r[0], 'mes': r[1], 'total': r[2]} for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify(result)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
