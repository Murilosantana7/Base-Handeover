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
# Configuração do diretório de downloads
# ==============================
DOWNLOAD_DIR = "/tmp"  
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==============================
# Função de renomear arquivo HANDEDOVER
# ==============================
def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"Arquivo Handedover salvo como: {new_file_path}")
        return new_file_path
    except Exception as e:
        print(f"Erro ao renomear o arquivo Handedover: {e}")
        return None

# ==============================
# Função de atualização Google Sheets - HANDEDOVER
# ==============================
def update_packing_google_sheets_handover(csv_file_path):
    try:
        if not os.path.exists(csv_file_path):
            print(f"Arquivo Handedover {csv_file_path} não encontrado.")
            return
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(
            "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183"
        )
        worksheet = sheet.worksheet("Base Handedover")
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        print("✅ Arquivo Handedover enviado com sucesso para a aba 'Base Handedover'.")
    except Exception as e:
        print(f"❌ Erro durante o upload Handedover: {e}")

# ==============================
# Fluxo principal Playwright
# ==============================
async def main():
    async with async_playwright() as p:
        # headless=True para rodar no GitHub Actions / Servidor
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # LOGIN
            print("🔐 Fazendo login no SPX (Ops134294)...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=30000)

            # TRATAMENTO DE POP-UP
            print("⏳ Aguardando renderização do pop-up...")
            await page.wait_for_timeout(8000) 
            try:
                viewport = page.viewport_size
                if viewport:
                    await page.mouse.click(viewport['width'] / 2, viewport['height'] / 2)
                await page.keyboard.press("Escape")
            except:
                pass

            # NAVEGAÇÃO: HANDEDOVER
            print("\n🚚 Indo para a página de viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_load_state("networkidle")
            
            print("🔍 Clicando no filtro 'Handedover'...")
            try:
                # Tenta pelo texto direto para ser mais estável que o XPath absoluto
                await page.get_by_text("Handedover").first.click()
            except:
                handedover_xpath = "/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/span[1]"
                await page.locator(f'xpath={handedover_xpath}').click()
                
            print("✅ Filtro 'Handedover' acionado.")
            await page.wait_for_timeout(5000)

            # EXPORTAR
            print("📤 Clicando em 'Exportar'...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(8000)

            # CENTRO DE TAREFAS (CORREÇÃO DO TIMEOUT)
            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_load_state("networkidle")

            # Localizador flexível: Exportar tarefa OU Export task
            selector_exportar = page.get_by_text(re.compile(r"Exportar tarefa|Export task", re.IGNORECASE))

            print("⏳ Aguardando a aba de exportação ficar visível...")
            try:
                # Espera até 45 segundos para o elemento aparecer
                await selector_exportar.wait_for(state="visible", timeout=45000)
                await selector_exportar.click()
                print("✅ Aba selecionada.")
            except Exception as e:
                print(f"⚠️ Erro ao clicar pelo texto, tentando pelo XPath fixo: {e}")
                # Fallback para o XPath que você identificou
                await page.locator('xpath=/html/body/div/div/div[2]/div[1]/div[1]/span/span[1]/span').click()

            await page.wait_for_timeout(5000)

            # DOWNLOAD
            print("⬇️ Iniciando download...")
            try:
                async with page.expect_download(timeout=60000) as download_info:
                    # Clica no primeiro botão "Baixar" da lista
                    await page.get_by_role("button", name="Baixar").first.click()

                download = await download_info.value
                download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                await download.save_as(download_path)
                print(f"✅ Download concluído: {download_path}")

                # PROCESSAMENTO FINAL
                new_file_path = rename_downloaded_file_handover(DOWNLOAD_DIR, download_path)
                if new_file_path:
                    update_packing_google_sheets_handover(new_file_path)
            except Exception as e:
                print(f"❌ Falha no download ou arquivo não ficou pronto a tempo: {e}")

            print("\n🎉 PROCESSO FINALIZADO!")

        except Exception as e:
            print(f"❌ Erro crítico: {e}")
            # Tira print do erro para debug se necessário
            await page.screenshot(path="erro_debug.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
