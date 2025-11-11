import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

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
# Fluxo principal Playwright - Apenas HANDEDOVER com clique no XPath específico
# ==============================
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Mude para True em produção
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # LOGIN
            print("🔐 Fazendo login no SPX...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=20000)

            # Fecha pop-up, se existir
            try:
                await page.locator('.ssc-dialog-close').click(timeout=10000)
            except:
                print("➡️ Nenhum pop-up encontrado. Pressionando Escape...")
                await page.keyboard.press("Escape")

            # ================== DOWNLOAD: HANDEDOVER ==================
            print("\n🚚 Indo para a página de viagens: hubLinehaulTrips/trip")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(8000)  # Espera inicial para carregamento

            # ⬇️ CLIQUE NO BOTÃO EXATO VIA XPATH (como solicitado)
            print("🔍 Clicando no filtro 'Handedover' pelo XPath específico...")
            handedover_xpath = (
                "/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/"
                "div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/"
                "div[1]/div[1]/div[3]/span[1]"
            )
            await page.locator(f'xpath={handedover_xpath}').click()
            print("✅ Filtro 'Handedover' clicado com sucesso.")
            await page.wait_for_timeout(10000)  # Aguarda carregamento dos dados após clique

            # Clica em "Exportar"
            print("📤 Clicando em 'Exportar'...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(12000)

            # Vai para o centro de exportação
            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(15000)

            await page.get_by_text("Exportar tarefa").click()
            await page.wait_for_timeout(8000)

            # Espera o download
            print("⬇️ Aguardando o download do arquivo...")
            async with page.expect_download(timeout=60000) as download_info:
                await page.get_by_role("button", name="Baixar").first.click()

            download = await download_info.value
            download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(download_path)
            print(f"✅ Download concluído: {download_path}")

            # Renomeia e envia para o Google Sheets
            new_file_path = rename_downloaded_file_handover(DOWNLOAD_DIR, download_path)
            if new_file_path:
                update_packing_google_sheets_handover(new_file_path)

            print("\n🎉 PROCESSO CONCLUÍDO: BASE HANDEDOVER ATUALIZADA COM SUCESSO!")

        except Exception as e:
            print(f"❌ Erro crítico: {e}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
