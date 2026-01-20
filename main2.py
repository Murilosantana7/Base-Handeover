import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

# ==============================
# CONFIGURAÇÕES
# ==============================
DOWNLOAD_DIR = "/tmp"
JSON_KEYFILE = "hxh.json"
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183"
WORKSHEET_NAME = "Base Handedover"

# CREDENCIAIS INSERIDAS
SHOPEE_OPS_ID = "Ops134294"
SHOPEE_PASS = "@Shopee123"

# ==============================
# FUNÇÕES AUXILIARES
# ==============================
def process_handedover_file(download_dir, download_path):
    """Renomeia o arquivo baixado para PROD-{HORA}.csv"""
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
            
        shutil.move(download_path, new_file_path)
        print(f"📄 Arquivo renomeado para: {new_file_path}")
        return new_file_path
    except Exception as e:
        print(f"❌ Erro ao renomear o arquivo: {e}")
        return None

def upload_handedover_gsheets(csv_file_path):
    """Faz o upload do CSV processado para o Google Sheets"""
    try:
        if not os.path.exists(csv_file_path):
            print(f"Arquivo {csv_file_path} não encontrado.")
            return

        print(f"📤 Iniciando upload para aba '{WORKSHEET_NAME}'...")
        
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEYFILE, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_url(SPREADSHEET_URL)
        worksheet = sheet.worksheet(WORKSHEET_NAME)
        
        # Leitura do CSV
        df = pd.read_csv(csv_file_path).fillna("")
        
        # Limpa a aba e insere os novos dados
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        
        print(f"✅ SUCESSO: Dados enviados para '{WORKSHEET_NAME}'.")
    except Exception as e:
        print(f"❌ Erro durante o upload no Google Sheets: {e}")

# ==============================
# FLUXO PRINCIPAL (PLAYWRIGHT)
# ==============================
async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            print("🔐 Acessando Shopee SPX...")
            await page.goto("https://spx.shopee.com.br/")
            
            # --- LOGIN ---
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill(SHOPEE_OPS_ID)
            await page.locator('xpath=//*[@placeholder="Senha"]').fill(SHOPEE_PASS)
            
            # Clica no botão de login
            await page.locator('button[type="submit"], button:has-text("Login")').first.click()
            
            await page.wait_for_load_state("networkidle")

            # --- TENTATIVA DE FECHAR POPUP ---
            try:
                close_btn = page.locator('.ssc-dialog-close')
                if await close_btn.is_visible(timeout=5000):
                    await close_btn.click()
            except:
                pass 

            # --- NAVEGAÇÃO HANDEDOVER ---
            print("\n🔄 Acessando Hub Linehaul Trips...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(3000)

            # Clicar na aba "Handedover"
            print("🔍 Selecionando filtro 'Handedover'...")
            try:
                await page.get_by_text("Handedover", exact=True).click(timeout=5000)
            except:
                print("⚠️ Texto não encontrado, tentando XPath original...")
                await page.locator('xpath=/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/span[1]').click()
            
            await page.wait_for_timeout(3000)

            # --- EXPORTAR ---
            print("Geração do relatório solicitada...")
            await page.get_by_role("button", name="Exportar").first.click()
            
            # Aguarda processamento
            await page.wait_for_timeout(6000) 

            # --- TASK CENTER ---
            print("Indo para o Task Center baixar o arquivo...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_load_state("networkidle")
            
            try:
                await page.get_by_text("Exportar tarefa").click(timeout=3000)
            except:
                pass

            # --- DOWNLOAD ---
            async with page.expect_download(timeout=60000) as download_info:
                await page.get_by_role("button", name="Baixar").first.click()

            download = await download_info.value
            temp_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(temp_path)
            print(f"📥 Download concluído: {download.suggested_filename}")

            # --- PROCESSAMENTO E UPLOAD ---
            final_path = process_handedover_file(DOWNLOAD_DIR, temp_path)
            if final_path:
                upload_handedover_gsheets(final_path)

            print("\n🎉 PROCESSO HANDEDOVER FINALIZADO!")

        except Exception as e:
            print(f"❌ Erro fatal no processo: {e}")
            await page.screenshot(path="erro_handedover.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
