# 🎟️ Distribuidor de Senhas — Streamlit

App em Streamlit que lê uma planilha do Google Sheets e distribui **senhas sequenciais por área**,
gravando os dados e gerando um **PDF** pronto para impressão.

## 🚀 Como rodar localmente

1. **Clone o repositório**
   ```bash
   git clone https://github.com/<seu-usuario>/SenhasGF.git
   cd SenhasGF
   ```

2. **Crie um ambiente virtual e instale as dependências**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure as variáveis de ambiente**
   - Copie o arquivo `.env.example` para `.env` e preencha o `SPREADSHEET_ID` com o ID da sua planilha.
   - Informe o caminho para o JSON da conta de serviço em `GOOGLE_SERVICE_ACCOUNT_FILE`. Se preferir OAuth, utilize
     `GOOGLE_CLIENT_SECRET_FILE` (o token será salvo automaticamente em `token.json`).
   - (Opcional) Ajuste `PRINT_SERVER_URL`, `PRINT_TOKEN`, `PDF_LOGO_PATH` e `APP_TZ` conforme a sua necessidade.

   > Dica: mantenha os arquivos sensíveis (JSONs de credenciais, `.env`, `token.json`) fora do controle de versão.

4. **Compartilhe a planilha** com o e-mail da conta de serviço (permissão de Editor) ou certifique-se de autorizar
   o OAuth na primeira execução.

5. **Execute o app**
   ```bash
   streamlit run streamlit_app.py
   ```

> Também é possível continuar usando o `secrets.toml` do Streamlit Cloud: basta informar as mesmas chaves do `.env`.

## ✅ Estrutura da Planilha

- Aba **`Nomes`** (editável): deve conter ao menos as colunas:
  - `Área` — nome exibido no app
  - `Aba` *(opcional)* — nome da aba de destino; se ausente, usa o próprio texto de `Área`
  - `Ativa` — *Sim/Não* (ou True/False, 1/0)

- Para **cada área ativa**, o app grava **nessa aba** (criando se não existir) o seguinte cabeçalho:
  ```
  Senha | Nome | Telefone | Bairro | Data e Hora de Registro | Data e Hora de Atendimento
  ```

A *Senha* é sequencial por planilha (linha - 1, considerando a linha 1 como cabeçalho).

## 🖨️ Impressão automática (opcional)

Defina `PRINT_SERVER_URL` e `PRINT_TOKEN` no `.env` (ou nos secrets) para ativar o envio automático do PDF gerado.
Quando omitidos, o app apenas disponibiliza o download do arquivo.

## 🧱 Base / Inspiração

- Padrão de autenticação e escrita no Sheets e técnica para extrair a linha gravada via `updatedRange` foram inspirados dos utilitários existentes (ver `utils.py` e `streamlit_app.py`).

## 🖼️ Logotipo do PDF

Para personalizar o cabeçalho do ticket, coloque um arquivo `logo.png` dentro da pasta `assets/` (fora do versionamento)
ou defina a variável de ambiente `PDF_LOGO_PATH` apontando para o arquivo desejado.
