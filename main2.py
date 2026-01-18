import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

# ==============================
# Configuração de Ambiente
# ==============================
DOWNLOAD_DIR = "/tmp" 
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"✅ Arquivo salvo: {new_file_name}")
        return new_file_path
    except Exception as e:
        print(f"❌ Erro ao renomear: {e}")
        return None

def update_google_sheets_handover(csv_file_path):
    try:
        if not os.path.exists(csv_file_path): return
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183")
        worksheet = sheet.worksheet("Base Handedover")
        
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        print("✅ Google Sheets atualizado!")
    except Exception as e:
        print(f"❌ Erro Sheets: {e}")

# ==============================
# Fluxo Principal Otimizado
# ==============================
async def main():
    async with async_playwright() as p:
        # Modo headless é obrigatório no GitHub Actions
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=True, 
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            print("🔐 Acessando portal SPX (Ops113074)...")
            # Mudança crucial: wait_until="commit" entra na página assim que o servidor responde
            await page.goto("https://spx.shopee.com.br/", wait_until="commit", timeout=120000)
            
            print("⏳ Aguardando campos de login...")
            # Espera apenas pelo elemento, não pela rede inteira
            input_user = page.locator('input[placeholder*="Ops ID"]')
            await input_user.wait_for(state="visible", timeout=60000)
            
            await input_user.fill('Ops113074')
            await page.locator('input[placeholder*="Senha"]').fill('@Shopee123')
            
            print("🚀 Clicando em Entrar...")
            await page.locator('button:has-text("Login"), button:has-text("Entrar"), .ant-btn-primary').first.click()
            
            # Espera curta para processar o clique
            await page.wait_for_timeout(10000)

            # 2. TRATAMENTO DE POP-UPS
            print("⏳ Limpando possíveis pop-ups...")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(2000)

            # 3. NAVEGAÇÃO DIRETA
            print("🚚 Indo para Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(15000)

            print("🔍 Selecionando 'Handedover'...")
            # Tenta localizar o texto e clicar via JavaScript para ignorar sobreposições
            await page.get_by_text("Handedover").first.evaluate("el => el.click()")
            await page.wait_for_timeout(5000)

            # 4. EXPORTAÇÃO E TASK CENTER
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name="Exportar").first.evaluate("el => el.click()")
            await page.wait_for_timeout(10000)

            print("📂 Baixando no Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter", wait_until="domcontentloaded")
            await page.wait_for_timeout(10000)

            # Clique na aba e download
            try:
                await page.get_by_text("Exportar tarefa").first.click(timeout=5000)
            except: pass

            async with page.expect_download(timeout=60000) as download_info:
                await page.locator("text=Baixar").first.evaluate("el => el.click()")

            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
            if final_path:
                update_google_sheets_handover(final_path)

        except Exception as e:
            print(f"❌ Erro durante a execução: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
