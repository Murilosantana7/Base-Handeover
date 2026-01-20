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
        print(f"✅ Arquivo salvo como: {new_file_path}")
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
        print(f"✅ Google Sheets 'Base Handedover' atualizada!")
    except Exception as e:
        print(f"❌ Erro no Sheets: {e}")

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
            print("🔐 Fazendo login no SPX (Handedover)...")
            await page.goto("https://spx.shopee.com.br/")
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), button:has-text("Entrar")').click()
            await page.wait_for_load_state("networkidle")

            # 2. LIMPEZA DE POP-UP (Método agressivo)
            print("🧹 Removendo bloqueios de tela...")
            await page.wait_for_timeout(8000)
            await page.evaluate('''() => {
                document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask, .ant-modal-mask').forEach(el => el.remove());
                document.body.style.overflow = 'auto';
            }''')
            await page.keyboard.press("Escape")

            # 3. FILTRO HANDEDOVER
            print("🚚 Indo para Viagens e filtrando Handedover...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(10000)
            
            # Clique forçado no filtro
            await page.get_by_text("Handedover").first.click(force=True)
            
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(8000)

            # 4. CENTRO DE TAREFAS
            print("📂 Indo para o Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(8000)
            
            # Seleciona a aba correta
            tab_exportar = page.get_by_text(re.compile(r"Exportar tarefa|Export Task", re.IGNORECASE)).first
            await tab_exportar.click(force=True)

            # 5. DOWNLOAD (Lógica do script Pending)
            print("⬇️ Aguardando botão 'Baixar' aparecer na primeira linha...")
            
            download_concluido = False
            for tentativa in range(1, 11):
                # Mira especificamente no botão 'Baixar' da primeira linha de dados
                # td:nth-child(6) é a coluna de Ação onde fica o botão
                primeiro_baixar = page.locator("tr").nth(1).locator('text="Baixar"')
                
                if await primeiro_baixar.is_visible():
                    print(f"✨ Botão 'Baixar' encontrado na tentativa {tentativa}!")
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            # O "Pulo do Gato": clique via JavaScript (evaluate)
                            await primeiro_baixar.evaluate("element => element.click()")
                        
                        download = await download_info.value
                        path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                        await download.save_as(path)
                        
                        final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                        if final_path: update_google_sheets_handover(final_path)
                        
                        download_concluido = True
                        break
                    except Exception as e:
                        print(f"⚠️ Erro no download: {e}")
                
                print(f"⏳ Tentativa {tentativa}: Aguardando arquivo processar. Refresh em 20s...")
                await page.wait_for_timeout(20000)
                await page.reload()
                await page.wait_for_load_state("domcontentloaded")
                await page.get_by_text(re.compile(r"Exportar tarefa|Export Task", re.IGNORECASE)).first.click(force=True)

            if not download_concluido:
                print("❌ O arquivo não ficou pronto após 10 tentativas.")

            print("\n🎉 PROCESSO CONCLUÍDO!")

        except Exception as e:
            print(f"❌ Erro Crítico: {e}")
            await page.screenshot(path="erro_final.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
