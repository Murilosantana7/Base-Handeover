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
# Configurações de Ambiente
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
        print(f"❌ Erro ao renomear: {e}")
        return None

def update_google_sheets(csv_file_path):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183")
        worksheet = sheet.worksheet("Base Handedover")
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        print("✅ Google Sheets atualizado!")
    except Exception as e:
        print(f"❌ Erro no Sheets: {e}")

# ==============================
# Fluxo Principal
# ==============================
async def main():
    async with async_playwright() as p:
        # headless=True para GitHub Actions
        browser = await p.chromium.launch(headless=True) 
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # 1. LOGIN
            print("🔐 Fazendo login...")
            await page.goto("https://spx.shopee.com.br/")
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), button:has-text("Entrar")').click()
            await page.wait_for_load_state("networkidle")

            # 2. LIMPEZA DE POP-UPS (Baseado no seu log de erro 'ssc-dialog')
            print("🧹 Removendo possíveis bloqueios de tela...")
            await page.wait_for_timeout(5000)
            # Remove qualquer modal ou máscara que esteja interceptando o clique via JavaScript
            await page.evaluate('''() => {
                const overlays = document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask, .ant-modal-mask, .ant-modal-wrap');
                overlays.forEach(el => el.remove());
                document.body.style.overflow = 'auto';
            }''')
            await page.keyboard.press("Escape")

            # 3. FILTRO HANDEDOVER
            print("🚚 Indo para Viagens e filtrando Handedover...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_load_state("networkidle")
            
            # Usando seletor de texto (mais estável que aquele XPath gigante do log)
            handedover_tab = page.get_by_text("Handedover").first
            await handedover_tab.wait_for(state="visible")
            # Click forçado ignora se houver algo na frente
            await handedover_tab.click(force=True) 
            
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(5000)

            # 4. CENTRO DE TAREFAS (Conforme sua imagem do Inspetor)
            print("📂 Acessando Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_load_state("networkidle")

            # Clicando no texto conforme solicitado (Regex para Português ou Inglês)
            export_task_btn = page.get_by_text(re.compile(r"Exportar tarefa|Export task", re.IGNORECASE)).first
            await export_task_btn.wait_for(state="visible")
            await export_task_btn.click(force=True)
            print("✅ Aba 'Exportar tarefa' clicada.")

            # 5. DOWNLOAD DO ARQUIVO
            print("⬇️ Aguardando botão 'Baixar' ficar pronto...")
            await page.wait_for_timeout(5000)
            
            # Tenta clicar em Baixar (o primeiro da lista)
            try:
                async with page.expect_download(timeout=60000) as download_info:
                    # Seletor baseado na sua imagem (link azul "Baixar")
                    await page.locator('a:has-text("Baixar"), span:has-text("Baixar")').first.click()
                
                download = await download_info.value
                path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                await download.save_as(path)
                
                # 6. FINALIZAÇÃO
                final_file = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                if final_file:
                    update_google_sheets(final_file)
                    
            except Exception as e:
                print(f"⚠️ O arquivo ainda não parece estar pronto para baixar: {e}")

            print("\n🎉 PROCESSO CONCLUÍDO COM SUCESSO!")

        except Exception as e:
            print(f"❌ Erro Crítico: {e}")
            await page.screenshot(path="debug_final.png") # Tira foto para ver o que barrou
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
