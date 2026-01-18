import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import re

# Configuração de Ambiente
DOWNLOAD_DIR = "/tmp" 
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
IS_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path): os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"✅ Arquivo renomeado para: {new_file_name}")
        return new_file_path
    except Exception as e:
        print(f"❌ Erro ao renomear: {e}")
        return None

def update_google_sheets_handover(csv_file_path):
    try:
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
        print(f"❌ Erro no Sheets: {e}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=IS_GITHUB, slow_mo=0 if IS_GITHUB else 500)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # 1. LOGIN RESILIENTE (Evita erro da imagem 8d26ad)
            print(f"🔐 Iniciando Login... (GitHub: {IS_GITHUB})")
            await page.goto("https://spx.shopee.com.br/", timeout=120000)
            await page.locator('input[placeholder*="Ops ID"]').fill('Ops134294')
            await page.locator('input[placeholder*="Senha"]').fill('@Shopee123')
            
            # Clique via JavaScript para ignorar bloqueios de sobreposição
            login_btn = page.locator('button:has-text("Login"), .ant-btn-primary').first
            await login_btn.evaluate("el => el.click()")
            
            await page.wait_for_timeout(15000)
            await page.keyboard.press("Escape")

            # 2. FILTROS
            print("🚚 Acessando Viagens e Aplicando Filtro...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(10000)
            
            # Filtro Handedover (conforme imagem 8bbb84)
            xpath_filtro = "xpath=/html/body/div/div/div[2]/div[2]/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div/div/div/div/div[3]/span"
            await page.locator(xpath_filtro).first.evaluate("el => el.click()")
            await page.wait_for_timeout(5000)

            # 3. EXPORTAR
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name=re.compile(r"Exportar|Export", re.I)).first.evaluate("el => el.click()")
            await page.wait_for_timeout(15000)

            # 4. DOWNLOAD (Bypass total para evitar erro das imagens 8caf07/8cbac0)
            print("📂 Navegando para Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(10000)

            # Clique em Export Task para garantir foco na tabela (conforme imagem 8c3ae1)
            try: await page.locator("text='Export Task'").first.evaluate("el => el.click()")
            except: pass

            print("⬇️ Tentando download forçado...")
            # Seletor híbrido para Baixar/Download (conforme imagem 8cbe49)
            btn_download = page.locator("text='Baixar', text='Download'").first
            
            async with page.expect_download(timeout=120000) as download_info:
                await btn_download.evaluate("el => el.click()")
                print("✅ Comando de download disparado via JS.")

            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
            if final_path:
                update_google_sheets_handover(final_path)

        except Exception as e:
            print(f"❌ Falha Crítica: {e}")
            if not IS_GITHUB: await page.screenshot(path="debug_error.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
