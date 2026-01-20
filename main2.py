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
# Função de renomear arquivo - HANDEDOVER
# ==============================
def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"✅ Arquivo Handedover salvo como: {new_file_path}")
        return new_file_path
    except Exception as e:
        print(f"❌ Erro ao renomear o arquivo: {e}")
        return None

# ==============================
# Função de atualização Google Sheets - HANDEDOVER
# ==============================
def update_packing_google_sheets_handover(csv_file_path):
    try:
        if not os.path.exists(csv_file_path):
            print(f"Arquivo {csv_file_path} não encontrado.")
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
        print(f"✅ Dados enviados com sucesso para a aba 'Base Handedover'.")
    except Exception as e:
        print(f"❌ Erro no Google Sheets: {e}")

# ==============================
# Fluxo principal Playwright
# ==============================
async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        # headless=True para GitHub Actions
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            # 1. LOGIN
            print("🔐 Fazendo login no SPX (Handedover)...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=40000)

            # 2. TRATAMENTO DE POP-UP (Método do Script Pending)
            print("⏳ Limpando bloqueios de tela...")
            await page.wait_for_timeout(8000) 
            await page.evaluate('''() => {
                const overlays = document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask, .ant-modal-mask, .ant-modal-wrap');
                overlays.forEach(el => el.remove());
                document.body.style.overflow = 'auto';
            }''')
            await page.keyboard.press("Escape")

            # 3. NAVEGAÇÃO E FILTRO HANDEDOVER
            print("\n🚚 Indo para a página de viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(10000)

            print("🔍 Filtrando por 'Handedover'...")
            # Tenta clicar no filtro usando o texto primeiro para estabilidade
            try:
                await page.get_by_text("Handedover").first.click(force=True, timeout=5000)
            except:
                # Fallback para o XPath específico do log anterior
                await page.locator('xpath=/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/span[1]').click(force=True)
            
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(8000)

            # 4. CENTRO DE TAREFAS
            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(8000)
            
            print("👆 Selecionando aba 'Exportar tarefa'...")
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
            except:
                pass

            # 5. DOWNLOAD COM LOOP DE VERIFICAÇÃO (CORRIGIDO)
            print("⬇️ Aguardando o arquivo ficar 'Pronto'...")
            
            download_sucesso = False
            for tentativa in range(1, 11): # Tenta por aprox. 3-4 minutos
                # Seleciona a primeira linha da tabela (índice 1, pois 0 é o cabeçalho)
                primeira_linha = page.locator("tr").nth(1)
                
                # De acordo com image_d9cc09.png: Coluna 3 é o Status
                status_celula = primeira_linha.locator("td").nth(3)
                status_texto = await status_celula.inner_text()
                
                if "Pronto" in status_texto:
                    print(f"✨ Status 'Pronto' detectado na tentativa {tentativa}!")
                    
                    # Coluna 5 é a Ação (onde está o link Baixar)
                    botao_baixar = primeira_linha.locator('a:has-text("Baixar"), span:has-text("Baixar")')
                    
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            # O "Pulo do Gato" do script Pending: clique via JS para bypass de navegação
                            await botao_baixar.evaluate("element => element.click()")
                        
                        download = await download_info.value
                        download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                        await download.save_as(download_path)
                        
                        # Finalização
                        new_file = rename_downloaded_file_handover(DOWNLOAD_DIR, download_path)
                        if new_file:
                            update_packing_google_sheets_handover(new_file)
                        
                        download_sucesso = True
                        break
                    except Exception as e:
                        print(f"⚠️ Erro no clique de download: {e}")
                
                print(f"⏳ Tentativa {tentativa}: Status é '{status_texto}'. Atualizando em 20s...")
                await page.wait_for_timeout(20000)
                await page.reload()
                await page.wait_for_load_state("domcontentloaded")
                # Re-clica na aba após o reload
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True)

            if not download_sucesso:
                print("❌ O arquivo não ficou pronto a tempo.")

            print("\n✅ Processo Base Handedover concluído!")

        except Exception as e:
            print(f"❌ Erro fatal: {e}")
            await page.screenshot(path=os.path.join(DOWNLOAD_DIR, "erro_handedover.png"), full_page=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
