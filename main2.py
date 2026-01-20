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
DOWNLOAD_DIR = "/tmp"  # Se estiver no Windows e der erro, use: os.path.join(os.getcwd(), "downloads")
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
        # Certifique-se de que o arquivo .json está na mesma pasta do script
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
        # Se for rodar no servidor/GitHub, mude headless para True
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # LOGIN (Usuário do Script 1)
            print("🔐 Fazendo login no SPX (Ops134294)...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=20000)

            # ================== NOVO TRATAMENTO DE POP-UP (DO SCRIPT 2) ==================
            print("⏳ Aguardando renderização do pop-up (10s)...")
            await page.wait_for_timeout(10000) 

            popup_closed = False

            # --- OPÇÃO 1: TECLA ESC (PRIORIDADE) ---
            print("1️⃣ Tentativa 1: Pressionando ESC (Método Rápido)...")
            try:
                # Clica no centro para garantir foco na janela
                viewport = page.viewport_size
                if viewport:
                    await page.mouse.click(viewport['width'] / 2, viewport['height'] / 2)

                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
            except Exception as e:
                print(f"Erro no ESC: {e}")

            await page.wait_for_timeout(1000)

            # --- OPÇÃO 2: BOTÕES (FALLBACK) ---
            print("2️⃣ Tentativa 2: Procurando botões de fechar...")

            # Lista combinada de seletores
            possible_buttons = [
                ".ssc-dialog-header .ssc-dialog-close-icon-wrapper",
                ".ssc-dialog-close-icon-wrapper",
                "svg.ssc-dialog-close",            
                ".ant-modal-close",              
                ".ant-modal-close-x",
                "[aria-label='Close']",
                ".ssc-modal-close"
            ]

            for selector in possible_buttons:
                if await page.locator(selector).count() > 0:
                    print(f"⚠️ Botão encontrado: {selector}")
                    try:
                        # Tenta clique JS primeiro (mais forte)
                        await page.locator(selector).first.evaluate("element => element.click()")
                        print("✅ Clique JS realizado no botão.")
                        popup_closed = True
                        break
                    except:
                        # Se falhar, tenta clique normal forçado
                        try:
                            await page.locator(selector).first.click(force=True)
                            print("✅ Clique forçado realizado.")
                            popup_closed = True
                            break
                        except Exception as e:
                            print(f"Falha ao clicar em {selector}: {e}")

            # --- OPÇÃO 3: MÁSCARA/FUNDO (ÚLTIMO RECURSO) ---
            if not popup_closed:
                print("3️⃣ Tentativa 3: Clicando no fundo escuro...")
                masks = [".ant-modal-mask", ".ssc-dialog-mask", ".ssc-modal-mask"]
                for mask in masks:
                    if await page.locator(mask).count() > 0:
                        try:
                            await page.locator(mask).first.click(position={"x": 10, "y": 10}, force=True)
                            print("✅ Clicado na máscara.")
                            break
                        except:
                            pass

            await page.wait_for_timeout(2000)
            # =======================================================================

            # ================== DOWNLOAD: HANDEDOVER ==================
            print("\n🚚 Indo para a página de viagens: hubLinehaulTrips/trip")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(8000)

            # CLIQUE NO BOTÃO EXATO VIA XPATH (Mantido original do Script 1)
            print("🔍 Clicando no filtro 'Handedover'...")
            handedover_xpath = (
                "/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/"
                "div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/"
                "div[1]/div[1]/div[3]/span[1]"
            )
            # Tenta clicar pelo XPath original, mas adicionei um try/catch simples caso falhe
            try:
                await page.locator(f'xpath={handedover_xpath}').click()
            except:
                print("⚠️ XPath falhou, tentando clicar pelo texto 'Handedover'...")
                await page.get_by_text("Handedover").click()
                
            print("✅ Filtro 'Handedover' acionado.")
            await page.wait_for_timeout(10000)

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
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
