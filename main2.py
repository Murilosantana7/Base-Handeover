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

            # 2. LIMPEZA AGRESSIVA DE POP-UPS (Baseado no seu Log de Erro)
            print("🧹 Removendo bloqueios de tela (ssc-dialog)...")
            await page.wait_for_timeout(5000)
            await page.evaluate('''() => {
                const elements = document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask, .ant-modal-mask, .ant-modal-wrap');
                elements.forEach(el => el.remove());
                document.body.style.overflow = 'auto';
            }''')
            await page.keyboard.press("Escape")

            # 3. NAVEGAÇÃO E FILTRO
            print("🚚 Indo para Viagens e filtrando Handedover...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_load_state("networkidle")
            
            # Clicando no filtro Handedover com força bruta
            await page.get_by_text("Handedover").first.click(force=True)
            
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(3000)

            # 4. CENTRO DE TAREFAS
            print("📂 Acessando Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_load_state("networkidle")

            # Clicando na aba "Exportar tarefa" usando o seletor exato da sua imagem
            tab_exportar = page.locator('span:has-text("Exportar tarefa")').first
            await tab_exportar.click(force=True)
            print("✅ Aba 'Exportar tarefa' selecionada.")

            # 5. LOOP DE DOWNLOAD (AGUARDANDO STATUS "PRONTO")
            print("⬇️ Aguardando processamento da primeira linha...")
            
            download_concluido = False
            for i in range(1, 11): # Tenta 10 vezes (aprox. 5 min)
                # Verifica a primeira linha da tabela
                primeira_linha = page.locator("tr").nth(1) # nth(0) é o cabeçalho
                status_text = await primeira_linha.locator("td").nth(4).inner_text() # Coluna Status
                
                if "Pronto" in status_text:
                    print(f"✨ Status 'Pronto' detectado na tentativa {i}!")
                    
                    # Clica no link "Baixar" da primeira linha
                    baixar_link = primeira_linha.locator('a:has-text("Baixar"), span:has-text("Baixar")')
                    
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            await baixar_link.click(force=True)
                        
                        download = await download_info.value
                        path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                        await download.save_as(path)
                        
                        # Processamento Final
                        arquivo_final = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                        if arquivo_final:
                            update_google_sheets(arquivo_final)
                        
                        download_concluido = True
                        break
                    except Exception as e:
                        print(f"⚠️ Erro ao baixar: {e}")
                
                print(f"⏳ Status atual: '{status_text}'. Aguardando 30s...")
                await page.wait_for_timeout(30000)
                await page.reload()
                await page.wait_for_load_state("networkidle")
                await page.locator('span:has-text("Exportar tarefa")').first.click(force=True)

            if not download_concluido:
                print("❌ O arquivo demorou demais para ficar pronto.")

            print("\n🎉 PROCESSO CONCLUÍDO!")

        except Exception as e:
            print(f"❌ Erro Crítico: {e}")
            await page.screenshot(path="debug_erro.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
