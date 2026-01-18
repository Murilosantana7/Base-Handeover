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
        if os.path.exists(new_file_path): os.remove(new_file_path)
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
        print("✅ Google Sheets atualizado com sucesso!")
    except Exception as e:
        print(f"❌ Erro no Sheets: {e}")

async def main():
    async with async_playwright() as p:
        # headless=True para GitHub Actions
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        # Bloqueio de imagens para performance
        await page.route("**/*.{png,jpg,jpeg,svg,gif}", lambda route: route.abort())

        try:
            # 1. LOGIN (Credencial Handedover)
            print("🔐 Iniciando Login (Ops134294)...")
            await page.goto("https://spx.shopee.com.br/", wait_until="commit", timeout=120000)
            
            # Espera estendida para evitar o erro de timeout da image_8ae583.png
            await page.wait_for_selector('input[placeholder*="Ops ID"]', timeout=60000)
            await page.locator('input[placeholder*="Ops ID"]').fill('Ops134294')
            await page.locator('input[placeholder*="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), button:has-text("Entrar"), .ant-btn-primary').first.click()
            
            print("⏳ Aguardando estabilização pós-login...")
            await page.wait_for_timeout(15000)
            await page.keyboard.press("Escape")

            # 2. NAVEGAÇÃO E FILTRO (Idêntico ao que funcionava)
            print("🚚 Acessando aba de Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip", wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(10000)

            print("🔍 Aplicando filtro Handedover pelo XPath...")
            # XPath vencedor
            user_xpath = "/html/body/div/div/div[2]/div[2]/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div/div/div/div/div[3]/span"
            await page.locator(f"xpath={user_xpath}").evaluate("el => el.click()")
            await page.wait_for_timeout(10000)

            # --- A PARTIR DAQUI O SCRIPT SEGUE A LÓGICA DE EXPORTAÇÃO E DOWNLOAD ---
            print("📤 Clicando em Exportar...")
            await page.get_by_role("button", name="Exportar").first.evaluate("el => el.click()")
            await page.wait_for_timeout(12000)

            print("📂 Navegando para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter", wait_until="domcontentloaded")
            await page.wait_for_timeout(15000)

            try:
                await page.get_by_text(re.compile(r"Exportar tarefa|Export Task", re.IGNORECASE)).first.click(timeout=10000)
            except: pass

            print("⬇️ Aguardando botão 'Baixar'...")
            baixar_btn = page.locator("text=Baixar").first
            await baixar_btn.wait_for(state="visible", timeout=60000)

            async with page.expect_download(timeout=90000) as download_info:
                # Sua técnica de clique JS para evitar travar a navegação
                await baixar_btn.evaluate("el => el.click()")

            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
            if final_path:
                update_google_sheets_handover(final_path)
                print("\n🎉 PROCESSO HANDEDOVER CONCLUÍDO!")

        except Exception as e:
            print(f"❌ Erro crítico: {e}")
            await page.screenshot(path="debug_erro.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
