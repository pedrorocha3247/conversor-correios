# -*- coding: utf-8 -*-
"""
Web app (Flask) para converter as pastas de dia em CSVs no formato Correios.

Funciona local e hospedado (Render):
  - o usuario SELECIONA a pasta do dia (ou envia um .zip dela);
  - o servidor converte os .txt em memoria;
  - devolve um .zip com os CSVs para baixar.

Rodar local:
    python app.py
    -> http://127.0.0.1:5000
"""

import os
import io
import base64
import zipfile

from flask import Flask, request, jsonify, render_template_string

import txt_para_correios as conv
import planilha_para_txt as planilha

EXT_PLANILHA = ('.xls', '.xlsx')

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64 MB por envio

ENCODING_TXT = conv.ENCODING


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def modelo_de_caminho(relpath):
    """Deduz o nome do modelo a partir do caminho relativo de um .txt.
    Ex.: '28-05-2026/5B/5B.txt' -> '5B'  (pasta pai do arquivo)."""
    if not relpath:
        return None
    partes = [p for p in relpath.replace('\\', '/').split('/') if p and p != '.']
    if not partes:
        return None
    if any(p == conv.NOME_PASTA_SAIDA for p in partes):
        return None  # ignora arquivos de uma saida anterior
    if len(partes) >= 2:
        return partes[-2]                       # pasta pai
    return os.path.splitext(partes[0])[0]       # txt solto -> nome do arquivo


def nome_base_de_caminho(relpath):
    """Primeiro nivel do caminho (ex.: a pasta do dia), para nomear o zip."""
    partes = [p for p in (relpath or '').replace('\\', '/').split('/') if p and p != '.']
    return partes[0] if partes else None


def _modelo_de_planilha(rel):
    """Para uma planilha, o nome do modelo vem do nome do arquivo (sem
    extensao). Ex.: '8C1.xlsx' -> '8C1'. Se a planilha estiver dentro de uma
    pasta de modelo (pasta/8C1/8C1.xlsx), usa a pasta-pai, igual ao .txt."""
    partes = [p for p in (rel or '').replace('\\', '/').split('/')
              if p and p != '.']
    if not partes:
        return None
    if len(partes) >= 2 and partes[-2] != conv.NOME_PASTA_SAIDA:
        return partes[-2]                       # pasta-pai, se houver
    return os.path.splitext(partes[-1])[0]      # senao, nome do arquivo


def coletar_de_arquivos(files):
    """Modo 'pasta': lista de FileStorage cujos filenames sao caminhos relativos.
    Aceita tanto .txt (fluxo antigo) quanto .xls/.xlsx (planilha SMT/SAC)."""
    modelos = {}
    nome_base = None
    for f in files:
        rel = f.filename or ''
        low = rel.lower()
        if low.endswith('.txt'):
            modelo = modelo_de_caminho(rel)
            if not modelo:
                continue
            texto = f.read().decode(ENCODING_TXT, errors='replace')
        elif low.endswith(EXT_PLANILHA):
            modelo = _modelo_de_planilha(rel)
            if not modelo:
                continue
            texto = planilha.ler_planilha_bytes(f.read(), rel)
        else:
            continue
        if nome_base is None:
            nome_base = nome_base_de_caminho(rel)
        modelos.setdefault(modelo, []).append(texto)
    return modelos, nome_base


def coletar_de_zip(file_zip):
    """Modo '.zip': le os .txt e/ou .xls/.xlsx de dentro do arquivo compactado."""
    modelos = {}
    nome_base = os.path.splitext(os.path.basename(file_zip.filename or 'saida'))[0]
    dados = file_zip.read()
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            low = info.filename.lower()
            if low.endswith('.txt'):
                modelo = modelo_de_caminho(info.filename)
                if not modelo:
                    continue
                texto = z.read(info).decode(ENCODING_TXT, errors='replace')
            elif low.endswith(EXT_PLANILHA):
                modelo = _modelo_de_planilha(info.filename)
                if not modelo:
                    continue
                texto = planilha.ler_planilha_bytes(z.read(info), info.filename)
            else:
                continue
            modelos.setdefault(modelo, []).append(texto)
    return modelos, nome_base


