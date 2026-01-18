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

# Detecta se está no GitHub ou no PC (IDLE)
IS_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path): os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"✅ Arquivo salvo como: {new_file_name}")
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
        print("✅ Dados enviados para o Google Sheets!")
    except Exception as e:
        print(f"❌ Erro no Sheets: {e}")

async def main():
    async with async_playwright() as p:
        # Abre navegador visual se for no PC, invisível se for no GitHub
        browser = await p.chromium.launch(
            headless=IS_GITHUB,
            slow_mo=0 if IS_GITHUB else 500
        )
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            print(f"🔐 Login (Ops134294) - Modo GitHub: {IS_GITHUB}")
            await page.goto("https://spx.shopee.com.br/", timeout=120000)
            await page.locator('input[placeholder*="Ops ID"]').fill('Ops134294')
            await page.locator('input[placeholder*="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), .ant-btn-primary').first.click()
            await page.wait_for_timeout(15000)
            await page.keyboard.press("Escape")

            print("🚚 Aplicando filtros de Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(10000)

            # Filtro Handedover via XPath (conforme imagem 8bbb84)
            xpath_filtro = "xpath=/html/body/div/div/div[2]/div[2]/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div/div/div/div/div[3]/span"
            await page.locator(xpath_filtro).first.click()
            await page.wait_for_timeout(5000)

            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name=re.compile(r"Exportar|Export", re.I)).first.click()
            await page.wait_for_timeout(15000)

            print("📂 Navegando para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(10000)

            # Limpeza visual para focar o primeiro item (image_8c3ae1)
            print("🧹 Limpando visualização (Export Task)...")
            try:
                await page.locator("text='Export Task'").first.click()
                await page.wait_for_timeout(5000)
            except: pass

            # --- O BLOCO DO DOWNLOAD (AJUSTADO PARA SER IGUAL AO PENDING) ---
            print("⬇️ Localizando botão de download...")
            try:
                # Usa um seletor que aceita Baixar ou Download (image_8cbe49)
                seletor_download = "text='Baixar', text='Download'"
                
                async with page.expect_download(timeout=90000) as download_info:
                    print("🚀 Executando clique forçado (Bypass Timeout)...")
                    # evaluate evita o erro de 'waiting for locator to be visible' (image_8caf07)
                    await page.locator(seletor_download).first.evaluate("el => el.click()")

                download = await download_info.value
                path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                await download.save_as(path)
                
                final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                if final_path:
                    update_google_sheets_handover(final_path)
                    print("🎉 PROCESSO CONCLUÍDO COM SUCESSO!")

            except Exception as e:
                print(f"❌ Erro no download: {e}")
                await page.screenshot(path="erro_download.png")

        finally:
            if IS_GITHUB:
                await browser.close()
            else:
                print("🏁 No IDLE, feche o navegador manualmente.")

if __name__ == "__main__":
    asyncio.run(main())
