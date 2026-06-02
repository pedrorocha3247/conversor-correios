# Conversor TXT → CSV Correios

Converte as pastas de **modelo de notificação** (cada uma com um `.txt`) em
arquivos **`.csv` no formato aceito pelos Correios**, agrupados por modelo.

- Web app (Flask): o usuário seleciona a pasta do dia **ou** envia um `.zip`,
  e baixa um `.zip` com os CSVs prontos.
- CLI: gera os CSVs direto no disco (`<pasta-do-dia>/_SAIDA`).

## Como funciona a conversão

Cada linha do `.txt` (campos separados por `#`) vira uma linha do `.csv`
(campos separados por `;`, encoding **cp1252**), com:

- ordenação por **CEP** ascendente;
- numeração de nomes duplicados: `(2) `, `(3) `…;
- empresas: prefixo `À ` → `A `;
- data `dd/mm/aa` → `dd/mm/aaaa`; telefone `(11)5039-4774` → `11 5039-4774`;
- correções de CEP conhecidas (dicionário em `txt_para_correios.py`);
- **endereços internacionais** (UF vazia/inválida ou CEP iniciando em `00`)
  vão para um `<modelo>_INTERNACIONAL.csv` separado, para conferência manual.

> Observação: endereços estrangeiros digitados com **UF brasileira válida**
> (ex.: cidade nos Açores com UF=RO) não são detectados automaticamente.

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py
# abre em http://127.0.0.1:5000
```

CLI (gera no disco, sem navegador):

```bash
python txt_para_correios.py "C:\caminho\para\a\pasta\do\dia"
```

## Deploy no Render

1. Suba este repositório no GitHub.
2. No Render: **New → Blueprint** e aponte para o repositório
   (ele lê o `render.yaml`). Ou **New → Web Service** com:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1`
3. Deploy. A URL pública pode ser usada por qualquer pessoa.

## Estrutura esperada da pasta do dia

```
28-05-2026/
├── 2B1/   └── 2B1.txt
├── 5B/    └── 5B.txt
├── 8C1/   └── 8C1.txt
└── ...
```

## Privacidade

Os `.txt`/`.csv` contêm dados pessoais (nome, telefone, endereço). O
`.gitignore` impede que esses arquivos sejam versionados. No app hospedado,
o processamento é feito em memória e o resultado só volta para quem enviou.
