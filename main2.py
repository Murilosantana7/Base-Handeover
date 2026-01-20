import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

# ==============================
# Configuração do diretório de downloads
# ==============================
DOWNLOAD_DIR = "/tmp" 
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==============================
# Função de renomear arquivo HANDEDOVER
# ==============================
def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"✅ Arquivo Handedover salvo como: {new_file_path}")
        return new_file_path
    except Exception as e:
        print(f"❌ Erro ao renomear o arquivo Handedover: {e}")
        return None

# ==============================
# Função de atualização Google Sheets - HANDEDOVER
# ==============================
def update_packing_google_sheets_handover(csv_file_path):
    try:
        if not os.path.exists(csv_file_path):
            print(f"Arquivo Handedover {csv_file_path} não encontrado.")
            return
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(
            "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183"
        )
        worksheet = sheet.worksheet("Base Handedover")
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        print("✅ Arquivo Handedover enviado com sucesso para a aba 'Base Handedover'.")
    except Exception as e:
        print(f"❌ Erro durante o upload Handedover: {e}")

# ==============================
# Fluxo principal Playwright
# ==============================
async def main():
    async with async_playwright() as p:
        # headless=False é necessário para rodar com xvfb no GitHub Actions
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={'width': 1366, 'height': 768} # Força resolução padrão para evitar layouts mobile
        )
        page = await context.new_page()

        try:
            # 1. LOGIN
            print("🔐 Fazendo login no SPX (Ops134294)...")
            await page.goto("https://spx.shopee.com.br/", timeout=60000)
            
            # Preenchimento robusto
            await page.locator('xpath=//*[@placeholder="Ops ID"]').wait_for(state="visible", timeout=20000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            
            print("🚀 Enviando login...")
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=30000)

            # 2. TRATAMENTO DE POP-UP (MANTIDO O SEU CÓDIGO)
            print("⏳ Verificando pop-ups (5s)...")
            await page.wait_for_timeout(5000) 
            
            popup_closed = False
            
            # Tentativa 1: ESC
            try:
                await page.keyboard.press("Escape")
            except: pass

            # Tentativa 2: Botões comuns
            if not popup_closed:
                possible_buttons = [
                    ".ssc-dialog-header .ssc-dialog-close-icon-wrapper",
                    ".ssc-dialog-close-icon-wrapper",
                    ".ant-modal-close",              
                    ".ant-modal-close-x"
                ]
                for selector in possible_buttons:
                    if await page.locator(selector).count() > 0:
                        try:
                            await page.locator(selector).first.click()
                            print(f"✅ Pop-up fechado via seletor: {selector}")
                            popup_closed = True
                            break
                        except: pass

            await page.wait_for_timeout(2000)

            # 3. NAVEGAÇÃO
            print("🚚 Indo para a página de viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(8000)

            print("🔍 Filtrando por 'Handedover'...")
            # Tenta clicar no filtro (com fallback robusto)
            try:
                # Tenta primeiro pelo texto simples (mais seguro que XPath gigante)
                await page.locator("text=Handedover").first.click(timeout=5000)
            except:
                try:
                    # Fallback para o seu XPath original se o texto falhar
                    xpath_hand = "/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/span[1]"
                    await page.locator(f'xpath={xpath_hand}').click()
                except:
                    print("⚠️ Aviso: Não consegui clicar em Handedover (pode já estar selecionado).")

            print("✅ Filtro aplicado (ou tentado).")
            await page.wait_for_timeout(5000)

            # 4. EXPORTAÇÃO
            print("📤 Solicitando Exportação...")
            try:
                await page.get_by_role("button", name="Exportar").first.click(timeout=10000)
            except:
                print("⚠️ Botão Exportar não encontrado (talvez página demorou).")

            print("📂 Indo para o Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            
            # Aguarda a tabela aparecer
            try:
                await page.wait_for_selector("table", timeout=20000)
            except: pass

            # 5. DOWNLOAD (CORREÇÃO CRÍTICA AQUI)
            # Removemos o clique em "Exportar tarefa" que travava o script
            print("⬇️ Procurando o arquivo mais recente...")

            # Procura botão Baixar (PT) ou Download (EN) NA PRIMEIRA LINHA da tabela
            btn_baixar = page.locator("tr").first.locator("text=Baixar").or_(page.locator("text=Download"))
            
            # Espera até 60s para o botão aparecer (caso esteja "Processando")
            print("⏳ Aguardando botão de download ficar visível...")
            await btn_baixar.first.wait_for(state="visible", timeout=60000)

            async with page.expect_download(timeout=60000) as download_info:
                await btn_baixar.first.click()

            download = await download_info.value
            download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(download_path)
            print(f"✅ Download original salvo: {download_path}")

            # 6. ATUALIZAÇÃO DA PLANILHA
            new_file_path = rename_downloaded_file_handover(DOWNLOAD_DIR, download_path)
            if new_file_path:
                update_packing_google_sheets_handover(new_file_path)

            print("\n🎉 PROCESSO CONCLUÍDO COM SUCESSO!")

        except Exception as e:
            print(f"❌ Erro crítico: {e}")
            # Tira print do erro para debug no GitHub Actions
            try: await page.screenshot(path="erro_fatal.png")
            except: pass
            raise e # Força o erro aparecer no log do GitHub
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
