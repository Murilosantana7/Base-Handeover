import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

# ==============================
# Configuração de Ambiente
# ==============================
DOWNLOAD_DIR = "/tmp"  # Se estiver no Windows, use: os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"✅ Arquivo renomeado para: {new_file_name}")
        return new_file_path
    except Exception as e:
        print(f"❌ Erro ao renomear arquivo: {e}")
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
        print("✅ Dados enviados para o Google Sheets!")
    except Exception as e:
        print(f"❌ Erro no Google Sheets: {e}")

# ==============================
# Fluxo Principal Playwright
# ==============================
async def main():
    async with async_playwright() as p:
        # Lançando navegador com viewport estável
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            accept_downloads=True, 
            viewport={'width': 1366, 'height': 768}
        )
        page = await context.new_page()

        try:
            # 1. LOGIN (Lógica Reforçada)
            print("🔐 Acessando portal SPX...")
            await page.goto("https://spx.shopee.com.br/", wait_until="domcontentloaded", timeout=60000)
            
            print("⏳ Aguardando campos de login...")
            input_user = page.locator('xpath=//*[@placeholder="Ops ID"]')
            await input_user.wait_for(state="visible", timeout=20000)
            
            # Focar e preencher
            await input_user.click()
            await input_user.fill('Ops134294')
            
            input_pass = page.locator('xpath=//*[@placeholder="Senha"]')
            await input_pass.click()
            await input_pass.fill('@Shopee123')
            
            print("🚀 Enviando formulário de login...")
            btn_login = page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button')
            await btn_login.evaluate("el => el.click()")
            
            # Espera estabilizar a rede após login
            await page.wait_for_load_state("networkidle", timeout=45000)

            # 2. TRATAMENTO DE POP-UPS (Baseado no Script Funcional)
            print("⏳ Verificando pop-ups (10s)...")
            await page.wait_for_timeout(10000)
            
            # Tentar fechar com ESC
            await page.keyboard.press("Escape")
            
            # Tentar fechar via seletores comuns
            fechar_seletores = [".ssc-dialog-close-icon-wrapper", ".ant-modal-close", ".ant-modal-close-x"]
            for seletor in fechar_seletores:
                if await page.locator(seletor).count() > 0:
                    await page.locator(seletor).first.evaluate("el => el.click()")
                    print(f"✅ Pop-up fechado via seletor: {seletor}")
                    break

            # 3. NAVEGAÇÃO E FILTRO
            print("🚚 Acessando página de viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(12000)

            print("🔍 Selecionando status 'Handedover'...")
            # Tentativa por texto (mais estável)
            try:
                await page.get_by_text("Handedover").first.evaluate("el => el.click()")
            except:
                xpath_hand = "/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/span[1]"
                await page.locator(f'xpath={xpath_hand}').evaluate("el => el.click()")
            
            await page.wait_for_timeout(8000)

            # 4. EXPORTAÇÃO E DOWNLOAD
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name="Exportar").first.evaluate("el => el.click()")
            await page.wait_for_timeout(10000)

            print("📂 Indo para o Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(12000)

            # Garante que a aba correta está ativa
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
            except: pass

            print("⬇️ Aguardando botão 'Baixar'...")
            await page.wait_for_selector("text=Baixar", timeout=30000)

            async with page.expect_download(timeout=60000) as download_info:
                # Clique via JS para evitar erros de intercepção
                await page.locator("text=Baixar").first.evaluate("el => el.click()")

            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            # Finalização
            final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
            if final_path:
                update_google_sheets_handover(final_path)
                print("\n🎉 PROCESSO CONCLUÍDO COM SUCESSO!")

        except Exception as e:
            print(f"❌ Ocorreu um erro: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
