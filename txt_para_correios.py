# -*- coding: utf-8 -*-
"""
Converte os arquivos .txt das pastas de modelo (de uma pasta de dia) em
arquivos .csv no formato EXATO aceito pelos Correios.

Uso:
    python txt_para_correios.py "C:\\Users\\Pedro\\OneDrive - Kasil\\5. TRANSF\\01.06\\28-05-2026"

O script percorre cada subpasta de modelo (2B1, 5B, 8C1, ...), le o .txt
de dentro dela e gera <modelo>.csv dentro de <pasta-do-dia>\\_SAIDA.

O formato de saida (separador, ordem das colunas, espacos, encoding cp1252)
e identico ao gerado pelo fluxo antigo (planilha -> script).
"""

import os
import sys
import glob

ENCODING = 'cp1252'          # leitura do .txt e escrita do .csv
NOME_PASTA_SAIDA = '_SAIDA'  # subpasta criada dentro da pasta do dia


# ---------------------------------------------------------------------------
# Correcao de CEP (mesmo dicionario e mesma regra do script original)
# ---------------------------------------------------------------------------
CEPS_CORRIGIDOS = {
    "19274000": "19272338",
    "18681830": "18681608",
    "81320000": "81320490",
    "14955000": "14955154",
    "00001000": "04718000",
    "13295000": "13295001",
    "18185000": "18185001",
    "18725000": "18725001",
    "06730000": "06733402",
}

# UFs brasileiras validas (usadas para classificar enderecos internacionais)
UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}


def ajustar_cep(cep):
    """Aplica apenas as correcoes pontuais conhecidas (dicionario).
    A regra generica '0000 -> 0001' NAO e aplicada: CEPs terminados em
    0000 sao mantidos como vieram no txt."""
    if cep is None:
        return ""
    cep_str = ''.join(ch for ch in str(cep) if ch.isdigit()).zfill(8)
    if cep_str == "00000000":
        return ""
    if cep_str in CEPS_CORRIGIDOS:
        return CEPS_CORRIGIDOS[cep_str]
    return cep_str


def eh_internacional(campos):
    """Heuristica para identificar enderecos fora do Brasil.
    Pega UF vazia/invalida ou CEP iniciando em '00' (faixa inexistente no BR).
    OBS: registros com UF brasileira valida mas endereco estrangeiro
    (ex.: cidade nos Acores com UF=RO) NAO sao detectados aqui e precisam
    de conferencia manual."""
    uf = campos[11].strip().upper()
    cep = campos[6]
    if uf == "" or uf not in UFS_VALIDAS:
        return True
    if cep[:2] == "00":
        return True
    return False


# ---------------------------------------------------------------------------
# Funcoes auxiliares de formatacao
# ---------------------------------------------------------------------------
def limpar(valor, remover_virgula=True):
    """Remove o separador ';' (e opcionalmente a virgula) de um campo,
    igual ao tratamento do script original."""
    if valor is None:
        return ""
    txt = str(valor).replace(';', '')
    if remover_virgula:
        txt = txt.replace(',', '')
    return txt


def expandir_data(valor):
    """Converte data dd/mm/aa em dd/mm/aaaa. Mantem o valor original se
    nao estiver no formato esperado."""
    v = str(valor).strip()
    partes = v.split('/')
    if len(partes) == 3 and len(partes[2]) == 2 and partes[2].isdigit():
        partes[2] = '20' + partes[2]
        return '/'.join(partes)
    return v


def formatar_telefone(valor):
    """(11)5039-4774 -> 11 5039-4774"""
    return str(valor).replace('(', '').replace(')', ' ')


def tratamento_auxiliar1(valor):
    """Para empresas o txt traz 'A<crase> NOME'; no CSV vira 'A NOME'."""
    v = str(valor)
    if v[:2] == 'À ':      # 'A' com crase + espaco
        v = 'A ' + v[2:]
    return v


def campo(partes, indice):
    """Acesso seguro ao campo de indice dado (retorna '' se nao existir)."""
    if 0 <= indice < len(partes):
        return partes[indice]
    return ""


