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
        print(f"✅ Arquivo Handedover salvo como: {new_file_path}")
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
        print(f"✅ Dados enviados para 'Base Handedover'.")
    except Exception: pass

async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        # headless=True para GitHub Actions
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            # 1. LOGIN (Igual ao Pending)
            print("🔐 Fazendo login...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=40000)

            # 2. LIMPEZA DE POP-UP (Método do Script Pending)
            print("⏳ Removendo bloqueios de tela...")
            await page.wait_for_timeout(10000) 
            await page.evaluate('''() => {
                const overlays = document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask, .ant-modal-mask, .ant-modal-wrap');
                overlays.forEach(el => el.remove());
                document.body.style.overflow = 'auto';
            }''')
            await page.keyboard.press("Escape")

            # 3. FILTRO E EXPORTAÇÃO
            print("🚚 Acessando Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(12000)
            
            print("🔍 Clicando no filtro Handedover...")
            # Usando evaluate para bypass de intercepção de pop-up
            await page.get_by_text("Handedover").first.evaluate("element => element.click()")
            
            await page.wait_for_timeout(5000)
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(12000)

            # 4. CENTRO DE TAREFAS (Lógica idêntica ao Pending)
            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(10000)
            
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
                print("✅ Aba selecionada.")
            except: pass

            # 5. DOWNLOAD (Bypass de espera de navegação do Pending)
            print("⬇️ Aguardando botão 'Baixar' aparecer...")
            try:
                # Espera o botão baixar aparecer (aumentado para 60s conforme seu erro)
                await page.wait_for_selector("text=Baixar", timeout=60000)
                print("✅ Botão 'Baixar' visível.")
            except:
                print("⚠️ Aviso: Botão demorou, tentando clique forçado via JS...")

            async with page.expect_download(timeout=60000) as download_info:
                # O clique via evaluate resolve o erro de "pointer events" interceptados
                await page.locator("text=Baixar").first.evaluate("element => element.click()")

            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)

            final_file = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
            if final_file:
                update_packing_google_sheets_handover(final_file)

            print("\n🎉 PROCESSO CONCLUÍDO COM SUCESSO!")

        except Exception as e:
            print(f"❌ Erro fatal: {e}")
            await page.screenshot(path="debug_final.png", full_page=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
