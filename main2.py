import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

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
            # 1. LOGIN RÁPIDO
            print("🔐 Login...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), button:has-text("Entrar")').click()
            
            # 2. LIMPEZA IMEDIATA
            await page.wait_for_timeout(7000) # Reduzido de 10s
            await page.evaluate('''() => {
                document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask, .ant-modal-mask').forEach(el => el.remove());
            }''')
            await page.keyboard.press("Escape")

            # 3. FILTRO HANDEDOVER (Ação Extra Necessária)
            print("🚚 Filtrando Handedover...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(8000) # Sincronizado com o Pending
            
            # Clique via JS para não travar nos pop-ups
            await page.get_by_text("Handedover").first.evaluate("element => element.click()")
            await page.wait_for_timeout(3000)
            
            print("📤 Exportando...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(8000) # Sincronizado com o Pending

            # 4. CENTRO DE TAREFAS (Igual ao Pending)
            print("📂 Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(7000)
            
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=3000)
            except: pass

            # 5. LOOP DE DOWNLOAD OTIMIZADO
            print("⬇️ Buscando botão Baixar...")
            download_concluido = False
            for i in range(1, 15):
                baixar_btn = page.locator('text="Baixar"').first
                
                if await baixar_btn.is_visible():
                    print(f"✨ Pronto! Iniciando download na tentativa {i}...")
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            # MESMA LÓGICA DO PENDING: Clique via evaluate
                            await baixar_btn.evaluate("element => element.click()")
                        
                        download = await download_info.value
                        path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                        await download.save_as(path)
                        
                        final = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                        if final: update_google_sheets_handover(final)
                        download_concluido = True
                        break
                    except Exception: pass
                
                # Se não achou, espera menos tempo para tentar de novo
                print(f"⏳ Tentativa {i}: Ainda processando. Reload em 10s...")
                await page.wait_for_timeout(10000) # Reduzido de 20s/30s
                await page.reload()
                await page.wait_for_load_state("domcontentloaded")
                try:
                    await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=3000)
                except: pass

            if not download_concluido: print("❌ Timeout.")

        except Exception as e:
            print(f"❌ Erro: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
