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

# ==============================
# Funções de Apoio (Handedover)
# ==============================
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
        print(f"✅ Google Sheets atualizada!")
    except Exception: pass

# ==============================
# Fluxo Principal
# ==============================
async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            # 1. LOGIN
            print("🔐 Fazendo login...")
            await page.goto("https://spx.shopee.com.br/")
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), button:has-text("Entrar")').click()
            await page.wait_for_load_state("networkidle")

            # 2. LIMPEZA DOS BLOQUEADORES (Baseado na sua image_d9bd00)
            print("🧹 Removendo bloqueios (.ssc-dialog-wrapper)...")
            await page.wait_for_timeout(10000) 
            await page.evaluate('''() => {
                const dialogs = document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask, .ant-modal-mask');
                dialogs.forEach(el => el.remove());
                document.body.style.overflow = 'auto';
            }''')
            await page.keyboard.press("Escape")

            # 3. NAVEGAÇÃO E FILTRO
            print("🚚 Indo para Viagens e filtrando Handedover...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(10000)
            
            # Clique via evaluate para bypass total de pop-ups bloqueadores
            await page.get_by_text("Handedover").first.evaluate("element => element.click()")
            
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(12000)

            # 4. CENTRO DE TAREFAS
            print("📂 Acessando Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(10000)
            
            # Localização exata via Breadcrumb identificado na image_d9b1fc
            aba_exportar = page.locator('.ssc-breadcrumb-item:has-text("Exportar tarefa")').or_(page.get_by_text("Export Task"))
            await aba_exportar.first.click(force=True)
            print("✅ Aba selecionada.")

            # 5. DOWNLOAD (Bypass de espera de navegação do Pending)
            print("⬇️ Aguardando processamento...")
            
            download_sucesso = False
            for i in range(1, 11):
                # Conforme image_d9cc09: Coluna 3 é Status, Coluna 5 é Ação
                primeira_linha = page.locator("tr").nth(1)
                status_text = await primeira_linha.locator("td").nth(3).inner_text()
                
                if "Pronto" in status_text:
                    print(f"✨ Status 'Pronto' detectado!")
                    # Localização exata do botão conforme image_e49ac1
                    btn_baixar = primeira_linha.locator('button span:has-text("Baixar"), a:has-text("Baixar")').first
                    
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            # Clique via JavaScript: ignora intercepções de diálogo
                            await btn_baixar.evaluate("element => element.click()")
                        
                        download = await download_info.value
                        path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                        await download.save_as(path)
                        
                        final = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                        if final: update_google_sheets_handover(final)
                        download_sucesso = True
                        break
                    except Exception as e:
                        print(f"⚠️ Erro no download: {e}")
                
                print(f"⏳ Tentativa {i}: Status é '{status_text}'. Atualizando...")
                await page.wait_for_timeout(20000)
                await page.reload()
                await page.wait_for_load_state("domcontentloaded")
                await page.get_by_text(re.compile(r"Exportar tarefa|Export Task", re.IGNORECASE)).first.click(force=True)

            if not download_sucesso: print("❌ O arquivo demorou demais para ficar pronto.")

        except Exception as e:
            print(f"❌ Erro Crítico: {e}")
            await page.screenshot(path="debug_final.png", full_page=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