# ---------------------------------------------------------------------------
# Conversao de uma linha do txt -> lista de 24 campos do csv
# ---------------------------------------------------------------------------
def linha_txt_para_campos(linha):
    p = linha.split('#')

    nome = limpar(campo(p, 2))
    if not nome.strip():
        return None  # linha sem nome -> ignorada

    ddd        = limpar(campo(p, 14))
    telefone   = limpar(campo(p, 15))
    cep        = ajustar_cep(campo(p, 9))
    logradouro = limpar(campo(p, 3))
    bairro     = limpar(campo(p, 4))
    cidade     = limpar(campo(p, 7))
    uf         = limpar(campo(p, 8))
    complemento = limpar(campo(p, 5))
    numero     = limpar(campo(p, 6))

    aux1 = 'Auxiliar1:' + tratamento_auxiliar1(limpar(campo(p, 19)))
    aux2 = 'Auxiliar2:' + expandir_data(limpar(campo(p, 20)))
    aux3 = 'Auxiliar3:' + limpar(campo(p, 21))
    aux4 = 'Auxiliar4:' + limpar(campo(p, 22))
    aux5 = 'Auxiliar5:' + limpar(campo(p, 23), remover_virgula=False)
    aux6 = 'Auxiliar6:' + formatar_telefone(limpar(campo(p, 24)))
    aux7 = 'Auxiliar7:' + limpar(campo(p, 25))
    aux8 = 'Auxiliar8:' + limpar(campo(p, 26))
    aux9 = 'Auxiliar9:' + limpar(campo(p, 27))

    return [
        '.', nome, '', ddd, telefone, '', cep, '',
        logradouro, bairro, cidade, uf, 'N', complemento, numero,
        aux1, aux2, aux3, aux4, aux5, aux6, aux7, aux8, aux9,
    ]


# ---------------------------------------------------------------------------
# Processa um arquivo .txt inteiro -> lista de linhas (campos) ja ordenada
# ---------------------------------------------------------------------------
def processar_conteudo(conteudo):
    """Recebe o TEXTO de um .txt e devolve a lista de registros (campos)
    crus, sem ordenar nem numerar duplicados."""
    registros = []
    for linha in conteudo.splitlines():
        if not linha.strip():
            continue
        campos = linha_txt_para_campos(linha)
        if campos is not None:
            registros.append(campos)
    return registros


def processar_txt(caminho_txt):
    """Le um .txt do disco e devolve seus registros crus."""
    with open(caminho_txt, 'r', encoding=ENCODING, errors='replace') as f:
        return processar_conteudo(f.read())


def ordenar_e_numerar(registros):
    """Ordena por CEP (estavel) e prefixa duplicados de nome com '(N) '."""
    registros.sort(key=lambda c: c[6])
    contagem = {}
    for c in registros:
        nome = c[1]
        contagem[nome] = contagem.get(nome, 0) + 1
        if contagem[nome] > 1:
            c[1] = '({}) {}'.format(contagem[nome], nome)
    return registros


def gerar_csv_bytes(registros):
    """Monta o conteudo do CSV (cp1252, ';' como separador, \\r\\n) em bytes."""
    texto = ''.join(';'.join(c) + '\r\n' for c in registros)
    return texto.encode(ENCODING, errors='replace')


def escrever_csv(caminho_csv, registros):
    with open(caminho_csv, 'wb') as f:
        f.write(gerar_csv_bytes(registros))


