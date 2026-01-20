import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import time

DOWNLOAD_DIR = "/tmp"

# Função auxiliar para logs com horário
def log(mensagem):
    horario = datetime.now().strftime("%H:%M:%S")
    print(f"[{horario}] {mensagem}")

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path): os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        log(f"✅ Arquivo renomeado: {new_file_name}")
        return new_file_path
    except Exception as e:
        log(f"❌ Erro ao renomear: {e}")
        return None

def update_google_sheets_handover(csv_file_path):
    # Alerta de segurança personalizado para colunas sensíveis
    log("⚠️ ALERTA: Este script irá atualizar dados nas colunas A, B, J, N, O, P e Q da aba 'Base Handedover'.")
    
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183")
        worksheet = sheet.worksheet("Base Handedover")
        
        log("📊 Lendo CSV e preparando dados...")
        df = pd.read_csv(csv_file_path).fillna("")
        
        log("🧹 Limpando aba atual...")
        worksheet.clear()
        
        log("📤 Enviando novos dados para o Google Sheets...")
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        log("✅ Google Sheets atualizada com sucesso!")
    except Exception as e:
        log(f"❌ Erro no Sheets: {e}")

async def main():
    start_time = time.time()
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    async with async_playwright() as p:
        log("🚀 Iniciando Navegador...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            # 1. LOGIN
            log("🔐 Acessando página de login...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)
            
            log("⌨️ Preenchendo credenciais...")
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), button:has-text("Entrar")').click()
            
            log("⏳ Aguardando processamento do login...")
            await page.wait_for_load_state("networkidle")

            # 2. LIMPEZA DE POP-UPS
            log("🧹 Iniciando limpeza de pop-ups e modais...")
            await page.wait_for_timeout(7000)
            await page.evaluate('''() => {
                const selectors = ['.ssc-dialog-wrapper', '.ssc-dialog-mask', '.ant-modal-mask', '.ant-modal-wrap'];
                selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
            }''')
            await page.keyboard.press("Escape")
            log("✅ Tela limpa.")

            # 3. FILTRO HANDEDOVER
            log("🚚 Navegando para Viagens (Trips)...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(8000)
            
            log("🔍 Aplicando filtro 'Handedover'...")
            # Uso de evaluate para garantir o clique mesmo com overlays residuais
            await page.get_by_text("Handedover").first.evaluate("element => element.click()")
            await page.wait_for_timeout(3000)
            
            log("📤 Clicando no botão 'Exportar'...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(8000)

            # 4. CENTRO DE TAREFAS
            log("📂 Indo para o Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(7000)
            
            log("👆 Selecionando aba de exportação...")
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
                log("✅ Aba 'Exportar tarefa' focada.")
            except:
                log("⚠️ Aviso: Falha ao focar aba (pode já estar ativa).")

            # 5. LOOP DE DOWNLOAD
            log("⬇️ Verificando disponibilidade do botão 'Baixar'...")
            download_concluido = False
            
            for i in range(1, 15):
                baixar_btn = page.locator('text="Baixar"').first
                
                if await baixar_btn.is_visible():
                    log(f"✨ Botão 'Baixar' detectado na tentativa {i}!")
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            log("🖱️ Executando clique de download (JS Evaluate)...")
                            await baixar_btn.evaluate("element => element.click()")
                        
                        download = await download_info.value
                        path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                        await download.save_as(path)
                        log(f"💾 Download finalizado: {download.suggested_filename}")
                        
                        final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                        if final_path:
                            update_google_sheets_handover(final_path)
                        
                        download_concluido = True
                        break
                    except Exception as e:
                        log(f"⚠️ Falha durante a captura do download: {e}")
                
                log(f"⏳ Tentativa {i}: Arquivo ainda processando. Novo refresh em 10s...")
                await page.wait_for_timeout(10000)
                await page.reload()
                await page.wait_for_load_state("domcontentloaded")
                try:
                    await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=3000)
                except: pass

            if not download_concluido:
                log("❌ ERRO: O arquivo demorou mais de 3 minutos para ficar pronto.")

            total_time = round(time.time() - start_time, 2)
            log(f"🎉 PROCESSO FINALIZADO EM {total_time} SEGUNDOS!")

        except Exception as e:
            log(f"❌ ERRO CRÍTICO: {e}")
            await page.screenshot(path="debug_travamento.png", full_page=True)
            log("📸 Screenshot de erro salvo como 'debug_travamento.png'.")
        finally:
            await browser.close()
            log("🔌 Navegador fechado.")

if __name__ == "__main__":
    asyncio.run(main())
