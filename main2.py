import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

DOWNLOAD_DIR = "/tmp"

# ==============================
# Função de renomear arquivo
# ==============================
def rename_downloaded_file(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv" 
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"Arquivo salvo como: {new_file_path}")
        return new_file_path
    except Exception as e:
        print(f"Erro ao renomear o arquivo: {e}")
        return None

# ==============================
# Função de atualização Google Sheets
# ==============================
def update_handedover_google_sheets(csv_file_path):
    try:
        if not os.path.exists(csv_file_path):
            print(f"Arquivo {csv_file_path} não encontrado.")
            return
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet1 = client.open_by_url(
            "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183"
        )
        worksheet1 = sheet1.worksheet("Base Handedover")
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet1.clear()
        worksheet1.update([df.columns.values.tolist()] + df.values.tolist())
        print(f"Arquivo enviado com sucesso para a aba 'Base Handedover'.")
    except Exception as e:
        print(f"Erro durante o processo no Sheets: {e}")

# ==============================
# Fluxo principal Playwright
# ==============================
async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            # LOGIN (Credenciais novas: Ops134294)
            print("🔐 Fazendo login no SPX (Handedover)...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            
            await page.wait_for_load_state("networkidle", timeout=40000)

            # TRATAMENTO DE POP-UP (Idêntico ao funcional)
            print("⏳ Aguardando renderização do pop-up (10s)...")
            await page.wait_for_timeout(10000) 
            await page.keyboard.press("Escape")
            
            # FILTRO HANDEDOVER
            print("\n🚚 Navegando para Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(12000)

            print("🔍 Selecionando filtro 'Handedover' via XPath...")
            user_xpath = "/html/body/div/div/div[2]/div[2]/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div/div/div/div/div[3]/span"
            await page.locator(f"xpath={user_xpath}").evaluate("el => el.click()")
            await page.wait_for_timeout(8000)

            # EXPORTAR
            print("📤 Clicando em exportar...")
            await page.get_by_role("button", name="Exportar").nth(0).click()
            await page.wait_for_timeout(12000)

            # TASK CENTER E DOWNLOAD (Lógica funcional de .evaluate)
            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(10000)
            
            print("👆 Selecionando aba de exportação...")
            try:
                import re
                await page.get_by_text(re.compile(r"Exportar tarefa|Export Task", re.IGNORECASE)).first.click(force=True, timeout=5000)
            except: pass

            print("⬇️ Aguardando botão 'Baixar'...")
            await page.wait_for_selector("text=Baixar", timeout=30000)

            async with page.expect_download(timeout=60000) as download_info:
                print("🔎 Executando clique via JavaScript (Bypass de espera)...")
                # Sua técnica confirmada para evitar travamentos
                await page.locator("text=Baixar").first.evaluate("element => element.click()")
                print("✅ Comando de clique enviado.")

            download = await download_info.value
            download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(download_path)

            new_file_path = rename_downloaded_file(DOWNLOAD_DIR, download_path)
            if new_file_path:
                update_handedover_google_sheets(new_file_path)

            print("\n✅ Processo Handedover concluído com sucesso.")

        except Exception as e:
            print(f"❌ Erro fatal: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