def converter_textos(modelos):
    """Converte um conjunto de modelos em memoria.

    modelos: dict {nome_modelo: [conteudo_txt, ...]}
    Retorna: {
        'arquivos': {nome_csv: bytes, ...},
        'modelos':  [resumo por modelo],
        'total_nacionais': int,
        'total_internacionais': int,
    }
    """
    arquivos = {}
    resumo = []
    total_nac = 0
    total_int = 0

    for modelo in sorted(modelos.keys()):
        registros = []
        for texto in modelos[modelo]:
            registros.extend(processar_conteudo(texto))
        if not registros:
            continue

        nacionais = [c for c in registros if not eh_internacional(c)]
        internac = [c for c in registros if eh_internacional(c)]
        ordenar_e_numerar(nacionais)
        ordenar_e_numerar(internac)

        arquivos[modelo + '.csv'] = gerar_csv_bytes(nacionais)
        total_nac += len(nacionais)

        info = {
            'modelo': modelo,
            'arquivo': modelo + '.csv',
            'nacionais': len(nacionais),
            'internacionais': len(internac),
            'arquivo_internacional': None,
        }
        if internac:
            nome_int = modelo + '_INTERNACIONAL.csv'
            arquivos[nome_int] = gerar_csv_bytes(internac)
            total_int += len(internac)
            info['arquivo_internacional'] = nome_int

        resumo.append(info)

    return {
        'arquivos': arquivos,
        'modelos': resumo,
        'total_nacionais': total_nac,
        'total_internacionais': total_int,
    }


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Uso: python txt_para_correios.py \"<caminho da pasta do dia>\"")
        sys.exit(1)

    pasta_dia = os.path.abspath(sys.argv[1])
    if not os.path.isdir(pasta_dia):
        print("ERRO: pasta nao encontrada:", pasta_dia)
        sys.exit(1)

    resultado = converter_pasta(pasta_dia)

    print("Pasta do dia :", resultado['pasta_dia'])
    print("Pasta saida  :", resultado['pasta_saida'])
    print("=" * 50)
    for m in resultado['modelos']:
        msg = "  {:<12} -> {} nacional(is)".format(m['arquivo'], m['nacionais'])
        if m['internacionais']:
            msg += "  |  {} internacional(is) -> {}".format(
                m['internacionais'], m['arquivo_internacional'])
        print(msg)
    print("=" * 50)
    print("Concluido: {} modelo(s) | {} nacionais | {} internacionais.".format(
        len(resultado['modelos']), resultado['total_nacionais'],
        resultado['total_internacionais']))


def converter_pasta(pasta_dia):
    """Processa uma pasta de dia inteira e grava os CSVs em <pasta>/_SAIDA.

    Retorna um dicionario com o resumo do processamento (usado tanto pelo
    CLI quanto pelo web app)."""
    pasta_dia = os.path.abspath(pasta_dia)
    if not os.path.isdir(pasta_dia):
        raise ValueError("Pasta nao encontrada: {}".format(pasta_dia))

    # Le todos os .txt e planilhas agrupados por pasta de modelo
    modelos = {}
    for nome_item in sorted(os.listdir(pasta_dia)):
        sub = os.path.join(pasta_dia, nome_item)
        if not os.path.isdir(sub) or nome_item == NOME_PASTA_SAIDA:
            continue
        textos = []
        for txt in glob.glob(os.path.join(sub, '*.txt')):
            with open(txt, 'r', encoding=ENCODING, errors='replace') as f:
                textos.append(f.read())
        # planilhas .xls/.xlsx na mesma pasta de modelo
        planilhas = (glob.glob(os.path.join(sub, '*.xls'))
                     + glob.glob(os.path.join(sub, '*.xlsx')))
        if planilhas:
            import planilha_para_txt as _pl
            for caminho in planilhas:
                with open(caminho, 'rb') as f:
                    textos.append(_pl.ler_planilha_bytes(f.read(), caminho))
        if not textos:
            continue
        modelos[nome_item] = textos

    res = converter_textos(modelos)

    # Grava os CSVs em <pasta_dia>/_SAIDA
    pasta_saida = os.path.join(pasta_dia, NOME_PASTA_SAIDA)
    os.makedirs(pasta_saida, exist_ok=True)
    for nome, dados in res['arquivos'].items():
        with open(os.path.join(pasta_saida, nome), 'wb') as f:
            f.write(dados)

    res['pasta_dia'] = pasta_dia
    res['pasta_saida'] = pasta_saida
    return res


if __name__ == '__main__':
    main()