def montar_zip(arquivos):
    """arquivos: {nome: bytes} -> bytes de um .zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template_string(PAGINA)


@app.route('/gerar', methods=['POST'])
def gerar():
    try:
        files = request.files.getlist('arquivos')
        zip_in = request.files.get('zip')
        planilha_in = request.files.get('planilha')

        tem_arquivo = files and any(
            (f.filename or '').lower().endswith(('.txt',) + EXT_PLANILHA)
            for f in files)

        if planilha_in and planilha_in.filename:
            rel = planilha_in.filename
            modelo = _modelo_de_planilha(rel)
            texto = planilha.ler_planilha_bytes(planilha_in.read(), rel)
            modelos = {modelo: [texto]}
            nome_base = os.path.splitext(os.path.basename(rel))[0]
        elif tem_arquivo:
            modelos, nome_base = coletar_de_arquivos(files)
        elif zip_in and zip_in.filename:
            modelos, nome_base = coletar_de_zip(zip_in)
        else:
            return jsonify({'ok': False, 'erro': 'Nenhum arquivo recebido.'})

        if not modelos:
            return jsonify({'ok': False, 'erro':
                            'Nao encontrei .txt nem planilha valida.'})

        res = conv.converter_textos(modelos)
        if not res['arquivos']:
            return jsonify({'ok': False, 'erro': 'Nenhum registro valido encontrado.'})

        zip_bytes = montar_zip(res['arquivos'])
        nome_zip = (nome_base or 'saida') + '.zip'

        return jsonify({
            'ok': True,
            'modelos': res['modelos'],
            'total_nacionais': res['total_nacionais'],
            'total_internacionais': res['total_internacionais'],
            'zip_nome': nome_zip,
            'zip_b64': base64.b64encode(zip_bytes).decode('ascii'),
        })
    except zipfile.BadZipFile:
        return jsonify({'ok': False, 'erro': 'O arquivo enviado nao e um .zip valido.'})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


# ---------------------------------------------------------------------------
# Pagina (HTML + JS embutidos)
# ---------------------------------------------------------------------------
PAGINA = r"""
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TXT &rarr; CSV Correios</title>
<style>
  :root { --azul:#1565c0; --azul2:#0d47a1; --bg:#0f172a; --card:#1e293b;
          --txt:#e2e8f0; --mut:#94a3b8; --ok:#22c55e; --warn:#f59e0b; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:Segoe UI,Roboto,Arial,sans-serif;
         background:var(--bg); color:var(--txt); min-height:100vh; }
  .wrap { max-width:840px; margin:0 auto; padding:32px 20px 60px; }
  h1 { font-size:24px; margin:0 0 4px; }
  .sub { color:var(--mut); margin:0 0 26px; font-size:14px; }
  .card { background:var(--card); border:1px solid #334155; border-radius:14px;
          padding:22px; margin-bottom:20px; }
  .tabs { display:flex; gap:8px; margin-bottom:18px; }
  .tab { flex:1; text-align:center; padding:10px; border-radius:10px; cursor:pointer;
         background:#0b1220; border:1px solid #334155; color:var(--mut); font-weight:600; }
  .tab.on { background:var(--azul); color:#fff; border-color:var(--azul); }
  .pane { display:none; } .pane.on { display:block; }
  .drop { border:2px dashed #475569; border-radius:12px; padding:30px; text-align:center;
          color:var(--mut); cursor:pointer; transition:.15s; }
  .drop:hover, .drop.hover { border-color:var(--azul); background:#0b1220; color:var(--txt); }
  .drop b { color:var(--txt); }
  .fileinfo { margin-top:12px; font-size:13px; color:var(--ok); min-height:18px; }
  button { cursor:pointer; border:0; border-radius:10px; font-weight:600; transition:.15s; }
  .btn-main { background:var(--azul); color:#fff; width:100%; margin-top:18px;
              padding:14px; font-size:16px; }
  .btn-main:hover { background:var(--azul2); }
  .btn-main:disabled { opacity:.5; cursor:wait; }
  .btn-dl { background:var(--ok); color:#06280f; padding:12px 18px; font-size:15px; }
  .hidden { display:none; }
  .resumo-top { display:flex; gap:14px; margin-bottom:16px; flex-wrap:wrap; }
  .pill { background:#0b1220; border:1px solid #334155; border-radius:10px; padding:10px 16px; }
  .pill b { font-size:20px; display:block; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th,td { text-align:left; padding:9px 10px; border-bottom:1px solid #334155; }
  th { color:var(--mut); }
  .tag-ok { color:var(--ok); } .tag-warn { color:var(--warn); } .erro { color:#f87171; }
  .nota { font-size:12px; color:var(--mut); margin-top:14px; line-height:1.5; }
  .spin { display:inline-block; width:16px; height:16px; border:2px solid #fff;
          border-top-color:transparent; border-radius:50%; animation:r .7s linear infinite;
          vertical-align:-3px; margin-right:8px; }
  @keyframes r { to { transform:rotate(360deg); } }
  input[type=file] { display:none; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Conversor TXT &rarr; CSV Correios</h1>
  <p class="sub">Selecione a pasta do dia e baixe os CSVs prontos.</p>

  <div class="card">
    <div class="tabs">
      <div id="tabPasta" class="tab on" onclick="setTab('pasta')">Selecionar pasta</div>
      <div id="tabZip"   class="tab"    onclick="setTab('zip')">Enviar .zip</div>
      <div id="tabPlan"  class="tab"    onclick="setTab('plan')">Enviar planilha</div>
    </div>

    <div id="panePasta" class="pane on">
      <div class="drop" onclick="document.getElementById('inPasta').click()">
        <b>Clique para escolher a pasta do dia</b><br>
        <span>(envia a pasta do dia inteira)</span>
      </div>
      <input id="inPasta" type="file" webkitdirectory directory multiple onchange="infoPasta()">
      <div id="infoPasta" class="fileinfo"></div>
    </div>

    <div id="paneZip" class="pane">
      <div id="dropZip" class="drop"
           onclick="document.getElementById('inZip').click()">
        <b>Clique ou arraste o .zip da pasta do dia</b><br>
        <span></span>
      </div>
      <input id="inZip" type="file" accept=".zip" onchange="infoZip()">
      <div id="infoZip" class="fileinfo"></div>
    </div>

    <div id="panePlan" class="pane">
      <div id="dropPlan" class="drop"
           onclick="document.getElementById('inPlan').click()">
        <b>Clique ou arraste a planilha (.xls / .xlsx)</b><br>
        <span>L&ecirc; a aba <b>INSIRA OS DADOS</b>. O nome do modelo vem do nome do arquivo.</span>
      </div>
      <input id="inPlan" type="file" accept=".xls,.xlsx" onchange="infoPlan()">
      <div id="infoPlan" class="fileinfo"></div>
    </div>

    <button id="btn" class="btn-main" onclick="gerar()">Gerar CSVs</button>
    <div class="nota">
      Cada pasta de modelo vira um <b>&lt;modelo&gt;.csv</b>. Endereços internacionais
      detectados vão para um <b>&lt;modelo&gt;_INTERNACIONAL.csv</b> separado.
    </div>
  </div>

  <div id="resultado" class="card hidden"></div>
</div>

<script>
let aba = 'pasta';
function setTab(t){
  aba = t;
  document.getElementById('tabPasta').classList.toggle('on', t==='pasta');
  document.getElementById('tabZip').classList.toggle('on', t==='zip');
  document.getElementById('tabPlan').classList.toggle('on', t==='plan');
  document.getElementById('panePasta').classList.toggle('on', t==='pasta');
  document.getElementById('paneZip').classList.toggle('on', t==='zip');
  document.getElementById('panePlan').classList.toggle('on', t==='plan');
}
function infoPlan(){
  const f = document.getElementById('inPlan').files[0];
  document.getElementById('infoPlan').textContent = f ? ('Selecionado: '+f.name) : '';
}
function infoPasta(){
  const fs = [...document.getElementById('inPasta').files].filter(f=>f.name.toLowerCase().endsWith('.txt'));
  document.getElementById('infoPasta').textContent = fs.length ? (fs.length+' arquivo(s) .txt selecionado(s)') : 'Nenhum .txt na pasta.';
}
function infoZip(){
  const f = document.getElementById('inZip').files[0];
  document.getElementById('infoZip').textContent = f ? ('Selecionado: '+f.name) : '';
}
// drag and drop do zip
const dz = document.getElementById('dropZip');
['dragover','dragenter'].forEach(e=>dz.addEventListener(e,ev=>{ev.preventDefault();dz.classList.add('hover');}));
['dragleave','drop'].forEach(e=>dz.addEventListener(e,ev=>{ev.preventDefault();dz.classList.remove('hover');}));
dz.addEventListener('drop',ev=>{ const f=ev.dataTransfer.files[0]; if(f){ document.getElementById('inZip').files=ev.dataTransfer.files; infoZip(); }});

// drag and drop da planilha
const dp = document.getElementById('dropPlan');
['dragover','dragenter'].forEach(e=>dp.addEventListener(e,ev=>{ev.preventDefault();dp.classList.add('hover');}));
['dragleave','drop'].forEach(e=>dp.addEventListener(e,ev=>{ev.preventDefault();dp.classList.remove('hover');}));
dp.addEventListener('drop',ev=>{ const f=ev.dataTransfer.files[0]; if(f){ document.getElementById('inPlan').files=ev.dataTransfer.files; infoPlan(); }});

function b64ToBlob(b64){
  const bin = atob(b64); const arr = new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
  return new Blob([arr], {type:'application/zip'});
}
function baixar(b64, nome){
  const url = URL.createObjectURL(b64ToBlob(b64));
  const a = document.createElement('a'); a.href=url; a.download=nome; a.click();
  setTimeout(()=>URL.revokeObjectURL(url), 4000);
}

async function gerar(){
  const fd = new FormData();
  if(aba==='pasta'){
    const fs = [...document.getElementById('inPasta').files].filter(f=>f.name.toLowerCase().endsWith('.txt'));
    if(!fs.length){ alert('Selecione a pasta do dia.'); return; }
    fs.forEach(f=> fd.append('arquivos', f, f.webkitRelativePath || f.name));
  } else if(aba==='zip') {
    const f = document.getElementById('inZip').files[0];
    if(!f){ alert('Selecione o arquivo .zip.'); return; }
    fd.append('zip', f);
  } else {
    const f = document.getElementById('inPlan').files[0];
    if(!f){ alert('Selecione a planilha (.xls ou .xlsx).'); return; }
    fd.append('planilha', f);
  }

  const box = document.getElementById('resultado');
  const btn = document.getElementById('btn');
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Gerando...';
  box.classList.remove('hidden'); box.innerHTML = 'Processando...';

  try{
    const r = await fetch('/gerar', { method:'POST', body: fd });
    const j = await r.json();
    if(!j.ok){ box.innerHTML = '<div class="erro">Erro: '+j.erro+'</div>'; return; }

    let linhas='';
    for(const m of j.modelos){
      const intl = m.internacionais
        ? '<span class="tag-warn">'+m.internacionais+' &rarr; '+m.arquivo_internacional+'</span>'
        : '<span style="color:#64748b">&mdash;</span>';
      linhas += '<tr><td><b>'+m.arquivo+'</b></td><td class="tag-ok">'+m.nacionais+'</td><td>'+intl+'</td></tr>';
    }
    box.innerHTML =
      '<div class="resumo-top">'
      + '<div class="pill"><b>'+j.modelos.length+'</b>modelos</div>'
      + '<div class="pill"><b class="tag-ok">'+j.total_nacionais+'</b>nacionais</div>'
      + '<div class="pill"><b class="tag-warn">'+j.total_internacionais+'</b>internacionais</div>'
      + '</div>'
      + '<table><thead><tr><th>Arquivo</th><th>Nacionais</th><th>Internacionais</th></tr></thead><tbody>'+linhas+'</tbody></table>'
      + '<div style="margin-top:18px"><button class="btn-dl" id="btnDl">Baixar '+j.zip_nome+'</button></div>';
    document.getElementById('btnDl').onclick = ()=> baixar(j.zip_b64, j.zip_nome);
    baixar(j.zip_b64, j.zip_nome);  // baixa automaticamente
  }catch(e){
    box.innerHTML = '<div class="erro">Falha: '+e+'</div>';
  }finally{
    btn.disabled=false; btn.textContent='Gerar CSVs';
  }
}
</script>
</body>
</html>
"""


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
