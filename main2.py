import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

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
        return new_file_path
    except Exception as e:
        return None

def update_packing_google_sheets_handover(csv_file_path):
    try:
        if not os.path.exists(csv_file_path):
            return
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183")
        worksheet = sheet.worksheet("Base Handedover")
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e:
        print(f"Erro no Sheets: {e}")

async def main():
    async with async_playwright() as p:
        # headless=True é obrigatório para rodar no GitHub Actions
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # Login
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill(os.environ.get('SHOPEE_USER', 'Ops134294'))
            await page.locator('xpath=//*[@placeholder="Senha"]').fill(os.environ.get('SHOPEE_PASS', '@Shopee123'))
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle")

            # Fechar Pop-ups
            await page.wait_for_timeout(5000)
            await page.keyboard.press("Escape")

            # Navegação até a exportação
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_load_state("networkidle")
            await page.get_by_text("Handedover").click()
            await page.wait_for_timeout(3000)
            await page.get_by_role("button", name="Exportar").first.click()
            
            # Centro de Tarefas
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_load_state("networkidle")

            # --- USO DO SEU XPATH ---
            xpath_exportar = '/html/body/div/div/div[2]/div[1]/div[1]/span/span[1]/span'
            botao_exportar = page.locator(f'xpath={xpath_exportar}')
            
            # Espera o botão aparecer e clica
            await botao_exportar.wait_for(state="visible", timeout=60000)
            await botao_exportar.click()
            await page.wait_for_timeout(5000)

            # Download
            async with page.expect_download(timeout=60000) as download_info:
                await page.get_by_role("button", name="Baixar").first.click()

            download = await download_info.value
            download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(download_path)

            # Processamento final
            new_file_path = rename_downloaded_file_handover(DOWNLOAD_DIR, download_path)
            if new_file_path:
                update_packing_google_sheets_handover(new_file_path)

        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
