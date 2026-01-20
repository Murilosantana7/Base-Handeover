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
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            accept_downloads=True, 
            viewport={'width': 1366, 'height': 768}
        )
        page = await context.new_page()

        try:
            # 1. LOGIN
            print("🔐 Acessando portal SPX...")
            await page.goto("https://spx.shopee.com.br/", timeout=60000)
            
            # Preenchimento de Login
            await page.locator('xpath=//*[@placeholder="Ops ID"]').wait_for(state="visible", timeout=20000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            
            print("🚀 Enviando login...")
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=30000)

            # 2. POP-UPS (Tratamento Rápido)
            print("⏳ Verificando pop-ups...")
            await page.wait_for_timeout(3000)
            try:
                await page.keyboard.press("Escape")
                close_btn = page.locator(".ssc-dialog-close-icon-wrapper").first
                if await close_btn.count() > 0:
                    await close_btn.click()
            except: pass

            # 3. NAVEGAÇÃO E FILTRO
            print("🚚 Indo para viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(8000)

            print("🔍 Filtrando Handedover...")
            try:
                # Tenta clicar no filtro
                await page.locator("text=Handedover").first.click(timeout=5000)
            except:
                xpath_hand = "/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/span[1]"
                try: await page.locator(f'xpath={xpath_hand}').click()
                except: pass
            
            await page.wait_for_timeout(3000)

            # 4. EXPORTAÇÃO
            print("📤 Solicitando Exportação...")
            try:
                await page.get_by_role("button", name="Exportar").first.click(timeout=10000)
            except:
                print("⚠️ Botão Exportar não encontrado (talvez página demorou).")

            print("📂 Indo para Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            
            # Aguarda a tabela aparecer para garantir que a página carregou
            try: await page.wait_for_selector("table", timeout=20000)
            except: pass

            # 5. DOWNLOAD (CORRIGIDO AQUI)
            print("⬇️ Procurando o primeiro botão de download disponível...")
            
            # --- MUDANÇA CRÍTICA ---
            # Removemos o .locator("tr").first que prendia o script no cabeçalho.
            # Agora ele busca "Qualquer texto Baixar ou Download na página" e pega o PRIMEIRO (.first)
            btn_baixar = page.locator("text=Baixar").or_(page.locator("text=Download")).first
            
            # Espera até 60s o botão aparecer (caso esteja com status "Processando...")
            await btn_baixar.wait_for(state="visible", timeout=60000)
            
            async with page.expect_download(timeout=60000) as download_info:
                await btn_baixar.click()

            print("✅ Download iniciado!")
            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            # Finalização
            final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
            if final_path:
                update_google_sheets_handover(final_path)
                print("\n🎉 PROCESSO CONCLUÍDO COM SUCESSO!")

        except Exception as e:
            print(f"❌ Erro fatal: {e}")
            try: await page.screenshot(path="erro_fatal.png")
            except: pass
            raise e 
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
