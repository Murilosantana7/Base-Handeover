import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import re

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
        print(f"✅ Arquivo Handedover salvo como: {new_file_path}")
        return new_file_path
    except Exception as e:
        print(f"❌ Erro ao renomear arquivo: {e}")
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
        print("✅ Dados enviados para a aba 'Base Handedover'!")
    except Exception as e:
        print(f"❌ Erro no Google Sheets: {e}")

# ==============================
# Fluxo Principal Playwright
# ==============================
async def main():
    async with async_playwright() as p:
        # Lançamento idêntico ao script que funciona (Base Pending)
        browser = await p.chromium.launch(headless=True) # Mantenha True para GitHub Actions
        context = await browser.new_context(
            accept_downloads=True, 
            viewport={'width': 1366, 'height': 768}
        )
        page = await context.new_page()

        try:
            # 1. LOGIN (Usando a lógica do script funcional e suas credenciais)
            print("🔐 Fazendo login no SPX (Ops113074)...")
            await page.goto("https://spx.shopee.com.br/", wait_until="networkidle", timeout=90000)
            
            # Espera pelo seletor de login (usando seletor flexível para GitHub)
            await page.wait_for_selector('input[placeholder*="Ops ID"], xpath=//*[@placeholder="Ops ID"]', timeout=30000)
            
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops113074')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            
            # Clique no botão de login
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            
            print("⏳ Aguardando estabilização pós-login (40s)...")
            await page.wait_for_load_state("networkidle", timeout=40000)

            # 2. TRATAMENTO DE POP-UPS
            print("⏳ Verificando pop-ups (10s)...")
            await page.wait_for_timeout(10000)
            await page.keyboard.press("Escape")
            
            possible_buttons = [".ssc-dialog-close-icon-wrapper", ".ant-modal-close", ".ant-modal-close-x"]
            for selector in possible_buttons:
                if await page.locator(selector).count() > 0:
                    await page.locator(selector).first.evaluate("el => el.click()")
                    break

            # 3. NAVEGAÇÃO E FILTRO HANDEDOVER
            print("🚚 Acessando página de viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(12000)

            print("🔍 Selecionando status 'Handedover'...")
            # Tentativa via JS para maior estabilidade
            try:
                await page.get_by_text("Handedover").first.evaluate("el => el.click()")
            except:
                xpath_hand = "/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/span[1]"
                await page.locator(f'xpath={xpath_hand}').evaluate("el => el.click()")
            
            await page.wait_for_timeout(10000)

            # 4. EXPORTAÇÃO
            print("📤 Clicando em Exportar...")
            await page.get_by_role("button", name="Exportar").first.evaluate("el => el.click()")
            await page.wait_for_timeout(12000)

            # 5. DOWNLOAD NO CENTRO DE TAREFAS
            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(12000)

            # Seleciona a aba correta
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
            except: pass

            print("⬇️ Aguardando botão 'Baixar'...")
            await page.wait_for_selector("text=Baixar", timeout=30000)

            async with page.expect_download(timeout=60000) as download_info:
                # A técnica "mágica" do evaluate para evitar bloqueios
                await page.locator("text=Baixar").first.evaluate("el => el.click()")

            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            # Finalização e Upload
            final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
            if final_path:
                update_google_sheets_handover(final_path)
                print("\n🎉 PROCESSO HANDEDOVER CONCLUÍDO!")

        except Exception as e:
            print(f"❌ Erro: {e}")
            await page.screenshot(path="debug_handedover.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
