import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import re

DOWNLOAD_DIR = "/tmp"

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path): os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"✅ Arquivo salvo: {new_file_name}")
        return new_file_path
    except Exception: return None

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
        print(f"✅ Sheets atualizada!")
    except Exception: pass

async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), button:has-text("Entrar")').click()
            await page.wait_for_load_state("networkidle")

            await page.wait_for_timeout(10000)
            await page.evaluate('''() => {
                const dialogs = document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask, .ant-modal-mask, .ant-modal-wrap');
                dialogs.forEach(el => el.remove());
                document.body.style.overflow = 'auto';
            }''')
            await page.keyboard.press("Escape")

            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(12000)
            
            await page.get_by_text("Handedover").first.evaluate("element => element.click()")
            await page.wait_for_timeout(5000)
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(12000)

            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(10000)
            
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
            except: pass

            print("⬇️ Aguardando processamento...")
            
            download_sucesso = False
            for i in range(1, 15):
                baixar_btn = page.locator('text="Baixar"').first
                
                if await baixar_btn.is_visible():
                    print(f"✨ Botão encontrado na tentativa {i}!")
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            await baixar_btn.evaluate("element => element.click()")
                        
                        download = await download_info.value
                        path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                        await download.save_as(path)
                        
                        final = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                        if final: update_google_sheets_handover(final)
                        download_sucesso = True
                        break
                    except Exception: pass
                
                await page.wait_for_timeout(15000)
                await page.reload()
                await page.wait_for_load_state("domcontentloaded")
                try:
                    await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
                except: pass

            if not download_sucesso: print("❌ Timeout.")

        except Exception as e:
            print(f"❌ Erro: {e}")
            await page.screenshot(path="debug.png", full_page=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
